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


def nome_admin(user) -> str:
    return f"@{user.username}" if user.username else (user.first_name or "Admin")


def label_admin(user) -> str:
    nome = user.first_name or "Admin"
    if user.username:
        return f"{nome} (@{user.username})"
    return nome


def gerar_texto_ranking() -> str:
    ranking = sorted(session_stats.items(), key=lambda x: x[1], reverse=True)[:3]
    if not ranking:
        return "📊 O ranking da sessão atual está vazio."

    texto = "🏆 *TOP 3 POPULARES DA SESSÃO* 🏆\n\n"
    medalhas = ["🥇", "🥈", "🥉"]
    for i, (user, count) in enumerate(ranking):
        texto += f"{medalhas[i]} {user}: {count} citações\n"
    return texto


def texto_moderacao(dados: dict) -> str:
    username = f"@{dados['user_username']}" if dados['user_username'] != "SemUsername" else "sem @username"
    return (
        "Nova mensagem para moderação:\n\n"
        f"📝 Texto: {dados['text']}\n"
        f"👤 Nickname: {dados['user_name']}\n"
        f"🔗 Username: {username}\n"
        f"🆔 ID: {dados['user_id']}"
    )


def notificar_inicio_para_outros(admin_ator_id: int, ator_label: str, modo: str):
    for adm in ADMIN_IDS:
        if adm == admin_ator_id:
            continue
        try:
            bot.send_message(adm, f"✅ {ator_label} iniciou a sessão em modo {modo}.")
        except Exception as e:
            logging.exception("Erro ao notificar início para admin %s: %s", adm, e)


def notificar_encerramento_para_admins(admin_ator_id: int, ator_label: str):
    for adm in ADMIN_IDS:
        try:
            if adm == admin_ator_id:
                bot.send_message(adm, "🛑 Você encerrou a sessão.")
            else:
                bot.send_message(adm, f"🛑 {ator_label} encerrou a sessão.")
        except Exception as e:
            logging.exception("Erro ao notificar encerramento para admin %s: %s", adm, e)


def notificar_moderacao_para_admins(admin_ator_id: int, ator_label: str, acao: str):
    # acao = "aprovou" ou "recusou"
    for adm in ADMIN_IDS:
        try:
            if adm == admin_ator_id:
                bot.send_message(adm, f"✅ Você {acao} a mensagem.")
            else:
                bot.send_message(adm, f"✅ {ator_label} {acao} a mensagem.")
        except Exception as e:
            logging.exception("Erro ao notificar moderação para admin %s: %s", adm, e)


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
                        bot.send_message(adm, "⏰ Sessão encerrada automaticamente por tempo esgotado.")
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

    ator_label = label_admin(message.from_user)

    with state_lock:
        bot_active = False
        end_time = None

    notificar_encerramento_para_admins(message.from_user.id, ator_label)


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
            ator_label = label_admin(call.from_user)

            with state_lock:
                bot_active = True
                end_time = None
                session_stats = {}

            # Apenas o iniciador recebe esse texto no card atual
            bot.edit_message_text(
                "✅ Você iniciou a sessão em modo manual.",
                call.message.chat.id,
                call.message.message_id
            )
            # Demais admins recebem notificação separada
            notificar_inicio_para_outros(call.from_user.id, ator_label, "manual")

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
            ator_label = label_admin(call.from_user)

            with state_lock:
                bot_active = True
                session_stats = {}
                end_time = datetime.now() + timedelta(hours=int(h), minutes=int(m))
                fim = end_time

            bot.edit_message_text(
                f"✅ Você iniciou a sessão em modo automático.\nFecha às: {fim.strftime('%H:%M:%S')}",
                call.message.chat.id,
                call.message.message_id
            )
            notificar_inicio_para_outros(call.from_user.id, ator_label, "automático")

        elif call.data.startswith(("ap_", "rj_")):
            act, msg_key = call.data.split("_", 1)
            admin_resp = nome_admin(call.from_user)
            ator_label = label_admin(call.from_user)

            with state_lock:
                if msg_key not in pending_messages:
                    bot.edit_message_text(
                        "⚠️ Esta mensagem já foi processada ou expirou.",
                        call.message.chat.id,
                        call.message.message_id
                    )
                    return
                dados = pending_messages.pop(msg_key)

            if act == "ap":
                mentions = re.findall(r"@\w+", dados["text"] or "")
                remetente_username = f"@{dados['user_username']}".lower()

                for mention in mentions:
                    if mention.lower() != remetente_username:
                        session_stats[mention] = session_stats.get(mention, 0) + 1

                bot.send_message(GROUP_ID, f"🔹 Mensagem anônima:\n\n{dados['text']}")
                bot.send_message(dados["user_id"], "✅ Sua mensagem foi aprovada!")
                status = f"✅ Aprovada por {admin_resp}"
                notificar_moderacao_para_admins(call.from_user.id, ator_label, "aprovou")
            else:
                bot.send_message(dados["user_id"], "❌ Sua mensagem foi recusada.")
                status = f"❌ Recusada por {admin_resp}"
                notificar_moderacao_para_admins(call.from_user.id, ator_label, "recusou")

            # Atualiza card para TODOS os admins (remove botões)
            admin_msgs = dados.get("admin_messages", {})
            novo_texto = f"{texto_moderacao(dados)}\n\n{status}"

            for adm_id, msg_id in admin_msgs.items():
                try:
                    bot.edit_message_text(novo_texto, adm_id, msg_id)
                except Exception as e:
                    logging.exception("Erro ao atualizar card do admin %s: %s", adm_id, e)

    except Exception as e:
        logging.exception("Erro no callback '%s': %s", call.data, e)


# --- RECEBIMENTO DE MENSAGENS PRIVADAS ---
@bot.message_handler(
    func=lambda m: m.chat.type == "private"
    and m.content_type == "text"
    and not m.text.startswith("/")
)
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

    dados = {
        "user_id": user_id,
        "user_name": user_name,
        "user_username": user_username,
        "text": message.text,
        "admin_messages": {}
    }

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ Aprovar", callback_data=f"ap_{msg_key}"),
        InlineKeyboardButton("❌ Recusar", callback_data=f"rj_{msg_key}")
    )

    for adm in ADMIN_IDS:
        try:
            sent = bot.send_message(adm, texto_moderacao(dados), reply_markup=markup)
            dados["admin_messages"][adm] = sent.message_id
        except Exception as e:
            logging.exception("Erro ao enviar para admin %s: %s", adm, e)

    with state_lock:
        pending_messages[msg_key] = dados

    bot.send_message(user_id, "📨 Enviada para aprovação do admin.")


# --- EXECUÇÃO ---
if __name__ == "__main__":
    logging.info("Bot iniciado...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
