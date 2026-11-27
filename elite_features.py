"""MARKETPULSE ELITE FEATURES — 4 ta yuqori darajadagi institutsional va brend funksiyasi:

1. Tezkor Earnings Natijalari Kartasi (BEAT / MISS — EPS Kutilma vs Fakt)
2. Oylik Katta Bozor Sarhisobi (1600x1000 Monthly Performance Matrix)
3. Kanal Tepasiga Qadaladigan (Pinned) Professional Navigatsiya Posti
4. Bozor Korrelyatsiyasi va Anomaliya Radari (Oltin vs DXY • S&P 500 vs VIX • BTC vs Nasdaq)
"""
import calendar
import io
import logging
import math
from datetime import datetime, timedelta

import requests
from PIL import Image, ImageDraw

import db
import images
import max_features
import telegram_api
from config import TASHKENT, USER_AGENT
from uz_alphabet import to_new_uzbek

log = logging.getLogger("elite_features")

NAVY_TOP = (6, 16, 38)
NAVY_BOT = (10, 34, 74)
CARD_BG = (13, 28, 56)
BORDER = (30, 62, 114)
CYAN = (0, 212, 255)
GREEN = (34, 211, 130)
RED = (248, 81, 100)
GOLD = (255, 195, 0)
ORANGE = (255, 145, 50)
WHITE = (246, 249, 255)
GREY = (154, 176, 206)

UZ_MONTHS = {
    1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel", 5: "May", 6: "Iyun",
    7: "Iyul", 8: "Avgust", 9: "Sentyabr", 10: "Oktyabr", 11: "Noyabr", 12: "Dekabr",
}


def _to_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=93)
    return buf.getvalue()


def _base_card(w: int, h: int, badge: str, title: str, accent=CYAN):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / float(h)
        d.line([(0, y), (w, y)], fill=tuple(int(NAVY_TOP[i] + (NAVY_BOT[i] - NAVY_TOP[i]) * t) for i in range(3)))
    for x in range(0, w, 80):
        d.line([(x, 0), (x, h)], fill=(14, 32, 66), width=1)
    for y in range(0, h, 80):
        d.line([(0, y), (w, y)], fill=(14, 32, 66), width=1)

    d.rectangle([0, 0, w, 6], fill=accent)

    badge = to_new_uzbek(badge)
    title = to_new_uzbek(title)
    f_badge = images._font(21, bold=True)
    bw = d.textlength(badge, font=f_badge) + 32
    d.rounded_rectangle([50, 30, 50 + bw, 68], radius=8, fill=accent)
    d.text((66, 36), badge, font=f_badge, fill=NAVY_TOP)

    dt_str = to_new_uzbek(datetime.now(TASHKENT).strftime("%d.%m.%Y • %H:%M (Toşkent)"))
    f_dt = images._font(20, bold=False)
    d.text((w - 50 - d.textlength(dt_str, font=f_dt), 38), dt_str, font=f_dt, fill=GREY)

    d.text((50, 82), title, font=images._font(40, bold=True), fill=WHITE)

    d.line([(50, h - 66), (w - 50, h - 66)], fill=BORDER, width=2)
    d.text((50, h - 52), "MARKETPULSE", font=images._font(28, bold=True), fill=WHITE)
    chan = "t.me/MarketPulseZK"
    f_ch = images._font(21, bold=True)
    d.text((w - 50 - d.textlength(chan, font=f_ch), h - 48), chan, font=f_ch, fill=CYAN)
    return img, d


# ==============================================================================
# 2. TEZKOR EARNINGS NATIJALARI KARTASI (BEAT / MISS)
# ==============================================================================

