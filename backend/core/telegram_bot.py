import requests

TELEGRAM_TOKEN = "8606896392:AAGywL-z1jcmkvwOyBZLzI0mshPr_5HG4H8"
TELEGRAM_CHAT_IDS = [
    "738678945",
    "140467689"
]


def send_telegram_message(text):

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        for chat_id in TELEGRAM_CHAT_IDS:

            requests.post(url, json={
                "chat_id": chat_id,
                "text": text
            })
    except Exception as e:
        print("Telegram error:", e)