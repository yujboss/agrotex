import requests

TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_IDS = []


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