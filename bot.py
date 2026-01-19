import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "7761415730:AAGZD1QDlwiNVLaoKZZEcar18b0HZhNPWhs"
bot = telebot.TeleBot(TOKEN)

# Lista de IDs dos administradores
ADMIN_IDS = [8154662660, 6439529867]

# ID do canal onde as mensagens serão enviadas
CHANNEL_ID = -1003175055759  # seu canal configurado

# Armazena mensagens pendentes para aprovação
pending_messages = {}

# Estado do bot: ativo ou inativo
bot_active = False

# Usuários que receberam aviso de espera
waiting_users = set()

# Comando /start para administradores
@bot.message_handler(commands=['start'])
def admin_start(message):
    if message.from_user.id in ADMIN_IDS:
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Sim", callback_data="start_confirm"),
            InlineKeyboardButton("❌ Cancelar", callback_data="start_cancel")
        )
        bot.send_message(message.chat.id, "Você deseja iniciar o correio anônimo?", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "Este comando só pode ser usado por administradores.")

# Comando /end para administradores
@bot.message_handler(commands=['end'])
def admin_end(message):
    global bot_active
    if message.from_user.id in ADMIN_IDS:
        bot_active = False
        bot.send_message(message.chat.id, "❌ Correio anônimo encerrado.")
    else:
        bot.send_message(message.chat.id, "Este comando só pode ser usado por administradores.")

# Confirmação de início via botão
@bot.callback_query_handler(func=lambda call: call.data in ["start_confirm", "start_cancel"])
def handle_start_buttons(call):
    global bot_active
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "Apenas administradores podem iniciar o bot.")
        return

    if call.data == "start_confirm":
        bot_active = True
        bot.send_message(call.message.chat.id, "✅ Correio anônimo iniciado.")
        for user_id in waiting_users:
            bot.send_message(user_id, "Prontinho, podemos começar a enviar.")
        waiting_users.clear()
        bot.answer_callback_query(call.id, "Bot iniciado.")
    elif call.data == "start_cancel":
        bot.send_message(call.message.chat.id, "Início cancelado.")
        bot.answer_callback_query(call.id, "Cancelado.")

# Recebe mensagens privadas
@bot.message_handler(func=lambda message: message.chat.type == "private" and not message.text.startswith('/') and message.content_type == "text")
def receive_message(message):
    global bot_active
    user_id = message.chat.id
    msg_id = message.message_id
    user_name = message.from_user.first_name

    if not bot_active:
        bot.send_message(user_id, "Aguardando boot inicial pelo administrador.")
        waiting_users.add(user_id)
        return

    pending_messages[msg_id] = {"user_id": user_id, "user_name": user_name, "text": message.text}
    bot.send_message(user_id, f"Sua mensagem:\n\n🔹 {message.text}\n\nAguardando aprovação do admin.")

    # Botões de aprovação
    markup = InlineKeyboardMarkup()
    approve_button = InlineKeyboardButton("✅ Aprovar", callback_data=f"approve_{msg_id}")
    reject_button = InlineKeyboardButton("❌ Recusar", callback_data=f"reject_{msg_id}")
    markup.add(approve_button, reject_button)

    for admin_id in ADMIN_IDS:
        bot.send_message(admin_id, f"Nova mensagem anônima recebida:\n\n🔹 {message.text}\n👤 Remetente: {user_name} (ID: {user_id})\n\nEssa informação só será visível para os administradores.", reply_markup=markup)
        bot.forward_message(admin_id, user_id, msg_id)

# Aprovação da mensagem
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def approve_message(call):
    msg_id = int(call.data.split("_")[1])
    if msg_id in pending_messages:
        bot.send_message(CHANNEL_ID, f"🔹 Mensagem anônima:\n{pending_messages[msg_id]['text']}")
        bot.send_message(pending_messages[msg_id]["user_id"], "✅ Sua mensagem foi aprovada e enviada ao canal!")
        del pending_messages[msg_id]
        bot.answer_callback_query(call.id, "Mensagem aprovada e enviada ao canal.")
    else:
        bot.answer_callback_query(call.id, "Mensagem não encontrada ou já processada.")

# Rejeição da mensagem
@bot.callback_query_handler(func=lambda call: call.data.startswith("reject_"))
def reject_message(call):
    msg_id = int(call.data.split("_")[1])
    if msg_id in pending_messages:
        bot.send_message(pending_messages[msg_id]["user_id"], "❌ Sua mensagem foi recusada pelo administrador.")
        del pending_messages[msg_id]
        bot.answer_callback_query(call.id, "Mensagem recusada.")
    else:
        bot.answer_callback_query(call.id, "Mensagem não encontrada ou já processada.")

bot.polling(none_stop=True)
