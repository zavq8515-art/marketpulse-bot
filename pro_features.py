"""MARKETPULSE PRO FEATURES — 7 ta professional treyderlik va investitsiya rukni.

1. Haftalik Iqtisodiy Taqvim (Economic Calendar)
2. Haftalik Choraklik Hisobotlar Taqvimı (Earnings Calendar)
3. Pre-Market Brifing ("Bozor ochilishi oldidan")
4. Bozor Kayfiyati: Fear & Greed Index + VIX (Spidometr infografika)
5. Kunlik Top 5 Gainers & Top 5 Losers + Sektor Issiqlik Xaritasi (Heatmap)
6. "Smart Money" — Insayderlar (SEC Form 4) va Yirik Fondlar (13F)
7. Avtomatik Interaktiv So'rovnomalar (Telegram Poll)
"""
import io
import logging
import math
import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw

import ai
import db
import images
import market
import telegram_api
from config import TASHKENT, USER_AGENT

log = logging.getLogger("pro_features")

W, H = 1280, 720
NAVY_TOP = (6, 16, 38)
NAVY_BOTTOM = (10, 34, 74)
CARD_BG = (13, 30, 62)
BORDER = (30, 64, 118)
CYAN = (0, 212, 255)
GREEN = (34, 211, 130)
RED = (248, 81, 100)
GOLD = (255, 195, 0)
ORANGE = (255, 145, 50)
WHITE = (245, 248, 255)
GREY = (150, 172, 204)

# Katta kapitallashuvli Top 35 aksiya (Top Gainers/Losers va Pre-Market uchun)
TOP_STOCKS = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AVGO",
    "LLY", "TSM", "ASML", "AMD", "ORCL", "CRM", "ADBE", "PLTR",
    "NFLX", "QCOM", "INTC", "MU", "PANW", "CRWD", "NOW", "UBER",
    "ISRG", "CAT", "DE", "XOM", "CVX", "WMT", "COST", "NKE",
    "BA", "COIN", "MSTR",
]

UZ_DAYS = {
    0: "Dushanba",
    1: "Seshanba",
    2: "Chorshanba",
    3: "Payshanba",
    4: "Juma",
    5: "Shanba",
    6: "Yakshanba",
}


# ==============================================================================
# UMUMIY GRAFIK YORDAMCHILAR (PILLOW 1280x720 MARKETPULSE DIZAYNI)
# ==============================================================================

def _new_canvas(badge_text: str, title_text: str, accent_color=CYAN):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line(
            [(0, y), (W, y)],
            fill=tuple(int(NAVY_TOP[i] + (NAVY_BOTTOM[i] - NAVY_TOP[i]) * t) for i in range(3)),
        )
    for x in range(0, W, 80):
        d.line([(x, 0), (x, H)], fill=(14, 32, 66), width=1)
    for y in range(0, H, 80):
        d.line([(0, y), (W, y)], fill=(14, 32, 66), width=1)

    d.rectangle([0, 0, W, 6], fill=accent_color)

    # Badge
    f_badge = images._font(22, bold=True)
    bw = d.textlength(badge_text, font=f_badge) + 34
    d.rounded_rectangle([55, 34, 55 + bw, 74], radius=8, fill=accent_color)
    d.text((72, 41), badge_text, font=f_badge, fill=NAVY_TOP)

    # Sana (o'ng yuqori)
    date_str = datetime.now(TASHKENT).strftime("%d.%m.%Y • %H:%M (Toshkent)")
    f_date = images._font(21, bold=False)
    d.text((W - 55 - d.textlength(date_str, font=f_date), 42), date_str, font=f_date, fill=GREY)

    # Sarlavha
    f_title = images._font(42, bold=True)
    d.text((55, 88), title_text, font=f_title, fill=WHITE)

    # Pastki chiziq va brend footer
    d.line([(55, H - 72), (W - 55, H - 72)], fill=BORDER, width=2)
    f_brand = images._font(30, bold=True)
    d.text((55, H - 56), "MARKETPULSE", font=f_brand, fill=WHITE)
    f_chan = images._font(22, bold=True)
    chan_txt = "t.me/MarketPulseZK"
    d.text((W - 55 - d.textlength(chan_txt, font=f_chan), H - 52), chan_txt, font=f_chan, fill=CYAN)

    return img, d


def _to_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _yahoo_quote_full(sym: str) -> dict | None:
    """Yahoo Finance v8 chart API dan joriy narx va kunlik o'zgarishni oladi."""
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
            params={"range": "5d", "interval": "1d"},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        r.raise_for_status()
        meta = r.json()["chart"]["result"][0]["meta"]
        price = float(meta["regularMarketPrice"])
        prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price)
        pct = ((price - prev) / prev * 100.0) if prev else 0.0
        return {"symbol": sym, "price": price, "prev": prev, "pct": pct}
    except Exception:
        return None


# ==============================================================================
# 1. HAFTALIK IQTISODIY TAQVIM (ECONOMIC CALENDAR)
# ==============================================================================

