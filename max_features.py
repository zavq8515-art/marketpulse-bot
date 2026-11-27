"""MARKETPULSE MAX FEATURES — 7 ta institutsional darajadagi professional rukn.

Barcha aksiya tahlillari faqat AAOIFI / Musaffa / Zoya skriningidan o'tgan
yirik (> $2B) kompaniyalar reyestri asosida ishlaydi.
QAT'IY QOIDA: Post matnida halollik/shariat/skrining nomlari UMUMAN ishlatilmaydi —
faqat sof moliyaviy, texnik va birja ma'lumotlari, #TIKER va giperhavolali manba beriladi.

Ruknlar:
1. Yirik Fondlar va Banklar Harakati (SEC 13D/13G + 13F + Form 4 Xarid/Sotuv)
2. Unusual Volume Radari (O'rtachadan 2x-3x yuqori savdo hajmi)
3. Real TradingView uslubidagi Texnik Tahlil Grafiklari (Candlestick + EMA 20/50/200 + RSI)
4. "Gigantlar Duelli" (Head-to-Head VS Infografika)
5. Fed Stavka Radari (FedWatch + Yield Curve Retsessiya Indikatori)
6. O'zbekiston Moliya Pulsi (Markaziy Bank USD/UZS, EUR/UZS + Global Oltin)
7. Haftalik "52-Week High / Low" Rekordchilar (All-Time/52W Scanner)
"""
import io
import logging
import math
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw

import db
import images
import telegram_api
from config import TASHKENT, USER_AGENT
from uz_alphabet import to_new_uzbek

log = logging.getLogger("max_features")

W, H = 1280, 720
NAVY_TOP = (6, 16, 38)
NAVY_BOTTOM = (10, 34, 74)
CARD_BG = (13, 28, 56)
CHART_BG = (11, 20, 38)
BORDER = (30, 62, 114)
CYAN = (0, 212, 255)
GREEN = (34, 211, 130)
RED = (248, 81, 100)
GOLD = (255, 195, 0)
PURPLE = (180, 110, 255)
ORANGE = (255, 145, 50)
WHITE = (245, 248, 255)
GREY = (150, 172, 204)

# Ichki skriningdan o'tgan >$2B yirik kompaniyalar reyestri (faqat ichki filtr)
SCREENED_TICKERS = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "TSLA", "ASML", "TSM", "LLY",
    "ISRG", "CRM", "ADBE", "AMD", "PLTR", "NOW", "QCOM", "PANW",
    "DE", "CAT", "UBER", "VRTX", "AVGO", "ORCL", "AMAT", "LRCX",
    "KLAC", "SNPS", "CDNS", "MU", "CRWD", "ANET", "SYK", "TMO",
    "DHR", "REGN", "NVO", "ZTS", "ETN", "HON", "COST", "WMT",
    "PG", "NKE", "XOM", "CVX",
]

SCREENED_SET = set(SCREENED_TICKERS)

COMPANY_NAMES = {
    "NVDA": "NVIDIA", "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
    "TSLA": "Tesla", "ASML": "ASML Holding", "TSM": "TSMC", "LLY": "Eli Lilly",
    "ISRG": "Intuitive Surgical", "CRM": "Salesforce", "ADBE": "Adobe", "AMD": "AMD",
    "PLTR": "Palantir", "NOW": "ServiceNow", "QCOM": "Qualcomm", "PANW": "Palo Alto",
    "DE": "John Deere", "CAT": "Caterpillar", "UBER": "Uber", "VRTX": "Vertex Pharma",
    "AVGO": "Broadcom", "ORCL": "Oracle", "AMAT": "Applied Materials", "LRCX": "Lam Research",
    "KLAC": "KLA Corp", "SNPS": "Synopsys", "CDNS": "Cadence", "MU": "Micron",
    "CRWD": "CrowdStrike", "ANET": "Arista Networks", "SYK": "Stryker", "TMO": "Thermo Fisher",
    "DHR": "Danaher", "REGN": "Regeneron", "NVO": "Novo Nordisk", "ZTS": "Zoetis",
    "ETN": "Eaton", "HON": "Honeywell", "COST": "Costco", "WMT": "Walmart",
    "PG": "Procter & Gamble", "NKE": "Nike", "XOM": "ExxonMobil", "CVX": "Chevron",
}

SEC_HEADERS = {"User-Agent": "MarketPulseResearch contact@marketpulse.uz"}


# ==============================================================================
# UMUMIY YORDAMCHI FUNKSIYALAR
# ==============================================================================

def _new_canvas(badge_text: str, title_text: str, accent_color=CYAN):
    badge_text = to_new_uzbek(badge_text)
    title_text = to_new_uzbek(title_text)
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

    f_badge = images._font(21, bold=True)
    bw = d.textlength(badge_text, font=f_badge) + 32
    d.rounded_rectangle([50, 30, 50 + bw, 68], radius=8, fill=accent_color)
    d.text((66, 36), badge_text, font=f_badge, fill=NAVY_TOP)

    date_str = datetime.now(TASHKENT).strftime("%d.%m.%Y • %H:%M (Toshkent)")
    f_date = images._font(20, bold=False)
    d.text((W - 50 - d.textlength(date_str, font=f_date), 38), date_str, font=f_date, fill=GREY)

    f_title = images._font(40, bold=True)
    d.text((50, 80), title_text, font=f_title, fill=WHITE)

    d.line([(50, H - 66), (W - 50, H - 66)], fill=BORDER, width=2)
    f_brand = images._font(28, bold=True)
    d.text((50, H - 52), "MARKETPULSE", font=f_brand, fill=WHITE)
    f_chan = images._font(21, bold=True)
    chan_txt = "t.me/MarketPulseZK"
    d.text((W - 50 - d.textlength(chan_txt, font=f_chan), H - 48), chan_txt, font=f_chan, fill=CYAN)

    return img, d


def _to_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=93)
    return buf.getvalue()


def _yahoo_ohlcv(sym: str, range_str: str = "6mo", interval: str = "1d") -> dict | None:
    """Yahoo Finance v8 chart API dan to'liq OHLCV tarixini oladi."""
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
            params={"range": range_str, "interval": interval},
            headers={"User-Agent": USER_AGENT},
            timeout=12,
        )
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        meta = res["meta"]
        q = res["indicators"]["quote"][0]
        timestamps = res.get("timestamp") or []
        opens, highs, lows, closes, vols = q.get("open", []), q.get("high", []), q.get("low", []), q.get("close", []), q.get("volume", [])

        candles = []
        for i in range(len(timestamps)):
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]
            v = vols[i] if i < len(vols) and vols[i] is not None else 0
            if None in (o, h, l, c):
                continue
            candles.append({
                "ts": timestamps[i],
                "o": float(o),
                "h": float(h),
                "l": float(l),
                "c": float(c),
                "v": float(v),
            })
        if len(candles) < 5:
            return None
        return {"symbol": sym, "meta": meta, "candles": candles}
    except Exception as e:
        log.debug("OHLCV error for %s: %s", sym, e)
        return None


def _calc_ema(values: list[float], period: int) -> list[float | None]:
    if len(values) < period:
        return [None] * len(values)
    k = 2.0 / (period + 1)
    ema = [None] * (period - 1)
    sma = sum(values[:period]) / period
    ema.append(sma)
    prev = sma
    for val in values[period:]:
        cur = val * k + prev * (1 - k)
        ema.append(cur)
        prev = cur
    return ema


