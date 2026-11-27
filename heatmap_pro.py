"""MARKETPULSE — PREMIUM WEEKLY STOCKS HEATMAP (Finviz / TradingView Treemap uslubi).

1600x1000 Ultra-HD proporsional sektorlar xaritasi (bozor kapitallashuviga mutanosib bloklar),
Yahoo Finance v8 API dan 100% aniq haftalik (5 savdo kuni) narx va foiz o'zgarishlari,
Yangi Özbek Alifbosi (Ö ö, Ğ ğ, Ş ş, Ç ç) va giperhavolali Manba bilan!
"""
import io
import logging
from datetime import datetime

import requests
from PIL import Image, ImageDraw

import db
import images
import telegram_api
from config import TASHKENT, USER_AGENT
from uz_alphabet import to_new_uzbek

log = logging.getLogger("heatmap_pro")

W, H = 1600, 1000
BG_DARK = (8, 13, 24)
PANEL_BG = (14, 21, 36)
WHITE = (248, 250, 255)
GREY = (158, 174, 200)
CYAN = (0, 212, 255)
GOLD = (255, 195, 0)

# Sektorlar va yirik aksiyalar (nisbiy bozor kapitallashuvi vazni bilan)
HEATMAP_SECTORS = [
    (
        "TEXNOLOGIYA VA AI",
        [
            ("NVDA", 36), ("AAPL", 35), ("MSFT", 32), ("AVGO", 14),
            ("ORCL", 10), ("AMD", 8), ("CRM", 8), ("PLTR", 7),
            ("ADBE", 6), ("NOW", 6), ("QCOM", 6), ("PANW", 5),
        ],
    ),
    (
        "INTERNET VA ALOQA",
        [
            ("GOOGL", 24), ("META", 17), ("NFLX", 9), ("UBER", 6), ("DIS", 6),
        ],
    ),
    (
        "ISTE’MOL VA AVTO",
        [
            ("AMZN", 23), ("TSLA", 14), ("WMT", 11), ("COST", 9), ("HD", 8), ("PG", 8),
        ],
    ),
    (
        "SOĞLIQNI SAQLAŞ",
        [
            ("LLY", 14), ("JNJ", 9), ("ISRG", 6), ("TMO", 6), ("VRTX", 5), ("NVO", 7),
        ],
    ),
    (
        "ENERGETIKA VA SANOAT",
        [
            ("XOM", 11), ("CVX", 8), ("CAT", 7), ("DE", 5), ("GE", 7), ("ETN", 5),
        ],
    ),
]


def _color_for_pct(pct: float) -> tuple[int, int, int]:
    """Finviz / TradingView 7 pog'onali aniq rang shkalasi."""
    if pct >= 4.0:
        return (0, 168, 84)
    if pct >= 2.0:
        return (22, 136, 74)
    if pct >= 0.4:
        return (34, 98, 64)
    if pct > -0.4:
        return (54, 64, 82)
    if pct > -2.0:
        return (132, 44, 52)
    if pct > -4.0:
        return (176, 34, 48)
    return (218, 26, 44)


def _fetch_weekly_quote(symbol: str) -> dict | None:
    """Yahoo Finance v8 chart API dan so'nggi 5 savdo kunlik aniq haftalik o'zgarish va joriy narxni oladi."""
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"range": "1mo", "interval": "1d"},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        closes = [float(c) for c in (res["indicators"]["quote"][0].get("close") or []) if c is not None]
        if len(closes) < 2:
            return None
        cur = closes[-1]
        # 5 savdo kuni oldingi yopilish (haftalik aniq o'zgarish)
        ref = closes[-6] if len(closes) >= 6 else closes[0]
        pct = ((cur - ref) / ref * 100.0) if ref else 0.0
        return {"symbol": symbol, "price": cur, "pct": pct}
    except Exception as e:
        log.debug("Heatmap quote error for %s: %s", symbol, e)
        return None