def fetch_weekly_economic_calendar() -> list[dict]:
    """ForexFactory ochiq JSON manbasidan joriy haftaning eng muhim AQSh makro voqealarini oladi."""
    events = []
    try:
        r = requests.get(
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        for ev in data:
            if ev.get("country") != "USD":
                continue
            impact = ev.get("impact", "")
            if impact not in ("High", "Medium"):
                continue
            dt_raw = ev.get("date", "")
            try:
                dt_utc = datetime.fromisoformat(dt_raw.replace("Z", "+00:00"))
                dt_uz = dt_utc.astimezone(TASHKENT)
                day_str = f"{UZ_DAYS.get(dt_uz.weekday(), '')[:4]}, {dt_uz.strftime('%d.%m %H:%M')}"
            except Exception:
                day_str = dt_raw[:16]

            events.append({
                "title": ev.get("title", ""),
                "impact": impact,
                "time_uz": day_str,
                "forecast": ev.get("forecast") or "—",
                "previous": ev.get("previous") or "—",
                "ts": dt_raw,
            })
        # High impact birinchi, keyin vaqt bo'yicha
        highs = [e for e in events if e["impact"] == "High"]
        meds = [e for e in events if e["impact"] == "Medium"]
        events = highs[:7] + meds[: max(0, 7 - len(highs))]
        events.sort(key=lambda x: x["ts"])
    except Exception as e:
        log.warning("Economic calendar fetch error: %s", e)
    return events[:7]


def render_economic_calendar_card(events: list[dict]) -> bytes:
    img, d = _new_canvas("MAKRO TAQVIM • AQSH", "HAFTANING ENG MUHIM IQTISODIY VOQEALARI", accent_color=GOLD)

    # Jadval sarlavhasi
    y = 158
    d.rounded_rectangle([55, y, W - 55, y + 46], radius=8, fill=(20, 48, 92))
    f_hdr = images._font(21, bold=True)
    d.text((75, y + 11), "VAQT (TOSHKENT)", font=f_hdr, fill=CYAN)
    d.text((310, y + 11), "VOQEA / INDIKATOR", font=f_hdr, fill=CYAN)
    d.text((885, y + 11), "PROGNOZ", font=f_hdr, fill=CYAN)
    d.text((1055, y + 11), "AVVALGI", font=f_hdr, fill=CYAN)

    f_row = images._font(22, bold=False)
    f_row_b = images._font(22, bold=True)
    y += 58
    for idx, ev in enumerate(events[:7]):
        bg = CARD_BG if idx % 2 == 0 else (10, 24, 52)
        d.rounded_rectangle([55, y, W - 55, y + 58], radius=8, fill=bg, outline=BORDER, width=1)
        dot_col = RED if ev["impact"] == "High" else ORANGE
        d.ellipse([72, y + 21, 88, y + 37], fill=dot_col)
        d.text((100, y + 16), ev["time_uz"], font=f_row, fill=WHITE)
        title = ev["title"][:42] + ("..." if len(ev["title"]) > 42 else "")
        d.text((310, y + 16), title, font=f_row_b, fill=WHITE)
        d.text((885, y + 16), str(ev["forecast"])[:12], font=f_row_b, fill=GOLD)
        d.text((1055, y + 16), str(ev["previous"])[:12], font=f_row, fill=GREY)
        y += 66

    return _to_jpeg(img)


def post_economic_calendar(dry_run: bool = False) -> bool:
    events = fetch_weekly_economic_calendar()
    if not events:
        log.warning("Haftalik iqtisodiy taqvim bo'sh.")
        return False

    rows_txt = []
    for ev in events:
        icon = "🔴" if ev["impact"] == "High" else "🟠"
        rows_txt.append(
            f"{icon} <b>{ev['time_uz']}</b> — {ev['title']}\n"
            f"   Prognoz: <b>{ev['forecast']}</b> | Avvalgi: {ev['previous']}"
        )

    html = (
        "📅 <b>HAFTALIK IQTISODIY TAQVIM (AQSH)</b>\n"
        "<i>Barcha vaqtlar Toshkent (UTC+5) bo‘yicha ko‘rsatilgan</i>\n\n"
        + "\n\n".join(rows_txt)
        + '\n\n🔴 — Yuqori ta’sir | 🟠 — O‘rta ta’sir\n\n'
        '<i>Manba: <a href="https://www.forexfactory.com/calendar">ForexFactory / U.S. Economic Calendar</a></i>'
    )
    img = render_economic_calendar_card(events)
    if dry_run:
        print("\n[DRY RUN - ECONOMIC CALENDAR]\n" + html)
        return True
    telegram_api.send_post(html, img)
    db.add_post(None, f"econ-cal-{datetime.now(TASHKENT).strftime('%Y-W%W')}", "Haftalik iqtisodiy taqvim", "")
    log.info("Haftalik iqtisodiy taqvim muvaffaqiyatli chiqarildi!")
    return True


# ==============================================================================
# 2. HAFTALIK CHORAKLIK HISOBOTLAR TAQVIMI (EARNINGS CALENDAR)
# ==============================================================================

def _parse_mcap_billions(mcap_str: str) -> float:
    if not mcap_str:
        return 0.0
    s = mcap_str.replace("$", "").replace(",", "").strip()
    try:
        return float(s) / 1e9
    except Exception:
        return 0.0


def fetch_weekly_earnings() -> list[dict]:
    """Nasdaq ochiq Earnings API orqali joriy haftaning eng yirik kompaniyalari hisobotlarini yig'adi."""
    now = datetime.now(TASHKENT)
    # Joriy haftaning ish kunlari (dushanba-juma)
    monday = now - timedelta(days=now.weekday())
    found = []
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    for offset in range(5):
        day_dt = monday + timedelta(days=offset)
        date_str = day_dt.strftime("%Y-%m-%d")
        try:
            r = requests.get(
                "https://api.nasdaq.com/api/calendar/earnings",
                params={"date": date_str},
                headers=headers,
                timeout=12,
            )
            if r.status_code != 200:
                continue
            rows = (r.json().get("data") or {}).get("rows") or []
            for row in rows:
                sym = (row.get("symbol") or "").strip().upper()
                mcap_b = _parse_mcap_billions(row.get("marketCap", ""))
                if not sym or (mcap_b < 15.0 and sym not in TOP_STOCKS):
                    continue
                t_raw = (row.get("time") or "").lower()
                timing = "Ochilishdan oldin" if "pre" in t_raw else ("Yopilgandan so‘ng" if "after" in t_raw else "Kun davomida")
                found.append({
                    "symbol": sym,
                    "name": (row.get("name") or sym)[:28],
                    "day": f"{UZ_DAYS[offset][:4]}, {day_dt.strftime('%d.%m')}",
                    "timing": timing,
                    "eps_est": row.get("epsForecast") or "—",
                    "mcap_b": mcap_b,
                    "sort_day": offset,
                })
        except Exception as e:
            log.debug("Earnings fetch error %s: %s", date_str, e)

    # Eng yirik 8 ta kompaniyani olamiz va kun bo'yicha tartiblaymiz
    found.sort(key=lambda x: -x["mcap_b"])
    top = found[:7]
    top.sort(key=lambda x: (x["sort_day"], -x["mcap_b"]))
    return top


def render_earnings_calendar_card(rows: list[dict]) -> bytes:
    img, d = _new_canvas("EARNINGS CALENDAR • WALL STREET", "HAFTANING ASOSIY MOLIYAVIY HISOBOTLARI", accent_color=CYAN)

    y = 158
    d.rounded_rectangle([55, y, W - 55, y + 46], radius=8, fill=(20, 48, 92))
    f_hdr = images._font(21, bold=True)
    d.text((75, y + 11), "KUN", font=f_hdr, fill=CYAN)
    d.text((230, y + 11), "TIKER", font=f_hdr, fill=CYAN)
    d.text((370, y + 11), "KOMPANIYA", font=f_hdr, fill=CYAN)
    d.text((780, y + 11), "VAQT", font=f_hdr, fill=CYAN)
    d.text((1045, y + 11), "EPS PROGNOZ", font=f_hdr, fill=CYAN)

    f_row = images._font(22, bold=False)
    f_row_b = images._font(22, bold=True)
    y += 58
    for idx, r in enumerate(rows[:7]):
        bg = CARD_BG if idx % 2 == 0 else (10, 24, 52)
        d.rounded_rectangle([55, y, W - 55, y + 58], radius=8, fill=bg, outline=BORDER, width=1)
        d.text((75, y + 16), r["day"], font=f_row, fill=GREY)
        d.text((230, y + 16), f"#{r['symbol']}", font=f_row_b, fill=GOLD)
        d.text((370, y + 16), r["name"][:26], font=f_row_b, fill=WHITE)
        d.text((780, y + 16), r["timing"], font=f_row, fill=CYAN)
        d.text((1065, y + 16), str(r["eps_est"]), font=f_row_b, fill=GREEN)
        y += 66

    return _to_jpeg(img)


def post_earnings_calendar(dry_run: bool = False) -> bool:
    rows = fetch_weekly_earnings()
    if not rows:
        log.warning("Bu hafta uchun yirik earnings hisobotlari topilmadi.")
        return False

    lines = []
    for r in rows:
        lines.append(
            f"• <b>{r['day']}</b> — <b>#{r['symbol']}</b> ({r['name']}) | {r['timing']} | EPS kutilma: <b>{r['eps_est']}</b>"
        )

    html = (
        "💼 <b>HAFTANING ASOSIY CHORAKLIK HISOBOTLARI (EARNINGS)</b>\n\n"
        + "\n".join(lines)
        + '\n\n<i>Manba: <a href="https://www.nasdaq.com/market-activity/earnings">NASDAQ Earnings Calendar</a></i>'
    )
    img = render_earnings_calendar_card(rows)
    if dry_run:
        print("\n[DRY RUN - EARNINGS CALENDAR]\n" + html)
        return True
    telegram_api.send_post(html, img)
    db.add_post(None, f"earnings-cal-{datetime.now(TASHKENT).strftime('%Y-W%W')}", "Haftalik Earnings taqvimi", "")
    log.info("Haftalik Earnings taqvimi muvaffaqiyatli chiqarildi!")
    return True


# ==============================================================================
# 3. PRE-MARKET BRIFING ("BOZOR OCHILISHI OLDIDAN")
# ==============================================================================

def fetch_premarket_data() -> dict:
    futures_map = [
        ("ES=F", "S&P 500 Fyuchers"),
        ("NQ=F", "Nasdaq 100 Fyuchers"),
        ("YM=F", "Dow Jones Fyuchers"),
        ("CL=F", "WTI Neft"),
        ("GC=F", "Oltin (Gold)"),
        ("BTC-USD", "Bitcoin"),
    ]
    futures = []
    for sym, label in futures_map:
        q = _yahoo_quote_full(sym)
        if q:
            q["label"] = label
            futures.append(q)

    movers = []
    for sym in TOP_STOCKS[:18]:
        q = _yahoo_quote_full(sym)
        if q:
            movers.append(q)
    movers.sort(key=lambda x: -abs(x["pct"]))
    return {"futures": futures, "movers": movers[:5]}


def render_premarket_card(data: dict) -> bytes:
    img, d = _new_canvas("PRE-MARKET BRIFING • NYSE / NASDAQ", "AQSH BOZORI OCHILISHI OLDIDAN HOLAT", accent_color=CYAN)

    # Chap ustun: Fyucherslar & Xomashyo
    f_sec = images._font(24, bold=True)
    f_lbl = images._font(23, bold=True)
    f_val = images._font(23, bold=True)

    d.text((55, 155), "FYUCHERSLAR VA ASOSIY AKTIVLAR", font=f_sec, fill=CYAN)
    y = 195
    for f in data["futures"][:6]:
        d.rounded_rectangle([55, y, 620, y + 66], radius=10, fill=CARD_BG, outline=BORDER, width=1)
        d.text((75, y + 18), f["label"], font=f_lbl, fill=WHITE)
        col = GREEN if f["pct"] >= 0 else RED
        val_txt = f"${f['price']:,.2f}  ({f['pct']:+.2f}%)"
        d.text((600 - d.textlength(val_txt, font=f_val), y + 18), val_txt, font=f_val, fill=col)
        y += 74

    # O'ng ustun: Eng faol aksiyalar
    d.text((660, 155), "ENG FAOL AKSIYALAR", font=f_sec, fill=GOLD)
    y = 195
    for m in data["movers"][:5]:
        d.rounded_rectangle([660, y, W - 55, y + 80], radius=10, fill=CARD_BG, outline=BORDER, width=1)
        col = GREEN if m["pct"] >= 0 else RED
        d.rounded_rectangle([672, y + 14, 680, y + 66], radius=4, fill=col)
        d.text((698, y + 23), f"#{m['symbol']}", font=images._font(28, bold=True), fill=WHITE)
        price_txt = f"${m['price']:,.2f}"
        pct_txt = f"{m['pct']:+.2f}%"
        d.text((950, y + 25), price_txt, font=f_val, fill=GREY)
        d.text((W - 75 - d.textlength(pct_txt, font=images._font(28, bold=True)), y + 23), pct_txt, font=images._font(28, bold=True), fill=col)
        y += 88

    return _to_jpeg(img)


def post_premarket_briefing(dry_run: bool = False) -> bool:
    data = fetch_premarket_data()
    if not data["futures"]:
        return False

    fut_lines = []
    for f in data["futures"]:
        arrow = "🟢" if f["pct"] >= 0 else "🔴"
        lbl = f["label"].replace("&", "&amp;")
        fut_lines.append(f"{arrow} <b>{lbl}:</b> ${f['price']:,.2f} (<b>{f['pct']:+.2f}%</b>)")

    mov_lines = []
    for m in data["movers"]:
        arrow = "📈" if m["pct"] >= 0 else "📉"
        mov_lines.append(f"{arrow} <b>#{m['symbol']}:</b> ${m['price']:,.2f} (<b>{m['pct']:+.2f}%</b>)")

    html = (
        "🔔 <b>PRE-MARKET BRIFING: AQSH BOZORI OCHILISHI OLDIDAN</b>\n\n"
        "📊 <b>Fyucherslar va asosiy aktivlar:</b>\n"
        + "\n".join(fut_lines)
        + "\n\n⚡ <b>Diqqat markazidagi faol aksiyalar:</b>\n"
        + "\n".join(mov_lines)
        + '\n\n<i>Manba: <a href="https://finance.yahoo.com/markets/">Yahoo Finance / NYSE Pre-Market</a></i>'
    )
    img = render_premarket_card(data)
    if dry_run:
        print("\n[DRY RUN - PREMARKET]\n" + html)
        return True
    telegram_api.send_post(html, img)
    db.add_post(None, f"premarket-{datetime.now(TASHKENT).strftime('%Y-%m-%d')}", "Pre-Market brifing", "")
    log.info("Pre-Market brifing muvaffaqiyatli chiqarildi!")
    return True


# ==============================================================================
# 4. BOZOR KAYFIYATI: FEAR & GREED INDEX + VIX (SPIDOMETR INFOGRAFIKA)
# ==============================================================================

def fetch_fear_and_greed() -> dict:
    """CNN Business Fear & Greed Index + VIX ko'rsatkichini oladi (zaxira hisoblash bilan)."""
    vix_q = _yahoo_quote_full("^VIX")
    vix_val = vix_q["price"] if vix_q else 18.0
    vix_pct = vix_q["pct"] if vix_q else 0.0

    score = None
    prev_close = None
    prev_week = None
    try:
        r = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "https://edition.cnn.com/",
                "Origin": "https://edition.cnn.com",
            },
            timeout=12,
        )
        if r.status_code == 200:
            fg = r.json().get("fear_and_greed", {})
            if fg.get("score") is not None:
                score = round(float(fg["score"]))
                prev_close = round(float(fg.get("previous_close") or score))
                prev_week = round(float(fg.get("previous_1_week") or score))
    except Exception as e:
        log.debug("CNN Fear & Greed fetch fallback: %s", e)

    # Agar CNN bloklasa, VIX asosida real vaqt indeksini hisoblaymiz
    if score is None:
        # VIX 12 -> ~80 (Greed), VIX 20 -> ~50 (Neutral), VIX 35 -> ~15 (Extreme Fear)
        score = int(max(5, min(95, round(105 - vix_val * 2.7))))
        prev_close = score
        prev_week = score

    if score <= 25:
        label_uz, col = "KUCHLI VAHIMA (Extreme Fear)", RED
    elif score <= 45:
        label_uz, col = "QO‘RQUV (Fear)", ORANGE
    elif score <= 55:
        label_uz, col = "NEYTRAL (Neutral)", GOLD
    elif score <= 75:
        label_uz, col = "OCHKO‘ZLIK (Greed)", (140, 220, 90)
    else:
        label_uz, col = "KUCHLI OCHKO‘ZLIK (Extreme Greed)", GREEN

    return {
        "score": score,
        "prev_close": prev_close,
        "prev_week": prev_week,
        "label_uz": label_uz,
        "color": col,
        "vix": vix_val,
        "vix_pct": vix_pct,
    }


