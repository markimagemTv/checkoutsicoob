import sqlite3
import datetime
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, CallbackContext
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
import re
import os

# Conectar ao banco SQLite
conn = sqlite3.connect("producao.db", check_same_thread=False)
c = conn.cursor()

# Tabela de produção
c.execute('''CREATE TABLE IF NOT EXISTS producao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atendente TEXT,
    data TEXT,
    dados TEXT
)''')

# Tabela de atendentes
c.execute('''CREATE TABLE IF NOT EXISTS atendentes (
    user_id INTEGER PRIMARY KEY,
    nome TEXT
)''')
conn.commit()

# Estado temporário para nome de atendente
esperando_nome = {}

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

def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    c.execute("SELECT nome FROM atendentes WHERE user_id = ?", (user_id,))
    resultado = c.fetchone()

    if resultado:
        nome = resultado[0]
        botoes = [
            [InlineKeyboardButton("➕ Adicionar Nova Produção", callback_data="adicionar_producao")],
            [InlineKeyboardButton("📅 Produção Diária", callback_data="resumo_dia")],
            [InlineKeyboardButton("🗓️ Produção Semanal", callback_data="resumo_semana")],
            [InlineKeyboardButton("📆 Produção Mensal", callback_data="resumo_mes")],
            [InlineKeyboardButton("📊 Produção Geral", callback_data="producao_geral")],
            [InlineKeyboardButton("🔍 Buscar por Data/Atendente", callback_data="buscar_data")]
        ]
        update.message.reply_text(f"👋 Olá, {nome}! Escolha uma opção abaixo:",
                                  reply_markup=InlineKeyboardMarkup(botoes))
    else:
        esperando_nome[user_id] = True
        update.message.reply_text("👤 Por favor, envie seu nome para registro:")

def registrar_nome(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if esperando_nome.get(user_id):
        nome = update.message.text.strip()
        c.execute("INSERT INTO atendentes (user_id, nome) VALUES (?, ?)", (user_id, nome))
        conn.commit()
        esperando_nome.pop(user_id)
        update.message.reply_text(f"✅ Nome registrado como {nome}. Use /start para iniciar novamente.")
        return True
    return False

def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data == "adicionar_producao":
        botoes = [[InlineKeyboardButton(text=item, callback_data=f"producao_{item}")] for item in itens_producao]
        query.edit_message_text("📝 Selecione o item de produção:", reply_markup=InlineKeyboardMarkup(botoes))

    elif data.startswith("producao_"):
        item = data.replace("producao_", "")
        query.edit_message_text(f"✍️ Envie o valor para *{item}*", parse_mode='Markdown')
        context.user_data['item_producao'] = item

    elif data.startswith("resumo_"):
        if data == "resumo_dia":
            totalizar(query, context, periodo='dia')
        elif data == "resumo_semana":
            totalizar(query, context, periodo='semana')
        elif data == "resumo_mes":
            totalizar(query, context, periodo='mes')

    elif data == "producao_geral":
        totalizar(query, context, periodo='todos')

    elif data == "buscar_data":
        query.edit_message_text("🔎 Envie a data (AAAA-MM-DD) e o nome do atendente, separados por vírgula.\nExemplo: 2025-07-25, João")
        context.user_data['modo_busca'] = True

def registrar_dados(update, context):
    if registrar_nome(update, context):
        return

    user_id = update.effective_user.id
    c.execute("SELECT nome FROM atendentes WHERE user_id = ?", (user_id,))
    resultado = c.fetchone()
    if not resultado:
        update.message.reply_text("⚠️ Por favor, envie seu nome primeiro usando /start.")
        return

    nome = resultado[0]
    texto = update.message.text

    if context.user_data.get('modo_busca'):
        context.user_data.pop('modo_busca', None)
        try:
            data_str, atendente = [x.strip() for x in texto.split(",")]
            c.execute("SELECT dados FROM producao WHERE data = ? AND atendente = ?", (data_str, atendente))
            registros = c.fetchall()
            if registros:
                resposta = f"📄 Produção de {atendente} em {data_str}:\n" + "\n".join([r[0] for r in registros])
            else:
                resposta = "⚠️ Nenhum dado encontrado."
            update.message.reply_text(resposta)
        except:
            update.message.reply_text("❌ Formato inválido. Use: AAAA-MM-DD, Nome")
        return

    item = context.user_data.get('item_producao')
    if not item:
        update.message.reply_text("⚠️ Use /start para selecionar o item que deseja informar.")
        return

    data = datetime.date.today().isoformat()
    registro = f"{item}: {texto}"

    c.execute("INSERT INTO producao (atendente, data, dados) VALUES (?, ?, ?)",
              (nome, data, registro))
    conn.commit()

    context.user_data.pop('item_producao', None)
    update.message.reply_text("✅ Produção registrada com sucesso! Use /start para enviar mais ou ver relatórios.")

def totalizar(update, context, periodo='dia'):
    hoje = datetime.date.today()
    if periodo == 'semana':
        inicio = hoje - datetime.timedelta(days=hoje.weekday())
    elif periodo == 'mes':
        inicio = hoje.replace(day=1)
    elif periodo == 'todos':
        c.execute("SELECT data, atendente, dados FROM producao ORDER BY data DESC")
        linhas = c.fetchall()
        resposta = "📊 *Produção Geral*\n"
        for data, atendente, dado in linhas:
            resposta += f"\n📅 {data} - 👤 {atendente}: {dado}"
        update.callback_query.edit_message_text(resposta, parse_mode='Markdown')
        return
    else:
        inicio = hoje

    c.execute("SELECT dados FROM producao WHERE data >= ?", (inicio.isoformat(),))
    linhas = c.fetchall()

    resumo = {}
    for linha in linhas:
        for item in itens_producao:
            if item.lower() in linha[0].lower():
                valor = linha[0].split(":")[-1].strip()
                resumo[item] = resumo.get(item, []) + [valor]

    texto = f"📊 *Resumo de Produção ({periodo.title()})*\n"
    for k, v in resumo.items():
        texto += f"\n• {k}: {', '.join(v)}"

    if hasattr(update, 'message'):
        update.message.reply_text(texto, parse_mode='Markdown')
    else:
        update.callback_query.edit_message_text(text=texto, parse_mode='Markdown')

# Token do Bot (substitua pelo seu)
TOKEN = '7215000074:AAHbJH1V0vJsdLzCfeK4dMK-1el5qF-cPTQ'

updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher

# Handlers
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CallbackQueryHandler(callback_handler))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, registrar_dados))

# Iniciar o bot
updater.start_polling()
updater.idle()
