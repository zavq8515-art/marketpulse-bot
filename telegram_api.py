"""Telegram Bot API orqali kanalga yuborish."""
import logging
import re

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL

log = logging.getLogger("telegram")
API = "https://api.telegram.org/bot{token}/{method}"
CAPTION_LIMIT = 1024


def _api(method, **kwargs):
    r = requests.post(API.format(token=TELEGRAM_BOT_TOKEN, method=method), timeout=60, **kwargs)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram xatosi: {data.get('description')}")
    return data["result"]


def _visible_len(html_text):
    return len(re.sub(r"<[^>]+>", "", html_text))


def send_post(html_text, image_bytes=None):
    if image_bytes and _visible_len(html_text) <= CAPTION_LIMIT:
        return _api(
            "sendPhoto",
            data={"chat_id": TELEGRAM_CHANNEL, "caption": html_text, "parse_mode": "HTML"},
            files={"photo": ("marketpulse.jpg", image_bytes, "image/jpeg")},
        )
    if image_bytes:
        _api(
            "sendPhoto",
            data={"chat_id": TELEGRAM_CHANNEL},
            files={"photo": ("marketpulse.jpg", image_bytes, "image/jpeg")},
        )
    return _api(
        "sendMessage",
        data={
            "chat_id": TELEGRAM_CHANNEL,
            "text": html_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )


def send_media_group(html_text, images_list):
    """Bir nechta suratni (kompaniya binosi, mahsuloti, grafik va h.k.) bitta albom qilib yuboradi."""
    if not images_list:
        return send_post(html_text)
    if len(images_list) == 1:
        return send_post(html_text, images_list[0])

    import json
    media = []
    files = {}
    for idx, img_bytes in enumerate(images_list[:4]):  # 2-4 ta surat optimal
        attach_name = f"photo_{idx}"
        item = {"type": "photo", "media": f"attach://{attach_name}"}
        if idx == 0:
            # Albomning birinchi suratiga sarlavha va matn biriktiriladi
            if _visible_len(html_text) <= CAPTION_LIMIT:
                item["caption"] = html_text
                item["parse_mode"] = "HTML"
        media.append(item)
        files[attach_name] = (f"{attach_name}.jpg", img_bytes, "image/jpeg")

    res = _api(
        "sendMediaGroup",
        data={"chat_id": TELEGRAM_CHANNEL, "media": json.dumps(media)},
        files=files,
    )
    # Agar matn 1024 belgidan oshib birinchi suratga sig'magan bo'lsa, alohida xabar qilib jo'natiladi
    if _visible_len(html_text) > CAPTION_LIMIT:
        send_post(html_text)
    return res


def check():
    """Token va kanal huquqlarini tekshiradi."""
    me = _api("getMe")
    chat = _api("getChat", data={"chat_id": TELEGRAM_CHANNEL})
    member = _api("getChatMember", data={"chat_id": TELEGRAM_CHANNEL, "user_id": me["id"]})
    can_post = member.get("status") == "creator" or member.get("can_post_messages")
    return me["username"], chat.get("title"), member.get("status"), bool(can_post)