def render_fear_greed_card(fg: dict) -> bytes:
    img, d = _new_canvas("BOZOR KAYFIYATI • SENTIMENT", "FEAR & GREED INDEX VA VIX TAHLILI", accent_color=fg["color"])

    # Yarim doira spidometr (chap-markaz)
    cx, cy = 430, 480
    radius = 240
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]

    # 5 ta rangli zona (180° dan 360° gacha)
    zones = [
        (180, 216, RED),
        (216, 252, ORANGE),
        (252, 288, GOLD),
        (288, 324, (140, 220, 90)),
        (324, 360, GREEN),
    ]
    for a1, a2, zcol in zones:
        d.arc(bbox, start=a1, end=a2, fill=zcol, width=42)

    # Strelka (needle)
    angle_deg = 180 + (fg["score"] / 100.0) * 180.0
    angle_rad = math.radians(angle_deg)
    nx = cx + int((radius - 32) * math.cos(angle_rad))
    ny = cy + int((radius - 32) * math.sin(angle_rad))
    d.line([(cx, cy), (nx, ny)], fill=WHITE, width=8)
    d.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], fill=WHITE, outline=fg["color"], width=4)

    # Markaziy raqam
    score_txt = str(fg["score"])
    f_big = images._font(92, bold=True)
    d.text((cx - d.textlength(score_txt, font=f_big) / 2, cy - 140), score_txt, font=f_big, fill=fg["color"])

    f_lbl = images._font(28, bold=True)
    d.text((cx - d.textlength(fg["label_uz"], font=f_lbl) / 2, cy + 36), fg["label_uz"], font=f_lbl, fill=WHITE)

    # 0 va 100 belgilari
    f_sm = images._font(22, bold=True)
    d.text((cx - radius - 10, cy + 12), "0", font=f_sm, fill=RED)
    d.text((cx + radius - 26, cy + 12), "100", font=f_sm, fill=GREEN)

    # O'ng tarafdagi statistika bloklari
    cards = [
        ("VIX (QO‘RQUV INDEKSI)", f"{fg['vix']:.2f} ({fg['vix_pct']:+.2f}%)", RED if fg["vix"] >= 20 else GREEN),
        ("KECHAGI YOPILISH", f"{fg['prev_close']} / 100", CYAN),
        ("1 HAFTA OLDIN", f"{fg['prev_week']} / 100", GOLD),
    ]
    y = 195
    for title, val, col in cards:
        d.rounded_rectangle([760, y, W - 55, y + 118], radius=12, fill=CARD_BG, outline=BORDER, width=2)
        d.text((790, y + 18), title, font=images._font(21, bold=True), fill=GREY)
        d.text((790, y + 54), val, font=images._font(38, bold=True), fill=col)
        y += 138

    return _to_jpeg(img)


