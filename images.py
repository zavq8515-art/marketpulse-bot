"""Post uchun surat: haqiqiy foto (maqola/Wikipedia/Wikimedia) + MARKETPULSE watermark."""
import io
import logging
import os
from datetime import datetime

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from config import ASSETS_DIR, TASHKENT, USER_AGENT

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

CATEGORY_DEFAULT_QUERIES = {
    "MARKETS": "New York Stock Exchange trading floor",
    "MACRO": "United States Capitol Washington",
    "FED": "Federal Reserve Eccles Building",
    "BONDS": "United States Department of the Treasury",
    "FOREX": "United States one hundred-dollar bill",
    "COMMODITIES": "Oil platform sea",
    "GEOPOLITICS": "Container ship cargo port",
    "CRYPTO": "Data center server room",
    "COMPANY": "Wall Street Manhattan",
    "TECH": "Data center servers",
}

BAD_IMAGE_PATTERNS = (
    "googleusercontent.com",
    "gstatic.com",
    "favicon",
    "logo",
    "avatar",
    "sprite",
    "default",
    "placeholder",
    "1x1",
    "pixel",
    "marketwatch-logo",
    "cnbc-logo",
    "yahoo_finance",
)

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


def _watermark_photo(im: Image.Image) -> bytes:
    """Haqiqiy suratni 1280x720 o'lchamga keltirib, MARKETPULSE burchak yozuvini qo'shadi."""
    im = im.convert("RGB")
    centering = (0.5, 0.22) if im.height > im.width * 0.85 else (0.5, 0.5)
    im = ImageOps.fit(im, (W, H), method=Image.Resampling.LANCZOS, centering=centering).convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    f_brand = _font(28, bold=True)
    f_sub = _font(19, bold=False)
    brand_txt = "MARKETPULSE"
    sub_txt = "t.me/MarketPulseZK"

    bw = max(d.textlength(brand_txt, font=f_brand), d.textlength(sub_txt, font=f_sub)) + 54
    bh = 68
    bx, by = W - bw - 28, H - bh - 24

    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=12, fill=(6, 16, 38, 215))
    d.rounded_rectangle([bx + 12, by + 12, bx + 18, by + bh - 12], radius=3, fill=(0, 212, 255, 255))
    d.text((bx + 30, by + 9), brand_txt, font=f_brand, fill=(255, 255, 255, 255))
    d.text((bx + 30, by + 40), sub_txt, font=f_sub, fill=(0, 212, 255, 240))

    out = Image.alpha_composite(im, overlay).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


WIKI_HEADERS = {"User-Agent": "MarketPulseBot/1.0 (https://t.me/MarketPulseZK; marketpulse@bot.local)"}


def _download_valid_photo(url: str):
    if not url or any(p in url.lower() for p in BAD_IMAGE_PATTERNS):
        return None
    if url.lower().split("?")[0].endswith((".svg", ".gif")):
        return None
    try:
        headers = WIKI_HEADERS if "wikimedia.org" in url or "wikipedia.org" in url else {"User-Agent": USER_AGENT}
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content))
        if im.width < 450 or im.height < 250:
            return None
        return _watermark_photo(im)
    except Exception as e:  # noqa: BLE001
        log.debug("Surat yuklanmadi (%s): %s", url, e)
        return None


def _wiki_photo_url(query: str):
    if not query:
        return None
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": 5,
                "prop": "pageimages",
                "piprop": "original",
                "format": "json",
            },
            headers=WIKI_HEADERS,
            timeout=10,
        ).json()
        pages = sorted(r.get("query", {}).get("pages", {}).values(), key=lambda x: x.get("index", 99))
        for p in pages:
            orig = p.get("original", {})
            src = orig.get("source", "")
            w, h = orig.get("width", 0), orig.get("height", 0)
            if (
                src
                and w >= 500
                and h >= 300
                and not src.lower().endswith((".svg", ".gif"))
                and "logo" not in src.lower()
            ):
                return src
    except Exception:  # noqa: BLE001
        pass

    try:
        r = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": f"filetype:bitmap {query}",
                "gsrnamespace": 6,
                "gsrlimit": 6,
                "prop": "imageinfo",
                "iiprop": "url|dimensions",
                "format": "json",
            },
            headers=WIKI_HEADERS,
            timeout=10,
        ).json()
        pages = sorted(r.get("query", {}).get("pages", {}).values(), key=lambda x: x.get("index", 99))
        for landscape_only in (True, False):
            for p in pages:
                ii = (p.get("imageinfo") or [{}])[0]
                src = ii.get("url", "")
                w, h = ii.get("width", 0), ii.get("height", 0)
                if landscape_only and w < h:
                    continue
                if (
                    src
                    and w >= 600
                    and h >= 350
                    and not src.lower().endswith((".svg", ".gif"))
                    and "logo" not in src.lower()
                ):
                    return src
    except Exception:  # noqa: BLE001
        pass
    return None