def _parse_float(val: str) -> float | None:
    if not val:
        return None
    s = str(val).replace("$", "").replace(",", "").replace("%", "").strip()
    if s in ("", "N/A", "—", "-"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def fetch_latest_earnings_results() -> list[dict]:
    """Nasdaq Earnings API orqali bugun/kecha hisobot bergan yirik aksiyalar (EPS Kutilma vs Fakt) natijasini oladi."""
    now = datetime.now(TASHKENT)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    results = []

    for delta in (0, 1):
        d_str = (now - timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            r = requests.get(
                "https://api.nasdaq.com/api/calendar/earnings",
                params={"date": d_str},
                headers=headers,
                timeout=12,
            )
            if r.status_code != 200:
                continue
            rows = (r.json().get("data") or {}).get("rows") or []
            for row in rows:
                sym = (row.get("symbol") or "").strip().upper()
                if sym not in max_features.SCREENED_SET:
                    continue
                eps_act = _parse_float(row.get("eps"))
                eps_est = _parse_float(row.get("epsForecast"))
                if eps_act is None or eps_est is None:
                    continue
                surp = _parse_float(row.get("surprise"))
                if surp is None and eps_est != 0:
                    surp = (eps_act - eps_est) / abs(eps_est) * 100.0
                results.append({
                    "symbol": sym,
                    "name": max_features.COMPANY_NAMES.get(sym, (row.get("name") or sym)[:26]),
                    "date": d_str,
                    "eps_act": eps_act,
                    "eps_est": eps_est,
                    "surprise_pct": surp or 0.0,
                    "is_beat": eps_act >= eps_est,
                })
        except Exception as e:
            log.debug("Earnings results fetch error (%s): %s", d_str, e)

    return results


def render_earnings_result_card(res: dict, price_info: dict | None) -> bytes:
    is_beat = res["is_beat"]
    accent = GREEN if is_beat else RED
    status_txt = "KUTILMADAN YUQORI (BEAT)" if is_beat else "KUTILMADAN PAST (MISS)"

    img, d = _base_card(
        1280, 720,
        f"EARNINGS NATIJASI • #{res['symbol']}",
        f"{res['name'].upper()} — ÇORAKLIK MOLIYAVIY HISOBOT",
        accent=accent,
    )

    # Yuqori katta status banneri
    d.rounded_rectangle([50, 152, 1230, 244], radius=16, fill=(14, 48, 36) if is_beat else (58, 16, 26), outline=accent, width=3)
    f_st = images._font(40, bold=True)
    st_uz = to_new_uzbek(status_txt)
    d.text((640 - d.textlength(st_uz, font=f_st) / 2, 174), st_uz, font=f_st, fill=accent)

    # 3 ta asosiy metrika kartasi
    cards = [
        ("EPS (FAKT)", f"${res['eps_act']:.2f}", accent),
        ("EPS (KUTILMA)", f"${res['eps_est']:.2f}", CYAN),
        ("FARQ (SURPRISE)", f"{res['surprise_pct']:+.2f}%", accent),
    ]
    cx = 50
    cw = 374
    for lbl, val, col in cards:
        d.rounded_rectangle([cx, 276, cx + cw, 470], radius=16, fill=CARD_BG, outline=BORDER, width=2)
        d.text((cx + 28, 300), to_new_uzbek(lbl), font=images._font(22, bold=True), fill=GREY)
        d.text((cx + 28, 355), val, font=images._font(58, bold=True), fill=col)
        cx += cw + 29

    # Pastki bozor reaksiyasi paneli
    d.rounded_rectangle([50, 502, 1230, 616], radius=14, fill=CARD_BG, outline=BORDER, width=2)
    if price_info:
        pcol = GREEN if price_info["pct"] >= 0 else RED
        d.text((80, 524), to_new_uzbek(f"#{res['symbol']} JORIY BOZOR NARXI"), font=images._font(20, bold=True), fill=GREY)
        d.text((80, 556), f"${price_info['price']:,.2f}   ({price_info['pct']:+.2f}%)", font=images._font(36, bold=True), fill=pcol)
    else:
        d.text((80, 544), to_new_uzbek(f"#{res['symbol']} hisobot sanasi: {res['date']}"), font=images._font(28, bold=True), fill=WHITE)

    return _to_jpeg(img)


def post_earnings_results(dry_run: bool = False) -> int:
    """Hisobot bergan yangi yirik kompaniyalar natijalarini BEAT/MISS kartasi bilan chiqaradi."""
    items = fetch_latest_earnings_results()
    posted = 0
    for res in items:
        key = f"{res['symbol']}_{res['date']}"
        if not dry_run and db.is_feature_done("earnings_result", key):
            continue

        ohlcv = max_features._yahoo_ohlcv(res["symbol"], range_str="5d", interval="1d")
        price_info = None
        if ohlcv and len(ohlcv["candles"]) >= 2:
            cur, prev = ohlcv["candles"][-1]["c"], ohlcv["candles"][-2]["c"]
            price_info = {"price": cur, "pct": (cur - prev) / prev * 100.0 if prev else 0.0}

        badge = "🟢 <b>BEAT (Kutilmadan yuqori)</b>" if res["is_beat"] else "🔴 <b>MISS (Kutilmadan past)</b>"
        price_line = (
            f"\n• Joriy bozor narxi: <b>${price_info['price']:,.2f} ({price_info['pct']:+.2f}%)</b>"
            if price_info else ""
        )
        html = (
            f"🎯 <b>HISOBOT NATIJASI: #{res['symbol']} ({res['name']})</b>\n\n"
            f"• Natija: {badge}\n"
            f"• <b>EPS (Fakt):</b> <b>${res['eps_act']:.2f}</b> | Kutilma: ${res['eps_est']:.2f}\n"
            f"• Farq (Surprise): <b>{res['surprise_pct']:+.2f}%</b>"
            f"{price_line}\n\n"
            f'<i>Manba: <a href="https://www.nasdaq.com/market-activity/stocks/{res["symbol"].lower()}/earnings">NASDAQ Earnings / SEC 8-K</a></i>'
        )
        img = render_earnings_result_card(res, price_info)
        if dry_run:
            print(f"\n[DRY RUN - EARNINGS RESULT #{res['symbol']}]\n" + to_new_uzbek(html))
            posted += 1
            break

        telegram_api.send_post(html, img)
        db.mark_feature_done("earnings_result", key)
        db.add_post(None, f"earnings-res-{key.lower()}", f"#{res['symbol']} Earnings natijasi", "")
        log.info("Earnings natijasi (#%s) muvaffaqiyatli chiqarildi!", res["symbol"])
        posted += 1
        if posted >= 2:
            break
    return posted


# ==============================================================================
# 3. OYLIK KATTA BOZOR SARHISOBI (1600x1000 MONTHLY PERFORMANCE MATRIX)
# ==============================================================================

def _fetch_1m_change(sym: str) -> dict | None:
    d = max_features._yahoo_ohlcv(sym, range_str="1mo", interval="1d")
    if not d or len(d["candles"]) < 5:
        return None
    cur = d["candles"][-1]["c"]
    first = d["candles"][0]["c"]
    pct = (cur - first) / first * 100.0 if first else 0.0
    return {"symbol": sym, "price": cur, "pct": pct}


def fetch_monthly_review_data() -> dict:
    macro_list = [
        ("^GSPC", "S&P 500"),
        ("^IXIC", "Nasdaq"),
        ("^DJI", "Dow Jones"),
        ("GC=F", "Oltin (Gold)"),
        ("CL=F", "WTI Neft"),
        ("BTC-USD", "Bitcoin"),
        ("DX-Y.NYB", "DXY Dollar"),
        ("^VIX", "VIX Indeksi"),
    ]
    macros = []
    for sym, name in macro_list:
        q = _fetch_1m_change(sym)
        if q:
            q["name"] = name
            macros.append(q)

    stocks = []
    for sym in max_features.SCREENED_TICKERS[:32]:
        q = _fetch_1m_change(sym)
        if q:
            q["name"] = max_features.COMPANY_NAMES.get(sym, sym)
            stocks.append(q)
    stocks.sort(key=lambda x: -x["pct"])

    return {
        "macros": macros,
        "gainers": stocks[:5],
        "losers": sorted(stocks[-5:], key=lambda x: x["pct"]),
    }


def render_monthly_review_card(data: dict, month_label: str) -> bytes:
    img, d = _base_card(
        1600, 1000,
        f"OYLIK BOZOR SARHISOBI • {month_label.upper()}",
        f"{month_label.upper()} OYI YAKUNLARI — GLOBAL BOZOR MATRITSASI",
        accent=GOLD,
    )

    # Chap qism: 8 ta Makro va Global Aktiv plitkalari (2x4)
    d.text((50, 150), to_new_uzbek("ASOSIY INDEKSLAR, XOMAŞYO VA KRIPTO (1 OYLIK)"), font=images._font(23, bold=True), fill=CYAN)
    tw, th = 355, 165
    gap = 16
    for idx, m in enumerate(data["macros"][:8]):
        r, c = divmod(idx, 2)
        x1 = 50 + c * (tw + gap)
        y1 = 192 + r * (th + gap)
        col = GREEN if m["pct"] >= 0 else RED
        bg = (14, 52, 42) if m["pct"] >= 0 else (56, 18, 28)
        d.rounded_rectangle([x1, y1, x1 + tw, y1 + th], radius=14, fill=bg, outline=col, width=2)
        d.text((x1 + 22, y1 + 18), to_new_uzbek(m["name"]), font=images._font(24, bold=True), fill=WHITE)
        d.text((x1 + 22, y1 + 58), f"{m['pct']:+.2f}%", font=images._font(44, bold=True), fill=col)
        d.text((x1 + 22, y1 + 120), f"Joriy: {m['price']:,.2f}", font=images._font(20, bold=False), fill=GREY)

    # O'ng qism: Oyning Top 5 Qahramonlari va Top 5 Autsayderlari
    rx = 815
    d.text((rx, 150), to_new_uzbek("OYNING TOP 5 ÖSGAN AKSIYALARI"), font=images._font(23, bold=True), fill=GREEN)
    y = 192
    for g in data["gainers"][:5]:
        d.rounded_rectangle([rx, y, 1550, y + 60], radius=10, fill=CARD_BG, outline=(24, 102, 68), width=1)
        d.text((rx + 20, y + 15), f"#{g['symbol']}", font=images._font(26, bold=True), fill=WHITE)
        d.text((rx + 155, y + 17), g["name"][:18], font=images._font(21, bold=False), fill=GREY)
        d.text((rx + 420, y + 17), f"${g['price']:,.2f}", font=images._font(22, bold=True), fill=WHITE)
        ptxt = f"{g['pct']:+.2f}%"
        d.text((1530 - d.textlength(ptxt, font=images._font(26, bold=True)), y + 14), ptxt, font=images._font(26, bold=True), fill=GREEN)
        y += 68

    y += 22
    d.text((rx, y), to_new_uzbek("OYNING TOP 5 TUŞGAN AKSIYALARI"), font=images._font(23, bold=True), fill=RED)
    y += 42
    for l in data["losers"][:5]:
        d.rounded_rectangle([rx, y, 1550, y + 60], radius=10, fill=CARD_BG, outline=(120, 34, 48), width=1)
        d.text((rx + 20, y + 15), f"#{l['symbol']}", font=images._font(26, bold=True), fill=WHITE)
        d.text((rx + 155, y + 17), l["name"][:18], font=images._font(21, bold=False), fill=GREY)
        d.text((rx + 420, y + 17), f"${l['price']:,.2f}", font=images._font(22, bold=True), fill=WHITE)
        ptxt = f"{l['pct']:+.2f}%"
        d.text((1530 - d.textlength(ptxt, font=images._font(26, bold=True)), y + 14), ptxt, font=images._font(26, bold=True), fill=RED)
        y += 68

    return _to_jpeg(img)


def is_last_day_of_month(dt: datetime) -> bool:
    last_day = calendar.monthrange(dt.year, dt.month)[1]
    return dt.day == last_day


def post_monthly_review(dry_run: bool = False) -> bool:
    now = datetime.now(TASHKENT)
    month_label = f"{UZ_MONTHS.get(now.month, '')} {now.year}"
    data = fetch_monthly_review_data()
    if not data["macros"]:
        return False

    m_lines = "\n".join(
        f"{'🟢' if m['pct'] >= 0 else '🔴'} <b>{m['name'].replace('&', '&amp;')}:</b> {m['price']:,.2f} (<b>{m['pct']:+.2f}%</b>)"
        for m in data["macros"][:6]
    )
    g_lines = " | ".join(f"<b>#{g['symbol']}</b> ({g['pct']:+.1f}%)" for g in data["gainers"][:3])
    l_lines = " | ".join(f"<b>#{l['symbol']}</b> ({l['pct']:+.1f}%)" for l in data["losers"][:3])

    html = (
        f"📅 <b>OYLIK KATTA BOZOR SARHISOBI — {month_label.upper()}</b>\n\n"
        f"🌍 <b>Global aktivlar (1 oylik natija):</b>\n{m_lines}\n\n"
        f"🚀 <b>Oy qahramonlari:</b> {g_lines}\n"
        f"📉 <b>Oy autsayderlari:</b> {l_lines}\n\n"
        f"💾 <i>Uşbu oylik hisobotni özingizga saqlab qöying (Saved Messages)!</i>\n\n"
        '<i>Manba: <a href="https://finance.yahoo.com/markets/">Yahoo Finance / Wall Street Monthly Review</a></i>'
    )
    img = render_monthly_review_card(data, month_label)
    if dry_run:
        print(f"\n[DRY RUN - MONTHLY REVIEW {month_label}]\n" + to_new_uzbek(html))
        return True
    telegram_api.send_post(html, img)
    db.add_post(None, f"monthly-review-{now.strftime('%Y-%m')}", f"Oylik sarhisob: {month_label}", "")
    log.info("Oylik Bozor Sarhisobi (%s) muvaffaqiyatli chiqarildi!", month_label)
    return True


# ==============================================================================
# 4. KANAL TEPASIGA QADALADIGAN (PINNED) NAVIGATSIYA POSTI
# ==============================================================================

def render_navigation_banner() -> bytes:
    img, d = _base_card(
        1280, 720,
        "RASMIY NAVIGATSIYA • XARITA",
        "MARKETPULSE — MOLIYA, INVESTITSIYA VA TREYDING",
        accent=GOLD,
    )
    d.text((50, 142), to_new_uzbek("“Murakkab moliya → oddiy til → kuçli signal.”"), font=images._font(28, bold=True), fill=CYAN)

    pillars = [
        ("⚡ 24/7 BOZOR PULSI", "Global yangiliklar, Real-Time narx signallari, Pre-Market va Kunlik yakun", CYAN),
        ("🗺 HEATMAP & GRAFIKLAR", "1600×1000 Stocks Heatmap, TradingView shamçali grafiklar (EMA/RSI)", GREEN),
        ("🏦 SMART MONEY & MAKRO", "SEC 13D/13G va Form 4, Unusual Volume, Fed Radar, Fear & Greed, CBU.uz", GOLD),
        ("🎓 AKADEMIYA & VIDEO", "100 darslik bepul kurs (şanba-yakşanba) + 60 Soniyada Moliya videolari", ORANGE),
    ]
    y = 200
    for head, desc, col in pillars:
        d.rounded_rectangle([50, y, 1230, y + 96], radius=14, fill=CARD_BG, outline=col, width=2)
        d.rounded_rectangle([64, y + 18, 72, y + 78], radius=4, fill=col)
        d.text((92, y + 14), to_new_uzbek(head), font=images._font(26, bold=True), fill=col)
        d.text((92, y + 52), to_new_uzbek(desc), font=images._font(21, bold=False), fill=WHITE)
        y += 110

    return _to_jpeg(img)


def post_channel_navigation(pin: bool = True, dry_run: bool = False) -> bool:
    html = (
        "📌 <b>MARKETPULSE — KANAL XARITASI VA NAVIGATSIYA</b>\n"
        "<i>“Murakkab moliya → oddiy til → kuçli signal.”</i>\n\n"
        "Xuş kelibsiz! Bu yerda siz AQŞ va global fond bozori böyiça barcha muhim tahlillarni 24/7 kuzatib borasiz:\n\n"
        "⚡ <b>24/7 Tezkor Yangiliklar &amp; Real-Time Signallar:</b> Fed, inflyatsiya, geosiyosat, neft, oltin, kripto va keskin narx harakatlari.\n"
        "🗺 <b>Haftalik Stocks Heatmap &amp; Texnik Grafiklar:</b> Şanba ertalab 1600×1000 bozor xaritasi + har iş kuni TradingView shamçali grafiklar (EMA/RSI).\n"
        "🏦 <b>Smart Money &amp; Institutsional Radar:</b> SEC 13D/13G, Form 4, Unusual Volume, Fear &amp; Greed, Fed Yield Curve va Earnings (BEAT/MISS).\n"
        "🇺🇿 <b>Özbekiston Moliya Pulsi:</b> Markaziy Bank (USD/EUR/RUB) kurslari va global oltin.\n"
        "🎬 <b>60 Soniyada Moliya:</b> Har kuni 10:00, 15:00 va 20:00 da qisqa hujjatli videolar.\n"
        "🎓 <b>Bepul 100 Darslik Akademiya:</b> Har şanba va yakşanba (juma keçqurun — barcha darslar kutubxonasi!).\n\n"
        "🔍 <b>Tezkor tiker qidiruvi:</b> #NVDA #AAPL #TSLA #MSFT #GOOGL #AMD #PLTR #LLY\n\n"
        '<i>Manba: <a href="https://t.me/MarketPulseZK">MarketPulse Rasmiy Kanal</a></i>'
    )
    img = render_navigation_banner()
    if dry_run:
        print("\n[DRY RUN - CHANNEL NAVIGATION]\n" + to_new_uzbek(html))
        return True
    res = telegram_api.send_post(html, img)
    if pin and isinstance(res, dict) and res.get("message_id"):
        pinned = telegram_api.pin_message(int(res["message_id"]), disable_notification=True)
        log.info("Kanal navigatsiyasi joylandi (msg_id=%s, pinned=%s)!", res["message_id"], pinned)
    return True


# ==============================================================================
# 5. BOZOR KORRELYATSIYASI VA ANOMALIYA RADARI
# ==============================================================================

def _pearson_corr(xs: list[float], ys: list[float]) -> float:
    n = min(len(xs), len(ys))
    if n < 5:
        return 0.0
    xs, ys = xs[-n:], ys[-n:]
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den_x = math.sqrt(sum((a - mx) ** 2 for a in xs))
    den_y = math.sqrt(sum((b - my) ** 2 for b in ys))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def _daily_returns(sym: str) -> tuple[list[float], float]:
    d = max_features._yahoo_ohlcv(sym, range_str="1mo", interval="1d")
    if not d or len(d["candles"]) < 8:
        return [], 0.0
    closes = [c["c"] for c in d["candles"]]
    rets = [(closes[i] - closes[i - 1]) / closes[i - 1] * 100.0 for i in range(1, len(closes)) if closes[i - 1]]
    w5 = (closes[-1] - closes[-6]) / closes[-6] * 100.0 if len(closes) >= 6 else 0.0
    return rets, w5


def fetch_correlation_pairs() -> list[dict]:
    specs = [
        ("GC=F", "Oltin", "DX-Y.NYB", "DXY Dollar", "inverse"),
        ("^GSPC", "S&P 500", "^VIX", "VIX Qörquv", "inverse"),
        ("BTC-USD", "Bitcoin", "^IXIC", "Nasdaq", "positive"),
    ]
    out = []
    for s1, n1, s2, n2, expected in specs:
        r1, w1 = _daily_returns(s1)
        r2, w2 = _daily_returns(s2)
        if not r1 or not r2:
            continue
        corr = _pearson_corr(r1, r2)
        # Anomaliya aniqlash
        if expected == "inverse":
            is_anom = corr > 0.25 or (w1 > 1.0 and w2 > 1.0)
            note = "ANOMALIYA: Ikkalasi birga harakatlanmoqda!" if is_anom else "NORMAL: Klassik teskari muvozanat"
        else:
            is_anom = corr < -0.15
            note = "ANOMALIYA: Kripto va Nasdaq ajralib ketdi!" if is_anom else "NORMAL: Risk-on boğliqlik saqlanmoqda"
        out.append({
            "pair": f"{n1}  vs  {n2}",
            "n1": n1, "w1": w1,
            "n2": n2, "w2": w2,
            "corr": corr,
            "is_anom": is_anom,
            "note": note,
        })
    return out


def render_correlation_card(pairs: list[dict]) -> bytes:
    any_anom = any(p["is_anom"] for p in pairs)
    img, d = _base_card(
        1280, 720,
        "KORRELYATSIYA VA ANOMALIYA RADARI",
        "GLOBAL AKTIVLAR ÖRTASIDAGI BOĞLIQLIK TAHLILI (1 OYLIK)",
        accent=ORANGE if any_anom else CYAN,
    )

    y = 160
    for p in pairs:
        col = ORANGE if p["is_anom"] else GREEN
        d.rounded_rectangle([50, y, 1230, y + 142], radius=16, fill=CARD_BG, outline=col, width=2)
        d.text((80, y + 18), to_new_uzbek(p["pair"]), font=images._font(30, bold=True), fill=WHITE)

        # Status badge
        badge_txt = to_new_uzbek("⚡ ANOMALIYA" if p["is_anom"] else "✅ NORMAL")
        f_b = images._font(20, bold=True)
        bw = d.textlength(badge_txt, font=f_b) + 28
        d.rounded_rectangle([1200 - bw, y + 18, 1200, y + 54], radius=8, fill=col)
        d.text((1200 - bw + 14, y + 24), badge_txt, font=f_b, fill=NAVY_TOP)

        # 5 kunlik harakatlar
        m_txt = f"{p['n1']}: {p['w1']:+.2f}%   |   {p['n2']}: {p['w2']:+.2f}%   |   Korrelyatsiya (r): {p['corr']:+.2f}"
        d.text((80, y + 64), to_new_uzbek(m_txt), font=images._font(22, bold=True), fill=CYAN)
        d.text((80, y + 102), to_new_uzbek(p["note"]), font=images._font(20, bold=False), fill=GREY)
        y += 162

    return _to_jpeg(img)


def post_correlation_radar(dry_run: bool = False) -> bool:
    pairs = fetch_correlation_pairs()
    if not pairs:
        return False

    lines = []
    for p in pairs:
        icon = "⚡" if p["is_anom"] else "✅"
        p_name = p["pair"].replace("&", "&amp;")
        lines.append(
            f"{icon} <b>{p_name}</b> — Korrelyatsiya: <b>r = {p['corr']:+.2f}</b>\n"
            f"   5 kunlik: {p['n1'].replace('&', '&amp;')} (<b>{p['w1']:+.2f}%</b>) | {p['n2']} (<b>{p['w2']:+.2f}%</b>)\n"
            f"   <i>{p['note']}</i>"
        )

    html = (
        "🧠 <b>BOZOR KORRELYATSIYASI VA ANOMALIYA RADARI</b>\n"
        "<i>Aktivlar örtasidagi 1 oylik matematik boğliqlik (r = +1.0 birga, r = -1.0 teskari):</i>\n\n"
        + "\n\n".join(lines)
        + '\n\n<i>Manba: <a href="https://finance.yahoo.com/markets/">Yahoo Finance / Quantitative Correlation Data</a></i>'
    )
    img = render_correlation_card(pairs)
    if dry_run:
        print("\n[DRY RUN - CORRELATION RADAR]\n" + to_new_uzbek(html))
        return True
    telegram_api.send_post(html, img)
    db.add_post(None, f"corr-radar-{datetime.now(TASHKENT).strftime('%Y-W%W')}", "Korrelyatsiya va Anomaliya radari", "")
    log.info("Korrelyatsiya va Anomaliya radari muvaffaqiyatli chiqarildi!")
    return True