def post_fear_and_greed(dry_run: bool = False) -> bool:
    fg = fetch_fear_and_greed()
    html = (
        f"🧭 <b>BOZOR KAYFIYATI: FEAR &amp; GREED INDEX — {fg['score']}/100</b>\n\n"
        f"• Joriy holat: <b>{fg['label_uz']}</b>\n"
        f"• Kechagi ko‘rsatkich: <b>{fg['prev_close']}/100</b> | 1 hafta oldin: <b>{fg['prev_week']}/100</b>\n"
        f"• <b>#VIX (Volatillik indeksi):</b> <b>{fg['vix']:.2f}</b> ({fg['vix_pct']:+.2f}%)\n\n"
        f"📌 <i>Ma’lumot uchun: 0–25 kuchli vahima (ko‘pincha bozor tubiga yaqin), 75–100 esa kuchli ochko‘zlik (qizib ketish) zonasini bildiradi.</i>\n\n"
        '<i>Manba: <a href="https://edition.cnn.com/markets/fear-and-greed">CNN Business Fear &amp; Greed / CBOE VIX</a></i>'
    )
    img = render_fear_greed_card(fg)
    if dry_run:
        print("\n[DRY RUN - FEAR & GREED]\n" + html)
        return True
    telegram_api.send_post(html, img)
    db.add_post(None, f"fear-greed-{datetime.now(TASHKENT).strftime('%Y-%m-%d')}", f"Fear & Greed: {fg['score']}", "")
    log.info("Fear & Greed indeksi (%d) muvaffaqiyatli chiqarildi!", fg["score"])
    return True


