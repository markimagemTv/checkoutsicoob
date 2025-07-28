import os
import sqlite3
import datetime
import re
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

DB_PATH = "producao.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS producao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atendente TEXT,
    data TEXT,
    dados TEXT
)''')
conn.commit()

itens_producao = ["Vendas", "Atendimentos", "Suporte", "Reembolsos"]

def encode_data(dado):
    return dado.replace(" ", "_")

def decode_data(dado):
    return dado.replace("_", " ")

def parse_valor(texto):
    texto = texto.replace("R$", "").replace(".", "").replace(",", ".")
    match = re.findall(r"[-+]?\d*\.\d+|\d+", texto)
    return float(match[0]) if match else None

teclado_persistente = ReplyKeyboardMarkup([
    ["➕ Adicionar Nova Produção"],
    ["📅 Produção Diária", "🗓️ Produção Semanal"],
    ["📆 Produção Mensal", "📊 Produção Geral"],
    ["❌ Excluir Produção"]
], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nome = update.effective_user.first_name
    context.user_data['nome'] = nome
    await update.message.reply_text(
        f"Olá, {nome}! 👋\nBem-vindo ao sistema de registro de produção.",
        reply_markup=teclado_persistente
    )

async def registrar_dados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    nome = context.user_data.get("nome")

    if "➕ Adicionar Nova Produção" in texto:
        botoes = [[InlineKeyboardButton(item, callback_data="producao_" + encode_data(item))] for item in itens_producao]
        await update.message.reply_text("📝 Escolha o item para registrar:", reply_markup=InlineKeyboardMarkup(botoes))
        return

    item = context.user_data.get('item_producao')
    if item:
        valor = parse_valor(texto)
        if valor is None:
            await update.message.reply_text("❌ Valor inválido. Ex: R$1500 ou 1500")
            return
        data_atual = datetime.date.today().isoformat()
        texto_registro = f"{item}: {texto}"
        c.execute("INSERT INTO producao (atendente, data, dados) VALUES (?, ?, ?)", (nome, data_atual, texto_registro))
        conn.commit()
        await update.message.reply_text(f"✅ Produção registrada:\n{texto_registro}", reply_markup=teclado_persistente)
        context.user_data.pop('item_producao')
        return

    if texto == "❌ Excluir Produção":
        await mostrar_producoes_para_excluir(update, context)
        return

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("producao_"):
        item = decode_data(data.replace("producao_", ""))
        context.user_data['item_producao'] = item
        await query.edit_message_text(f"✍️ Envie o valor para: *{item}*", parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("excluir_"):
        prod_id = int(data.replace("excluir_", ""))
        c.execute("DELETE FROM producao WHERE id = ?", (prod_id,))
        conn.commit()
        await query.edit_message_text("🗑️ Produção excluída com sucesso.")

async def mostrar_producoes_para_excluir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nome = context.user_data.get('nome')
    c.execute("SELECT id, data, dados FROM producao WHERE atendente = ? ORDER BY id DESC LIMIT 10", (nome,))
    registros = c.fetchall()
    if not registros:
        await update.message.reply_text("⚠️ Nenhuma produção encontrada para excluir.")
        return
    botoes = [[InlineKeyboardButton(f"{r[1]} - {r[2]}", callback_data=f"excluir_{r[0]}")] for r in registros]
    await update.message.reply_text("❌ Selecione a produção para excluir:", reply_markup=InlineKeyboardMarkup(botoes))

async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("⚠️ Defina a variável de ambiente BOT_TOKEN.")
        return

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, registrar_dados))
    app.add_handler(CallbackQueryHandler(callback_handler))

    print("🤖 Bot iniciado...")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