def _layout_slice_and_dice(items: list[dict], x: float, y: float, w: float, h: float) -> list[tuple[dict, tuple[int, int, int, int]]]:
    """Rekursiv muvozanatli (binary squarified) Treemap joylashtirish algoritmi."""
    if not items:
        return []
    if len(items) == 1:
        return [(items[0], (int(round(x)), int(round(y)), int(round(x + w)), int(round(y + h))))]

    total = sum(it["weight"] for it in items)
    if total <= 0:
        total = len(items)

    # Massivni vazn bo'yicha eng muvozanatli 2 guruhga bo'lamiz
    acc = 0.0
    split_idx = 1
    best_diff = float("inf")
    for i in range(1, len(items)):
        acc += items[i - 1]["weight"]
        diff = abs(acc - total / 2.0)
        if diff < best_diff:
            best_diff = diff
            split_idx = i

    left_items = items[:split_idx]
    right_items = items[split_idx:]
    left_w = sum(it["weight"] for it in left_items)
    ratio = left_w / float(total)

    if w >= h:
        w1 = w * ratio
        return (
            _layout_slice_and_dice(left_items, x, y, w1, h)
            + _layout_slice_and_dice(right_items, x + w1, y, w - w1, h)
        )
    else:
        h1 = h * ratio
        return (
            _layout_slice_and_dice(left_items, x, y, w, h1)
            + _layout_slice_and_dice(right_items, x, y + h1, w, h - h1)
        )


def fetch_heatmap_data() -> list[dict]:
    """Barcha sektorlar va aksiyalar bo'yicha real haftalik narxlarni yig'adi."""
    sectors_data = []
    for sec_name, tickers in HEATMAP_SECTORS:
        stocks = []
        for sym, weight in tickers:
            q = _fetch_weekly_quote(sym)
            if q:
                q["weight"] = weight
                stocks.append(q)
        if stocks:
            stocks.sort(key=lambda s: -s["weight"])
            sectors_data.append({
                "name": to_new_uzbek(sec_name),
                "weight": sum(s["weight"] for s in stocks),
                "stocks": stocks,
            })
    return sectors_data


