import os
import re
import threading
from datetime import datetime, timedelta
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- CONFIGURAÇÕES DIRETAS ---
TOKEN = "7761415730:AAGZD1QDlwiNVLaoKZZEcar18b0HZhNPWhs"
GROUP_ID = -1001468375523
ADMIN_IDS = [8154662660, 6439529867, 7511846281, 8038903090]

bot = telebot.TeleBot(TOKEN)

# --- ESTADO GLOBAL ---
bot_active = False
end_time = None
pending_messages = {}
session_stats = {} 

# --- MONITOR DE TEMPO ---
def monitor_tempo():
    global bot_active, end_time
    while True:
        if bot_active and end_time:
            if datetime.now() >= end_time:
                bot_active = False
                end_time = None
                try:
                    bot.send_message(CHANNEL_ID, "🛑 **CORREIO ENCERRADO!**\nA sessão automática chegou ao fim. Obrigado a todos! 💌")
                except: pass
                for adm in ADMIN_IDS:
                    try: bot.send_message(adm, "⏰ **TEMPO ESGOTADO!** O correio foi fechado automaticamente.")
                    except: pass
        threading.Event().wait(30)

threading.Thread(target=monitor_tempo, daemon=True).start()

# --- AUXILIARES ---
def gerar_texto_ranking():
    ranking = sorted(session_stats.items(), key=lambda x: x[1], reverse=True)[:3]
    if not ranking: return "📊 O ranking da sessão atual está vazio."
    texto = "🏆 **TOP 3 POPULARES DA SESSÃO** 🏆\n\n"
    medalhas = ["🥇", "🥈", "🥉"]
    for i, (user, count) in enumerate(ranking):
        texto += f"{medalhas[i]} {user}: {count} citações\n"
    return texto

# --- COMANDOS ADMIN ---
@bot.message_handler(commands=['start'])
def admin_start(message):
    if message.from_user.id in ADMIN_IDS:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✅ Sim, Iniciar", callback_data="wiz_mode"),
                   InlineKeyboardButton("❌ Cancelar", callback_data="wiz_cancel"))
        bot.send_message(message.chat.id, "🚀 Iniciar nova sessão do Correio Anônimo?", reply_markup=markup)

@bot.message_handler(commands=['end'])
def manual_stop(message):
    if message.from_user.id in ADMIN_IDS:
        global bot_active, end_time
        bot_active = False
        end_time = None
        bot.send_message(message.chat.id, "❌ **CORREIO ENCERRADO.**")

@bot.message_handler(commands=['ranking'])
def cmd_ranking(message):
    if message.from_user.id in ADMIN_IDS:
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton("📢 Compartilhar", callback_data="rank_share"),
            InlineKeyboardButton("✖️ Fechar", callback_data="rank_close")
        )
        bot.send_message(message.chat.id, gerar_texto_ranking(), reply_markup=markup, parse_mode="Markdown")

# --- PROCESSADOR CENTRAL (CALLBACKS) ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    global bot_active, end_time, session_stats
    uid = call.from_user.id
    bot.answer_callback_query(call.id)

    if uid not in ADMIN_IDS: return

    if call.data == "rank_share":
        bot.send_message(CHANNEL_ID, gerar_texto_ranking(), parse_mode="Markdown")
    elif call.data == "rank_close":
        bot.delete_message(call.message.chat.id, call.message.message_id)
    elif call.data == "wiz_cancel":
        bot.edit_message_text("❌ Início da sessão do Correio Anônimo foi cancelado.", call.message.chat.id, call.message.message_id)
        return
    elif call.data == "wiz_mode":
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🕹️ Manual", callback_data="setup_m"),
            InlineKeyboardButton("⏲️ Automático", callback_data="setup_a")
        )
        bot.edit_message_text("Como deseja gerenciar o tempo?", call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif call.data == "setup_m":
        bot_active = True
        session_stats = {}
        bot.edit_message_text("✅ Correio iniciado (MODO MANUAL).", call.message.chat.id, call.message.message_id)
    elif call.data == "setup_a":
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton("1h", callback_data="auto_h1"), 
            InlineKeyboardButton("2h", callback_data="auto_h2")
        )
        bot.edit_message_text("Duração base:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif call.data.startswith("auto_h"):
        h = call.data[-1]
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton(f"{h}h:00", callback_data=f"final_{h}_0"),
            InlineKeyboardButton(f"{h}h:15", callback_data=f"final_{h}_15"),
            InlineKeyboardButton(f"{h}h:30", callback_data=f"final_{h}_30")
        )
        bot.edit_message_text(f"🕒 {h}h escolhido. Adicionar minutos?", call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif call.data.startswith("final_"):
        _, h, m = call.data.split("_")
        bot_active = True
        session_stats = {}
        end_time = datetime.now() + timedelta(hours=int(h), minutes=int(m))
        bot.edit_message_text(f"✅ **CORREIO INICIADO!**\nFecha às: {end_time.strftime('%H:%M:%S')}", call.message.chat.id, call.message.message_id)
    elif call.data.startswith(("ap_", "rj_")):
        act, m_id = call.data.split("_")
        if m_id in pending_messages:
            dados = pending_messages.pop(m_id)
            
            # --- PATCH DE NULL SAFETY (Tolerância a Falhas) ---
            user = call.from_user
            identificacao = f"@{user.username}" if user.username else user.first_name
            # --------------------------------------------------

            if act == "ap":
                mentions = re.findall(r'@\w+', dados['text'])
                for m in mentions:
                    if m.lower() != f"@{dados['user_username']}".lower():
                        session_stats[m] = session_stats.get(m, 0) + 1
                bot.send_message(CHANNEL_ID, f"🔹 **Mensagem Anônima:**\n\n{dados['text']}")
                bot.edit_message_text(f"✅ Aprovada por {identificacao}", call.message.chat.id, call.message.message_id)
                bot.send_message(dados['user_id'], "✅ Sua mensagem foi aprovada!")
            else:
                bot.edit_message_text(f"❌ Recusada por {identificacao}", call.message.chat.id, call.message.message_id)
                bot.send_message(dados['user_id'], "❌ Sua mensagem foi recusada.")
                
# --- RECEBIMENTO ---
@bot.message_handler(func=lambda m: m.chat.type == "private" and not m.text.startswith('/'))
def receive_message(message):
    if not bot_active:
        return bot.send_message(message.chat.id, "⏳ O correio está fechado no momento.")

    user_id = message.chat.id
    user_name = message.from_user.first_name
    user_username = message.from_user.username or "SemUsername"
    m_id = str(message.message_id)

    pending_messages[m_id] = {
        "user_id": user_id, 
        "user_name": user_name,
        "user_username": user_username,
        "text": message.text
    }

    markup = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Aprovar", callback_data=f"ap_{m_id}"),
        InlineKeyboardButton("❌ Recusar", callback_data=f"rj_{m_id}")
    )

    for adm in ADMIN_IDS:
        try:
            bot.send_message(adm, f"Nova mensagem anônima recebida:\n\n🔹 {message.text}\n👤 Remetente: {user_name} (ID: {user_id} | @{user_username})", reply_markup=markup)
            bot.forward_message(adm, user_id, message.message_id)
        except: pass
    bot.send_message(user_id, "📨 Enviada para aprovação do admin.")

bot.polling(none_stop=True)
