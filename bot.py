import sqlite3
import datetime
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, CallbackContext
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
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
    nome TEXT,
    cargo TEXT,
    lotacao TEXT
)''')
conn.commit()

# Estado temporário para registro
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

# Teclado persistente
teclado_persistente = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("➕ Adicionar Nova Produção")],
        [KeyboardButton("📅 Produção Diária"), KeyboardButton("🗓️ Produção Semanal")],
        [KeyboardButton("📆 Produção Mensal"), KeyboardButton("📊 Produção Geral")],
        [KeyboardButton("🔍 Buscar por Data/Atendente")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    c.execute("SELECT nome, cargo, lotacao FROM atendentes WHERE user_id = ?", (user_id,))
    resultado = c.fetchone()

    if resultado:
        nome = resultado[0]
        update.message.reply_text(f"👋 Olá, {nome}! Escolha uma opção abaixo:", reply_markup=teclado_persistente)
    else:
        estado_registro[user_id] = 'nome'
        update.message.reply_text("👤 Por favor, envie seu nome para registro:")

def registrar_nome(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    texto = update.message.text.strip()

    if estado_registro.get(user_id) == 'nome':
        context.user_data['nome'] = texto
        estado_registro[user_id] = 'cargo'
        update.message.reply_text("💼 Agora envie seu cargo:")
        return True
    elif estado_registro.get(user_id) == 'cargo':
        context.user_data['cargo'] = texto
        estado_registro[user_id] = 'lotacao'
        botoes = [[KeyboardButton(f"PA{str(i).zfill(2)}")] for i in range(10)] + [[KeyboardButton("PA DIGITAL")]]
        update.message.reply_text("🏢 Escolha sua lotação:", reply_markup=ReplyKeyboardMarkup(botoes, resize_keyboard=True))
        return True
    elif estado_registro.get(user_id) == 'lotacao':
        nome = context.user_data['nome']
        cargo = context.user_data['cargo']
        lotacao = texto
        c.execute("INSERT INTO atendentes (user_id, nome, cargo, lotacao) VALUES (?, ?, ?, ?)", (user_id, nome, cargo, lotacao))
        conn.commit()
        estado_registro.pop(user_id)
        update.message.reply_text(f"✅ Cadastro completo como {nome} - {cargo} ({lotacao}). Use /start novamente.", reply_markup=teclado_persistente)
        return True

    return False

def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data.startswith("producao_"):
        item = data.replace("producao_", "")
        query.edit_message_text(f"✍️ Envie o valor para *{item}*", parse_mode='Markdown')
        context.user_data['item_producao'] = item

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
            data_obj = datetime.datetime.strptime(data_str, "%d/%m/%Y").date()
            data_iso = data_obj.isoformat()
            c.execute("SELECT dados FROM producao WHERE data = ? AND atendente = ?", (data_iso, atendente))
            registros = c.fetchall()
            if registros:
               resposta = f"📄 Produção de {atendente} em {data_str}:\n" + "\n".join([r[0] for r in registros])
         else:
                resposta = "⚠️ Nenhum dado encontrado."
            update.message.reply_text(resposta)
        except:
            update.message.reply_text("❌ Formato inválido. Use: DD/MM/AAAA, Nome")
        return

    comandos = {
        "➕ Adicionar Nova Produção": lambda: enviar_botoes_producao(update),
        "📅 Produção Diária": lambda: totalizar(update, context, periodo='dia'),
        "🗓️ Produção Semanal": lambda: totalizar(update, context, periodo='semana'),
        "📆 Produção Mensal": lambda: totalizar(update, context, periodo='mes'),
        "📊 Produção Geral": lambda: totalizar(update, context, periodo='todos'),
        "🔍 Buscar por Data/Atendente": lambda: busca_data_atendente(update, context)
    }
    if texto in comandos:
        comandos[texto]()
        return

    item = context.user_data.get('item_producao')
    if not item:
        update.message.reply_text("⚠️ Use o botão 'Adicionar Nova Produção' para selecionar o item.")
        return

    data = datetime.date.today().isoformat()
    registro = f"{item}: {texto}"
    c.execute("INSERT INTO producao (atendente, data, dados) VALUES (?, ?, ?)", (nome, data, registro))
    conn.commit()

    context.user_data.pop('item_producao', None)
    update.message.reply_text("✅ Produção registrada com sucesso!", reply_markup=teclado_persistente)

def enviar_botoes_producao(update):
    botoes = [[InlineKeyboardButton(text=item, callback_data=f"producao_{item}")] for item in itens_producao]
    update.message.reply_text("📝 Selecione o item de produção:", reply_markup=InlineKeyboardMarkup(botoes))

def busca_data_atendente(update, context):
    context.user_data['modo_busca'] = True
    update.message.reply_text("🔎 Envie a data (DD/MM/AAAA) e o nome do atendente separados por vírgula.\nExemplo: 25/07/2025, João")

def totalizar(update, context, periodo='dia'):
    hoje = datetime.date.today()
    if periodo == 'semana':
        inicio = hoje - datetime.timedelta(days=hoje.weekday())
        c.execute("SELECT dados FROM producao WHERE data >= ?", (inicio.isoformat(),))
        linhas = c.fetchall()
    elif periodo == 'mes':
        inicio = hoje.replace(day=1)
        c.execute("SELECT dados FROM producao WHERE data >= ?", (inicio.isoformat(),))
        linhas = c.fetchall()
    elif periodo == 'todos':
        c.execute("SELECT dados FROM producao")
        linhas = c.fetchall()
    else:
        inicio = hoje
        c.execute("SELECT dados FROM producao WHERE data >= ?", (inicio.isoformat(),))
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

    update.message.reply_text(texto, parse_mode='Markdown')

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