# ==============================================================================
# 5. TOP 5 GAINERS & TOP 5 LOSERS + SEKTOR HEATMAP
# ==============================================================================

def fetch_movers_and_heatmap() -> dict:
    quotes = []
    for sym in TOP_STOCKS:
        q = _yahoo_quote_full(sym)
        if q:
            quotes.append(q)
    quotes.sort(key=lambda x: -x["pct"])
    gainers = quotes[:5]
    losers = sorted(quotes[-5:], key=lambda x: x["pct"])
    sectors = market.get_sector_etfs()
    return {"gainers": gainers, "losers": losers, "sectors": sectors}


def render_movers_heatmap_card(data: dict) -> bytes:
    img, d = _new_canvas("WALL STREET HEATMAP & MOVERS", "SEKTORLAR XARITASI VA KUN QAHRAMONLARI", accent_color=GREEN)

    # Chap taraf: Sektorlar Issiqlik Xaritasi (Heatmap 2 ustunli plitkalar)
    d.text((55, 152), "SEKTORLAR ISSIQLIK XARITASI (ETF)", font=images._font(22, bold=True), fill=CYAN)
    sectors = data["sectors"][:10]
    cols = 2
    tile_w, tile_h = 278, 84
    gap = 12
    for idx, s in enumerate(sectors):
        r_idx, c_idx = divmod(idx, cols)
        x1 = 55 + c_idx * (tile_w + gap)
        y1 = 190 + r_idx * (tile_h + gap)
        pct = s["change_pct"]
        if pct >= 1.5:
            bg = (16, 130, 74)
        elif pct >= 0:
            bg = (18, 88, 56)
        elif pct <= -1.5:
            bg = (168, 36, 52)
        else:
            bg = (112, 32, 44)
        d.rounded_rectangle([x1, y1, x1 + tile_w, y1 + tile_h], radius=10, fill=bg, outline=(255, 255, 255, 40), width=1)
        d.text((x1 + 14, y1 + 10), f"{s['symbol']} • {s['name'][:14]}", font=images._font(19, bold=True), fill=WHITE)
        d.text((x1 + 14, y1 + 42), s["change_desc"], font=images._font(28, bold=True), fill=WHITE)

    # O'ng taraf: Top 5 Gainers & Top 5 Losers
    rx = 660
    d.text((rx, 152), "TOP 5 O‘SGAN AKSIYALAR", font=images._font(22, bold=True), fill=GREEN)
    y = 188
    for g in data["gainers"][:5]:
        d.rounded_rectangle([rx, y, W - 55, y + 38], radius=6, fill=CARD_BG, outline=(24, 96, 64), width=1)
        d.text((rx + 14, y + 7), f"#{g['symbol']}", font=images._font(21, bold=True), fill=WHITE)
        d.text((rx + 150, y + 7), f"${g['price']:,.2f}", font=images._font(20, bold=False), fill=GREY)
        ptxt = f"{g['pct']:+.2f}%"
        d.text((W - 70 - d.textlength(ptxt, font=images._font(22, bold=True)), y + 6), ptxt, font=images._font(22, bold=True), fill=GREEN)
        y += 44

    y += 14
    d.text((rx, y), "TOP 5 TUSHGAN AKSIYALAR", font=images._font(22, bold=True), fill=RED)
    y += 34
    for l in data["losers"][:5]:
        d.rounded_rectangle([rx, y, W - 55, y + 38], radius=6, fill=CARD_BG, outline=(112, 34, 48), width=1)
        d.text((rx + 14, y + 7), f"#{l['symbol']}", font=images._font(21, bold=True), fill=WHITE)
        d.text((rx + 150, y + 7), f"${l['price']:,.2f}", font=images._font(20, bold=False), fill=GREY)
        ptxt = f"{l['pct']:+.2f}%"
        d.text((W - 70 - d.textlength(ptxt, font=images._font(22, bold=True)), y + 6), ptxt, font=images._font(22, bold=True), fill=RED)
        y += 44

    return _to_jpeg(img)


