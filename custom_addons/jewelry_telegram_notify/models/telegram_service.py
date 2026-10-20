import json
import logging
import urllib.error
import urllib.parse
import urllib.request

_logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(token, chat_id, text):
    """Send a Telegram message. Returns True on success, False on failure."""
    if not token or not chat_id:
        return False
    url = TELEGRAM_API_URL.format(token=token)
    payload = json.dumps({
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        _logger.warning("Telegram send failed (HTTP %s) for chat_id=%s: %s", e.code, chat_id, e.read())
    except Exception as e:
        _logger.warning("Telegram send failed for chat_id=%s: %s", chat_id, e)
    return False


def test_connection(token, chat_id):
    """Send a test message. Returns (success, error_message)."""
    if not token:
        return False, "Bot token is not configured."
    if not chat_id:
        return False, "No Telegram Chat ID set on your user profile."
    ok = send_message(token, chat_id, "✅ Telegram notifications are working!")
    if ok:
        return True, None
    return False, "Failed to send message. Check the token and Chat ID."
