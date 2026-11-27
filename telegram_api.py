"""Telegram Bot API orqali kanalga yuborish."""
import logging
import re

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL
from uz_alphabet import to_new_uzbek

log = logging.getLogger("telegram")
API = "https://api.telegram.org/bot{token}/{method}"
CAPTION_LIMIT = 1024
CHANNEL_FOOTER = '📊 <b>MARKETPULSE</b> | <a href="https://t.me/MarketPulseZK">@MarketPulseZK</a>'

SOURCE_LINKS = {
    "yahoo finance": "https://finance.yahoo.com",
    "nasdaq": "https://www.nasdaq.com",
    "sec": "https://www.sec.gov/edgar/searchedgar/companysearch",
    "federal reserve": "https://www.federalreserve.gov",
    "bls": "https://www.bls.gov",
    "cnbc": "https://www.cnbc.com",
    "reuters": "https://www.reuters.com",
    "bloomberg": "https://www.bloomberg.com",
    "marketwatch": "https://www.marketwatch.com",
    "coindesk": "https://www.coindesk.com",
    "cnn": "https://edition.cnn.com/markets/fear-and-greed",
    "forexfactory": "https://www.forexfactory.com/calendar",
    "marketpulse": "https://t.me/MarketPulseZK",
}


def _ensure_source_and_footer(html_text: str) -> str:
    """Har bir post ostida giperhavolali Manba va doimiy kanal havolasi (@MarketPulseZK) bo'lishini kafolatlaydi."""
    if not html_text:
        return html_text
    text = html_text.strip()
    low = text.lower()

    # 1. Agar Manba qatori bor-u, lekin giperhavola (<a href) bo'lmasa — uni bosiladigan havolaga aylantirish
    if "manba" in low:
        def _linkify_manba(m):
            full = m.group(0)
            if "<a " in full.lower():
                return full
            inner = m.group(1).strip()
            url = "https://finance.yahoo.com"
            ilow = inner.lower()
            for key, u in SOURCE_LINKS.items():
                if key in ilow:
                    url = u
                    break
            return f'<i>Manba: <a href="{url}">{inner}</a></i>'

        text = re.sub(r"<i>\s*Manba:\s*([^<]+)</i>", _linkify_manba, text, flags=re.IGNORECASE)
    else:
        text += '\n\n<i>Manba: <a href="https://finance.yahoo.com">Yahoo Finance / MarketPulse</a></i>'

    # 2. Doimiy kanal havolasi ostida bo'lishini ta'minlash (takrorlamasdan)
    if "t.me/marketpulsezk" not in text.lower() and "@marketpulsezk" not in text.lower():
        text += f"\n\n{CHANNEL_FOOTER}"

    # 3. 100% Yangi O'zbek Alifbosi (Ö ö, Ğ ğ, Ş ş, Ç ç) va imlo nazorati
    return to_new_uzbek(text.strip())


def _api(method, **kwargs):
    r = requests.post(API.format(token=TELEGRAM_BOT_TOKEN, method=method), timeout=60, **kwargs)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram xatosi: {data.get('description')}")
    return data["result"]


def _visible_len(html_text):
    return len(re.sub(r"<[^>]+>", "", html_text))


def send_post(html_text, image_bytes=None):
    html_text = _ensure_source_and_footer(html_text)
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
    html_text = _ensure_source_and_footer(html_text)
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


def send_poll(question: str, options: list[str], is_anonymous: bool = True):
    """Telegram kanalga rasmiy interaktiv so'rovnoma (Poll) yuboradi (Yangi alifboda)."""
    import json
    q_new = to_new_uzbek(str(question))[:300]
    opts = [{"text": to_new_uzbek(str(o))[:100]} for o in options[:10]]
    return _api(
        "sendPoll",
        data={
            "chat_id": TELEGRAM_CHANNEL,
            "question": q_new,
            "options": json.dumps(opts),
            "is_anonymous": is_anonymous,
        },
    )


def check():
    """Token va kanal huquqlarini tekshiradi."""
    me = _api("getMe")
    chat = _api("getChat", data={"chat_id": TELEGRAM_CHANNEL})
    member = _api("getChatMember", data={"chat_id": TELEGRAM_CHANNEL, "user_id": me["id"]})
    can_post = member.get("status") == "creator" or member.get("can_post_messages")
    return me["username"], chat.get("title"), member.get("status"), bool(can_post)