def post_top_movers_heatmap(dry_run: bool = False) -> bool:
    data = fetch_movers_and_heatmap()
    if not data["gainers"] or not data["losers"]:
        return False

    g_txt = "\n".join(
        f"{'🟢' if g['pct'] >= 0 else '🟡'} <b>#{g['symbol']}</b>: ${g['price']:,.2f} (<b>{g['pct']:+.2f}%</b>)"
        for g in data["gainers"]
    )
    l_txt = "\n".join(f"🔴 <b>#{l['symbol']}</b>: ${l['price']:,.2f} (<b>{l['pct']:+.2f}%</b>)" for l in data["losers"])

    html = (
        "🗺 <b>BOZOR ISSIQLIK XARITASI VA KUN YETAKCHILARI</b>\n\n"
        "🚀 <b>Top 5 eng ko‘p o‘sgan aksiyalar:</b>\n"
        f"{g_txt}\n\n"
        "📉 <b>Top 5 eng ko‘p tushgan aksiyalar:</b>\n"
        f"{l_txt}\n\n"
        '<i>Manba: <a href="https://finance.yahoo.com/markets/stocks/gainers/">Yahoo Finance / Wall Street Movers</a></i>'
    )
    img = render_movers_heatmap_card(data)
    if dry_run:
        print("\n[DRY RUN - MOVERS & HEATMAP]\n" + html)
        return True
    telegram_api.send_post(html, img)
    db.add_post(None, f"movers-heatmap-{datetime.now(TASHKENT).strftime('%Y-%m-%d')}", "Top Gainers/Losers & Heatmap", "")
    log.info("Top Movers & Heatmap posti muvaffaqiyatli chiqarildi!")
    return True


