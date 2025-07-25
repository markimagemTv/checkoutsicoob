import sqlite3
import datetime
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, CallbackContext
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup

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

# Teclado persistente sempre visível
teclado_persistente = [
    ["➕ Adicionar Nova Produção", "📅 Produção Diária"],
    ["🗓️ Produção Semanal", "📆 Produção Mensal"],
    ["📊 Produção Geral", "🔍 Buscar por Data/Atendente"]
]
reply_markup_persistente = ReplyKeyboardMarkup(teclado_persistente, resize_keyboard=True)

def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    c.execute("SELECT nome FROM atendentes WHERE user_id = ?", (user_id,))
    resultado = c.fetchone()

    if resultado:
        nome = resultado[0]
        update.message.reply_text(
            f"👋 Olá, {nome}! Escolha uma opção abaixo:",
            reply_markup=reply_markup_persistente
        )
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
        update.message.reply_text(
            f"✅ Nome registrado como {nome}. Use /start para iniciar novamente.",
            reply_markup=reply_markup_persistente
        )
        return True
    return False

def mensagem_texto(update: Update, context: CallbackContext):
    texto = update.message.text

    # Se estiver esperando nome, registra
    if registrar_nome(update, context):
        return

    # Busca o atendente no banco
    user_id = update.effective_user.id
    c.execute("SELECT nome FROM atendentes WHERE user_id = ?", (user_id,))
    resultado = c.fetchone()
    if not resultado:
        update.message.reply_text("⚠️ Por favor, envie seu nome primeiro usando /start.")
        return

    nome = resultado[0]

    if texto == "➕ Adicionar Nova Produção":
        botoes = [[InlineKeyboardButton(text=item, callback_data=f"producao_{item}")] for item in itens_producao]
        update.message.reply_text("📝 Selecione o item de produção:", reply_markup=InlineKeyboardMarkup(botoes))

    elif texto == "📅 Produção Diária":
        totalizar(update, context, periodo='dia')

    elif texto == "🗓️ Produção Semanal":
        totalizar(update, context, periodo='semana')

    elif texto == "📆 Produção Mensal":
        totalizar(update, context, periodo='mes')

    elif texto == "📊 Produção Geral":
        totalizar(update, context, periodo='todos')

    elif texto == "🔍 Buscar por Data/Atendente":
        update.message.reply_text(
            "🔎 Envie a data (AAAA-MM-DD) e o nome do atendente, separados por vírgula.\nExemplo: 2025-07-25, João",
            reply_markup=reply_markup_persistente
        )
        context.user_data['modo_busca'] = True

    else:
        # Se estiver em modo busca, processa a consulta
        if context.user_data.get('modo_busca'):
            context.user_data.pop('modo_busca', None)
            try:
                data_str, atendente_busca = [x.strip() for x in texto.split(",")]
                c.execute("SELECT dados FROM producao WHERE data = ? AND atendente = ?", (data_str, atendente_busca))
                registros = c.fetchall()
                if registros:
                    resposta = f"📄 Produção de {atendente_busca} em {data_str}:\n" + "\n".join([r[0] for r in registros])
                else:
                    resposta = "⚠️ Nenhum dado encontrado."
                update.message.reply_text(resposta, reply_markup=reply_markup_persistente)
            except:
                update.message.reply_text("❌ Formato inválido. Use: AAAA-MM-DD, Nome", reply_markup=reply_markup_persistente)
            return

        # Caso contrário, tenta registrar a produção
        item = context.user_data.get('item_producao')
        if not item:
            update.message.reply_text("⚠️ Use o botão ➕ Adicionar Nova Produção para começar.", reply_markup=reply_markup_persistente)
            return

        data = datetime.date.today().isoformat()
        registro = f"{item}: {texto}"

        c.execute("INSERT INTO producao (atendente, data, dados) VALUES (?, ?, ?)",
                  (nome, data, registro))
        conn.commit()

        context.user_data.pop('item_producao', None)
        update.message.reply_text("✅ Produção registrada com sucesso!", reply_markup=reply_markup_persistente)

def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data.startswith("producao_"):
        item = data.replace("producao_", "")
        query.edit_message_text(f"✍️ Envie o valor para *{item}*", parse_mode='Markdown')
        context.user_data['item_producao'] = item

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
        for data_, atendente_, dado in linhas:
            resposta += f"\n📅 {data_} - 👤 {atendente_}: {dado}"
        update.message.reply_text(resposta, parse_mode='Markdown', reply_markup=reply_markup_persistente)
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

    update.message.reply_text(texto, parse_mode='Markdown', reply_markup=reply_markup_persistente)

# Token do Bot (substitua pelo seu)
TOKEN = '7215000074:AAHbJH1V0vJsdLzCfeK4dMK-1el5qF-cPTQ'

updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher

# Handlers
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CallbackQueryHandler(callback_handler))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, mensagem_texto))

# Iniciar o bot
updater.start_polling()
updater.idle()
