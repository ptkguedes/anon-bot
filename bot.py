import os
import json
import re
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- CARREGAMENTO DE AMBIENTE ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
# Converte a string do .env para uma lista de inteiros real
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS").split(",")]

bot = telebot.TeleBot(TOKEN)

# --- ESTADO GLOBAL (RAM) ---
bot_active = False
end_time = None
pending_messages = {}
session_stats = {} # Zera a cada nova sessão

# --- MONITOR DE TEMPO (AUTOMÁTICO) ---
def monitor_tempo():
    global bot_active, end_time
    while True:
        if bot_active and end_time:
            if datetime.now() >= end_time:
                bot_active = False
                end_time = None
                for adm in ADMIN_IDS:
                    try:
                        bot.send_message(adm, "⏰ **TEMPO ESGOTADO!** O correio foi fechado automaticamente.")
                    except: pass
        threading.Event().wait(30)

# Inicia a thread de monitoramento em background
threading.Thread(target=monitor_tempo, daemon=True).start()

# --- AUXILIARES ---
def gerar_texto_ranking():
    # Ordena pelo valor e fatia os 3 primeiros (Top 3)
    ranking = sorted(session_stats.items(), key=lambda x: x[1], reverse=True)[:3]
    if not ranking:
        return "📊 O ranking da sessão atual ainda está vazio."
    
    texto = "🏆 **TOP 3 POPULARES DA SESSÃO** 🏆\n\n"
    medalhas = ["🥇", "🥈", "🥉"]
    for i, (user, count) in enumerate(ranking):
        texto += f"{medalhas[i]} {user}: {count} citações\n"
    return texto

# --- COMANDOS DE ADMIN ---

@bot.message_handler(commands=['start'])
def admin_start(message):
    if message.from_user.id in ADMIN_IDS:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✅ Sim, Iniciar", callback_data="wiz_mode"),
                   InlineKeyboardButton("❌ Cancelar", callback_data="wiz_cancel"))
        bot.send_message(message.chat.id, "🚀 Iniciar nova sessão do Correio Anônimo?", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "👋 Olá! Envie sua mensagem e eu a levarei para moderação.")

@bot.message_handler(commands=['endtime', 'end', 'ranking'])
def handle_admin_commands(message):
    global bot_active, end_time
    if message.from_user.id not in ADMIN_IDS: return

    cmd = message.text.split('@')[0] # Remove o username do bot se houver

    if cmd == '/endtime':
        if bot_active and end_time:
            end_time = None
            bot.send_message(message.chat.id, "🛑 **TEMPORIZADOR CANCELADO.** O correio agora está em modo MANUAL.")
        else:
            bot.send_message(message.chat.id, "Não há um temporizador ativo.")
    
    elif cmd == '/end':
        bot_active = False
        end_time = None
        bot.send_message(message.chat.id, "❌ **CORREIO ENCERRADO.** Nenhuma nova mensagem será aceita.")

    elif cmd == '/ranking':
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton("📢 Compartilhar", callback_data="rank_share"),
            InlineKeyboardButton("✖️ Fechar", callback_data="rank_close")
        )
        bot.send_message(message.chat.id, gerar_texto_ranking(), reply_markup=markup, parse_mode="Markdown")

# --- PROCESSADOR CENTRAL (CALLBACKS) ---
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    global bot_active, end_time, session_stats
    uid = call.from_user.id
    bot.answer_callback_query(call.id) # Remove o "loading" do botão

    if uid not in ADMIN_IDS: return

    # 1. Ações de Ranking
    if call.data == "rank_share":
        bot.send_message(CHANNEL_ID, gerar_texto_ranking(), parse_mode="Markdown")
    elif call.data == "rank_close":
        bot.delete_message(call.message.chat.id, call.message.message_id)

    # 2. Fluxo do Wizard (Configuração de Início)
    elif call.data == "wiz_mode":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🕹️ Manual", callback_data="setup_m"),
                   InlineKeyboardButton("⏲️ Automático", callback_data="setup_a"))
        bot.edit_message_text("Escolha o modo de duração:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "setup_m":
        bot_active = True
        session_stats = {} # ZERA O RANKING PARA A NOVA SESSÃO
        bot.edit_message_text("✅ Correio iniciado no modo **MANUAL**.", call.message.chat.id, call.message.message_id)

    elif call.data == "setup_a":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("1h", callback_data="auto_h1"), InlineKeyboardButton("2h", callback_data="auto_h2"))
        bot.edit_message_text("Duração base:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("auto_h"):
        h = call.data[-1]
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"{h}h:00", callback_data=f"final_{h}_0"),
                   InlineKeyboardButton(f"{h}h:15", callback_data=f"final_{h}_15"),
                   InlineKeyboardButton(f"{h}h:30", callback_data=f"final_{h}_30"))
        bot.edit_message_text(f"🕒 Escolhido {h}h. Adicionar minutos?", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("final_"):
        _, h, m = call.data.split("_")
        bot_active = True
        session_stats = {} # ZERA O RANKING PARA A NOVA SESSÃO
        end_time = datetime.now() + timedelta(hours=int(h), minutes=int(m))
        bot.edit_message_text(f"✅ **CORREIO INICIADO!**\nFecha às: {end_time.strftime('%H:%M:%S')}", call.message.chat.id, call.message.message_id)

    # 3. Fluxo de Aprovação
    elif call.data.startswith(("ap_", "rj_")):
        act, m_id = call.data.split("_")
        if m_id in pending_messages:
            dados = pending_messages.pop(m_id)
            if act == "ap":
                # Ranking só conta se for aprovado
                mentions = re.findall(r'@\w+', dados['text'])
                for m in mentions:
                    if m.lower() != f"@{dados['user']}".lower(): # Filtro anti-auto-menção
                        session_stats[m] = session_stats.get(m, 0) + 1
                
                bot.send_message(CHANNEL_ID, f"💌 **Mensagem Anônima:**\n\n{dados['text']}")
                bot.edit_message_text(f"✅ Postada por @{call.from_user.username}", call.message.chat.id, call.message.message_id)
                try: bot.send_message(dados['user_id'], "🥳 Sua mensagem foi aprovada e postada!")
                except: pass
            else:
                bot.edit_message_text("❌ Recusada.", call.message.chat.id, call.message.message_id)
                try: bot.send_message(dados['user_id'], "❌ Sua mensagem foi recusada pela moderação.")
                except: pass

# --- RECEBIMENTO ---
@bot.message_handler(func=lambda m: m.chat.type == "private" and not m.text.startswith('/'))
def receive_message(message):
    if not bot_active: 
        return bot.send_message(message.chat.id, "⏳ O correio está fechado no momento.")
    
    m_id = str(message.message_id)
    pending_messages[m_id] = {
        "user_id": message.chat.id, 
        "user": message.from_user.username or "Anon", 
        "text": message.text
    }
    
    markup = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Aprovar", callback_data=f"ap_{m_id}"),
        InlineKeyboardButton("❌ Recusar", callback_data=f"rj_{m_id}")
    )
    for adm in ADMIN_IDS:
        try: bot.send_message(adm, f"📝 **Nova mensagem de @{message.from_user.username}:**\n\n{message.text}", reply_markup=markup)
        except: pass
    bot.send_message(message.chat.id, "✅ Enviada para moderação!")

bot.polling(none_stop=True)
