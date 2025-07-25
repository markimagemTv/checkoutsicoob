import psycopg2
import datetime
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import re
import os

# Conectar ao banco PostgreSQL (Railway)
DATABASE_URL = os.environ.get("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL, sslmode='require')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS producao (
    id SERIAL PRIMARY KEY,
    atendente TEXT,
    data DATE,
    dados TEXT
)''')
conn.commit()

def start(update, context):
    update.message.reply_text("👋 Olá! Envie sua produção no formato solicitado.")

def registrar_dados(update, context):
    nome = update.message.from_user.first_name
    texto = update.message.text
    data = datetime.date.today().isoformat()

    c.execute("INSERT INTO producao (atendente, data, dados) VALUES (%s, %s, %s)",
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
    c.execute("SELECT dados FROM producao WHERE data = %s", (data,))
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

    resposta = f"\ud83d\udcc5 *Resumo de Produção - {data}*\n"
    resposta += f"\n\ud83d\udcb3 Contas Abertas: {totais['Contas Abertas']}"
    resposta += f"\n\ud83d\ude97 Giro Carteira: {totais['Giro Carteira']}"
    resposta += f"\n\ud83c\udf1f Capital Integralizado: R$ {totais['Capital Integralizado']:.2f}"
    resposta += f"\n\ud83d\udcb0 Aplicações: R$ {totais['Aplicações']:.2f}"
    resposta += f"\n\ud83d\udccd Visitas Realizadas: {totais['Visitas Realizadas']}"
    resposta += f"\n\ud83d\udd39 Contratos Cobrança: {totais['Contratos Cobrança'][0]} - R$ {totais['Contratos Cobrança'][1]:.2f}"
    resposta += f"\n\ud83d\udcc8 Consignado Liberado: R$ {totais['Consignado Liberado']:.2f}"
    resposta += f"\n\ud83d\udcb3 Consórcio Contratado: R$ {totais['Consórcio Contratado']:.2f}"
    resposta += f"\n\ud83d\udcca SIPAG: {totais['SIPAG'][0]} - R$ {totais['SIPAG'][1]:.2f}"
    resposta += f"\n\ud83c\udfe6 Previdência: R$ {totais['Previdência']:.2f}"
    resposta += f"\n\ud83d\ude97 Seguro Auto: R$ {totais['Seguro Auto']:.2f}"
    resposta += f"\n\ud83d\udc65 Seguro Vida: R$ {totais['Seguro Vida']:.2f}"
    resposta += f"\n\ud83c\udfe1 Seguro Patrimonial: R$ {totais['Seguro Patrimonial']:.2f}"
    resposta += f"\n\ud83d\udcbc Seguro Empresarial: R$ {totais['Seguro Empresarial']:.2f}"
    resposta += f"\n\ud83d\udd0e Contatos de Prospecção: {totais['Prospecção']}"
    resposta += f"\n\u274c Contatos com Inativos: {totais['Inativos']}"
    resposta += f"\n\ud83d\udcc6 Contatos Fábrica de Limites: {totais['Limites']}"
    resposta += f"\n\ud83c\udfe2 Empresas visitadas em Campo: {totais['Empresas']}"
    resposta += f"\n\ud83d\udce2 Indicações solicitadas: {totais['Indicações']}"

    update.message.reply_text(resposta, parse_mode='Markdown')

# Token do Bot (substitua pelo seu)
TOKEN = 'SEU_TOKEN_AQUI'

updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher

# Handlers
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("resumo", totalizar))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, registrar_dados))

# Iniciar o bot
updater.start_polling()
updater.idle()
