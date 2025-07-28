import sqlite3
import datetime
import re
import os
import logging
import base64

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, constants
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes
)

# Logging para debug
logging.basicConfig(level=logging.INFO)

# Conectar ao banco SQLite
conn = sqlite3.connect("producao.db", check_same_thread=False)
c = conn.cursor()

# Criar tabelas
c.execute('''CREATE TABLE IF NOT EXISTS producao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atendente TEXT,
    data TEXT,
    dados TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS atendentes (
    user_id INTEGER PRIMARY KEY,
    nome TEXT,
    cargo TEXT,
    lotacao TEXT
)''')
conn.commit()

estado_registro = {}

itens_producao = [
    "R$ Operações de Crédito",
    "Qtd Contas Abertas",
    "Qtd Giro Carteira",
    "R$ Capital Integralizado",
    "R$ Aplicações",
    "Qtd Visitas Realizadas",
    "Qtd e Valor Novos Contratos Cobrança",
    "R$ Consignado Liberado",
    "R$ Consórcio Contratado",
    "Qtd e Valor:  SIPAG: Faturamento",
    "R$ Previdência",
    "R$ Seguro Auto",
    "R$ Seguro Vida",
    "R$ Seguro Patrimonial",
    "R$ seguro empresarial",
    "Cooperados Visitados no dia",
    "Contatos de Prospecção",
    "Contatos com Inativos",
    "Contatos Fábrica de Limites",
    "Empresas visitadas em Campo",
    "Indicações solicitadas"
]

