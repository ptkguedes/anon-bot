import re
import time
import threading
import logging
from datetime import datetime, timedelta

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# --- CONFIGURAÇÕES ---
TOKEN = "7761415730:AAGZD1QDlwiNVLaoKZZEcar18b0HZhNPWhs"
GROUP_ID = -1001468375523
ADMIN_IDS = [8154662660, 6439529867, 7511846281, 8038903090]

bot = telebot.TeleBot(TOKEN, parse_mode=None)

# --- LOGS ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# --- ESTADO GLOBAL ---
bot_active = False
end_time = None
pending_messages = {}  # chave: "{user_id}_{message_id}"
session_stats = {}
state_lock = threading.Lock()


# --- AUXILIARES ---
def gerar_msg_key(user_id: int, message_id: int) -> str:
    return f"{user_id}_{message_id}"


def gerar_texto_ranking() -> str:
    ranking = sorted(session_stats.items(), key=lambda x: x[1], reverse=True)[:3]
    if not ranking:
        return "📊 O ranking da sessão atual está vazio."

    texto = "🏆 *TOP 3 POPULARES DA SESSÃO* 🏆\n\n"
    medalhas = ["🥇", "🥈", "🥉"]
    for i, (user, count) in enumerate(ranking):
        texto += f"{medalhas[i]} {user}: {count} citações\n"
    return texto


# --- MONITOR DE TEMPO ---
def monitor_tempo():
    global bot_active, end_time
    while True:
        try:
            with state_lock:
                ativo = bot_active
                fim = end_time

            if ativo and fim and datetime.now() >= fim:
                with state_lock:
                    bot_active = False
                    end_time = None

                try:
                    bot.send_message(
                        GROUP_ID,
                        "🛑 *CORREIO ENCERRADO!*\nA sessão automática chegou ao fim. Obrigado a todos! 💌",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logging.exception("Erro ao avisar encerramento no grupo: %s", e)

                for adm in ADMIN_IDS:
                    try:
                        bot.send_message(
                            adm,
                            "⏰ *TEMPO ESGOTADO!* O correio foi fechado automaticamente.",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logging.exception("Erro ao avisar admin %s: %s", adm, e)

            time.sleep(30)

        except Exception as e:
            logging.exception("Erro no monitor de tempo: %s", e)
            time.sleep(5)


threading.Thread(target=monitor_tempo, daemon=True).start()


# --- COMANDOS ADMIN ---
@bot.message_handler(commands=["start"])
def admin_start(message):
    if message.from_user.id not in ADMIN_IDS:
        return

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ Sim, Iniciar", callback_data="wiz_mode"),
        InlineKeyboardButton("❌ Cancelar", callback_data="wiz_cancel")
    )
    bot.send_message(
        message.chat.id,
        "🚀 Iniciar nova sessão do Correio Anônimo?",
        reply_markup=markup
    )


@bot.message_handler(commands=["end"])
def manual_stop(message):
    global bot_active, end_time
    if message.from_user.id not in ADMIN_IDS:
        return

    with state_lock:
        bot_active = False
        end_time = None

    bot.send_message(message.chat.id, "❌ *CORREIO ENCERRADO.*", parse_mode="Markdown")


@bot.message_handler(commands=["ranking"])
def cmd_ranking(message):
    if message.from_user.id not in ADMIN_IDS:
        return

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("📢 Compartilhar", callback_data="rank_share"),
        InlineKeyboardButton("✖️ Fechar", callback_data="rank_close")
    )
    bot.send_message(
        message.chat.id,
        gerar_texto_ranking(),
        reply_markup=markup,
        parse_mode="Markdown"
    )


@bot.message_handler(commands=["status"])
def cmd_status(message):
    if message.from_user.id not in ADMIN_IDS:
        return

    with state_lock:
        ativo = bot_active
        fim = end_time

    if not ativo:
        bot.send_message(message.chat.id, "ℹ️ Correio está *fechado*.", parse_mode="Markdown")
        return

    if fim:
        bot.send_message(
            message.chat.id,
            f"✅ Correio *aberto* (automático).\nFecha às: `{fim.strftime('%H:%M:%S')}`",
            parse_mode="Markdown"
        )
    else:
        bot.send_message(
            message.chat.id,
            "✅ Correio *aberto* (manual).",
            parse_mode="Markdown"
        )


