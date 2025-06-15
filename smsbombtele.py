from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")

BASE_TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

PRICES = {
    "1": {"amount_usd": 5, "desc": "20 minutes of spam calls and texts", "duration": 20},
    "2": {"amount_usd": 15, "desc": "1 hour of spam calls and texts", "duration": 60},
    "3": {"amount_usd": 30, "desc": "2 hours of spam calls and texts", "duration": 120},
    "4": {"amount_usd": 50, "desc": "6 hours of spam calls and texts", "duration": 360},
    "5": {"amount_usd": 100, "desc": "1 whole day of spam calls and texts", "duration": 1440},
    "6": {"amount_usd": 300, "desc": "Full lifetime access", "duration": None},  # lifetime
}

LIFETIME_ID = "18KBrM0PE7hLjZ"

# In-memory user state store (for demo only!)
user_states = {}

def send_message(chat_id, text):
    url = f"{BASE_TELEGRAM_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)


def create_nowpayments_invoice(amount_usd, chat_id, option):
    url = "https://api.nowpayments.io/v1/invoice"
    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "price_amount": amount_usd,
        "price_currency": "usd",
        "pay_currency": "btc",
        "order_id": f"smsbomb-{chat_id}-{option}",
        "order_description": f"SMSBomb by SKYY - Option {option}",
        "ipn_callback_url": f"{WEBHOOK_HOST}/nowpayments"
    }
    response = requests.post(url, json=data, headers=headers)
    if response.status_code in [200, 201]:
        return response.json()
    else:
        print(f"Error creating invoice: {response.status_code} {response.text}")
        return None


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()

    if not data or 'message' not in data:
        return jsonify({"status": "ignored"})

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    # Handle /start
    if text == "/start":
        user_states[chat_id] = {'step': 'awaiting_option'}
        msg = (
            "👋 *Welcome to SMSBomb by SKYY!* 👋\n\n"
            "Choose a package by sending the number below:\n"
        )
        for k, v in PRICES.items():
            price = v["amount_usd"]
            desc = v["desc"]
            msg += f"• *{k}*: ${price} BTC — {desc}\n"
        msg += (
            "\nOr send your *Lifetime ID* if you already have one.\n\n"
            "Use /stop anytime to cancel an active job."
        )
        send_message(chat_id, msg)
        return jsonify({"status": "ok"})

    # Handle /stop command
    if text == "/stop":
        state = user_states.get(chat_id)
        if state and state.get('step') == 'done':
            send_message(chat_id, "ℹ️ You have no active bombing jobs right now.")
        elif state and state.get('step') in ['awaiting_phone', 'bombing']:
            user_states[chat_id]['step'] = 'done'
            send_message(chat_id, "🛑 Your SMS bombing job has been stopped. No more messages will be sent. Use /start to begin again.")
        else:
            send_message(chat_id, "ℹ️ No bombing job to stop. Use /start to begin.")
        return jsonify({"status": "ok"})

    # Check if user sent lifetime ID
    if text == LIFETIME_ID:
        user_states[chat_id] = {'step': 'awaiting_phone', 'duration': None, 'lifetime_id': LIFETIME_ID}
        send_message(chat_id, "✅ *Lifetime access recognized!* Send the phone number to start the prank.")
        return jsonify({"status": "ok"})

    state = user_states.get(chat_id)

    if not state:
        send_message(chat_id, "Please start by typing /start")
        return jsonify({"status": "ok"})

    # Awaiting option (1-6)
    if state['step'] == 'awaiting_option':
        if text not in PRICES:
            send_message(chat_id, "❌ Invalid option. Please send a number between 1 and 6.")
            return jsonify({"status": "ok"})
        option = text
        price_data = PRICES[option]
        invoice = create_nowpayments_invoice(price_data["amount_usd"], chat_id, option)
        if not invoice:
            send_message(chat_id, "⚠️ Failed to create payment invoice. Please try again later.")
            return jsonify({"status": "ok"})
        user_states[chat_id].update({
            'step': 'awaiting_payment',
            'invoice_id': invoice['id'],
            'duration': price_data["duration"],
            'option': option
        })
        pay_url = invoice["invoice_url"]
        send_message(chat_id,
                     f"💰 Please pay *${price_data['amount_usd']} BTC* using the link below:\n"
                     f"{pay_url}\n\n"
                     "Once your payment is confirmed, you'll be prompted to send the phone number.")
        return jsonify({"status": "ok"})

    # Awaiting phone number (after payment)
    if state['step'] == 'awaiting_phone':
        phone = text
        if len(phone) < 6 or not any(c.isdigit() for c in phone):
            send_message(chat_id, "❌ Please send a valid phone number.")
            return jsonify({"status": "ok"})
        user_states[chat_id].update({
            'step': 'bombing',
            'phone': phone
        })
        dur_text = "lifetime" if state.get('lifetime_id') else f"{state.get('duration')} minutes"
        send_message(chat_id,
                     f"✅ SMS Bombing started on *{phone}* | Job ending in *{dur_text}*.\n\n"
                     "Use /stop to cancel this job anytime.")
        return jsonify({"status": "ok"})

    # Awaiting payment confirmation
    if state['step'] == 'awaiting_payment':
        send_message(chat_id, "⏳ Waiting for payment confirmation. Please pay using the invoice link sent earlier.")
        return jsonify({"status": "ok"})

    # Bombing active or done states
    if state['step'] in ['bombing', 'done']:
        send_message(chat_id, "ℹ️ Use /stop to cancel your bombing job or /start to create a new one.")
        return jsonify({"status": "ok"})

    return jsonify({"status": "ok"})


@app.route("/nowpayments", methods=["POST"])
def nowpayments_ipn():
    data = request.get_json()
    payment_status = data.get("payment_status")
    invoice_id = data.get("invoice_id")
    order_id = data.get("order_id")

    if not order_id or not order_id.startswith("smsbomb-"):
        return jsonify({"status": "ignored"})

    try:
        chat_id = int(order_id.split("-")[1])
    except ValueError:
        return jsonify({"status": "ignored"})

    if payment_status == "finished":
        user_state = user_states.get(chat_id)
        if user_state and user_state.get('invoice_id') == invoice_id:
            user_states[chat_id]['step'] = 'awaiting_phone'
            send_message(chat_id, "✅ Payment received! Now, please send the phone number to start the prank.")

            # If lifetime option, send lifetime ID
            if user_state.get('option') == '6':
                send_message(chat_id,
                             f"🎉 Congrats! You purchased *Lifetime Access*.\n"
                             f"Your Lifetime ID is: `{LIFETIME_ID}`\n"
                             "Save this ID — you can use it to start bombing without paying again.")
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