def brand_card(title, points=None, category="MARKETS"):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line(
            [(0, y), (W, y)],
            fill=tuple(int(NAVY_TOP[i] + (NAVY_BOTTOM[i] - NAVY_TOP[i]) * t) for i in range(3)),
        )
    for x in range(0, W, 80):
        d.line([(x, 0), (x, H)], fill=(20, 40, 80), width=1)
    for y in range(0, H, 80):
        d.line([(0, y), (W, y)], fill=(20, 40, 80), width=1)
    pts = [(0, 600), (160, 560), (300, 590), (450, 500), (600, 530), (760, 430), (900, 470), (1060, 360), (1280, 390)]
    d.line(pts, fill=(0, 110, 160), width=4)

    label = CATEGORY_LABELS.get(category, "GLOBAL MARKETS").replace("📈 ", "")
    f_label = _font(28, bold=True)
    d.rounded_rectangle([60, 50, 60 + d.textlength(label, font=f_label) + 40, 100], radius=10, fill=CYAN)
    d.text((80, 56), label, font=f_label, fill=NAVY_TOP)

    f_title = _font(68, bold=True)
    lines = _wrap(d, title.upper(), f_title, W - 120)
    if len(lines) > 3:
        f_title = _font(54, bold=True)
        lines = _wrap(d, title.upper(), f_title, W - 120)[:4]
    y = 150
    for line in lines:
        d.text((60, y), line, font=f_title, fill=WHITE)
        y += f_title.size + 14

    f_pt = _font(38, bold=True)
    y += 20
    for p in (points or [])[:3]:
        d.rectangle([60, y + 8, 68, y + 40], fill=CYAN)
        d.text((88, y), p, font=f_pt, fill=CYAN)
        y += 58

    d.line([(60, H - 90), (W - 60, H - 90)], fill=BLUE, width=2)
    d.text((60, H - 72), "MARKETPULSE", font=_font(40, bold=True), fill=WHITE)
    date = datetime.now(TASHKENT).strftime("%d.%m.%Y • %H:%M (Toshkent)")
    f_date = _font(26)
    d.text((W - 60 - d.textlength(date, font=f_date), H - 62), date, font=f_date, fill=GREY)
    d.text((W - 60 - d.textlength("t.me/MarketPulseZK", font=f_date), 62), "t.me/MarketPulseZK", font=f_date, fill=GREY)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def pick_image(article, post):
    """1) Maqolaning haqiqiy fotosi, 2) Kompaniya/mavzu bo'yicha Wikipedia fotosi, 3) Kategoriya fotosi."""
    # 1. Maqolaning o'zidagi haqiqiy foto (CNBC, AP, Reuters, CoinDesk va h.k.)
    img = _download_valid_photo(article.get("image"))
    if img:
        return img

    # 2. AI aniqlagan kompaniya / shaxs / birja bo'yicha haqiqiy foto
    query = post.get("photo_query")
    if query:
        img = _download_valid_photo(_wiki_photo_url(query))
        if img:
            return img

    # 3. Kategoriya bo'yicha mavzuga mos haqiqiy foto (NYSE, Data Center, Fed binosi va h.k.)
    cat = post.get("category", "MARKETS")
    fallback_q = CATEGORY_DEFAULT_QUERIES.get(cat, "New York Stock Exchange trading floor")
    img = _download_valid_photo(_wiki_photo_url(fallback_q))
    if img:
        return img

    # 4. Eng oxirgi chora
    return brand_card(
        post.get("card_title") or "Bozor yangiligi",
        [p for p in post.get("card_points", []) if p][:3],
        cat,
    )