# --- PROCESSADOR CENTRAL (CALLBACKS) ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    global bot_active, end_time, session_stats

    uid = call.from_user.id
    bot.answer_callback_query(call.id)

    if uid not in ADMIN_IDS:
        return

    try:
        if call.data == "rank_share":
            bot.send_message(GROUP_ID, gerar_texto_ranking(), parse_mode="Markdown")

        elif call.data == "rank_close":
            bot.delete_message(call.message.chat.id, call.message.message_id)

        elif call.data == "wiz_cancel":
            bot.edit_message_text(
                "❌ Início da sessão do Correio Anônimo foi cancelado.",
                call.message.chat.id,
                call.message.message_id
            )

        elif call.data == "wiz_mode":
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("🕹️ Manual", callback_data="setup_m"),
                InlineKeyboardButton("⏲️ Automático", callback_data="setup_a")
            )
            bot.edit_message_text(
                "Como deseja gerenciar o tempo?",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )

        elif call.data == "setup_m":
            with state_lock:
                bot_active = True
                end_time = None
                session_stats = {}
            bot.edit_message_text(
                "✅ Correio iniciado (MODO MANUAL).",
                call.message.chat.id,
                call.message.message_id
            )

        elif call.data == "setup_a":
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("1h", callback_data="auto_h1"),
                InlineKeyboardButton("2h", callback_data="auto_h2")
            )
            bot.edit_message_text(
                "Duração base:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )

        elif call.data.startswith("auto_h"):
            h = call.data[-1]
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton(f"{h}h:00", callback_data=f"final_{h}_0"),
                InlineKeyboardButton(f"{h}h:15", callback_data=f"final_{h}_15"),
                InlineKeyboardButton(f"{h}h:30", callback_data=f"final_{h}_30")
            )
            bot.edit_message_text(
                f"🕒 {h}h escolhido. Adicionar minutos?",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )

        elif call.data.startswith("final_"):
            _, h, m = call.data.split("_")
            with state_lock:
                bot_active = True
                session_stats = {}
                end_time = datetime.now() + timedelta(hours=int(h), minutes=int(m))

            bot.edit_message_text(
                f"✅ *CORREIO INICIADO!*\nFecha às: `{end_time.strftime('%H:%M:%S')}`",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown"
            )

        elif call.data.startswith(("ap_", "rj_")):
            act, msg_key = call.data.split("_", 1)

            if msg_key not in pending_messages:
                bot.edit_message_text(
                    "⚠️ Esta mensagem já foi processada ou expirou.",
                    call.message.chat.id,
                    call.message.message_id
                )
                return

            dados = pending_messages.pop(msg_key)

            user = call.from_user
            identificacao = f"@{user.username}" if user.username else user.first_name

            if act == "ap":
                mentions = re.findall(r"@\w+", dados["text"] or "")
                remetente_username = f"@{dados['user_username']}".lower()

                for mention in mentions:
                    if mention.lower() != remetente_username:
                        session_stats[mention] = session_stats.get(mention, 0) + 1

                # SEM markdown no texto do usuário para evitar erro de parse
                bot.send_message(
                    GROUP_ID,
                    f"🔹 Mensagem anônima:\n\n{dados['text']}"
                )

                bot.edit_message_text(
                    f"✅ Aprovada por {identificacao}",
                    call.message.chat.id,
                    call.message.message_id
                )
                bot.send_message(dados["user_id"], "✅ Sua mensagem foi aprovada!")

            else:
                bot.edit_message_text(
                    f"❌ Recusada por {identificacao}",
                    call.message.chat.id,
                    call.message.message_id
                )
                bot.send_message(dados["user_id"], "❌ Sua mensagem foi recusada.")

    except Exception as e:
        logging.exception("Erro no callback '%s': %s", call.data, e)


# --- RECEBIMENTO DE MENSAGENS PRIVADAS ---
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.content_type == "text" and not m.text.startswith("/"))
def receive_message(message):
    with state_lock:
        ativo = bot_active

    if not ativo:
        bot.send_message(message.chat.id, "⏳ O correio está fechado no momento.")
        return

    user_id = message.chat.id
    user_name = message.from_user.first_name or "Usuário"
    user_username = message.from_user.username or "SemUsername"
    msg_key = gerar_msg_key(user_id, message.message_id)

    pending_messages[msg_key] = {
        "user_id": user_id,
        "user_name": user_name,
        "user_username": user_username,
        "text": message.text
    }

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ Aprovar", callback_data=f"ap_{msg_key}"),
        InlineKeyboardButton("❌ Recusar", callback_data=f"rj_{msg_key}")
    )

    for adm in ADMIN_IDS:
        try:
            bot.send_message(
                adm,
                (
                    "Nova mensagem anônima recebida:\n\n"
                    f"🔹 {message.text}\n"
                    f"👤 Remetente: {user_name} (ID: {user_id} | @{user_username})"
                ),
                reply_markup=markup
            )
            bot.forward_message(adm, user_id, message.message_id)
        except Exception as e:
            logging.exception("Erro ao enviar para admin %s: %s", adm, e)

    bot.send_message(user_id, "📨 Enviada para aprovação do admin.")


# --- EXECUÇÃO ---
if __name__ == "__main__":
    logging.info("Bot iniciado...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