def render_stocks_heatmap(sectors_data: list[dict]) -> bytes:
    """1600x1000 Ultra-HD premium Treemap Stocks Heatmap chizadi."""
    img = Image.new("RGB", (W, H), BG_DARK)
    d = ImageDraw.Draw(img)

    # Yuqori aksent chiziq
    d.rectangle([0, 0, W, 6], fill=GOLD)

    # Sarlavha paneli (y=0..108)
    f_badge = images._font(21, bold=True)
    badge = to_new_uzbek("HAFTALIK STOCKS HEATMAP • WALL STREET")
    bw = d.textlength(badge, font=f_badge) + 32
    d.rounded_rectangle([32, 22, 32 + bw, 58], radius=8, fill=GOLD)
    d.text((48, 28), badge, font=f_badge, fill=BG_DARK)

    title = to_new_uzbek("AQŞ FOND BOZORI ISSIQLIK XARITASI (5 KUNLIK)")
    d.text((32, 66), title, font=images._font(30, bold=True), fill=WHITE)

    # O'ng yuqorida sana va rang shkalasi (Legend)
    date_str = datetime.now(TASHKENT).strftime("%d.%m.%Y • %H:%M (Toşkent)")
    f_dt = images._font(20, bold=False)
    d.text((W - 32 - d.textlength(date_str, font=f_dt), 24), date_str, font=f_dt, fill=GREY)

    legend_items = [
        ("-4%+", (218, 26, 44)),
        ("-2%", (176, 34, 48)),
        ("-1%", (132, 44, 52)),
        ("0%", (54, 64, 82)),
        ("+1%", (34, 98, 64)),
        ("+2%", (22, 136, 74)),
        ("+4%+", (0, 168, 84)),
    ]
    lx = W - 32 - len(legend_items) * 66
    ly = 62
    f_leg = images._font(16, bold=True)
    for lbl, col in legend_items:
        d.rounded_rectangle([lx, ly, lx + 60, ly + 30], radius=5, fill=col)
        tw = d.textlength(lbl, font=f_leg)
        d.text((lx + (60 - tw) / 2, ly + 6), lbl, font=f_leg, fill=WHITE)
        lx += 66

    # Asosiy Treemap maydoni (x=28..1572, y=114..932)
    map_x, map_y = 28, 114
    map_w, map_h = W - 56, H - 182
    sector_rects = _layout_slice_and_dice(sectors_data, map_x, map_y, map_w, map_h)

    for sec, (sx1, sy1, sx2, sy2) in sector_rects:
        # Sektor konteyneri
        pad = 4
        bx1, by1, bx2, by2 = sx1 + pad, sy1 + pad, sx2 - pad, sy2 - pad
        d.rounded_rectangle([bx1, by1, bx2, by2], radius=8, fill=PANEL_BG, outline=(36, 52, 82), width=2)

        # Sektor sarlavha tasmasi
        hdr_h = 28
        d.rectangle([bx1 + 2, by1 + 2, bx2 - 2, by1 + hdr_h], fill=(18, 28, 48))
        sec_title = sec["name"]
        f_sec = images._font(16, bold=True)
        while d.textlength(sec_title, font=f_sec) > (bx2 - bx1 - 18) and len(sec_title) > 6:
            sec_title = sec_title[:-2] + "…"
        d.text((bx1 + 10, by1 + 5), sec_title, font=f_sec, fill=CYAN)

        # Sektor ichidagi aksiyalar treemapi
        inner_rects = _layout_slice_and_dice(
            sec["stocks"],
            bx1 + 4,
            by1 + hdr_h + 3,
            (bx2 - bx1) - 8,
            (by2 - by1) - hdr_h - 7,
        )

        for st, (tx1, ty1, tx2, ty2) in inner_rects:
            tw_box = tx2 - tx1
            th_box = ty2 - ty1
            if tw_box < 20 or th_box < 20:
                continue
            tile_col = _color_for_pct(st["pct"])
            d.rounded_rectangle([tx1 + 2, ty1 + 2, tx2 - 2, ty2 - 2], radius=6, fill=tile_col, outline=BG_DARK, width=2)

            cx = (tx1 + tx2) / 2.0
            cy = (ty1 + ty2) / 2.0

            # Shrift hajmini blok o'lchamiga qarab dinamik moslaymiz
            min_dim = min(tw_box, th_box)
            sym_size = max(15, min(42, int(min_dim * 0.24)))
            pct_size = max(13, min(28, int(min_dim * 0.16)))
            prc_size = max(12, min(20, int(min_dim * 0.11)))

            f_sym = images._font(sym_size, bold=True)
            f_pct = images._font(pct_size, bold=True)
            sym_txt = st["symbol"]
            pct_txt = f"{st['pct']:+.2f}%"

            # Agar kenglikka sig'masa kichraytiramiz
            while d.textlength(sym_txt, font=f_sym) > tw_box - 12 and sym_size > 12:
                sym_size -= 2
                f_sym = images._font(sym_size, bold=True)
            while d.textlength(pct_txt, font=f_pct) > tw_box - 12 and pct_size > 11:
                pct_size -= 2
                f_pct = images._font(pct_size, bold=True)

            show_price = tw_box >= 115 and th_box >= 100
            if show_price:
                f_prc = images._font(prc_size, bold=False)
                prc_txt = f"${st['price']:,.2f}"
                total_h = sym_size + pct_size + prc_size + 10
                y0 = cy - total_h / 2.0
                d.text((cx - d.textlength(sym_txt, font=f_sym) / 2, y0), sym_txt, font=f_sym, fill=WHITE)
                d.text((cx - d.textlength(pct_txt, font=f_pct) / 2, y0 + sym_size + 4), pct_txt, font=f_pct, fill=WHITE)
                d.text((cx - d.textlength(prc_txt, font=f_prc) / 2, y0 + sym_size + pct_size + 8), prc_txt, font=f_prc, fill=(225, 235, 248))
            else:
                total_h = sym_size + pct_size + 4
                y0 = cy - total_h / 2.0
                d.text((cx - d.textlength(sym_txt, font=f_sym) / 2, y0), sym_txt, font=f_sym, fill=WHITE)
                d.text((cx - d.textlength(pct_txt, font=f_pct) / 2, y0 + sym_size + 3), pct_txt, font=f_pct, fill=WHITE)

    # Pastki brend tasmasi
    d.line([(28, H - 56), (W - 28, H - 56)], fill=(30, 50, 86), width=2)
    d.text((32, H - 44), "MARKETPULSE", font=images._font(28, bold=True), fill=WHITE)
    sub_f = images._font(20, bold=False)
    d.text((252, H - 38), to_new_uzbek("• Haftalik Fond Bozori Issiqlik Xaritasi (Real Vaqt Ma’lumotlari)"), font=sub_f, fill=GREY)
    chan_txt = "t.me/MarketPulseZK"
    f_ch = images._font(22, bold=True)
    d.text((W - 32 - d.textlength(chan_txt, font=f_ch), H - 40), chan_txt, font=f_ch, fill=CYAN)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=94)
    return buf.getvalue()


