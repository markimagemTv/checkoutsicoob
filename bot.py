import sqlite3
import datetime
import re
import os
import logging
import base64
import hashlib

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ParseMode
)
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    CallbackQueryHandler, CallbackContext
)

logging.basicConfig(level=logging.INFO)

conn = sqlite3.connect("producao.db", check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS producao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    atendente TEXT,
    data TEXT,
    dados TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS atendentes (
    user_id INTEGER PRIMARY KEY,
    nome TEXT,
    cargo TEXT,
    lotacao TEXT,
    senha_hash TEXT
)''')

conn.commit()

estado_registro = {}

itens_producao = [
    "R$ Operações de Crédito", "Qtd Contas Abertas", "Qtd Giro Carteira",
    "R$ Capital Integralizado", "R$ Aplicações", "Qtd Visitas Realizadas",
    "Qtd e Valor Novos Contratos Cobrança", "R$ Consignado Liberado",
    "R$ Consórcio Contratado", "Qtd e Valor:  SIPAG: Faturamento",
    "R$ Previdência", "R$ Seguro Auto", "R$ Seguro Vida",
    "R$ Seguro Patrimonial", "R$ seguro empresarial",
    "Cooperados Visitados no dia", "Contatos de Prospecção",
    "Contatos com Inativos", "Contatos Fábrica de Limites",
    "Empresas visitadas em Campo", "Indicações solicitadas"
]

producoes_temp = {}

teclado_persistente = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("➕ Adicionar Nova Produção")],
        [KeyboardButton("📅 Produção Diária"), KeyboardButton("🗓️ Produção Semanal")],
        [KeyboardButton("📆 Produção Mensal"), KeyboardButton("📊 Produção Geral")],
        [KeyboardButton("🔍 Buscar por Data/Atendente"), KeyboardButton("📍 Buscar por PA")],
        [KeyboardButton("🗑️ Excluir Produção")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

def gerar_hash(senha: str) -> str:
    return hashlib.sha256(senha.encode()).hexdigest()

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
        return

    elif estado_registro.get(user_id) == 'cargo':
        context.user_data['cargo'] = texto
        estado_registro[user_id] = 'lotacao'
        botoes = [[KeyboardButton(f"PA{str(i).zfill(2)}")] for i in range(10)] + [[KeyboardButton("PA DIGITAL")]]
        update.message.reply_text("🏢 Escolha sua lotação:", reply_markup=ReplyKeyboardMarkup(botoes, resize_keyboard=True))
        return

    elif estado_registro.get(user_id) == 'lotacao':
        context.user_data['lotacao'] = texto
        estado_registro[user_id] = 'senha'
        update.message.reply_text("🔒 Agora defina uma senha para proteger sua produção:")
        return

    elif estado_registro.get(user_id) == 'senha':
        senha = texto
        nome = context.user_data['nome']
        cargo = context.user_data['cargo']
        lotacao = context.user_data['lotacao']
        senha_hash = gerar_hash(senha)
        c.execute("INSERT INTO atendentes (user_id, nome, cargo, lotacao, senha_hash) VALUES (?, ?, ?, ?, ?)",
                  (user_id, nome, cargo, lotacao, senha_hash))
        conn.commit()
        estado_registro.pop(user_id)
        update.message.reply_text(f"✅ Cadastro completo como {nome} - {cargo} ({lotacao}). Use /start novamente.", reply_markup=teclado_persistente)
        return

    if context.user_data.get('registrando_producao'):
        item = context.user_data.get('item_atual')
        producoes_temp.setdefault(user_id, []).append(f"{item}: {texto}")
        prox_indice = context.user_data['indice_atual'] + 1
        if prox_indice < len(itens_producao):
            context.user_data['indice_atual'] = prox_indice
            context.user_data['item_atual'] = itens_producao[prox_indice]
            update.message.reply_text(f"{itens_producao[prox_indice]}:")
        else:
            dados_final = " | ".join(producoes_temp[user_id])
            data_hoje = datetime.datetime.now().strftime("%d/%m/%Y")
            c.execute("SELECT nome FROM atendentes WHERE user_id = ?", (user_id,))
            atendente = c.fetchone()[0]
            c.execute("INSERT INTO producao (user_id, atendente, data, dados) VALUES (?, ?, ?, ?)",
                      (user_id, atendente, data_hoje, dados_final))
            conn.commit()
            update.message.reply_text("✅ Produção registrada com sucesso!", reply_markup=teclado_persistente)
            context.user_data['registrando_producao'] = False
            producoes_temp[user_id] = []
        return

    if context.user_data.get('modo_exclusao'):
        try:
            data_str, trecho = map(str.strip, texto.split(","))
            context.user_data['exclusao_data'] = data_str
            context.user_data['exclusao_trecho'] = trecho
            update.message.reply_text("🔒 Confirme sua senha para excluir essa produção:")
            context.user_data['modo_exclusao'] = False
            context.user_data['confirmando_exclusao'] = True
        except:
            update.message.reply_text("❌ Formato inválido. Tente novamente.")
        return

    if context.user_data.get('confirmando_exclusao'):
        senha = texto
        c.execute("SELECT senha_hash FROM atendentes WHERE user_id = ?", (user_id,))
        senha_hash_db = c.fetchone()[0]
        if gerar_hash(senha) == senha_hash_db:
            data = context.user_data['exclusao_data']
            trecho = context.user_data['exclusao_trecho']
            c.execute("DELETE FROM producao WHERE user_id = ? AND data = ? AND dados LIKE ?",
                      (user_id, data, f"%{trecho}%"))
            conn.commit()
            update.message.reply_text("✅ Produção excluída com sucesso.", reply_markup=teclado_persistente)
        else:
            update.message.reply_text("❌ Senha incorreta. Operação cancelada.", reply_markup=teclado_persistente)
        context.user_data['confirmando_exclusao'] = False
        return

def iniciar_producao(update, context):
    user_id = update.effective_user.id
    context.user_data['registrando_producao'] = True
    context.user_data['indice_atual'] = 0
    context.user_data['item_atual'] = itens_producao[0]
    update.message.reply_text(f"📌 Vamos começar sua produção!
{itens_producao[0]}:")

def iniciar_exclusao(update, context):
    context.user_data['modo_exclusao'] = True
    update.message.reply_text(
        "🗑️ Envie a *data da produção* (DD/MM/AAAA) e parte do *conteúdo* registrado, separados por vírgula.\n"
        "Exemplo: 28/07/2025, R$ Operações de Crédito",
        parse_mode=ParseMode.MARKDOWN
    )

def busca_por_pa(update, context):
    user_id = update.effective_user.id
    c.execute("SELECT cargo, lotacao FROM atendentes WHERE user_id = ?", (user_id,))
    dados = c.fetchone()
    if not dados:
        update.message.reply_text("⚠️ Cadastro não encontrado.")
        return
    cargo, lotacao = dados
    if cargo.lower() not in ['gerente', 'coordenador', 'supervisor', 'diretor']:
        update.message.reply_text("❌ Apenas gerentes ou superiores podem acessar essa função.")
        return
    c.execute("SELECT atendente, data, dados FROM producao INNER JOIN atendentes ON producao.user_id = atendentes.user_id WHERE lotacao = ?", (lotacao,))
    resultados = c.fetchall()
    if resultados:
        resposta = "📍 Produções do seu PA:\n\n"
        for r in resultados:
            resposta += f"👤 {r[0]} | 📅 {r[1]}\n📌 {r[2]}\n\n"
        update.message.reply_text(resposta[:4096])
    else:
        update.message.reply_text("Nenhuma produção encontrada para seu PA.")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN não definido nas variáveis de ambiente.")

updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher

dp.add_handler(CommandHandler("start", start))
dp.add_handler(MessageHandler(Filters.regex("^➕ Adicionar Nova Produção$"), iniciar_producao))
dp.add_handler(MessageHandler(Filters.regex("^🗑️ Excluir Produção$"), iniciar_exclusao))
dp.add_handler(MessageHandler(Filters.regex("^📍 Buscar por PA$"), busca_por_pa))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, registrar_nome))

updater.start_polling()
updater.idle()
