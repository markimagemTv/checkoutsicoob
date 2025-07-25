import sqlite3
import datetime
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram import Update
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

def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    c.execute("SELECT nome FROM atendentes WHERE user_id = ?", (user_id,))
    resultado = c.fetchone()

    if resultado:
        nome = resultado[0]
        update.message.reply_text(f"👋 Olá, {nome}! Envie sua produção no formato solicitado.")
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
        update.message.reply_text(f"✅ Nome registrado como {nome}. Agora envie sua produção no formato solicitado.")
        return True
    return False

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
    data = datetime.date.today().isoformat()

    c.execute("INSERT INTO producao (atendente, data, dados) VALUES (?, ?, ?)",
              (nome, data, texto))
    conn.commit()

    update.message.reply_text("✅ Produção registrada com sucesso!")

def extrair_valor(texto, chave):
    try:
        padrao = rf"{re.escape(chave)}[:\s]*([\d,.]+)"
        match = re.search(padrao, texto, re.IGNORECASE)
        if match:
            return float(match.group(1).replace('.', '').replace(',', '.'))
    except:
        pass
    return 0.0

def extrair_qtd_valor(texto, chave):
    try:
        padrao = rf"{re.escape(chave)}[:\s]*(\d+)[^\d]+([\d,.]+)"
        match = re.search(padrao, texto, re.IGNORECASE)
        if match:
            qtd = int(match.group(1))
            valor = float(match.group(2).replace('.', '').replace(',', '.'))
            return qtd, valor
    except:
        pass
    return 0, 0.0

def totalizar(update, context):
    data = datetime.date.today().isoformat()
    c.execute("SELECT dados FROM producao WHERE data = ?", (data,))
    linhas = c.fetchall()

    totais = {
        'Contas Abertas': 0,
        'Giro Carteira': 0,
        'Capital Integralizado': 0.0,
        'Aplicações': 0.0,
        'Visitas Realizadas': 0,
        'Contratos Cobrança': [0, 0.0],
        'Consignado Liberado': 0.0,
        'Consórcio Contratado': 0.0,
        'SIPAG': [0, 0.0],
        'Previdência': 0.0,
        'Seguro Auto': 0.0,
        'Seguro Vida': 0.0,
        'Seguro Patrimonial': 0.0,
        'Seguro Empresarial': 0.0,
        'Prospecção': 0,
        'Inativos': 0,
        'Limites': 0,
        'Empresas': 0,
        'Indicações': 0
    }

    for linha in linhas:
        texto = linha[0]
        totais['Contas Abertas'] += int(extrair_valor(texto, "Qtd Contas Abertas") or 0)
        totais['Giro Carteira'] += int(extrair_valor(texto, "Qtd Giro Carteira") or 0)
        totais['Capital Integralizado'] += extrair_valor(texto, "Capital Integralizado")
        totais['Aplicações'] += extrair_valor(texto, "Aplicações")
        totais['Visitas Realizadas'] += int(extrair_valor(texto, "Qtd Visitas Realizadas") or 0)
        qtd, val = extrair_qtd_valor(texto, "Qtd e Valor Novos Contratos Cobrança")
        totais['Contratos Cobrança'][0] += qtd
        totais['Contratos Cobrança'][1] += val
        totais['Consignado Liberado'] += extrair_valor(texto, "Consignado Liberado")
        totais['Consórcio Contratado'] += extrair_valor(texto, "Consórcio Contratado")
        qtd, val = extrair_qtd_valor(texto, "Qtd e Valor:  SIPAG: Faturamento")
        totais['SIPAG'][0] += qtd
        totais['SIPAG'][1] += val
        totais['Previdência'] += extrair_valor(texto, "Previdência")
        totais['Seguro Auto'] += extrair_valor(texto, "Seguro Auto")
        totais['Seguro Vida'] += extrair_valor(texto, "Seguro Vida")
        totais['Seguro Patrimonial'] += extrair_valor(texto, "Seguro Patrimonial")
        totais['Seguro Empresarial'] += extrair_valor(texto, "seguro empresarial")
        totais['Prospecção'] += int(extrair_valor(texto, "Contatos de Prospecção") or 0)
        totais['Inativos'] += int(extrair_valor(texto, "Contatos com Inativos") or 0)
        totais['Limites'] += int(extrair_valor(texto, "Contatos Fábrica de Limites") or 0)
        totais['Empresas'] += int(extrair_valor(texto, "Empresas visitadas em Campo") or 0)
        totais['Indicações'] += int(extrair_valor(texto, "Indicações solicitadas") or 0)

    resposta = f"📅 *Resumo de Produção - {data}*\n"
    resposta += f"\n💳 Contas Abertas: {totais['Contas Abertas']}"
    resposta += f"\n🚗 Giro Carteira: {totais['Giro Carteira']}"
    resposta += f"\n🌟 Capital Integralizado: R$ {totais['Capital Integralizado']:.2f}"
    resposta += f"\n💰 Aplicações: R$ {totais['Aplicações']:.2f}"
    resposta += f"\n📍 Visitas Realizadas: {totais['Visitas Realizadas']}"
    resposta += f"\n🔹 Contratos Cobrança: {totais['Contratos Cobrança'][0]} - R$ {totais['Contratos Cobrança'][1]:.2f}"
    resposta += f"\n📈 Consignado Liberado: R$ {totais['Consignado Liberado']:.2f}"
    resposta += f"\n💳 Consórcio Contratado: R$ {totais['Consórcio Contratado']:.2f}"
    resposta += f"\n📊 SIPAG: {totais['SIPAG'][0]} - R$ {totais['SIPAG'][1]:.2f}"
    resposta += f"\n🏦 Previdência: R$ {totais['Previdência']:.2f}"
    resposta += f"\n🚗 Seguro Auto: R$ {totais['Seguro Auto']:.2f}"
    resposta += f"\n👥 Seguro Vida: R$ {totais['Seguro Vida']:.2f}"
    resposta += f"\n🏡 Seguro Patrimonial: R$ {totais['Seguro Patrimonial']:.2f}"
    resposta += f"\n💼 Seguro Empresarial: R$ {totais['Seguro Empresarial']:.2f}"
    resposta += f"\n🔎 Contatos de Prospecção: {totais['Prospecção']}"
    resposta += f"\n❌ Contatos com Inativos: {totais['Inativos']}"
    resposta += f"\n📆 Contatos Fábrica de Limites: {totais['Limites']}"
    resposta += f"\n🏢 Empresas visitadas em Campo: {totais['Empresas']}"
    resposta += f"\n📢 Indicações solicitadas: {totais['Indicações']}"

    update.message.reply_text(resposta, parse_mode='Markdown')

# Token do Bot (substitua pelo seu)
TOKEN = '7215000074:AAHbJH1V0vJsdLzCfeK4dMK-1el5qF-cPTQ'

updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher

# Handlers
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("resumo", totalizar))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, registrar_dados))

# Iniciar o bot
updater.start_polling()
updater.idle()
