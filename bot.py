import sqlite3
import datetime
import re
import os
import logging
import base64

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes
)
from telegram.constants import ParseMode

# Logging para debug
logging.basicConfig(level=logging.INFO)

# Conectar ao banco SQLite
conn = sqlite3.connect("producao.db", check_same_thread=False)
c = conn.cursor()

# Tabelas
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
        [KeyboardButton("➕ Adicionar Nova Produção"), KeyboardButton("❌ Excluir Produção")],
        [KeyboardButton("📅 Produção Diária"), KeyboardButton("🗓️ Produção Semanal")],
        [KeyboardButton("📆 Produção Mensal"), KeyboardButton("📊 Produção Geral")],
        [KeyboardButton("🔍 Buscar por Data/Atendente"), KeyboardButton("📍 Buscar por PA")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

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
        botoes = [
            [KeyboardButton(f"PA{str(i).zfill(2)}") for i in range(5)],
            [KeyboardButton(f"PA{str(i).zfill(2)}") for i in range(5, 10)],
            [KeyboardButton("PA DIGITAL")]
        ]
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

def encode_data(texto):
    return base64.urlsafe_b64encode(texto.encode()).decode()

def decode_data(encoded):
    return base64.urlsafe_b64decode(encoded.encode()).decode()

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
            await query.edit_message_text("✅ Produção excluída com sucesso.")
        except Exception:
            await query.edit_message_text("❌ Erro ao excluir a produção.")

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
    texto_lower = texto.lower()

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
        pa = texto
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
                            try:
                                valor_str = r[0].split(":")[-1].strip()
                                valor_str = valor_str.replace("R$", "").replace(".", "").replace(",", ".")
                                encontrado = re.findall(r"[-+]?\d*\.\d+|\d+", valor_str)
                                if not encontrado:
                                    continue
                                valor = float(encontrado[0])
                                soma_itens[item] = soma_itens.get(item, 0) + valor
                            except:
                                pass
                if soma_itens:
                    resposta += f"\n👤 *{nome_pa}*:\n"
                    for item, total in soma_itens.items():
                        if "R$" in item:
                            resposta += f"• {item}: R$ {total:,.2f}\n"
                        else:
                            resposta += f"• {item}: {int(total)}\n"

        await update.message.reply_text(resposta, parse_mode=ParseMode.MARKDOWN)
        return

    comandos = {
        "➕ adicionar nova produção": lambda: enviar_botoes_producao(update),
        "❌ excluir produção": lambda: listar_producoes_para_excluir(update, context),
        "📅 produção diária": lambda: totalizar(update, context, periodo='dia'),
        "🗓️ produção semanal": lambda: totalizar(update, context, periodo='semana'),
        "📆 produção mensal": lambda: totalizar(update, context, periodo='mes'),
        "📊 produção geral": lambda: totalizar(update, context, periodo='todos'),
        "🔍 buscar por data/atendente": lambda: ativar_busca_data_atendente(update, context),
        "📍 buscar por pa": lambda: ativar_busca_por_pa(update, context)
    }

    if texto_lower in comandos:
        await comandos[texto_lower]()
        return

    # Caso seja um valor para registrar produção
    item = context.user_data.get('item_producao')
    if item:
        try:
            valor = float(texto.replace(",", "."))
        except ValueError:
            await update.message.reply_text("❌ Valor inválido, envie um número.")
            return

        hoje = datetime.date.today().isoformat()
        dados_registro = f"{item}: {valor}"
        c.execute("INSERT INTO producao (atendente, data, dados) VALUES (?, ?, ?)", (nome, hoje, dados_registro))
        conn.commit()
        context.user_data.pop('item_producao')
        await update.message.reply_text(f"✅ Registrado: {dados_registro}", reply_markup=teclado_persistente)
    else:
        await update.message.reply_text("❌ Comando não reconhecido. Use o menu abaixo:", reply_markup=teclado_persistente)

async def enviar_botoes_producao(update: Update):
    botoes = []
    for item in itens_producao:
        codigo = encode_data(item)
        botoes.append([InlineKeyboardButton(text=item, callback_data=f"producao_{codigo}")])
    await update.message.reply_text(
        "Escolha um item para registrar:",
        reply_markup=InlineKeyboardMarkup(botoes)
    )

async def listar_producoes_para_excluir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("SELECT nome FROM atendentes WHERE user_id = ?", (user_id,))
    resultado = c.fetchone()
    if not resultado:
        await update.message.reply_text("⚠️ Você precisa se cadastrar primeiro com /start.")
        return

    nome = resultado[0]
    hoje = datetime.date.today().isoformat()
    c.execute("SELECT id, dados FROM producao WHERE atendente = ? AND data = ?", (nome, hoje))
    registros = c.fetchall()

    if not registros:
        await update.message.reply_text("ℹ️ Nenhuma produção encontrada para hoje.")
        return

    botoes = []
    for registro_id, dados in registros:
        botoes.append([
            InlineKeyboardButton(
                text=f"❌ Excluir: {dados[:30]}...",
                callback_data=f"excluir_{registro_id}"
            )
        ])

    await update.message.reply_text(
        "🗑️ Selecione a produção que deseja excluir:",
        reply_markup=InlineKeyboardMarkup(botoes)
    )

async def totalizar(update: Update, context: ContextTypes.DEFAULT_TYPE, periodo='dia'):
    user_id = update.effective_user.id
    c.execute("SELECT nome FROM atendentes WHERE user_id = ?", (user_id,))
    resultado = c.fetchone()
    if not resultado:
        await update.message.reply_text("⚠️ Você precisa se cadastrar primeiro com /start.")
        return
    nome = resultado[0]

    hoje = datetime.date.today()
    if periodo == 'dia':
        data_inicio = hoje
    elif periodo == 'semana':
        data_inicio = hoje - datetime.timedelta(days=hoje.weekday())
    elif periodo == 'mes':
        data_inicio = hoje.replace(day=1)
    else:
        data_inicio = None

    if data_inicio:
        c.execute("SELECT dados FROM producao WHERE atendente = ? AND data >= ?", (nome, data_inicio.isoformat()))
    else:
        c.execute("SELECT dados FROM producao WHERE atendente = ?", (nome,))
    registros = c.fetchall()
    if not registros:
        await update.message.reply_text("ℹ️ Nenhuma produção registrada para o período.")
        return

    soma_itens = {}
    for r in registros:
        texto = r[0].lower()
        for item in itens_producao:
            if item.lower() in texto:
                try:
                    # Extrair número da string
                    valor_str = r[0].split(":")[-1].strip()
                    valor_str = valor_str.replace("R$", "").replace(".", "").replace(",", ".")
                    encontrado = re.findall(r"[-+]?\d*\.\d+|\d+", valor_str)
                    if not encontrado:
                        continue
                    valor = float(encontrado[0])
                    soma_itens[item] = soma_itens.get(item, 0) + valor
                except:
                    continue

    resposta = f"📊 Produção {periodo} para {nome}:\n"
    for item, total in soma_itens.items():
        if "R$" in item:
            resposta += f"• {item}: R$ {total:,.2f}\n"
        else:
            resposta += f"• {item}: {int(total)}\n"

    await update.message.reply_text(resposta, parse_mode=ParseMode.MARKDOWN)

async def ativar_busca_data_atendente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['modo_busca'] = True
    await update.message.reply_text("📅 Envie a data e o atendente no formato: DD/MM/AAAA, Nome")

async def ativar_busca_por_pa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['modo_pa'] = True
    await update.message.reply_text("📍 Envie o PA para buscar as produções:")

def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), registrar_dados))

    application.run_polling()

if __name__ == '__main__':
    main()