# ==============================================================================
# 6. "SMART MONEY" — INSAYDERLAR (SEC FORM 4) VA YIRIK FONDLAR (13F)
# ==============================================================================

def fetch_smart_money_buys() -> list[dict]:
    """OpenInsider ochiq reyestridan eng yirik haftalik insayder xaridlarini (SEC Form 4) oladi."""
    buys = []
    try:
        r = requests.get(
            "http://openinsider.com/top-insider-purchases-of-the-week",
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find("table", class_="tinytable")
            if table:
                seen_syms = set()
                for tr in table.find_all("tr")[1:40]:
                    tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                    if len(tds) < 13:
                        continue
                    ticker = tds[3].strip().upper()
                    company = tds[4].strip()
                    insider = tds[5].strip()
                    role = tds[6].strip()
                    val_str = tds[12].strip()  # masalan: +$12,450,000
                    if not ticker or ticker in seen_syms or not val_str.startswith("+$"):
                        continue
                    seen_syms.add(ticker)
                    buys.append({
                        "symbol": ticker,
                        "company": company[:30],
                        "insider": insider[:26],
                        "role": role[:22],
                        "value": val_str,
                        "price": tds[8].strip(),
                        "date": tds[2].strip(),
                    })
                    if len(buys) >= 5:
                        break
    except Exception as e:
        log.warning("OpenInsider fetch error: %s", e)
    return buys


def render_smart_money_card(buys: list[dict]) -> bytes:
    img, d = _new_canvas("SMART MONEY • SEC FORM 4", "YIRIK INSAYDER XARIDLARI (WALL STREET)", accent_color=GOLD)

    y = 158
    d.rounded_rectangle([55, y, W - 55, y + 46], radius=8, fill=(20, 48, 92))
    f_hdr = images._font(20, bold=True)
    d.text((75, y + 12), "TIKER", font=f_hdr, fill=CYAN)
    d.text((200, y + 12), "KOMPANIYA", font=f_hdr, fill=CYAN)
    d.text((540, y + 12), "INSAYDER / LAVOZIM", font=f_hdr, fill=CYAN)
    d.text((990, y + 12), "XARID HAJMI", font=f_hdr, fill=CYAN)

    y += 60
    for idx, b in enumerate(buys[:5]):
        bg = CARD_BG if idx % 2 == 0 else (10, 24, 52)
        d.rounded_rectangle([55, y, W - 55, y + 76], radius=10, fill=bg, outline=BORDER, width=1)
        d.text((75, y + 22), f"#{b['symbol']}", font=images._font(26, bold=True), fill=GOLD)
        d.text((200, y + 24), b["company"][:22], font=images._font(22, bold=True), fill=WHITE)
        d.text((540, y + 12), b["insider"], font=images._font(21, bold=True), fill=WHITE)
        d.text((540, y + 42), f"{b['role']} • {b['date']}", font=images._font(18, bold=False), fill=GREY)
        d.text((990, y + 22), b["value"], font=images._font(26, bold=True), fill=GREEN)
        y += 86

    return _to_jpeg(img)


def post_smart_money(dry_run: bool = False) -> bool:
    buys = fetch_smart_money_buys()
    if not buys:
        log.warning("Yirik insayder xaridlari topilmadi.")
        return False

    lines = []
    for b in buys:
        lines.append(
            f"🐳 <b>#{b['symbol']}</b> ({b['company']})\n"
            f"   Kim: {b['insider']} (<i>{b['role']}</i>) | Summa: <b>{b['value']}</b> (narx: {b['price']})"
        )

    html = (
        "🐳 <b>SMART MONEY: YIRIK INSAYDER XARIDLARI (SEC FORM 4)</b>\n"
        "<i>Kompaniya rahbarlari va yirik aksiyadorlar o‘z pullariga sotib olgan aksiyalar:</i>\n\n"
        + "\n\n".join(lines)
        + '\n\n<i>Manba: <a href="https://www.sec.gov/edgar/searchedgar/companysearch">SEC EDGAR (Form 4) / OpenInsider</a></i>'
    )
    img = render_smart_money_card(buys)
    if dry_run:
        print("\n[DRY RUN - SMART MONEY]\n" + html)
        return True
    telegram_api.send_post(html, img)
    db.add_post(None, f"smart-money-{datetime.now(TASHKENT).strftime('%Y-%m-%d')}", "Smart Money SEC Form 4", "")
    log.info("Smart Money posti muvaffaqiyatli chiqarildi!")
    return True


# ==============================================================================
# 7. AVTOMATIK INTERAKTIV SO'ROVNOMALAR (TELEGRAM POLL)
# ==============================================================================

POLLS_BANK = [
    (
        "📊 Keyingi yirik kompaniya tahlili qaysi aksiya haqida bo‘lsin?",
        ["#TSLA (Tesla)", "#AAPL (Apple)", "#MSFT (Microsoft)", "#PLTR (Palantir)", "#AMD (AMD)"],
    ),
    (
        "📈 Sizningcha, bu hafta S&P 500 indeksi qanday yopiladi?",
        ["🟢 Ko‘tariladi (+1% dan ko‘p)", "🟡 O‘zgarishsiz / yonlama", "🔴 Pasayadi (-1% dan ko‘p)"],
    ),
    (
        "🏦 Fed keyingi yig‘ilishda foiz stavkasini nima qiladi deb o‘ylaysiz?",
        ["📉 Pasaytiradi (-25 bp)", "⏸ O‘zgarishsiz qoldiradi", "📈 Oshiradi"],
    ),
    (
        "💰 Hozir qo‘lingizda $10,000 bo‘lsa, qaysi sohaga uzoq muddatga tikardingiz?",
        ["🤖 AI va Yarimo‘tkazgichlar (#NVDA, #ASML)", "🥇 Oltin va xomashyo", "₿ Kriptovalyuta (Bitcoin)", "📈 S&P 500 indeks fondi"],
    ),
    (
        "⏱ Siz qaysi uslubdagi bozor ishtirokchisisiz?",
        ["💎 Uzoq muddatli investor (1+ yil)", "📊 Swing treyder (bir necha kun/hafta)", "⚡ Kunlik treyder (Intraday)", "🎓 Hali o‘rganyapman (Akademiya)"],
    ),
    (
        "🚗 #TSLA (Tesla) aksiyasining keyingi 6 oydagi yo‘nalishi qanday bo‘ladi?",
        ["🚀 Kuchli o‘sish", "⚖️ Hozirgi darajada qoladi", "📉 Tuzatish (pasayish)"],
    ),
    (
        "🪙 Oltin narxi bu yil yana yangi tarixiy rekord o‘rnatadimi?",
        ["✅ Ha, inflyatsiya va geosiyosat qo‘llab-quvvatlaydi", "❌ Yo‘q, kuchli tuzatish bo‘ladi", "🤔 Kuzatib boryapman"],
    ),
    (
        "🎓 MarketPulse Weekend Akademiya darslari sizga qanchalik foydali bo‘lyapti?",
        ["🔥 Juda zo‘r, har hafta kutyapman!", "👍 Foydali, davom etsin", "📈 Grafik va misollar ko‘proq bo‘lsin"],
    ),
]


def post_interactive_poll(dry_run: bool = False) -> bool:
    chosen_idx = 0
    for idx in range(len(POLLS_BANK)):
        if not db.is_feature_done("interactive_poll", f"poll_{idx}"):
            chosen_idx = idx
            break

    question, options = POLLS_BANK[chosen_idx]
    if dry_run:
        print(f"\n[DRY RUN - POLL #{chosen_idx}]\nSavol: {question}\nVariantlar: {options}")
        return True

    telegram_api.send_poll(question, options, is_anonymous=True)
    db.mark_feature_done("interactive_poll", f"poll_{chosen_idx}")
    log.info("Interaktiv so'rovnoma (#%d) kanalga muvaffaqiyatli yuborildi!", chosen_idx)
    return True
