"""Post uchun surat: rasmiy manba surati yoki MARKETPULSE brend kartasi."""
import io
import logging
import os
from datetime import datetime
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFont

from config import ASSETS_DIR, TASHKENT, USER_AGENT
from sources import ALLOWED_IMAGE_DOMAINS

log = logging.getLogger("images")

W, H = 1280, 720
NAVY_TOP, NAVY_BOTTOM = (6, 16, 38), (10, 34, 74)
CYAN, BLUE, WHITE, GREY = (0, 212, 255), (40, 120, 255), (245, 248, 255), (150, 170, 200)

CATEGORY_LABELS = {
    "MARKETS": "📈 GLOBAL MARKETS",
    "MACRO": "MAKROIQTISODIYOT",
    "FED": "FED & FOIZ STAVKALARI",
    "BONDS": "TREASURY & OBLIGATSIYALAR",
    "FOREX": "FOREX & DOLLAR",
    "COMMODITIES": "XOMASHYO",
    "GEOPOLITICS": "GEOSIYOSAT",
    "CRYPTO": "KRIPTO",
    "COMPANY": "KOMPANIYALAR",
    "TECH": "TEXNOLOGIYA & AI",
}

FONT_CANDIDATES_BOLD = [
    ASSETS_DIR / "font-bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT_CANDIDATES = [
    ASSETS_DIR / "font.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size, bold=False):
    for path in FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def brand_card(title, points=None, category="MARKETS"):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):  # vertikal gradient
        t = y / H
        d.line(
            [(0, y), (W, y)],
            fill=tuple(int(NAVY_TOP[i] + (NAVY_BOTTOM[i] - NAVY_TOP[i]) * t) for i in range(3)),
        )
    # dekorativ grid va grafik chizig'i
    for x in range(0, W, 80):
        d.line([(x, 0), (x, H)], fill=(20, 40, 80), width=1)
    for y in range(0, H, 80):
        d.line([(0, y), (W, y)], fill=(20, 40, 80), width=1)
    pts = [(0, 600), (160, 560), (300, 590), (450, 500), (600, 530), (760, 430), (900, 470), (1060, 360), (1280, 390)]
    d.line(pts, fill=(0, 110, 160), width=4)

    # Yuqori chap: kategoriya
    label = CATEGORY_LABELS.get(category, "GLOBAL MARKETS").replace("📈 ", "")
    f_label = _font(28, bold=True)
    d.rounded_rectangle([60, 50, 60 + d.textlength(label, font=f_label) + 40, 100], radius=10, fill=CYAN)
    d.text((80, 56), label, font=f_label, fill=NAVY_TOP)

    # Sarlavha
    f_title = _font(68, bold=True)
    lines = _wrap(d, title.upper(), f_title, W - 120)
    if len(lines) > 3:
        f_title = _font(54, bold=True)
        lines = _wrap(d, title.upper(), f_title, W - 120)[:4]
    y = 150
    for line in lines:
        d.text((60, y), line, font=f_title, fill=WHITE)
        y += f_title.size + 14

    # Raqamli faktlar
    f_pt = _font(38, bold=True)
    y += 20
    for p in (points or [])[:3]:
        d.rectangle([60, y + 8, 68, y + 40], fill=CYAN)
        d.text((88, y), p, font=f_pt, fill=CYAN)
        y += 58

    # Pastki qism: brend va sana
    d.line([(60, H - 90), (W - 60, H - 90)], fill=BLUE, width=2)
    d.text((60, H - 72), "MARKETPULSE", font=_font(40, bold=True), fill=WHITE)
    date = datetime.now(TASHKENT).strftime("%d.%m.%Y • %H:%M (Toshkent)")
    f_date = _font(26)
    d.text((W - 60 - d.textlength(date, font=f_date), H - 62), date, font=f_date, fill=GREY)
    d.text((W - 60 - d.textlength("t.me/MarketPulseZK", font=f_date), 62), "t.me/MarketPulseZK", font=f_date, fill=GREY)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _allowed(url):
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in ALLOWED_IMAGE_DOMAINS)


def official_image(article):
    """Faqat rasmiy / ruxsat etilgan domendagi suratni yuklaydi."""
    img_url = article.get("image")
    if not img_url or not (_allowed(article.get("url", "")) or _allowed(img_url)):
        return None
    try:
        r = requests.get(img_url, headers={"User-Agent": USER_AGENT}, timeout=20)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content))
        if im.width < 500:  # kichik logotiplarni o'tkazib yuboramiz
            return None
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG", quality=90)
        return buf.getvalue()
    except Exception as e:  # noqa: BLE001
        log.info("Rasmiy surat yuklanmadi: %s", e)
        return None


def pick_image(article, post):
    return official_image(article) or brand_card(
        post.get("card_title") or "Bozor yangiligi",
        [p for p in post.get("card_points", []) if p][:3],
        post.get("category", "MARKETS"),
    )
