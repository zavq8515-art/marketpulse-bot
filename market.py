"""Keskin narx harakatlari haqida ogohlantirish (faqat chegaradan oshganda).

Har kuni bir xil "narx snapshot" chiqarmaslik uchun post faqat aktiv belgilangan
chegaradan ko'p harakat qilganda chiqadi. Har bir daraja (1x, 2x, 3x chegara)
kuniga faqat bir marta e'lon qilinadi.
"""
import logging
from datetime import datetime

import requests

import db
from config import NEW_YORK, USER_AGENT

log = logging.getLogger("market")

# symbol: (nomi, chegara, turi) — turi "pct" (foiz) yoki "bp" (bazis punkt, yieldlar uchun)
WATCHLIST = {
    "^GSPC": ("S&P 500", 1.2, "pct"),
    "^IXIC": ("Nasdaq Composite", 1.5, "pct"),
    "^DJI": ("Dow Jones", 1.2, "pct"),
    "^RUT": ("Russell 2000", 2.0, "pct"),
    "^VIX": ("VIX (qo‘rquv indeksi)", 15.0, "pct"),
    "^TNX": ("US 10Y Treasury Yield", 10.0, "bp"),
    "DX-Y.NYB": ("DXY (dollar indeksi)", 0.8, "pct"),
    "CL=F": ("WTI neft", 3.0, "pct"),
    "BZ=F": ("Brent neft", 3.0, "pct"),
    "GC=F": ("Oltin", 1.8, "pct"),
    "BTC-USD": ("Bitcoin", 4.0, "pct"),
    "ETH-USD": ("Ethereum", 5.0, "pct"),
    "NVDA": ("NVIDIA", 5.0, "pct"),
}


def _quote(sym):
    """Yahoo Finance chart API: (oxirgi narx, oldingi yopilish)."""
    r = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
        params={"range": "1d", "interval": "5m"},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    r.raise_for_status()
    meta = r.json()["chart"]["result"][0]["meta"]
    prev = meta.get("previousClose") or meta.get("chartPreviousClose")
    return float(meta["regularMarketPrice"]), float(prev)


def check_moves():
    """Chegaradan oshgan harakatlar ro'yxatini qaytaradi."""
    day = datetime.now(NEW_YORK).strftime("%Y-%m-%d")
    alerts = []
    for sym, (name, threshold, kind) in WATCHLIST.items():
        try:
            last, prev = _quote(sym)
        except Exception as e:  # noqa: BLE001
            log.info("%s narxi olinmadi: %s", sym, e)
            continue
        if not prev:
            continue
        if kind == "bp":
            move = (last - prev) * 100  # ^TNX foizda beriladi: 4.25 -> 425 bp
            pct = (last - prev) / prev * 100
        else:
            move = pct = (last - prev) / prev * 100
        level = int(abs(move) // threshold)
        if level < 1:
            continue
        signed_level = level if move > 0 else -level
        if db.price_alert_done(sym, day, signed_level):
            continue
        alerts.append(
            {
                "symbol": sym,
                "name": name,
                "price": round(last, 4 if kind == "bp" else 2),
                "change_pct": pct,
                "move_desc": f"{move:+.0f} bp" if kind == "bp" else f"{pct:+.2f}%",
                "day": day,
                "level": signed_level,
            }
        )
    return alerts
