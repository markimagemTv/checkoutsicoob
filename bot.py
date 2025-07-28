import sqlite3
import datetime
import re
import os
import logging
import base64

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.constants import ParseMode
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    CallbackQueryHandler, CallbackContext
)

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
        [KeyboardButton("➕ Adicionar Nova Produção")],
        [KeyboardButton("📅 Produção Diária"), KeyboardButton("🗓️ Produção Semanal")],
        [KeyboardButton("📆 Produção Mensal"), KeyboardButton("📊 Produção Geral")],
        [KeyboardButton("🔍 Buscar por Data/Atendente"), KeyboardButton("📍 Buscar por PA")],
        [KeyboardButton("❌ Excluir Produção")]
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

def encode_data(texto):
    return base64.urlsafe_b64encode(texto.encode()).decode()

def decode_data(encoded):
    return base64.urlsafe_b64decode(encoded.encode()).decode()

def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data.startswith("producao_"):
        try:
            item_codificado = data.replace("producao_", "")
            item = decode_data(item_codificado)
            context.user_data['item_producao'] = item
            query.edit_message_text(f"✍️ Envie o valor para *{item}*", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            query.edit_message_text("❌ Erro ao decodificar o item de produção.")

    elif data.startswith("excluir_"):
        try:
            registro_id = int(data.replace("excluir_", ""))
            c.execute("DELETE FROM producao WHERE id = ?", (registro_id,))
            conn.commit()
            query.edit_message_text("✅ Produção excluída com sucesso.")
        except Exception as e:
            query.edit_message_text("❌ Erro ao excluir a produção.")

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
            update.message.reply_text(resposta)
        except:
            update.message.reply_text("❌ Formato inválido. Use: DD/MM/AAAA, Nome")
        return

    if context.user_data.get('modo_pa'):
        context.user_data.pop('modo_pa', None)
        pa = texto
        c.execute("SELECT nome FROM atendentes WHERE lotacao = ?", (pa,))
        nomes = [r[0] for r in c.fetchall()]
        if not nomes:
            update.message.reply_text("⚠️ Nenhum atendente encontrado com esse PA.")
            return

        resposta = f"📍 *Produções por Atendentes do {pa}*\n"
        for nome in nomes:
            c.execute("SELECT dados FROM producao WHERE atendente = ?", (nome,))
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
                    resposta += f"\n👤 *{nome}*:\n"
                    for item, total in soma_itens.items():
                        if "R$" in item:
                            resposta += f"• {item}: R$ {total:,.2f}\n"
                        else:
                            resposta += f"• {item}: {int(total)}\n"

        update.message.reply_text(resposta, parse_mode=ParseMode.MARKDOWN)
        return

    comandos = {
        "➕ adicionar nova produção": lambda: enviar_botoes_producao(update),
        "📅 produção diária": lambda: totalizar(update, context, periodo='dia'),
        "🗓️ produção semanal": lambda: totalizar(update, context, periodo='semana'),
        "📆 produção mensal": lambda: totalizar(update, context, periodo='mes'),
        "📊 produção geral": lambda: totalizar(update, context, periodo='todos'),
        "🔍 buscar por data/atendente": lambda: busca_data_atendente(update, context),
        "📍 buscar por pa": lambda: busca_por_pa(update, context),
        "❌ excluir produção": lambda: iniciar_exclusao(update, context)
    }

    if texto_lower in comandos:
        comandos[texto_lower]()
        return

    item = context.user_data.get('item_producao')
    if not item:
        update.message.reply_text("⚠️ Use o botão 'Adicionar Nova Produção' para selecionar o item.")
        return

    # Validação e formatação do valor recebido
    valor_texto = texto.replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        if item.startswith("R$"):
            valor = float(valor_texto)
            registro = f"{item}: R$ {valor:,.2f}"
        else:
            valor = int(float(valor_texto))
            registro = f"{item}: {valor}"
    except:
        update.message.reply_text("❌ Valor inválido. Por favor, envie um número válido.")
        return

    data = datetime.date.today().isoformat()
    c.execute("INSERT INTO producao (atendente, data, dados) VALUES (?, ?, ?)", (nome, data, registro))
    conn.commit()

    context.user_data.pop('item_producao', None)
    update.message.reply_text("✅ Produção registrada com sucesso!", reply_markup=teclado_persistente)

def enviar_botoes_producao(update):
    botoes = [
        [InlineKeyboardButton(text=item, callback_data=f"producao_{encode_data(item)}")]
        for item in itens_producao
    ]
    update.message.reply_text("📝 Selecione o item de produção:", reply_markup=InlineKeyboardMarkup(botoes))

def busca_data_atendente(update, context):
    context.user_data['modo_busca'] = True
    update.message.reply_text("🔎 Envie a data (DD/MM/AAAA) e o nome do atendente separados por vírgula.\nExemplo: 25/07/2025, João")

def busca_por_pa(update, context):
    context.user_data['modo_pa'] = True
    update.message.reply_text("📍 Envie o nome do PA. Exemplo: PA01 ou PA DIGITAL")

def totalizar(update, context, periodo='dia'):
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

    resposta = f"📊 *Produção {periodo.capitalize()}*\n"
    for item, total in resumo.items():
        if "R$" in item:
            resposta += f"• {item}: R$ {total:,.2f}\n"
        else:
            resposta += f"• {item}: {int(total)}\n"

    update.message.reply_text(resposta, parse_mode=ParseMode.MARKDOWN)

def iniciar_exclusao(update, context):
    user_id = update.effective_user.id
    c.execute("SELECT id, data, dados FROM producao WHERE atendente = ?", (context.user_data.get('nome'),))
    registros = c.fetchall()
    if not registros:
        update.message.reply_text("⚠️ Nenhuma produção encontrada para excluir.")
        return
    botoes = [
        [InlineKeyboardButton(text=f"{r[1]}: {r[2]}", callback_data=f"excluir_{r[0]}")]
        for r in registros
    ]
    update.message.reply_text("❌ Selecione a produção que deseja excluir:", reply_markup=InlineKeyboardMarkup(botoes))

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    updater = Updater(token=token, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, registrar_dados))
    dp.add_handler(CallbackQueryHandler(callback_handler))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