def _calc_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    if len(closes) <= period:
        return [None] * len(closes)
    rsis = [None] * period
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    rs = (avg_g / avg_l) if avg_l != 0 else 100.0
    rsis.append(100.0 - (100.0 / (1.0 + rs)))

    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        g = max(diff, 0.0)
        l = max(-diff, 0.0)
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
        rs = (avg_g / avg_l) if avg_l != 0 else 100.0
        rsis.append(100.0 - (100.0 / (1.0 + rs)))
    return rsis


# ==============================================================================
# 1. YIRIK FONDLAR VA BANKLAR HARAKATI (SEC 13D/13G + 13F + INSAYDER XARID/SOTUV)
# ==============================================================================

def _fetch_screened_openinsider() -> list[dict]:
    """OpenInsider screener orqali faqat skriningdan o'tgan yirik aksiyalardagi >$1M SEC Form 4 xarid/sotuvlarini oladi."""
    items = []
    tickers_param = "+".join(SCREENED_TICKERS[:28])
    url = (
        f"http://openinsider.com/screener?s={tickers_param}"
        "&fd=30&xp=1&xs=1&vl=1000&cnt=30&page=1"
    )
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table", class_="tinytable")
        if not table:
            return []
        seen = set()
        for tr in table.find_all("tr")[1:40]:
            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(tds) < 13:
                continue
            sym = tds[3].strip().upper()
            if sym not in SCREENED_SET:
                continue
            val_str = tds[12].strip()
            if not (val_str.startswith("+$") or val_str.startswith("-$")):
                continue
            act_type = "BUY" if val_str.startswith("+$") else "SELL"
            dedup_key = f"{sym}_{act_type}_{tds[5].strip()[:12]}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            items.append({
                "symbol": sym,
                "company": COMPANY_NAMES.get(sym, tds[4].strip()[:24]),
                "actor": tds[5].strip()[:24],
                "role": tds[6].strip()[:20],
                "value": val_str,
                "price": tds[8].strip(),
                "date": tds[2].strip(),
                "type": act_type,
            })
            if len(items) >= 5:
                break
    except Exception as e:
        log.debug("OpenInsider screener error: %s", e)
    return items


def _fetch_sec_13dg_filings() -> list[dict]:
    """SEC EDGAR Full-Text Search orqali eng so'nggi 13D / 13G yirik fondlar hisobotlarini oladi."""
    filings = []
    start_dt = (datetime.now(TASHKENT) - timedelta(days=14)).strftime("%Y-%m-%d")
    end_dt = datetime.now(TASHKENT).strftime("%Y-%m-%d")
    major_funds = ("BlackRock", "Vanguard", "Berkshire", "Bridgewater", "Citadel", "State Street", "Morgan Stanley", "FMR")
    try:
        r = requests.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={
                "q": '"BlackRock" OR "Vanguard" OR "Berkshire" OR "Citadel"',
                "forms": "SC 13G,SC 13D,SC 13G/A,SC 13D/A",
                "dateRange": "custom",
                "startdt": start_dt,
                "enddt": end_dt,
            },
            headers=SEC_HEADERS,
            timeout=15,
        )
        if r.status_code != 200:
            return []
        hits = (r.json().get("hits") or {}).get("hits") or []
        seen = set()
        for h in hits[:40]:
            src = h.get("_source") or {}
            names = src.get("display_names") or []
            joined = " ".join(names)
            matched_sym = None
            for sym in SCREENED_TICKERS:
                cname = COMPANY_NAMES.get(sym, "")
                if (cname and cname.lower() in joined.lower()) or f"({sym})" in joined.upper():
                    matched_sym = sym
                    break
            if not matched_sym or matched_sym in seen:
                continue
            fund_name = next((f for f in major_funds if f.lower() in joined.lower()), names[0][:24] if names else "Institutsional fond")
            seen.add(matched_sym)
            filings.append({
                "symbol": matched_sym,
                "company": COMPANY_NAMES.get(matched_sym, matched_sym),
                "actor": fund_name,
                "role": src.get("form", "SC 13G"),
                "value": "5%+ Ulush hisoboti",
                "price": src.get("file_date", ""),
                "date": src.get("file_date", ""),
                "type": "FUND",
            })
            if len(filings) >= 3:
                break
    except Exception as e:
        log.debug("SEC 13D/G fetch error: %s", e)
    return filings


def render_institutional_card(records: list[dict]) -> bytes:
    img, d = _new_canvas("SEC 13D / 13G • FORM 4", "YIRIK FONDLAR VA INSAYDERLAR HARAKATI", accent_color=GOLD)

    y = 148
    d.rounded_rectangle([50, y, W - 50, y + 44], radius=8, fill=(20, 48, 92))
    f_hdr = images._font(19, bold=True)
    d.text((70, y + 11), "TUR", font=f_hdr, fill=CYAN)
    d.text((195, y + 11), "TIKER / KOMPANIYA", font=f_hdr, fill=CYAN)
    d.text((545, y + 11), "FOND / INSAYDER", font=f_hdr, fill=CYAN)
    d.text((970, y + 11), "HAJM / HOLAT", font=f_hdr, fill=CYAN)

    y += 56
    for idx, rec in enumerate(records[:6]):
        bg = CARD_BG if idx % 2 == 0 else (10, 24, 52)
        d.rounded_rectangle([50, y, W - 50, y + 68], radius=10, fill=bg, outline=BORDER, width=1)
        if rec["type"] == "BUY":
            tag, col = "XARID", GREEN
        elif rec["type"] == "SELL":
            tag, col = "SOTUV", RED
        else:
            tag, col = "13D/13G", CYAN

        d.rounded_rectangle([66, y + 17, 174, y + 51], radius=6, fill=col)
        tw = d.textlength(tag, font=images._font(18, bold=True))
        d.text((120 - tw / 2, y + 23), tag, font=images._font(18, bold=True), fill=NAVY_TOP)

        d.text((195, y + 10), f"#{rec['symbol']}", font=images._font(24, bold=True), fill=GOLD)
        d.text((195, y + 39), rec["company"][:22], font=images._font(18, bold=False), fill=GREY)

        d.text((545, y + 10), rec["actor"][:25], font=images._font(21, bold=True), fill=WHITE)
        d.text((545, y + 39), f"{rec['role']} • {rec['date']}", font=images._font(17, bold=False), fill=GREY)

        d.text((970, y + 20), rec["value"][:20], font=images._font(23, bold=True), fill=col)
        y += 76

    return _to_jpeg(img)