GOLD = (255, 195, 0)
GOLD_TEXT = (255, 215, 80)


def academy_card(lesson_id: int, title: str, module_name: str = "", points: list = None):
    """Akademiya darslari uchun maxsus brend karta (gold/navy/cyan dizayn)."""
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line(
            [(0, y), (W, y)],
            fill=tuple(int(NAVY_TOP[i] + (NAVY_BOTTOM[i] - NAVY_TOP[i]) * t) for i in range(3)),
        )
    for x in range(0, W, 80):
        d.line([(x, 0), (x, H)], fill=(16, 36, 75), width=1)
    for y in range(0, H, 80):
        d.line([(0, y), (W, y)], fill=(16, 36, 75), width=1)

    # Yuqori oltin chiziq
    d.rectangle([0, 0, W, 6], fill=GOLD)

    # Akademiya badge
    badge_txt = f"🎓 AKADEMIYA | DARS #{lesson_id}"
    f_badge = _font(26, bold=True)
    bw = d.textlength(badge_txt, font=f_badge) + 36
    d.rounded_rectangle([60, 42, 60 + bw, 88], radius=8, fill=GOLD)
    d.text((78, 50), badge_txt, font=f_badge, fill=NAVY_TOP)

    # Modul nomi
    if module_name:
        f_mod = _font(20, bold=False)
        short_mod = module_name.split(":")[0].strip() if ":" in module_name else module_name[:24]
        mw = d.textlength(short_mod, font=f_mod) + 28
        d.rounded_rectangle([60 + bw + 14, 44, 60 + bw + 14 + mw, 86], radius=8, outline=CYAN, width=2, fill=(10, 30, 65))
        d.text((60 + bw + 28, 53), short_mod, font=f_mod, fill=CYAN)

    # Dars sarlavhasi
    f_title = _font(54, bold=True)
    lines = _wrap(d, title, f_title, W - 120)
    if len(lines) > 2:
        f_title = _font(44, bold=True)
        lines = _wrap(d, title, f_title, W - 120)[:3]
    y = 125
    for line in lines:
        d.text((60, y), line, font=f_title, fill=WHITE)
        y += f_title.size + 14

    # Asosiy nuqtalar / terminlar
    f_pt = _font(30, bold=False)
    y += 15
    for p in (points or [])[:3]:
        d.rounded_rectangle([60, y + 6, 68, y + 36], radius=3, fill=GOLD)
        d.text((86, y), str(p), font=f_pt, fill=(230, 240, 255))
        y += 48

    # Pastki brend chiziq
    d.line([(60, H - 85), (W - 60, H - 85)], fill=(30, 60, 110), width=2)
    f_brand = _font(34, bold=True)
    d.text((60, H - 68), "MARKETPULSE", font=f_brand, fill=WHITE)
    f_sub = _font(22, bold=False)
    d.text((60 + d.textlength("MARKETPULSE", font=f_brand) + 16, H - 60), "• 100 Qadamda Investitsiya va Treyderlik", font=f_sub, fill=GOLD_TEXT)

    channel_txt = "t.me/MarketPulseZK"
    f_chan = _font(24, bold=True)
    d.text((W - 60 - d.textlength(channel_txt, font=f_chan), H - 62), channel_txt, font=f_chan, fill=CYAN)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def pick_academy_image(lesson_id: int, lesson_data: dict, post: dict):
    """Akademiya darsi uchun: haqiqiy mavzuli foto yoki maxsus akademiya kartasi."""
    query = post.get("photo_query") or lesson_data.get("photo_query")
    if query:
        url = _wiki_photo_url(query)
        if url:
            img = _download_valid_photo(url)
            if img:
                return img
    # Agar foto topilmasa, oltin ramkali maxsus akademiya kartasini yaratadi
    points = post.get("card_points") or [t[0] for t in lesson_data.get("terms", [])[:3]]
    return academy_card(
        lesson_id=lesson_id,
        title=lesson_data.get("title", ""),
        module_name=lesson_data.get("module", ""),
        points=points,
    )

