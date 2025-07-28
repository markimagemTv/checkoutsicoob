import sqlite3
import datetime
import re
import os
import logging
import base64

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ParseMode, constants
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

# Criar tabelas se não existirem
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
            await query.edit_message_text(f"✍️ Envie o valor para *{item}*", parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await query.edit_message_text("❌ Erro ao decodificar o item de produção.")

    elif data.startswith("excluir_"):
        try:
            registro_id = int(data.replace("excluir_", ""))
            c.execute("DELETE FROM producao WHERE id = ?", (registro_id,))
            conn.commit()
            await query.edit_message_text("🗑️ Produção excluída com sucesso!")
        except Exception:
            await query.edit_message_text("❌ Erro ao excluir a produção.")

def parse_valor(texto):
    # Remove R$, espaços e transforma vírgula em ponto para floats
    texto = texto.upper().replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        valor = float(texto)
        return valor
    except:
        return None

async def mostrar_producoes_para_excluir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("SELECT nome FROM atendentes WHERE user_id = ?", (user_id,))
    resultado = c.fetchone()
    if not resultado:
        await update.message.reply_text("⚠️ Você precisa se registrar usando /start antes.")
        return

    nome = resultado[0]
    c.execute("SELECT id, data, dados FROM producao WHERE atendente = ? ORDER BY data DESC LIMIT 10", (nome,))
    registros = c.fetchall()
    if not registros:
        await update.message.reply_text("⚠️ Você não tem registros de produção para excluir.")
        return

    botoes = [
        [InlineKeyboardButton(f"{r[1]} - {r[2]}", callback_data=f"excluir_{r[0]}")]
        for r in registros
    ]
    await update.message.reply_text("❌ Selecione a produção que deseja excluir:", reply_markup=InlineKeyboardMarkup(botoes))

async def busca_data_atendente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['modo_busca'] = True
    await update.message.reply_text("🔎 Envie a data (DD/MM/AAAA) e o nome do atendente separados por vírgula.\nExemplo: 25/07/2025, João")

async def busca_por_pa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['modo_pa'] = True
    await update.message.reply_text("📍 Envie o nome do PA. Exemplo: PA01 ou PA DIGITAL")

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
                try:
                    valor_str = texto.split(":")[-1].strip()
                    valor_str = valor_str.replace("R$", "").replace(".", "").replace(",", ".")
                    encontrado = re.findall(r"[-+]?\d*\.\d+|\d+", valor_str)
                    if not encontrado:
                        continue
                    valor = float(encontrado[0])
                    resumo[item] = resumo.get(item, 0) + valor
                except:
                    pass

    texto = f"📊 *Resumo de Produção ({periodo.title()})*\n"
    for item, total in resumo.items():
        if "R$" in item:
            texto += f"\n• {item}: R$ {total:,.2f}"
        else:
            texto += f"\n• {item}: {int(total)}"

    await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)

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

    # Modo busca por data e atendente
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

    # Modo busca por PA
    if context.user_data.get('modo_pa'):
        context.user_data.pop('modo_pa', None)
        pa = texto
        c.execute("SELECT nome FROM atendentes WHERE lotacao = ?", (pa,))
        atendentes = c.fetchall()
        if not atendentes:
            await update.message.reply_text(f"⚠️ Nenhum atendente encontrado para {pa}")
            return
        nomes = [a[0] for a in atendentes]
        c.execute(f"SELECT dados, atendente, data FROM producao WHERE atendente IN ({','.join('?'*len(nomes))})", nomes)
        registros = c.fetchall()
        if registros:
            resposta = f"📄 Produção no {pa}:\n"
            for reg in registros:
                resposta += f"{reg[2]} - {reg[1]}:\n{reg[0]}\n\n"
        else:
            resposta = "⚠️ Nenhum dado encontrado."
        await update.message.reply_text(resposta)
        return

    # Registrar dados normais
    if "➕ Adicionar Nova Produção" in texto:
        # Mostrar teclado com opções para escolher item
        botoes = [
            [InlineKeyboardButton(item, callback_data="producao_" + encode_data(item))]
            for item in itens_producao
        ]
        await update.message.reply_text("📝 Escolha o item para registrar:", reply_markup=InlineKeyboardMarkup(botoes))
        return

    # Espera o valor para o item selecionado
    item = context.user_data.get('item_producao')
    if item:
        valor = parse_valor(texto)
        if valor is None:
            await update.message.reply_text("❌ Valor inválido. Envie um valor numérico válido, ex: R$1500, 1500, 1.500,00")
            return
        data_atual = datetime.date.today().isoformat()
        texto_registro = f"{item}: {texto}"
        c.execute("INSERT INTO producao (atendente, data, dados) VALUES (?, ?, ?)", (nome, data_atual, texto_registro))
        conn.commit()
        await update.message.reply_text(f"✅ Produção registrada:\n{texto_registro}", reply_markup=teclado_persistente)
        context.user_data.pop('item_producao')
        return

    # Botões especiais
    if texto == "📅 Produção Diária":
        await totalizar(update, context, 'dia')
        return
    if texto == "🗓️ Produção Semanal":
        await totalizar(update, context, 'semana')
        return
    if texto == "📆 Produção Mensal":
        await totalizar(update, context, 'mes')
        return
    if texto == "📊 Produção Geral":
        await totalizar(update, context, 'todos')
        return
    if texto == "🔍 Buscar por Data/Atendente":
        await busca_data_atendente(update, context)
        return
    if texto == "📍 Buscar por PA":
        await busca_por_pa(update, context)
        return
    if texto == "❌ Excluir Produção":
        await mostrar_producoes_para_excluir(update, context)
        return

    await update.message.reply_text("⚠️ Comando ou entrada não reconhecido. Use /start para reiniciar.")

if __name__ == "__main__":
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("⚠️ Defina a variável de ambiente BOT_TOKEN com seu token do Telegram.")
        exit(1)

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), registrar_dados))
    app.add_handler(CallbackQueryHandler(callback_handler))

    print("🤖 Bot iniciado...")

    # Executa o bot sem asyncio.run() para evitar conflito de event loop
    app.run_polling()