def post_institutional_flows(dry_run: bool = False) -> bool:
    insider_moves = _fetch_screened_openinsider()
    funds = _fetch_sec_13dg_filings()

    records = funds + insider_moves
    if not records:
        log.warning("Yirik fondlar/insayderlar bo'yicha yangi yozuv topilmadi.")
        return False

    lines = []
    for r in records[:6]:
        if r["type"] == "BUY":
            icon, act = "🟢", "Yirik xarid"
        elif r["type"] == "SELL":
            icon, act = "🔴", "Yirik sotuv"
        else:
            icon, act = "🏦", f"Fond hisoboti ({r['role']})"
        lines.append(
            f"{icon} <b>#{r['symbol']}</b> ({r['company']}) — <b>{act}</b>\n"
            f"   Ishtirokchi: <b>{r['actor']}</b> | Hajm: <b>{r['value']}</b>"
        )

    html = (
        "🏦 <b>YIRIK FONDLAR VA INSAYDERLAR HARAKATI (SEC)</b>\n"
        "<i>Yirik fondlar (13D/13G) hamda kompaniya rahbarlari (Form 4) amalga oshirgan asosiy bitimlar:</i>\n\n"
        + "\n\n".join(lines)
        + '\n\n<i>Manba: <a href="https://www.sec.gov/edgar/searchedgar/companysearch">SEC EDGAR (13D / 13G / Form 4)</a></i>'
    )
    img = render_institutional_card(records)
    if dry_run:
        print("\n[DRY RUN - INSTITUTIONAL FLOWS]\n" + html)
        return True
    telegram_api.send_post(html, img)
    db.add_post(None, f"inst-flows-{datetime.now(TASHKENT).strftime('%Y-%m-%d')}", "SEC Institutional & Insider Flows", "")
    log.info("Yirik fondlar va insayderlar posti muvaffaqiyatli chiqarildi!")
    return True


# ==============================================================================
# 2. UNUSUAL VOLUME RADARI (G'AYRITABIIY SAVDO HAJMI)
# ==============================================================================

def scan_unusual_volume() -> list[dict]:
    """Skriningdan o'tgan yirik aksiyalar ichida kunlik savdo hajmi 20 kunlik o'rtachadan keskin oshganlarini topadi."""
    hits = []
    for sym in SCREENED_TICKERS:
        data = _yahoo_ohlcv(sym, range_str="1mo", interval="1d")
        if not data or len(data["candles"]) < 10:
            continue
        candles = data["candles"]
        latest = candles[-1]
        prev = candles[-2]
        hist_vols = [c["v"] for c in candles[:-1] if c["v"] > 0]
        if not hist_vols or latest["v"] <= 0:
            continue
        avg_vol = sum(hist_vols) / len(hist_vols)
        ratio = latest["v"] / avg_vol
        pct = ((latest["c"] - prev["c"]) / prev["c"] * 100.0) if prev["c"] else 0.0
        hits.append({
            "symbol": sym,
            "name": COMPANY_NAMES.get(sym, sym),
            "price": latest["c"],
            "pct": pct,
            "volume": latest["v"],
            "avg_vol": avg_vol,
            "ratio": ratio,
        })
    hits.sort(key=lambda x: -x["ratio"])
    # Avval >= 1.5x bo'lganlarni, kam bo'lsa eng yuqori 5 tasini olamiz
    strong = [h for h in hits if h["ratio"] >= 1.5]
    return strong[:5] if len(strong) >= 3 else hits[:5]


def _fmt_vol(v: float) -> str:
    if v >= 1e9:
        return f"{v / 1e9:.2f}B"
    if v >= 1e6:
        return f"{v / 1e6:.1f}M"
    return f"{v / 1e3:.0f}K"


def render_unusual_volume_card(items: list[dict]) -> bytes:
    img, d = _new_canvas("UNUSUAL VOLUME RADAR • SMART MONEY", "G‘AYRITABIIY SAVDO HAJMI KUZATILGAN AKSIYALAR", accent_color=ORANGE)

    max_ratio = max([x["ratio"] for x in items] + [2.5])
    y = 158
    for item in items[:5]:
        d.rounded_rectangle([50, y, W - 50, y + 86], radius=12, fill=CARD_BG, outline=BORDER, width=1)
        col = GREEN if item["pct"] >= 0 else RED
        d.rounded_rectangle([62, y + 14, 70, y + 72], radius=4, fill=col)

        d.text((88, y + 12), f"#{item['symbol']}", font=images._font(28, bold=True), fill=WHITE)
        d.text((88, y + 48), item["name"], font=images._font(19, bold=False), fill=GREY)

        # Narx va kunlik foiz
        d.text((310, y + 14), f"${item['price']:,.2f}", font=images._font(26, bold=True), fill=WHITE)
        d.text((310, y + 48), f"{item['pct']:+.2f}%", font=images._font(21, bold=True), fill=col)

        # Hajm taqqoslash progress bari
        bar_x1, bar_x2 = 520, 960
        bar_w = int((item["ratio"] / max_ratio) * (bar_x2 - bar_x1))
        d.rounded_rectangle([bar_x1, y + 26, bar_x2, y + 58], radius=8, fill=(22, 42, 78))
        d.rounded_rectangle([bar_x1, y + 26, bar_x1 + max(24, bar_w), y + 58], radius=8, fill=GOLD if item["ratio"] >= 2.0 else CYAN)

        # Koeffitsiyent va real hajm
        ratio_txt = f"{item['ratio']:.2f}x"
        d.text((990, y + 12), ratio_txt, font=images._font(32, bold=True), fill=GOLD if item["ratio"] >= 2.0 else CYAN)
        vol_txt = f"{_fmt_vol(item['volume'])} (o‘rt: {_fmt_vol(item['avg_vol'])})"
        d.text((990, y + 50), vol_txt, font=images._font(17, bold=False), fill=GREY)

        y += 96

    return _to_jpeg(img)


def post_unusual_volume(dry_run: bool = False) -> bool:
    items = scan_unusual_volume()
    if not items:
        return False

    lines = []
    for it in items:
        flow = "🟢 Xarid oqimi" if it["pct"] >= 0 else "🔴 Sotuv bosimi"
        lines.append(
            f"⚡ <b>#{it['symbol']}</b> ({it['name']}) — Hajm: <b>{it['ratio']:.2f}x</b> ({_fmt_vol(it['volume'])} dona)\n"
            f"   Narx: <b>${it['price']:,.2f} ({it['pct']:+.2f}%)</b> | {flow}"
        )

    html = (
        "⚡ <b>UNUSUAL VOLUME RADARI: G‘AYRITABIIY SAVDO HAJMI</b>\n"
        "<i>Kunlik savdo hajmi o‘zining 20 kunlik o‘rtachasidan eng keskin oshgan yirik aksiyalar:</i>\n\n"
        + "\n\n".join(lines)
        + '\n\n<i>Manba: <a href="https://finance.yahoo.com/markets/stocks/most-active/">Yahoo Finance / NASDAQ Volume Radar</a></i>'
    )
    img = render_unusual_volume_card(items)
    if dry_run:
        print("\n[DRY RUN - UNUSUAL VOLUME]\n" + html)
        return True
    telegram_api.send_post(html, img)
    db.add_post(None, f"unusual-vol-{datetime.now(TASHKENT).strftime('%Y-%m-%d')}", "Unusual Volume Radar", "")
    log.info("Unusual Volume Radari muvaffaqiyatli chiqarildi!")
    return True


# ==============================================================================
# 3. REAL TRADINGVIEW USLUBIDAGI TEXNIK TAHLIL GRAFIKLARI (CANDLESTICK + EMA + RSI)
# ==============================================================================

CHART_ROTATION = ["NVDA", "TSLA", "AAPL", "MSFT", "GOOGL", "AMD", "PLTR", "ASML", "LLY", "AVGO", "CRM", "PANW", "UBER", "CAT"]