def post_weekly_stocks_heatmap(dry_run: bool = False, save_preview_path=None) -> bool:
    """Haftalik Premium Stocks Heatmap suratini chizib, aniq manbasi bilan kanalga chiqaradi."""
    sectors_data = fetch_heatmap_data()
    all_stocks = [s for sec in sectors_data for s in sec["stocks"]]
    if len(all_stocks) < 10:
        log.warning("Heatmap uchun yetarli ma'lumot yig'ilmadi.")
        return False

    all_stocks.sort(key=lambda x: -x["pct"])
    top_up = all_stocks[:3]
    top_dn = sorted(all_stocks[-3:], key=lambda x: x["pct"])

    up_txt = "\n".join(f"🟢 <b>#{s['symbol']}</b>: ${s['price']:,.2f} (<b>{s['pct']:+.2f}%</b>)" for s in top_up)
    dn_txt = "\n".join(f"🔴 <b>#{s['symbol']}</b>: ${s['price']:,.2f} (<b>{s['pct']:+.2f}%</b>)" for s in top_dn)

    greens = sum(1 for s in all_stocks if s["pct"] > 0)
    reds = len(all_stocks) - greens

    html = (
        "🗺 <b>HAFTALIK STOCKS HEATMAP — AQŞ FOND BOZORI XARITASI</b>\n"
        f"<i>Yakunlangan savdo haftasi natijalari ({greens} ta yaşil 🟢 | {reds} ta qizil 🔴)</i>\n\n"
        "🚀 <b>Hafta yetakçilari:</b>\n"
        f"{up_txt}\n\n"
        "📉 <b>Hafta bosim ostida qolganlari:</b>\n"
        f"{dn_txt}\n\n"
        '<i>Manba: <a href="https://finance.yahoo.com/markets/">Yahoo Finance / Wall Street Weekly Data</a></i>'
    )

    img_bytes = render_stocks_heatmap(sectors_data)
    if save_preview_path:
        with open(save_preview_path, "wb") as f:
            f.write(img_bytes)

    if dry_run:
        print("\n[DRY RUN - WEEKLY STOCKS HEATMAP]\n" + to_new_uzbek(html))
        return True

    telegram_api.send_post(html, img_bytes)
    db.add_post(None, f"stocks-heatmap-{datetime.now(TASHKENT).strftime('%Y-W%W')}", "Haftalik Stocks Heatmap", "")
    log.info("Haftalik Stocks Heatmap (%d ta aksiya) muvaffaqiyatli kanalga chiqarildi!", len(all_stocks))
    return True