teclado_persistente = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("➕ Adicionar Nova Produção")],
        [KeyboardButton("📅 Produção Diária"), KeyboardButton("🗓️ Produção Semanal")],
        [KeyboardButton("📆 Produção Mensal"), KeyboardButton("📊 Produção Geral")],
        [KeyboardButton("🔍 Buscar por Data/Atendente"), KeyboardButton("📍 Buscar por PA")],
        [KeyboardButton("❌ Excluir Produção")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

def encode_data(texto):
    return base64.urlsafe_b64encode(texto.encode()).decode()

def decode_data(encoded):
    return base64.urlsafe_b64decode(encoded.encode()).decode()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("SELECT nome, cargo, lotacao FROM atendentes WHERE user_id = ?", (user_id,))
    resultado = c.fetchone()

    if resultado:
        nome = resultado[0]
        await update.message.reply_text(f"👋 Olá, {nome}! Escolha uma opção abaixo:", reply_markup=teclado_persistente)
    else:
        estado_registro[user_id] = 'nome'
        await update.message.reply_text("👤 Por favor, envie seu nome para registro:")

async def registrar_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto = update.message.text.strip()

    if estado_registro.get(user_id) == 'nome':
        context.user_data['nome'] = texto
        estado_registro[user_id] = 'cargo'
        await update.message.reply_text("💼 Agora envie seu cargo:")
        return True
    elif estado_registro.get(user_id) == 'cargo':
        context.user_data['cargo'] = texto
        estado_registro[user_id] = 'lotacao'
        botoes = [[KeyboardButton(f"PA{str(i).zfill(2)}")] for i in range(10)] + [[KeyboardButton("PA DIGITAL")]]
        await update.message.reply_text("🏢 Escolha sua lotação:", reply_markup=ReplyKeyboardMarkup(botoes, resize_keyboard=True))
        return True
    elif estado_registro.get(user_id) == 'lotacao':
        nome = context.user_data['nome']
        cargo = context.user_data['cargo']
        lotacao = texto
        c.execute("INSERT INTO atendentes (user_id, nome, cargo, lotacao) VALUES (?, ?, ?, ?)", (user_id, nome, cargo, lotacao))
        conn.commit()
        estado_registro.pop(user_id)
        await update.message.reply_text(f"✅ Cadastro completo como {nome} - {cargo} ({lotacao}). Use /start novamente.", reply_markup=teclado_persistente)
        return True
    return False

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("producao_"):
        try:
            item_codificado = data.replace("producao_", "")
            item = decode_data(item_codificado)
            context.user_data['item_producao'] = item
            await query.edit_message_text(f"✍️ Envie o valor para *{item}*", parse_mode=constants.ParseMode.MARKDOWN)
        except Exception as e:
            await query.edit_message_text("❌ Erro ao decodificar o item de produção.")
    elif data.startswith("excluir_"):
        try:
            id_excluir = int(data.replace("excluir_", ""))
            c.execute("DELETE FROM producao WHERE id = ?", (id_excluir,))
            conn.commit()
            await query.edit_message_text(f"✅ Produção ID {id_excluir} excluída com sucesso!", reply_markup=teclado_persistente)
        except Exception as e:
            await query.edit_message_text("❌ Erro ao excluir a produção.")

async def enviar_botoes_producao(update: Update):
    botoes = [
        [InlineKeyboardButton(text=item, callback_data=f"producao_{encode_data(item)}")]
        for item in itens_producao
    ]
    await update.message.reply_text("📝 Selecione o item de produção:", reply_markup=InlineKeyboardMarkup(botoes))

async def busca_data_atendente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['modo_busca'] = True
    await update.message.reply_text("🔎 Envie a data (DD/MM/AAAA) e o nome do atendente separados por vírgula.\nExemplo: 25/07/2025, João")

async def busca_por_pa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['modo_pa'] = True
    await update.message.reply_text("📍 Envie o nome do PA. Exemplo: PA01 ou PA DIGITAL")

async def mostrar_producoes_para_excluir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("SELECT nome FROM atendentes WHERE user_id = ?", (user_id,))
    resultado = c.fetchone()
    if not resultado:
        await update.message.reply_text("⚠️ Você precisa estar cadastrado para usar essa função. Use /start para se cadastrar.")
        return
    nome = resultado[0]

    c.execute("SELECT id, data, dados FROM producao WHERE atendente = ? ORDER BY data DESC LIMIT 10", (nome,))
    registros = c.fetchall()

    if not registros:
        await update.message.reply_text("⚠️ Você não tem produções registradas para excluir.")
        return

    botoes = [
        [InlineKeyboardButton(f"ID {reg[0]} | {reg[1]} | {reg[2][:30]}...", callback_data=f"excluir_{reg[0]}")]
        for reg in registros
    ]
    await update.message.reply_text("❌ Selecione a produção que deseja excluir:", reply_markup=InlineKeyboardMarkup(botoes))

def parse_valor(texto):
    """
    Tenta interpretar o valor enviado pelo usuário como número,
    podendo conter R$ e formatos com vírgula ou ponto.
    """
    texto = texto.upper().replace("R$", "").strip()
    texto = texto.replace(".", "").replace(",", ".")  # Ajusta para ponto decimal
    encontrado = re.findall(r"[-+]?\d*\.\d+|\d+", texto)
    if not encontrado:
        return None
    try:
        valor = float(encontrado[0])
        return valor
    except:
        return None

async def totalizar(update: Update, context: ContextTypes.DEFAULT_TYPE, periodo='dia'):
    hoje = datetime.date.today()
    if periodo == 'semana':
        inicio = hoje - datetime.timedelta(days=hoje.weekday())
    elif periodo == 'mes':
        inicio = hoje.replace(day=1)
    elif periodo == 'todos':
        inicio = None
    else:
        inicio = hoje

    if inicio:
        c.execute("SELECT dados FROM producao WHERE data >= ?", (inicio.isoformat(),))
    else:
        c.execute("SELECT dados FROM producao")
    linhas = c.fetchall()

    resumo = {}
    for linha in linhas:
        texto = linha[0]
        for item in itens_producao:
            if item.lower() in texto.lower():
                valor = parse_valor(texto.split(":")[-1].strip())
                if valor is not None:
                    resumo[item] = resumo.get(item, 0) + valor

    texto = f"📊 *Resumo de Produção ({periodo.title()})*\n"
    for item, total in resumo.items():
        if "R$" in item:
            texto += f"\n• {item}: R$ {total:,.2f}"
        else:
            texto += f"\n• {item}: {int(total)}"

    await update.message.reply_text(texto, parse_mode=constants.ParseMode.MARKDOWN)

async def registrar_dados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await registrar_nome(update, context):
        return

    user_id = update.effective_user.id
    c.execute("SELECT nome FROM atendentes WHERE user_id = ?", (user_id,))
    resultado = c.fetchone()
    if not resultado:
        await update.message.reply_text("⚠️ Por favor, envie seu nome primeiro usando /start.")
        return

    nome = resultado[0]
    texto = update.message.text.strip()

    # Modos especiais
    if context.user_data.get('modo_busca'):
        context.user_data.pop('modo_busca', None)
        try:
            data_str, atendente = [x.strip() for x in texto.split(",")]
            data_obj = datetime.datetime.strptime(data_str, "%d/%m/%Y").date()
            data_iso = data_obj.isoformat()
            c.execute("SELECT dados FROM producao WHERE data = ? AND atendente = ?", (data_iso, atendente))
            registros = c.fetchall()
            if registros:
                resposta = f"📄 Produção de {atendente} em {data_str}:\n" + "\n".join([r[0] for r in registros])
            else:
                resposta = "⚠️ Nenhum dado encontrado."
            await update.message.reply_text(resposta)
        except:
            await update.message.reply_text("❌ Formato inválido. Use: DD/MM/AAAA, Nome")
        return

    if context.user_data.get('modo_pa'):
        context.user_data.pop('modo_pa', None)
        pa = texto.upper()
        c.execute("SELECT nome FROM atendentes WHERE lotacao = ?", (pa,))
        nomes = [r[0] for r in c.fetchall()]
        if not nomes:
            await update.message.reply_text("⚠️ Nenhum atendente encontrado com esse PA.")
            return

        resposta = f"📍 *Produções por Atendentes do {pa}*\n"
        for nome_pa in nomes:
            c.execute("SELECT dados FROM producao WHERE atendente = ?", (nome_pa,))
            registros = c.fetchall()
            if registros:
                soma_itens = {}
                for r in registros:
                    for item in itens_producao:
                        if item.lower() in r[0].lower():
                            valor = parse_valor(r[0].split(":")[-1].strip())
                            if valor is not None:
                                soma_itens[item] = soma_itens.get(item, 0) + valor
                if soma_itens:
                    resposta += f"\n👤 *{nome_pa}*:\n"
                    for item, total in soma_itens.items():
                        if "R$" in item:
                            resposta += f"  • {item}: R$ {total:,.2f}\n"
                        else:
                            resposta += f"  • {item}: {int(total)}\n"
        await update.message.reply_text(resposta, parse_mode=constants.ParseMode.MARKDOWN)
        return

    comandos = {
        "➕ Adicionar Nova Produção": enviar_botoes_producao,
        "📅 Produção Diária": lambda u, c: totalizar(u, c, periodo='dia'),
        "🗓️ Produção Semanal": lambda u, c: totalizar(u, c, periodo='semana'),
        "📆 Produção Mensal": lambda u, c: totalizar(u, c, periodo='mes'),
        "📊 Produção Geral": lambda u, c: totalizar(u, c, periodo='todos'),
        "🔍 Buscar por Data/Atendente": busca_data_atendente,
        "📍 Buscar por PA": busca_por_pa,
        "❌ Excluir Produção": mostrar_producoes_para_excluir
    }

    if texto in comandos:
        await comandos[texto](update, context)
        return

    item = context.user_data.get('item_producao')
    if not item:
        await update.message.reply_text("⚠️ Use o botão '➕ Adicionar Nova Produção' para selecionar o item.")
        return

    valor = parse_valor(texto)
    if valor is None:
        await update.message.reply_text("❌ Valor inválido. Envie um número válido, ex: 1500, 1.500,00 ou R$ 1500,00")
        return

    data_hoje = datetime.date.today().isoformat()
    dados = f"{item}: {valor}" if "R$" in item else f"{item}: {int(valor)}"
    c.execute("INSERT INTO producao (atendente, data, dados) VALUES (?, ?, ?)", (nome, data_hoje, dados))
    conn.commit()
    context.user_data.pop('item_producao')
    await update.message.reply_text(f"✅ Produção registrada:\n{dados}", reply_markup=teclado_persistente)

async def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("⚠️ Defina a variável de ambiente BOT_TOKEN com seu token do Telegram.")
        return

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), registrar_dados))

    print("🤖 Bot iniciado...")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