def _get_next_chart_symbol() -> str:
    for sym in CHART_ROTATION:
        if not db.is_feature_done("tech_chart_sym", sym):
            return sym
    return CHART_ROTATION[0]


def render_candlestick_chart(symbol: str, candles: list[dict], ema20, ema50, ema200, rsis, sup: float, res: float) -> bytes:
    """TradingView qorong'i mavzusida 1280x720 shamchali grafik + EMA 20/50/200 + Support/Resistance + RSI(14)."""
    name = COMPANY_NAMES.get(symbol, symbol)
    last_c = candles[-1]["c"]
    prev_c = candles[-2]["c"]
    pct = ((last_c - prev_c) / prev_c * 100.0) if prev_c else 0.0

    img, d = _new_canvas(
        f"TEXNIK TAHLIL • #{symbol}",
        f"{name.upper()} — KUNLIK GRAFIK (EMA & RSI)",
        accent_color=GREEN if pct >= 0 else RED,
    )

    # Oxirgi 65 kunni chizamiz (hisob-kitoblar 6 oylik/1 yillik tarixdan olingan)
    n = min(65, len(candles))
    vis_c = candles[-n:]
    vis_e20 = ema20[-n:]
    vis_e50 = ema50[-n:]
    vis_e200 = ema200[-n:]
    vis_rsi = rsis[-n:]

    # Grafik maydonlari
    cx1, cx2 = 60, 1140
    cy1, cy2 = 148, 495     # Asosiy shamlar maydoni
    ry1, ry2 = 522, 636     # Pastki RSI(14) maydoni

    d.rounded_rectangle([cx1, cy1, cx2, cy2], radius=8, fill=CHART_BG, outline=BORDER, width=1)
    d.rounded_rectangle([cx1, ry1, cx2, ry2], radius=8, fill=CHART_BG, outline=BORDER, width=1)

    # Narx shkalasi
    all_prices = [c["h"] for c in vis_c] + [c["l"] for c in vis_c] + [sup, res]
    for arr in (vis_e20, vis_e50, vis_e200):
        all_prices.extend([v for v in arr if v is not None])
    p_min = min(all_prices) * 0.985
    p_max = max(all_prices) * 1.015
    p_span = max(p_max - p_min, 0.01)

    def py(price: float) -> int:
        return int(cy2 - ((price - p_min) / p_span) * (cy2 - cy1 - 24) - 12)

    # Gorizontal panjara va o'ng narx o'qi
    f_ax = images._font(17, bold=False)
    for step in range(5):
        val = p_min + (p_span * step / 4.0)
        yy = py(val)
        d.line([(cx1 + 2, yy), (cx2 - 2, yy)], fill=(22, 38, 66), width=1)
        d.text((cx2 + 12, yy - 9), f"${val:,.1f}", font=f_ax, fill=GREY)

    # Support va Resistance chiziqlari
    for lvl, lcol, ltxt in ((res, RED, f"RES ${res:,.1f}"), (sup, GREEN, f"SUP ${sup:,.1f}")):
        yy = py(lvl)
        for sx in range(cx1 + 8, cx2 - 8, 16):
            d.line([(sx, yy), (min(sx + 9, cx2 - 8), yy)], fill=lcol, width=2)
        d.rounded_rectangle([cx1 + 10, yy - 22, cx1 + 148, yy - 2], radius=4, fill=(14, 26, 48))
        d.text((cx1 + 16, yy - 20), ltxt, font=images._font(15, bold=True), fill=lcol)

    # Shamchalar (Candlesticks)
    step_x = (cx2 - cx1 - 24) / float(n)
    body_w = max(4, int(step_x * 0.62))

    def px(idx: int) -> int:
        return int(cx1 + 12 + idx * step_x + step_x / 2)

    for i, c in enumerate(vis_c):
        x = px(i)
        col = GREEN if c["c"] >= c["o"] else RED
        yh, yl, yo, yc = py(c["h"]), py(c["l"]), py(c["o"]), py(c["c"])
        d.line([(x, yh), (x, yl)], fill=col, width=2)
        top_b, bot_b = min(yo, yc), max(yo, yc)
        if bot_b - top_b < 2:
            bot_b = top_b + 2
        d.rectangle([x - body_w // 2, top_b, x + body_w // 2, bot_b], fill=col)

    # EMA chiziqlari (EMA 20 = Cyan, EMA 50 = Gold, EMA 200 = Purple)
    for arr, ecol in ((vis_e20, CYAN), (vis_e50, GOLD), (vis_e200, PURPLE)):
        pts = [(px(i), py(v)) for i, v in enumerate(arr) if v is not None]
        if len(pts) >= 2:
            d.line(pts, fill=ecol, width=3)

    # Legenda (yuqori chap ichkarida)
    f_leg = images._font(17, bold=True)
    d.text((cx1 + 16, cy1 + 10), "EMA 20", font=f_leg, fill=CYAN)
    d.text((cx1 + 98, cy1 + 10), "EMA 50", font=f_leg, fill=GOLD)
    d.text((cx1 + 180, cy1 + 10), "EMA 200", font=f_leg, fill=PURPLE)

    # Joriy narx belgi (o'ng o'qda)
    ly = py(last_c)
    d.rounded_rectangle([cx2 + 6, ly - 13, W - 20, ly + 13], radius=5, fill=GREEN if pct >= 0 else RED)
    d.text((cx2 + 12, ly - 10), f"${last_c:,.1f}", font=images._font(17, bold=True), fill=NAVY_TOP)

    # RSI(14) sub-grafigi
    def ry(val: float) -> int:
        return int(ry2 - (val / 100.0) * (ry2 - ry1 - 14) - 7)

    for lvl, lcol in ((70, RED), (50, GREY), (30, GREEN)):
        yy = ry(lvl)
        for sx in range(cx1 + 6, cx2 - 6, 14):
            d.line([(sx, yy), (min(sx + 7, cx2 - 6), yy)], fill=lcol, width=1)
        d.text((cx2 + 12, yy - 8), str(lvl), font=images._font(15, bold=False), fill=lcol)

    rsi_pts = [(px(i), ry(v)) for i, v in enumerate(vis_rsi) if v is not None]
    if len(rsi_pts) >= 2:
        d.line(rsi_pts, fill=CYAN, width=3)

    cur_rsi = next((v for v in reversed(vis_rsi) if v is not None), 50.0)
    d.text((cx1 + 14, ry1 + 6), f"RSI (14): {cur_rsi:.1f}", font=images._font(17, bold=True), fill=WHITE)

    return _to_jpeg(img)


def post_technical_chart(symbol: str = None, dry_run: bool = False) -> bool:
    sym = (symbol or _get_next_chart_symbol()).upper()
    data = _yahoo_ohlcv(sym, range_str="1y", interval="1d")
    if not data or len(data["candles"]) < 55:
        log.warning("Texnik grafik uchun yetarli tarix topilmadi: %s", sym)
        return False

    candles = data["candles"]
    closes = [c["c"] for c in candles]
    ema20 = _calc_ema(closes, 20)
    ema50 = _calc_ema(closes, 50)
    ema200 = _calc_ema(closes, 200)
    rsis = _calc_rsi(closes, 14)

    last_c = closes[-1]
    prev_c = closes[-2]
    pct = ((last_c - prev_c) / prev_c * 100.0) if prev_c else 0.0
    cur_e20 = ema20[-1]
    cur_e50 = ema50[-1]
    cur_e200 = ema200[-1]
    cur_rsi = rsis[-1] or 50.0

    # Oxirgi 45 kundan Support va Resistance darajalari
    recent_45 = candles[-45:]
    sup = min(c["l"] for c in recent_45)
    res = max(c["h"] for c in recent_45)

    if cur_e50 and last_c > cur_e50 and (not cur_e200 or cur_e50 > cur_e200):
        trend_txt = "🟢 Yuqoriga yo‘nalgan (Buqa trendi)"
    elif cur_e50 and last_c < cur_e50 and (not cur_e200 or cur_e50 < cur_e200):
        trend_txt = "🔴 Pastga yo‘nalgan (Ayiq trendi)"
    else:
        trend_txt = "🟡 Konsolidatsiya / Yonlama harakat"

    if cur_rsi >= 70:
        rsi_zone = "Haddan tashqari xarid (Overbought — tuzatish xavfi)"
    elif cur_rsi <= 30:
        rsi_zone = "Haddan tashqari sotuv (Oversold — tiklanish zonasi)"
    else:
        rsi_zone = "Muvozanatli (Neytral zona)"

    e200_str = f"${cur_e200:,.2f}" if cur_e200 else "—"
    name = COMPANY_NAMES.get(sym, sym)

    html = (
        f"📈 <b>TEXNIK TAHLIL GRAFIGI: #{sym} ({name})</b>\n\n"
        f"• Joriy narx: <b>${last_c:,.2f} ({pct:+.2f}%)</b>\n"
        f"• Asosiy trend: <b>{trend_txt}</b>\n"
        f"• <b>EMA darajalari:</b> EMA20: ${cur_e20:,.2f} | EMA50: ${cur_e50:,.2f} | EMA200: {e200_str}\n"
        f"• <b>RSI (14):</b> <b>{cur_rsi:.1f}</b> — <i>{rsi_zone}</i>\n"
        f"• <b>Asosiy darajalar (45 kun):</b> Support (Qo‘llab-quvvatlash) <b>${sup:,.2f}</b> | Resistance (Qarshilik) <b>${res:,.2f}</b>\n\n"
        f'<i>Manba: <a href="https://finance.yahoo.com/quote/{sym}">Yahoo Finance / Technical Chart</a></i>'
    )
    img = render_candlestick_chart(sym, candles, ema20, ema50, ema200, rsis, sup, res)
    if dry_run:
        print(f"\n[DRY RUN - TECHNICAL CHART #{sym}]\n" + html)
        return True
    telegram_api.send_post(html, img)
    db.mark_feature_done("tech_chart_sym", sym)
    db.add_post(None, f"tech-chart-{sym.lower()}-{datetime.now(TASHKENT).strftime('%Y-%m-%d')}", f"#{sym} Texnik tahlil", "")
    log.info("Texnik tahlil grafigi (#%s) muvaffaqiyatli chiqarildi!", sym)
    return True


# ==============================================================================
# 4. "GIGANTLAR DUELLI" (HEAD-TO-HEAD VS INFOGRAFIKA)
# ==============================================================================

DUEL_PAIRS = [
    ("NVDA", "AMD", "AI va Yarimo‘tkazgichlar jangi"),
    ("AAPL", "MSFT", "Texnologiya gigantlari to‘qnashuvi"),
    ("LLY", "NVO", "Farmatsevtika liderlari duelli"),
    ("ASML", "TSM", "Chip sanoati yuragi: Uskuna vs Ishlab chiqarish"),
    ("WMT", "COST", "Chakana savdo gigantlari"),
    ("CAT", "DE", "Og‘ir sanoat va aqlli texnika"),
    ("PANW", "CRWD", "Kiberxavfsizlik liderlari"),
    ("CRM", "NOW", "Korporativ bulut va AI agentlar"),
    ("XOM", "CVX", "Global energetika gigantlari"),
    ("GOOGL", "TSLA", "Sun’iy intellekt va avtonom kelajak"),
]


def _duel_stats(sym: str) -> dict | None:
    data = _yahoo_ohlcv(sym, range_str="1y", interval="1d")
    if not data or len(data["candles"]) < 25:
        return None
    c = data["candles"]
    cur = c[-1]["c"]
    first = c[0]["c"]
    m1 = c[-21]["c"] if len(c) >= 21 else first
    high52 = max(x["h"] for x in c)
    low52 = min(x["l"] for x in c)
    return {
        "symbol": sym,
        "name": COMPANY_NAMES.get(sym, sym),
        "price": cur,
        "ret_1y": (cur - first) / first * 100.0,
        "ret_1m": (cur - m1) / m1 * 100.0,
        "high52": high52,
        "low52": low52,
        "from_high": (cur - high52) / high52 * 100.0,
    }


def render_duel_card(a: dict, b: dict, subtitle: str) -> bytes:
    img, d = _new_canvas("GIGANTLAR DUELLI • HEAD-TO-HEAD", f"#{a['symbol']}  VS  #{b['symbol']} — {subtitle.upper()[:32]}", accent_color=GOLD)

    # Chap karta (A - Cyan) va O'ng karta (B - Gold)
    d.rounded_rectangle([50, 152, 600, 622], radius=16, fill=CARD_BG, outline=CYAN, width=3)
    d.rounded_rectangle([680, 152, W - 50, 622], radius=16, fill=CARD_BG, outline=GOLD, width=3)

    # Markaziy VS aylana
    d.ellipse([588, 336, 692, 440], fill=GOLD, outline=NAVY_TOP, width=5)
    f_vs = images._font(42, bold=True)
    d.text((640 - d.textlength("VS", font=f_vs) / 2, 362), "VS", font=f_vs, fill=NAVY_TOP)

    for st, x1, col in ((a, 80, CYAN), (b, 710, GOLD)):
        d.text((x1, 174), f"#{st['symbol']}", font=images._font(48, bold=True), fill=col)
        d.text((x1, 232), st["name"], font=images._font(26, bold=True), fill=WHITE)

        metrics = [
            ("Joriy aksiya narxi", f"${st['price']:,.2f}", WHITE),
            ("1 yillik daromadlilik", f"{st['ret_1y']:+.2f}%", GREEN if st["ret_1y"] >= 0 else RED),
            ("Oxirgi 1 oylik harakat", f"{st['ret_1m']:+.2f}%", GREEN if st["ret_1m"] >= 0 else RED),
            ("52 haftalik maksimumdan", f"{st['from_high']:.1f}%", ORANGE if st["from_high"] < -15 else CYAN),
            ("52 haftalik diapazon", f"${st['low52']:,.0f} – ${st['high52']:,.0f}", GREY),
        ]
        y = 285
        for lbl, val, vcol in metrics:
            d.text((x1, y), lbl, font=images._font(18, bold=False), fill=GREY)
            d.text((x1, y + 23), val, font=images._font(27, bold=True), fill=vcol)
            y += 65

    return _to_jpeg(img)


def post_giant_duel(dry_run: bool = False) -> bool:
    chosen_idx = 0
    for idx in range(len(DUEL_PAIRS)):
        if not db.is_feature_done("giant_duel", f"duel_{idx}"):
            chosen_idx = idx
            break
    sym_a, sym_b, subtitle = DUEL_PAIRS[chosen_idx]
    a, b = _duel_stats(sym_a), _duel_stats(sym_b)
    if not a or not b:
        return False

    winner = a if a["ret_1y"] >= b["ret_1y"] else b
    html = (
        f"⚔️ <b>GIGANTLAR DUELLI: #{a['symbol']} vs #{b['symbol']}</b>\n"
        f"<i>{subtitle}</i>\n\n"
        f"🔹 <b>#{a['symbol']} ({a['name']}):</b>\n"
        f"• Narx: <b>${a['price']:,.2f}</b> | 1 yillik: <b>{a['ret_1y']:+.2f}%</b> | 1 oylik: {a['ret_1m']:+.2f}%\n"
        f"• 52W cho‘qqidan farq: {a['from_high']:.1f}%\n\n"
        f"🔸 <b>#{b['symbol']} ({b['name']}):</b>\n"
        f"• Narx: <b>${b['price']:,.2f}</b> | 1 yillik: <b>{b['ret_1y']:+.2f}%</b> | 1 oylik: {b['ret_1m']:+.2f}%\n"
        f"• 52W cho‘qqidan farq: {b['from_high']:.1f}%\n\n"
        f"🏆 <b>1 yillik o‘sish yetakchisi:</b> <b>#{winner['symbol']}</b> ({winner['ret_1y']:+.2f}%)\n"
        f"👇 <i>Siz uzoq muddatga qaysi birini tanlagan bo‘lardingiz?</i>\n\n"
        '<i>Manba: <a href="https://finance.yahoo.com">Yahoo Finance / NASDAQ</a></i>'
    )
    img = render_duel_card(a, b, subtitle)
    if dry_run:
        print(f"\n[DRY RUN - GIANT DUEL #{sym_a} vs #{sym_b}]\n" + html)
        return True
    telegram_api.send_post(html, img)
    db.mark_feature_done("giant_duel", f"duel_{chosen_idx}")
    db.add_post(None, f"duel-{sym_a.lower()}-{sym_b.lower()}", f"#{sym_a} vs #{sym_b}", "")
    log.info("Gigantlar duelli (#%s vs #%s) muvaffaqiyatli chiqarildi!", sym_a, sym_b)
    return True


# ==============================================================================
# 5. FED STAVKA RADARI (FEDWATCH + YIELD CURVE RETSESSIYA INDIKATORI)
# ==============================================================================

# FOMC yig'ilish sanalari (2026-2027)
FOMC_DATES = [
    date(2026, 12, 9),
    date(2027, 1, 27),
    date(2027, 3, 17),
    date(2027, 4, 28),
    date(2027, 6, 9),
    date(2027, 7, 28),
    date(2027, 9, 15),
    date(2027, 10, 27),
    date(2027, 12, 8),
]


def fetch_fed_and_yield_curve() -> dict | None:
    points = []
    for sym, label in (("^IRX", "3 Oy (Fed)"), ("^FVX", "5 Yil"), ("^TNX", "10 Yil"), ("^TYX", "30 Yil")):
        d = _yahoo_ohlcv(sym, range_str="5d", interval="1d")
        if d:
            val = d["candles"][-1]["c"]
            prev = d["candles"][-2]["c"]
            points.append({"sym": sym, "label": label, "val": val, "diff_bp": (val - prev) * 100.0})
    if len(points) < 3:
        return None

    y3m = next((p["val"] for p in points if p["sym"] == "^IRX"), points[0]["val"])
    y10 = next((p["val"] for p in points if p["sym"] == "^TNX"), points[-1]["val"])
    spread_10_3m = y10 - y3m

    today = datetime.now(TASHKENT).date()
    next_fomc = next((dt for dt in FOMC_DATES if dt >= today), today + timedelta(days=30))
    days_left = (next_fomc - today).days

    if spread_10_3m < 0:
        curve_status = "🔴 TESKARI (Inverted — Retsessiya ogohlantirishi)"
        curve_col = RED
    elif spread_10_3m < 0.35:
        curve_status = "🟡 TEKIS (Flat — Ehtiyotkorlik zonasi)"
        curve_col = GOLD
    else:
        curve_status = "🟢 NORMAL (Ijobiy iqtisodiy kutilma)"
        curve_col = GREEN

    return {
        "points": points,
        "y3m": y3m,
        "y10": y10,
        "spread": spread_10_3m,
        "next_fomc": next_fomc.strftime("%d.%m.%Y"),
        "days_left": days_left,
        "curve_status": curve_status,
        "curve_col": curve_col,
    }


def render_fed_radar_card(fd: dict) -> bytes:
    img, d = _new_canvas("FEDWATCH & YIELD CURVE • AQSH", "FED STAVKA RADARI VA OBLIGATSIYA EGRI CHIZIG‘I", accent_color=fd["curve_col"])

    # Chapda: Treasury Yield Curve grafigi
    gx1, gy1, gx2, gy2 = 55, 160, 740, 610
    d.rounded_rectangle([gx1, gy1, gx2, gy2], radius=14, fill=CHART_BG, outline=BORDER, width=2)
    d.text((gx1 + 24, gy1 + 18), "AQSH TREASURY DAROMADLILIK EGRI CHIZIG‘I (%)", font=images._font(20, bold=True), fill=CYAN)

    pts = fd["points"]
    vals = [p["val"] for p in pts]
    vmin, vmax = min(vals) - 0.4, max(vals) + 0.4
    vspan = max(vmax - vmin, 0.5)

    coords = []
    for idx, p in enumerate(pts):
        x = int(gx1 + 85 + idx * ((gx2 - gx1 - 170) / max(len(pts) - 1, 1)))
        y = int(gy2 - 75 - ((p["val"] - vmin) / vspan) * (gy2 - gy1 - 165))
        coords.append((x, y, p))

    # Chiziq va nuqtalar
    d.line([(x, y) for x, y, _ in coords], fill=CYAN, width=5)
    for x, y, p in coords:
        d.ellipse([x - 10, y - 10, x + 10, y + 10], fill=GOLD, outline=WHITE, width=3)
        vtxt = f"{p['val']:.2f}%"
        d.text((x - d.textlength(vtxt, font=images._font(22, bold=True)) / 2, y - 38), vtxt, font=images._font(22, bold=True), fill=WHITE)
        d.text((x - d.textlength(p["label"], font=images._font(19, bold=True)) / 2, gy2 - 42), p["label"], font=images._font(19, bold=True), fill=GREY)

    # O'ngda: 3 ta asosiy blok
    blocks = [
        ("KEYINGI FOMC YIG‘ILISHI", f"{fd['next_fomc']} ({fd['days_left']} kun qoldi)", GOLD),
        ("10Y – 3M SPREAD (FARQ)", f"{fd['spread']:+.2f}% ({fd['spread'] * 100:+.0f} bp)", fd["curve_col"]),
        ("QISQA MUDDATLI STAVKA (3M)", f"{fd['y3m']:.2f}%  |  10Y: {fd['y10']:.2f}%", CYAN),
    ]
    y = 160
    for lbl, val, col in blocks:
        d.rounded_rectangle([775, y, W - 50, y + 132], radius=14, fill=CARD_BG, outline=BORDER, width=2)
        d.text((800, y + 20), lbl, font=images._font(19, bold=True), fill=GREY)
        d.text((800, y + 60), val, font=images._font(30, bold=True), fill=col)
        y += 156

    return _to_jpeg(img)


def post_fed_radar(dry_run: bool = False) -> bool:
    fd = fetch_fed_and_yield_curve()
    if not fd:
        return False

    pts_txt = "\n".join(f"• <b>{p['label']}:</b> <b>{p['val']:.2f}%</b> ({p['diff_bp']:+.1f} bp)" for p in fd["points"])
    html = (
        "🏦 <b>FED STAVKA RADARI VA YIELD CURVE TAHLILI</b>\n\n"
        f"⏳ Keyingi FOMC yig‘ilishi: <b>{fd['next_fomc']}</b> (<b>{fd['days_left']} kun</b> qoldi)\n\n"
        "📊 <b>AQSh G‘aznachilik obligatsiyalari (Treasury Yields):</b>\n"
        f"{pts_txt}\n\n"
        f"📐 <b>10Y – 3M Spread:</b> <b>{fd['spread']:+.2f}%</b>\n"
        f"🧭 <b>Egri chiziq holati:</b> <b>{fd['curve_status']}</b>\n\n"
        '<i>Manba: <a href="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm">Federal Reserve / U.S. Treasury</a></i>'
    )
    img = render_fed_radar_card(fd)
    if dry_run:
        print("\n[DRY RUN - FED RADAR]\n" + html)
        return True
    telegram_api.send_post(html, img)
    db.add_post(None, f"fed-radar-{datetime.now(TASHKENT).strftime('%Y-W%W')}", "Fed & Yield Curve Radar", "")
    log.info("Fed Stavka Radari muvaffaqiyatli chiqarildi!")
    return True


# ==============================================================================
# 6. O'ZBEKISTON MOLIYA PULSI (MARKAZIY BANK USD/UZS, EUR/UZS + GLOBAL OLTIN)
# ==============================================================================

def fetch_uzbekistan_pulse() -> dict | None:
    rates = {}
    try:
        r = requests.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/", headers={"User-Agent": USER_AGENT}, timeout=15)
        r.raise_for_status()
        for row in r.json():
            ccy = row.get("Ccy")
            if ccy in ("USD", "EUR", "GBP", "RUB"):
                rates[ccy] = {
                    "rate": float(row["Rate"]),
                    "diff": float(row["Diff"]),
                    "date": row.get("Date", ""),
                }
    except Exception as e:
        log.warning("CBU.uz fetch error: %s", e)
        return None

    if "USD" not in rates:
        return None

    gold_d = _yahoo_ohlcv("GC=F", range_str="5d", interval="1d")
    dxy_d = _yahoo_ohlcv("DX-Y.NYB", range_str="5d", interval="1d")

    gold = None
    if gold_d:
        lc, pc = gold_d["candles"][-1]["c"], gold_d["candles"][-2]["c"]
        gold = {"price": lc, "pct": (lc - pc) / pc * 100.0}

    dxy = None
    if dxy_d:
        lc, pc = dxy_d["candles"][-1]["c"], dxy_d["candles"][-2]["c"]
        dxy = {"price": lc, "pct": (lc - pc) / pc * 100.0}

    return {"rates": rates, "gold": gold, "dxy": dxy}


def render_uzbekistan_card(uz: dict) -> bytes:
    img, d = _new_canvas("O‘ZBEKISTON MOLIYA PULSI • CBU.UZ", "MARKAZIY BANK VALYUTA KURSLARI VA GLOBAL OLTIN", accent_color=CYAN)

    rates = uz["rates"]
    order = [("USD", "AQSh Dollari ($)"), ("EUR", "Yevro (€)"), ("GBP", "Funt Sterling (£)"), ("RUB", "Rossiya Rubli (₽)")]
    y = 158
    for ccy, label in order:
        if ccy not in rates:
            continue
        r = rates[ccy]
        d.rounded_rectangle([50, y, 710, y + 104], radius=14, fill=CARD_BG, outline=BORDER, width=2)
        d.text((78, y + 16), f"{ccy} • {label}", font=images._font(22, bold=True), fill=GREY)
        d.text((78, y + 50), f"{r['rate']:,.2f} so‘m", font=images._font(36, bold=True), fill=WHITE)
        dcol = RED if r["diff"] > 0 else (GREEN if r["diff"] < 0 else GREY)
        dtxt = f"{r['diff']:+.2f} so‘m"
        d.text((685 - d.textlength(dtxt, font=images._font(26, bold=True)), y + 56), dtxt, font=images._font(26, bold=True), fill=dcol)
        y += 120

    # O'ng panel: Global Oltin va Dollar Indeksi (DXY)
    ry = 158
    if uz.get("gold"):
        g = uz["gold"]
        d.rounded_rectangle([745, ry, W - 50, ry + 224], radius=16, fill=(22, 34, 58), outline=GOLD, width=2)
        d.text((775, ry + 24), "JAHON OLTIN NARXI (XAU / GC=F)", font=images._font(21, bold=True), fill=GOLD)
        d.text((775, ry + 72), f"${g['price']:,.2f} / unsiya", font=images._font(42, bold=True), fill=WHITE)
        gcol = GREEN if g["pct"] >= 0 else RED
        d.text((775, ry + 136), f"Kunlik o‘zgarish: {g['pct']:+.2f}%", font=images._font(26, bold=True), fill=gcol)
        d.text((775, ry + 178), "O‘zbekiston oltin eksporti uchun muhim ko‘rsatkich", font=images._font(17, bold=False), fill=GREY)
        ry += 248

    if uz.get("dxy"):
        dx = uz["dxy"]
        d.rounded_rectangle([745, ry, W - 50, ry + 216], radius=16, fill=CARD_BG, outline=CYAN, width=2)
        d.text((775, ry + 24), "GLOBAL DOLLAR INDEKSI (DXY)", font=images._font(21, bold=True), fill=CYAN)
        d.text((775, ry + 72), f"{dx['price']:.2f}", font=images._font(46, bold=True), fill=WHITE)
        dcol = GREEN if dx["pct"] >= 0 else RED
        d.text((775, ry + 136), f"Kunlik o‘zgarish: {dx['pct']:+.2f}%", font=images._font(26, bold=True), fill=dcol)

    return _to_jpeg(img)


def post_uzbekistan_pulse(dry_run: bool = False) -> bool:
    uz = fetch_uzbekistan_pulse()
    if not uz:
        return False

    r = uz["rates"]
    cbu_date = r["USD"].get("date") or datetime.now(TASHKENT).strftime("%d.%m.%Y")
    lines = []
    for ccy, flag in (("USD", "🇺🇸"), ("EUR", "🇪🇺"), ("GBP", "🇬🇧"), ("RUB", "🇷🇺")):
        if ccy in r:
            arrow = "🔺" if r[ccy]["diff"] > 0 else ("🔻" if r[ccy]["diff"] < 0 else "➖")
            lines.append(f"{flag} <b>1 {ccy}:</b> <b>{r[ccy]['rate']:,.2f} so‘m</b> ({arrow} {r[ccy]['diff']:+.2f})")

    extra = []
    if uz.get("gold"):
        g = uz["gold"]
        extra.append(f"🥇 <b>Global Oltin (unsiya):</b> <b>${g['price']:,.2f}</b> ({g['pct']:+.2f}%)")
    if uz.get("dxy"):
        dx = uz["dxy"]
        extra.append(f"💵 <b>Dollar indeksi (DXY):</b> <b>{dx['price']:.2f}</b> ({dx['pct']:+.2f}%)")

    html = (
        f"🇺🇿 <b>O‘ZBEKISTON MOLIYA PULSI ({cbu_date})</b>\n\n"
        "🏦 <b>Markaziy Bank rasmiy valyuta kurslari:</b>\n"
        + "\n".join(lines)
        + ("\n\n🌍 <b>Global omillar (Oltin va Dollar):</b>\n" + "\n".join(extra) if extra else "")
        + '\n\n<i>Manba: <a href="https://cbu.uz/uz/">O‘zbekiston Markaziy Banki (CBU.uz) / Yahoo Finance</a></i>'
    )
    img = render_uzbekistan_card(uz)
    if dry_run:
        print("\n[DRY RUN - UZBEKISTAN PULSE]\n" + html)
        return True
    telegram_api.send_post(html, img)
    db.add_post(None, f"uz-pulse-{datetime.now(TASHKENT).strftime('%Y-%m-%d')}", "O'zbekiston Moliya Pulsi", "")
    log.info("O'zbekiston Moliya Pulsi muvaffaqiyatli chiqarildi!")
    return True


# ==============================================================================
# 7. HAFTALIK "52-WEEK HIGH / LOW" REKORDCHILAR (SCANNER)
# ==============================================================================

def scan_52w_extremes() -> dict:
    rows = []
    for sym in SCREENED_TICKERS:
        data = _yahoo_ohlcv(sym, range_str="1y", interval="1d")
        if not data or len(data["candles"]) < 40:
            continue
        c = data["candles"]
        cur = c[-1]["c"]
        h52 = max(x["h"] for x in c)
        l52 = min(x["l"] for x in c)
        span = max(h52 - l52, 0.01)
        pos_pct = (cur - l52) / span * 100.0  # 100% = 52W High, 0% = 52W Low
        rows.append({
            "symbol": sym,
            "name": COMPANY_NAMES.get(sym, sym),
            "price": cur,
            "h52": h52,
            "l52": l52,
            "from_high": (cur - h52) / h52 * 100.0,
            "from_low": (cur - l52) / l52 * 100.0,
            "pos_pct": pos_pct,
        })
    near_high = sorted(rows, key=lambda x: -x["pos_pct"])[:5]
    near_low = sorted(rows, key=lambda x: x["pos_pct"])[:5]
    return {"near_high": near_high, "near_low": near_low}


def render_52w_card(res: dict) -> bytes:
    img, d = _new_canvas("52-WEEK HIGH / LOW SCANNER", "YILLIK CHO‘QQI VA CHEGIRMA ZONASIDAGI GIGANTLAR", accent_color=GREEN)

    # Chap ustun: 52W High Breakout yetakchilari
    d.text((50, 150), "🚀 52 HAFTALIK CHO‘QQIGA ENG YAQIN (BREAKOUT)", font=images._font(21, bold=True), fill=GREEN)
    y = 188
    for r in res["near_high"][:5]:
        d.rounded_rectangle([50, y, 615, y + 78], radius=10, fill=CARD_BG, outline=(24, 96, 64), width=1)
        d.text((70, y + 10), f"#{r['symbol']}", font=images._font(24, bold=True), fill=WHITE)
        d.text((190, y + 12), f"${r['price']:,.2f}", font=images._font(22, bold=True), fill=CYAN)
        htxt = f"{r['from_high']:.1f}% (max: ${r['h52']:,.0f})"
        d.text((595 - d.textlength(htxt, font=images._font(19, bold=True)), y + 14), htxt, font=images._font(19, bold=True), fill=GREEN)
        # Range bar
        d.rounded_rectangle([70, y + 50, 595, y + 62], radius=5, fill=(22, 42, 78))
        fw = int((r["pos_pct"] / 100.0) * 525)
        d.rounded_rectangle([70, y + 50, 70 + max(12, fw), y + 62], radius=5, fill=GREEN)
        y += 88

    # O'ng ustun: 52W Low / Chegirma zonasi
    rx = 660
    d.text((rx, 150), "💎 52 HAFTALIK PASTKI ZONADA (CHEGIRMA)", font=images._font(21, bold=True), fill=GOLD)
    y = 188
    for r in res["near_low"][:5]:
        d.rounded_rectangle([rx, y, W - 50, y + 78], radius=10, fill=CARD_BG, outline=(112, 34, 48), width=1)
        d.text((rx + 20, y + 10), f"#{r['symbol']}", font=images._font(24, bold=True), fill=WHITE)
        d.text((rx + 140, y + 12), f"${r['price']:,.2f}", font=images._font(22, bold=True), fill=CYAN)
        ltxt = f"{r['from_high']:.1f}% (min: ${r['l52']:,.0f})"
        d.text((W - 70 - d.textlength(ltxt, font=images._font(19, bold=True)), y + 14), ltxt, font=images._font(19, bold=True), fill=RED)
        d.rounded_rectangle([rx + 20, y + 50, W - 70, y + 62], radius=5, fill=(22, 42, 78))
        fw = int((r["pos_pct"] / 100.0) * (W - 70 - rx - 20))
        d.rounded_rectangle([rx + 20, y + 50, rx + 20 + max(12, fw), y + 62], radius=5, fill=RED)
        y += 88

    return _to_jpeg(img)


def post_52w_scanner(dry_run: bool = False) -> bool:
    res = scan_52w_extremes()
    if not res["near_high"]:
        return False

    h_txt = "\n".join(
        f"🟢 <b>#{r['symbol']}</b> (${r['price']:,.2f}) — 52W cho‘qqidan <b>{r['from_high']:.1f}%</b>"
        for r in res["near_high"]
    )
    l_txt = "\n".join(
        f"🔴 <b>#{r['symbol']}</b> (${r['price']:,.2f}) — 52W cho‘qqidan <b>{r['from_high']:.1f}%</b> (min: ${r['l52']:,.0f})"
        for r in res["near_low"]
    )

    html = (
        "🏆 <b>HAFTALIK 52-WEEK HIGH / LOW REKORDCHILARI</b>\n\n"
        "🚀 <b>Yillik cho‘qqiga eng yaqin (Momentum Breakout):</b>\n"
        f"{h_txt}\n\n"
        "💎 <b>Yillik pastki zonada (Kuchli chegirma):</b>\n"
        f"{l_txt}\n\n"
        '<i>Manba: <a href="https://finance.yahoo.com/markets/">Yahoo Finance / NASDAQ 52W Scanner</a></i>'
    )
    img = render_52w_card(res)
    if dry_run:
        print("\n[DRY RUN - 52W SCANNER]\n" + html)
        return True
    telegram_api.send_post(html, img)
    db.add_post(None, f"52w-scanner-{datetime.now(TASHKENT).strftime('%Y-W%W')}", "52W High/Low Scanner", "")
    log.info("52-Week High/Low Scanner muvaffaqiyatli chiqarildi!")
    return True
