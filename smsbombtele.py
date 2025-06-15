from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import requests
import os

# ✅ Replace this with your new, secure Telegram Bot Token
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # Set in environment or replace with string
NOWPAYMENTS_API_KEY = os.environ.get("NOWPAYMENTS_API_KEY")  # Also store securely
BTC_RECEIVE_ADDRESS = "bc1qqca63az6zht7ttp09089wj0h8k6um7a65a9sh6"
WEBHOOK_HOST = "https://yourdomain.com"  # <- Replace with your actual public URL

# Prank Plan Prices
PRICING = {
    "1": {"price": 5, "minutes": 20},
    "2": {"price": 15, "minutes": 60},
    "3": {"price": 30, "minutes": 120},
    "4": {"price": 50, "minutes": 360},
    "5": {"price": 100, "minutes": 1440},
    "6": {"price": 300, "lifetime": True}
}

user_state = {}  # Temporary in-memory storage

# Set up Flask
app = Flask(__name__)
application = Application.builder().token(TOKEN).build()

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("1: $5 (20 mins)", callback_data="1")],
        [InlineKeyboardButton("2: $15 (1 hour)", callback_data="2")],
        [InlineKeyboardButton("3: $30 (2 hours)", callback_data="3")],
        [InlineKeyboardButton("4: $50 (6 hours)", callback_data="4")],
        [InlineKeyboardButton("5: $100 (1 day)", callback_data="5")],
        [InlineKeyboardButton("6: $300 (Lifetime)", callback_data="6")],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("💣 *SMSBomb by SKYY*\nChoose a plan:", parse_mode="Markdown", reply_markup=markup)

# Plan selection
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    choice = query.data
    plan = PRICING.get(choice)

    if not plan:
        await query.edit_message_text("Invalid option.")
        return

    amount = plan["price"]
    order_id = f"user_{user_id}_plan_{choice}"

    payload = {
        "price_amount": amount,
        "price_currency": "usd",
        "pay_currency": "btc",
        "order_id": order_id,
        "ipn_callback_url": f"{WEBHOOK_HOST}/nowpayments",
        "payout_address": BTC_RECEIVE_ADDRESS,
        "payout_currency": "btc"
    }

    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post("https://api.nowpayments.io/v1/invoice", json=payload, headers=headers)
    data = response.json()

    if "invoice_url" not in data:
        await query.edit_message_text("❌ Error creating invoice.")
        return

    user_state[user_id] = {
        "paid": False,
        "plan": choice,
        "invoice_id": data["invoice_id"],
        "order_id": order_id
    }

    await query.edit_message_text(
        f"🔗 [Click here to pay ${amount} in BTC]({data['invoice_url']})\n\nAfter paying, come back and send the target phone number.",
        parse_mode="Markdown",
        disable_web_page_preview=False
    )

# Handle messages (Lifetime ID or phone #)
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "18KBrM0PE7hLjZ":
        user_state[user_id] = {"paid": True, "lifetime": True}
        await update.message.reply_text("✅ Lifetime ID verified. Send a phone number.")
        return

    if user_state.get(user_id, {}).get("paid"):
        plan = user_state[user_id]
        minutes = PRICING.get(plan.get("plan"), {}).get("minutes", "∞")
        if plan.get("lifetime"):
            minutes = "∞"
        await update.message.reply_text(f"✅ SMS Bombing started on {text} 📱\n⏳ Job ending in {minutes} minutes")
    else:
        await update.message.reply_text("❗ You must pay first. Use /start to pick a plan.")

# Webhook from NOWPayments
@app.route("/nowpayments", methods=["POST"])
def nowpayments_webhook():
    data = request.json
    order_id = data.get("order_id")
    payment_status = data.get("payment_status")

    if payment_status == "finished" and order_id:
        try:
            user_id = int(order_id.split("_")[1])
            if user_id in user_state:
                user_state[user_id]["paid"] = True
                application.bot.send_message(
                    chat_id=user_id,
                    text="✅ Payment confirmed! Send the phone number to prank."
                )
        except Exception as e:
            print(f"Webhook error: {e}")
    return "OK"

# Telegram webhook handler
@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "ok"

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

# Run app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=f"{WEBHOOK_HOST}/webhook"
    )
