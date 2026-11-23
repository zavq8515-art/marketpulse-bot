"""MARKETPULSE avtomatik yangilik boti.

Ishga tushirish:
    python main.py            # doimiy ishlaydi (har CHECK_INTERVAL_MIN daqiqada)
    python main.py --once     # bir marta tekshiradi va chiqadi (GitHub Actions / cron uchun)
    python main.py --check    # bot token va kanal huquqlarini tekshiradi
    python main.py --card     # namunaviy brend kartani data/preview ga saqlaydi
"""
import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

import ai
import companies
import db
import education
import fetcher
import images
import market
import max_features
import pro_features
import telegram_api
from config import (
    CHECK_INTERVAL_MIN,
    DATA_DIR,
    DRY_RUN,
    GEMINI_API_KEY,
    MAX_POSTS_PER_DAY,
    MAX_POSTS_PER_RUN,
    MIN_GAP_MIN,
    MIN_IMPORTANCE,
    PREVIEW_DIR,
    QUIET_HOURS,
    TASHKENT,
    TELEGRAM_BOT_TOKEN,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(DATA_DIR / "bot.log", encoding="utf-8")],
)
log = logging.getLogger("main")
MIN_NOVELTY = 5
BREAKING = 8


def in_quiet_hours():
    if not QUIET_HOURS or "-" not in QUIET_HOURS:
        return False
    a, b = (int(x) for x in QUIET_HOURS.split("-"))
    h = datetime.now(TASHKENT).hour
    return a <= h < b if a < b else (h >= a or h < b)


def publish(html_text, image_bytes, label):
    # Har qanday postdan "Investor uchun ma'nosi" bo'limini butunlay olib tashlash
    import re
    pattern = r"(?:💡\s*)?(?:<blockquote>\s*)?(?:<b>\s*)?(?:💡\s*)?(?:Investor\s+uchun\s+ma[’'‘`]nosi:?)\s*(?:</b>)?.*?(?=(?:<i>\s*Manba|</blockquote>|\Z))"
    html_text = re.sub(pattern, "", html_text, flags=re.DOTALL | re.IGNORECASE).strip()
    html_text = re.sub(r"<blockquote>\s*</blockquote>", "", html_text).strip()
    html_text = re.sub(r"\n{3,}", "\n\n", html_text).strip()

    # Kompaniyalar tilga olinganda aksiya tiker heshteglarini ta'minlash (#TSLA, #NVDA...)
    html_text = ai.inject_ticker_hashtags(html_text)

    # Manba doim bo'lishini ta'minlash
    if "manba" not in html_text.lower():
        html_text += "\n\n<i>Manba: MarketPulse</i>"

    if DRY_RUN:
        PREVIEW_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        img_path = PREVIEW_DIR / f"{stamp}_{label}.jpg"
        img_path.write_bytes(image_bytes)
        (PREVIEW_DIR / f"{stamp}_{label}.html.txt").write_text(html_text, encoding="utf-8")
        print("\n" + "=" * 70 + f"\n[DRY RUN] Surat: {img_path}\n{html_text}\n" + "=" * 70)
        return True
    try:
        telegram_api.send_post(html_text, image_bytes)
        return True
    except Exception as e:  # noqa: BLE001
        log.error("Telegramga yuborilmadi: %s", e)
        return False


STOPWORDS = {"with", "from", "that", "this", "after", "over", "into", "amid", "says", "will", "what", "their", "have", "more", "news", "live", "updates"}


def _words(title):
    import re

    return {w for w in re.findall(r"[a-z0-9']+", title.lower()) if len(w) > 3 and w not in STOPWORDS}


def related_items(item, items):
    """Shu voqea haqidagi boshqa manbalardagi xabarlar (kontekst uchun)."""
    base = _words(item["title"])
    scored = []
    for it in items:
        if it["id"] == item["id"]:
            continue
        common = len(base & _words(it["title"]))
        if common >= 2:
            scored.append((common, it))
    return [it for _, it in sorted(scored, key=lambda x: -x[0])]


def gap_ok():
    last = db.last_post_time()
    return not last or datetime.now(timezone.utc) - last >= timedelta(minutes=MIN_GAP_MIN)


def process_news(budget):
    items = fetcher.fetch_new_items()
    if not items:
        return 0
    recent = db.recent_posts(48)
    selected = ai.triage(items, recent)
    if selected is None:
        log.error("AI saralash ishlamadi (API kalitini tekshiring). Xabarlar keyingi safar qayta ko'riladi")
        return 0
    recent_topics = {p["topic"] for p in recent}

    chosen, seen_topics = [], set()
    for s in sorted(selected, key=lambda x: -(x.get("importance", 0) * x.get("novelty", 0))):
        item = s.get("item")
        if not item:
            idx = s.get("index")
            if isinstance(idx, int) and 0 <= idx < len(items):
                item = items[idx]
        if not item:
            continue
        topic = (s.get("topic") or "").strip().lower()
        if s.get("importance", 0) < MIN_IMPORTANCE or s.get("novelty", 0) < MIN_NOVELTY:
            continue
        if topic in recent_topics or topic in seen_topics:
            continue
        seen_topics.add(topic)
        chosen.append((item, s, topic))

    chosen_ids = {c[0]["id"] for c in chosen}
    for it in items:  # tanlanmaganlar qayta tahlil qilinmasin
        if it["id"] not in chosen_ids:
            db.mark_seen(it)

    posted = 0
    for item, s, topic in chosen:
        if posted >= budget:
            break
        breaking = s.get("importance", 0) >= BREAKING
        if not breaking and not gap_ok():
            log.info("Oraliq vaqt hali o'tmadi, keyingi tekshiruvda chiqariladi")
            break
        log.info("Yozilmoqda [%s | imp=%s nov=%s]: %s", item["source"], s.get("importance"), s.get("novelty"), item["title"])
        article = fetcher.fetch_article(item)
        post = ai.write_post(item, article, related_items(item, items))
        if not post:
            db.mark_seen(item)
            continue
        image = images.pick_image(article, post)
        if publish(post["post_html"], image, topic[:40] or "news"):
            db.add_post(item["id"], topic, post.get("summary_uz", item["title"]), article["url"])
            db.mark_seen(item)
            posted += 1
    return posted


def _collect_live_headlines(limit: int = 25) -> list[str]:
    """Bozordagi keskin harakat sababini aniqlash uchun eng so'nggi sarlavhalarni yig'adi."""
    headlines = []
    try:
        fresh = fetcher.fetch_new_items()
        for it in fresh[:15]:
            headlines.append(f"[{it['source']}] {it['title']}")
    except Exception:  # noqa: BLE001
        pass
    for t in db.recent_titles():
        if t not in headlines:
            headlines.append(t)
    return headlines[:limit]


def process_price_moves(budget):
    """Real-time keskin harakatlarni ehtimoliy sabablari bilan BITTA tezkor postga jamlaydi."""
    moves = market.check_moves()
    if not moves or budget <= 0:
        return 0

    def close_levels():
        for a in moves:
            step = 1 if a["level"] > 0 else -1
            for lvl in range(step, a["level"] + step, step):
                db.mark_price_alert(a["symbol"], a["day"], lvl)

    headlines = _collect_live_headlines(25)
    post = ai.write_price_alert(moves, headlines, db.recent_posts(12))
    if not post:
        return 0
    if post.get("skip") or not post.get("post_html"):
        log.info("Narx harakatlari allaqachon yoritilgan, post chiqmadi")
        close_levels()
        return 0
    crypto_only = all(a["symbol"] in ("BTC-USD", "ETH-USD") for a in moves)
    image = images.brand_card(
        post.get("card_title") or "Bozorda keskin harakat",
        post.get("card_points") or [f"{a['name']}: {a['move_desc']}" for a in moves[:3]],
        "CRYPTO" if crypto_only else "MARKETS",
    )
    if publish(post["post_html"], image, "price_moves"):
        close_levels()
        topic = "price-" + "-".join(f"{a['symbol']}{a['level']:+d}" for a in moves)
        db.add_post(None, topic[:120], post.get("summary_uz", ""), "")
        return 1
    return 0


def post_live_market_reaction() -> bool:
    """Hozirgi real-time bozor reaksiyasini (indekslar, aktivlar va ehtimoliy sabablar) darhol chiqaradi."""
    log.info("Real-time bozor reaksiyasi tayyorlanmoqda...")
    indices = market.get_daily_indices()
    if not indices:
        return False

    moves = []
    for idx in indices:
        moves.append({
            "name": idx["name"],
            "price": f"{idx['price']:,.2f}",
            "move_desc": idx["change"],
            "pct": idx["change_pct"],
        })

    # Asosiy yirik aksiyalar ham qo'shiladi
    for sym, label in (("NVDA", "NVIDIA (#NVDA)"), ("TSLA", "Tesla (#TSLA)"), ("AAPL", "Apple (#AAPL)"), ("AMD", "AMD (#AMD)")):
        q = pro_features._yahoo_quote_full(sym)
        if q:
            moves.append({
                "name": label,
                "price": f"${q['price']:,.2f}",
                "move_desc": f"{q['pct']:+.2f}%",
                "pct": q["pct"],
            })

    headlines = _collect_live_headlines(25)
    post = ai.write_price_alert(moves, headlines, [], force_publish=True)
    if not post or not post.get("post_html"):
        return False

    top_pts = post.get("card_points") or [f"{m['name']}: {m['move_desc']}" for m in moves[:3]]
    img = images.brand_card(
        post.get("card_title") or "REAL-TIME BOZOR REAKSIYASI",
        top_pts[:3],
        "MARKETS",
    )
    if publish(post["post_html"], img, "live_market_reaction"):
        db.add_post(None, f"live-reaction-{datetime.now(TASHKENT).strftime('%Y-%m-%d-%H')}", post.get("summary_uz", "Real-time bozor reaksiyasi"), "")
        log.info("Real-time bozor reaksiyasi muvaffaqiyatli chiqarildi!")
        return True
    return False


def post_daily_close():
    log.info("Kunlik bozor yakunlari posti tayyorlanmoqda...")
    indices = market.get_daily_indices()
    if not indices:
        return False
    post = ai.write_daily_close(indices, db.recent_titles())
    if not post or not post.get("post_html"):
        return False
    img = images.pick_image({"image": None}, post)
    today_str = datetime.now(TASHKENT).strftime("%Y-%m-%d")
    if publish(post["post_html"], img, f"daily_close_{today_str}"):
        db.mark_feature_done("daily_close", today_str)
        db.add_post(None, f"daily-close-{today_str}", post.get("summary_uz", "Kunlik bozor yakuni"), "")
        log.info("Kunlik bozor yakuni posti muvaffaqiyatli chiqdi!")
        return True
    return False


def post_sector_etfs():
    log.info("Sektor ETFlari tahlili tayyorlanmoqda...")
    sectors = market.get_sector_etfs()
    if not sectors:
        return False
    post = ai.write_sector_etfs(sectors, db.recent_titles())
    if not post or not post.get("post_html"):
        return False
    img = images.pick_image({"image": None}, post)
    week_key = datetime.now(TASHKENT).strftime("%Y-W%W")
    if publish(post["post_html"], img, f"sector_etfs_{week_key}"):
        db.mark_feature_done("sector_etfs", week_key)
        db.add_post(None, f"sector-etfs-{week_key}", post.get("summary_uz", "Sektor ETFlari tahlili"), "")
        log.info("Sektor ETFlari posti muvaffaqiyatli chiqdi!")
        return True
    return False


def post_crypto_pulse():
    log.info("Kripto Pulse posti tayyorlanmoqda...")
    cryptos = market.get_crypto_pulse()
    if not cryptos:
        return False
    post = ai.write_crypto_pulse(cryptos, db.recent_titles())
    if not post or not post.get("post_html"):
        return False
    img = images.pick_image({"image": None}, post)
    today_str = datetime.now(TASHKENT).strftime("%Y-%m-%d")
    if publish(post["post_html"], img, f"crypto_pulse_{today_str}"):
        db.mark_feature_done("crypto_pulse", today_str)
        db.add_post(None, f"crypto-pulse-{today_str}", post.get("summary_uz", "Kripto bozor sharhi"), "")
        log.info("Kripto Pulse posti muvaffaqiyatli chiqdi!")
        return True
    return False


def post_weekly_gazette():
    log.info("Haftalik Investor Gazetasi tayyorlanmoqda...")
    indices = market.get_daily_indices()
    if not indices:
        return False
    post = ai.write_weekly_gazette(indices, db.recent_titles())
    if not post or not post.get("post_html"):
        return False
    img = images.pick_image({"image": None}, post)
    week_key = datetime.now(TASHKENT).strftime("%Y-W%W")
    if publish(post["post_html"], img, f"weekly_gazette_{week_key}"):
        db.mark_feature_done("weekly_gazette", week_key)
        db.add_post(None, f"weekly-gazette-{week_key}", post.get("summary_uz", "Haftalik Investor Gazetasi"), "")
        log.info("Haftalik Investor Gazetasi posti muvaffaqiyatli chiqdi!")
        return True
    return False


def process_scheduled_features():
    """Kunlik va haftalik doimiy tahliliy postlar avtomatik tekshiruvi."""
    now = datetime.now(TASHKENT)
    today_str = now.strftime("%Y-%m-%d")
    week_key = now.strftime("%Y-W%W")
    weekday = now.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun

    # 1. Kunlik bozor yakuni (dushanba-juma savdo yakunlari: seshanba-shanba 07:00-11:00 Toshkent vaqti)
    if weekday in (1, 2, 3, 4, 5) and 7 <= now.hour <= 11:
        if not db.is_feature_done("daily_close", today_str):
            post_daily_close()

    # 2. Sektor ETFlari (haftada 1 marta: juma kechasi yoki shanba)
    if (weekday == 4 and now.hour >= 20) or (weekday == 5 and now.hour <= 18):
        if not db.is_feature_done("sector_etfs", week_key):
            post_sector_etfs()

    # 3. Kripto Pulse (har kuni 12:00-15:00)
    if 12 <= now.hour <= 15:
        if not db.is_feature_done("crypto_pulse", today_str):
            post_crypto_pulse()

    # 4. Haftalik Investor Gazetasi (haftada 1 marta: shanba yoki yakshanba 10:00-16:00)
    if weekday in (5, 6) and 10 <= now.hour <= 16:
        if not db.is_feature_done("weekly_gazette", week_key):
            post_weekly_gazette()

    # 5. Weekend Akademiya (shanba va yakshanba kunlari har biri 3 tadan = 6 ta dars)
    if weekday in (5, 6):
        education.process_weekend_academy()

    # 6. Kompaniyalar tahlili (haftada 2 marta: seshanba va payshanba 16:00-18:00 Toshkent vaqti)
    if weekday in (1, 3) and 16 <= now.hour <= 18:
        day_key = f"{week_key}_day_{weekday}"
        if not db.is_feature_done("company_spotlight_sched", day_key):
            if companies.publish_company_spotlight():
                db.mark_feature_done("company_spotlight_sched", day_key)

    # 7. Haftalik Iqtisodiy Taqvim (dushanba 08:00-11:00 Toshkent vaqti)
    if weekday == 0 and 8 <= now.hour <= 11:
        if not db.is_feature_done("econ_calendar", week_key):
            try:
                if pro_features.post_economic_calendar():
                    db.mark_feature_done("econ_calendar", week_key)
            except Exception as e:  # noqa: BLE001
                log.warning("Iqtisodiy taqvimda xato: %s", e)

    # 8. Haftalik Choraklik Hisobotlar Taqvimı / Earnings (dushanba 11:00-14:00 Toshkent vaqti)
    if weekday == 0 and 11 <= now.hour <= 14:
        if not db.is_feature_done("earnings_calendar", week_key):
            try:
                if pro_features.post_earnings_calendar():
                    db.mark_feature_done("earnings_calendar", week_key)
            except Exception as e:  # noqa: BLE001
                log.warning("Earnings taqvimida xato: %s", e)

    # 9. Pre-Market Brifing (dushanba-juma 17:30-18:30 Toshkent vaqti, AQSh birjasi ochilishidan oldin)
    if weekday in (0, 1, 2, 3, 4) and (now.hour == 17 and now.minute >= 30 or now.hour == 18 and now.minute <= 30):
        if not db.is_feature_done("premarket", today_str):
            try:
                if pro_features.post_premarket_briefing():
                    db.mark_feature_done("premarket", today_str)
            except Exception as e:  # noqa: BLE001
                log.warning("Pre-Market brifingda xato: %s", e)

    # 10. Bozor Kayfiyati: Fear & Greed + VIX (seshanba va juma 11:00-13:00 Toshkent vaqti)
    if weekday in (1, 4) and 11 <= now.hour <= 13:
        if not db.is_feature_done("fear_greed", today_str):
            try:
                if pro_features.post_fear_and_greed():
                    db.mark_feature_done("fear_greed", today_str)
            except Exception as e:  # noqa: BLE001
                log.warning("Fear & Greed postida xato: %s", e)

    # 11. Top 5 Gainers/Losers + Sektor Heatmap (seshanba-shanba 07:30-11:30 Toshkent vaqti)
    if weekday in (1, 2, 3, 4, 5) and 7 <= now.hour <= 11:
        if not db.is_feature_done("movers_heatmap", today_str):
            try:
                if pro_features.post_top_movers_heatmap():
                    db.mark_feature_done("movers_heatmap", today_str)
            except Exception as e:  # noqa: BLE001
                log.warning("Movers & Heatmap postida xato: %s", e)

    # 12. Smart Money: Insayderlar / SEC Form 4 (chorshanba va juma 14:00-16:00 Toshkent vaqti)
    if weekday in (2, 4) and 14 <= now.hour <= 16:
        if not db.is_feature_done("smart_money", today_str):
            try:
                if pro_features.post_smart_money():
                    db.mark_feature_done("smart_money", today_str)
            except Exception as e:  # noqa: BLE001
                log.warning("Smart Money postida xato: %s", e)

    # 13. Interaktiv So'rovnoma / Poll (chorshanba va shanba 19:00-21:00 Toshkent vaqti)
    if weekday in (2, 5) and 19 <= now.hour <= 21:
        if not db.is_feature_done("interactive_poll_sched", today_str):
            try:
                if pro_features.post_interactive_poll():
                    db.mark_feature_done("interactive_poll_sched", today_str)
            except Exception as e:  # noqa: BLE001
                log.warning("Interaktiv so'rovnomada xato: %s", e)

    # 14. Yirik Fondlar & Insayderlar (SEC 13D/13G + Form 4: dushanba va payshanba 14:00-16:00)
    if weekday in (0, 3) and 14 <= now.hour <= 16:
        if not db.is_feature_done("institutional_flows", today_str):
            try:
                if max_features.post_institutional_flows():
                    db.mark_feature_done("institutional_flows", today_str)
            except Exception as e:  # noqa: BLE001
                log.warning("Yirik fondlar postida xato: %s", e)

    # 15. Unusual Volume Radari (dushanba-juma 21:00-22:30 Toshkent vaqti)
    if weekday in (0, 1, 2, 3, 4) and 21 <= now.hour <= 22:
        if not db.is_feature_done("unusual_volume", today_str):
            try:
                if max_features.post_unusual_volume():
                    db.mark_feature_done("unusual_volume", today_str)
            except Exception as e:  # noqa: BLE001
                log.warning("Unusual Volume radarida xato: %s", e)

    # 16. Real Texnik Tahlil Grafigi (dushanba-juma 15:00-17:00 Toshkent vaqti)
    if weekday in (0, 1, 2, 3, 4) and 15 <= now.hour <= 17:
        if not db.is_feature_done("technical_chart_daily", today_str):
            try:
                if max_features.post_technical_chart():
                    db.mark_feature_done("technical_chart_daily", today_str)
            except Exception as e:  # noqa: BLE001
                log.warning("Texnik tahlil grafigida xato: %s", e)

    # 17. Gigantlar Duelli VS (haftada 1 marta: yakshanba 16:00-19:00 Toshkent vaqti)
    if weekday == 6 and 16 <= now.hour <= 19:
        if not db.is_feature_done("giant_duel_sched", week_key):
            try:
                if max_features.post_giant_duel():
                    db.mark_feature_done("giant_duel_sched", week_key)
            except Exception as e:  # noqa: BLE001
                log.warning("Gigantlar duellida xato: %s", e)

    # 18. Fed Stavka Radari & Yield Curve (haftada 1 marta: chorshanba 10:00-12:00 Toshkent vaqti)
    if weekday == 2 and 10 <= now.hour <= 12:
        if not db.is_feature_done("fed_radar_sched", week_key):
            try:
                if max_features.post_fed_radar():
                    db.mark_feature_done("fed_radar_sched", week_key)
            except Exception as e:  # noqa: BLE001
                log.warning("Fed stavka radarida xato: %s", e)

    # 19. O'zbekiston Moliya Pulsi — USD/UZS & Oltin (dushanba, chorshanba, juma 09:00-11:00)
    if weekday in (0, 2, 4) and 9 <= now.hour <= 11:
        if not db.is_feature_done("uzbekistan_pulse", today_str):
            try:
                if max_features.post_uzbekistan_pulse():
                    db.mark_feature_done("uzbekistan_pulse", today_str)
            except Exception as e:  # noqa: BLE001
                log.warning("O'zbekiston moliya pulsida xato: %s", e)

    # 20. Haftalik 52-Week High/Low Scanner (juma 18:30-20:30 Toshkent vaqti)
    if weekday == 4 and 18 <= now.hour <= 20:
        if not db.is_feature_done("scanner_52w_sched", week_key):
            try:
                if max_features.post_52w_scanner():
                    db.mark_feature_done("scanner_52w_sched", week_key)
            except Exception as e:  # noqa: BLE001
                log.warning("52W Scanner postida xato: %s", e)

    # 21. Juma kechki Weekend Akademiya anonsi (har juma 19:00-23:00 Toshkent vaqti)
    if weekday == 4 and 19 <= now.hour <= 23:
        if not db.is_feature_done("academy_friday_announce", week_key):
            try:
                if education.post_weekend_announcement():
                    db.mark_feature_done("academy_friday_announce", week_key)
            except Exception as e:  # noqa: BLE001
                log.warning("Juma Akademiya anonsida xato: %s", e)

    # 22. Juma kechki O'tilgan Akademiya darslari mundarijasi (anonsdan keyin)
    if weekday == 4 and 19 <= now.hour <= 23:
        if not db.is_feature_done("academy_friday_archive", week_key):
            try:
                if education.post_academy_archive():
                    db.mark_feature_done("academy_friday_archive", week_key)
            except Exception as e:  # noqa: BLE001
                log.warning("Juma Akademiya arxivida xato: %s", e)


def run_once():
    if in_quiet_hours():
        log.info("Tungi tinchlik vaqti (%s), o'tkazib yuborildi", QUIET_HOURS)
        return

    # 1. Rejalashtirilgan doimiy postlar
    try:
        process_scheduled_features()
    except Exception as e:  # noqa: BLE001
        log.warning("Rejalashtirilgan postlar tekshiruvida xato: %s", e)

    # 2. Real-time keskin narx harakatlari (ENG YUQORI USTUVORLIK — kutmasdan darhol chiqadi!) va yangiliklar
    budget = min(MAX_POSTS_PER_RUN, MAX_POSTS_PER_DAY - db.posts_today_count(TASHKENT))
    if budget <= 0:
        log.info("Kunlik limit (%d) tugadi", MAX_POSTS_PER_DAY)
        return
    n = process_price_moves(budget)
    if budget - n > 0:
        n += process_news(budget - n)
    log.info("Tekshiruv tugadi. Chiqarilgan postlar: %d", n)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    p.add_argument("--check", action="store_true")
    p.add_argument("--card", action="store_true")
    p.add_argument("--daily-close", action="store_true")
    p.add_argument("--sector-etfs", action="store_true")
    p.add_argument("--crypto", action="store_true")
    p.add_argument("--gazette", action="store_true")
    p.add_argument("--lesson", type=int, help="Aniq dars ID raqamini chiqarish (1-100)")
    p.add_argument("--next-lesson", action="store_true", help="Navbatdagi akademiya darsini chiqarish")
    p.add_argument("--academy-status", action="store_true", help="Akademiya holatini ko'rish")
    p.add_argument("--academy-announce", action="store_true", help="Shanba/Yakshanba Akademiya darslari anonsini chiqarish")
    p.add_argument("--academy-archive", action="store_true", help="O'tilgan barcha Akademiya darslari giperhavolali mundarijasini chiqarish")
    p.add_argument("--company", type=str, help="Aniq kompaniya aksiyasini tahlil qilib chiqarish (masalan: NVDA, AAPL, TSLA)")
    p.add_argument("--company-spotlight", action="store_true", help="Navbatdagi yirik kompaniya tahlilini chiqarish")
    p.add_argument("--companies-list", action="store_true", help="Tahlil qilinadigan yirik kompaniyalar ro'yxatini ko'rish")
    p.add_argument("--econ-calendar", action="store_true", help="Haftalik iqtisodiy taqvimni chiqarish")
    p.add_argument("--earnings-calendar", action="store_true", help="Haftalik choraklik hisobotlar (Earnings) taqvimini chiqarish")
    p.add_argument("--premarket", action="store_true", help="Pre-Market brifingni chiqarish")
    p.add_argument("--fear-greed", action="store_true", help="Fear & Greed Index + VIX spidometrini chiqarish")
    p.add_argument("--movers-heatmap", action="store_true", help="Top 5 Gainers/Losers + Sektor Heatmap chiqarish")
    p.add_argument("--smart-money", action="store_true", help="Smart Money (SEC Form 4 insayder xaridlari) chiqarish")
    p.add_argument("--poll", action="store_true", help="Interaktiv Telegram so'rovnomasi yuborish")
    p.add_argument("--inst-flows", action="store_true", help="Yirik fondlar va insayderlar (SEC 13D/13G + Form 4) chiqarish")
    p.add_argument("--unusual-volume", action="store_true", help="Unusual Volume radarini chiqarish")
    p.add_argument("--tech-chart", nargs="?", const="AUTO", help="Texnik tahlil grafigi (masalan: --tech-chart NVDA)")
    p.add_argument("--duel", action="store_true", help="Gigantlar Duelli (VS infografika) chiqarish")
    p.add_argument("--fed-radar", action="store_true", help="Fed Stavka Radari va Yield Curve chiqarish")
    p.add_argument("--uz-pulse", action="store_true", help="O'zbekiston Moliya Pulsi (USD/UZS & Oltin) chiqarish")
    p.add_argument("--scanner-52w", action="store_true", help="Haftalik 52-Week High/Low Scanner chiqarish")
    p.add_argument("--market-pulse-now", action="store_true", help="Hozirgi real-time bozor reaksiyasini darhol chiqarish")
    args = p.parse_args()
    db.init()

    if args.card:
        PREVIEW_DIR.mkdir(exist_ok=True)
        out = PREVIEW_DIR / "sample_card.jpg"
        out.write_bytes(images.brand_card("Fed stavkani o‘zgarishsiz qoldirdi", ["Stavka: 3.75–4.00%", "US 10Y: 4.12%"], "FED"))
        print(f"Namuna karta: {out}")
        return
    if args.check:
        user, title, status, can_post = telegram_api.check()
        print(f"Bot: @{user}\nKanal: {title}\nHolat: {status}\nPost yubora oladimi: {'HA' if can_post else 'YOQ'}")
        return
    if args.daily_close:
        post_daily_close()
        return
    if args.sector_etfs:
        post_sector_etfs()
        return
    if args.crypto:
        post_crypto_pulse()
        return
    if args.gazette:
        post_weekly_gazette()
        return
    if args.lesson:
        education.publish_lesson(args.lesson)
        return
    if args.next_lesson:
        education.publish_lesson()
        return
    if args.academy_status:
        next_id = education.get_next_lesson_id()
        l = education.get_lesson(next_id)
        print(f"\n🎓 MARKETPULSE AKADEMIYA HOLATI:")
        print(f"Keyingi navbatdagi dars: #{next_id}")
        print(f"Modul: {l['module']}")
        print(f"Mavzu: {l['title']}")
        return
    if args.academy_announce:
        if education.post_weekend_announcement():
            db.mark_feature_done("academy_friday_announce", datetime.now(TASHKENT).strftime("%Y-W%W"))
        return
    if args.academy_archive:
        if education.post_academy_archive():
            db.mark_feature_done("academy_friday_archive", datetime.now(TASHKENT).strftime("%Y-W%W"))
        return
    if args.company:
        companies.publish_company_spotlight(args.company.upper().strip())
        return
    if args.company_spotlight:
        companies.publish_company_spotlight()
        return
    if args.companies_list:
        print("\n🏢 MARKETPULSE — YIRIK KOMPANIYALAR REYESTRI (> $2B):")
        for idx, c in enumerate(companies.COMPANIES_DB, 1):
            done = "✅" if db.is_feature_done("company_spotlight", c["symbol"]) else "⏳"
            print(f"{idx:2d}. {done} #{c['symbol']:<5} | {c['name']:<25} | {c['market_cap']:<15} | {c['sector']}")
        return
    if args.econ_calendar:
        pro_features.post_economic_calendar()
        return
    if args.earnings_calendar:
        pro_features.post_earnings_calendar()
        return
    if args.premarket:
        pro_features.post_premarket_briefing()
        return
    if args.fear_greed:
        pro_features.post_fear_and_greed()
        return
    if args.movers_heatmap:
        pro_features.post_top_movers_heatmap()
        return
    if args.smart_money:
        pro_features.post_smart_money()
        return
    if args.poll:
        pro_features.post_interactive_poll()
        return
    if args.inst_flows:
        max_features.post_institutional_flows()
        return
    if args.unusual_volume:
        max_features.post_unusual_volume()
        return
    if args.tech_chart:
        sym = None if args.tech_chart == "AUTO" else args.tech_chart.upper().strip()
        max_features.post_technical_chart(sym)
        return
    if args.duel:
        max_features.post_giant_duel()
        return
    if args.fed_radar:
        max_features.post_fed_radar()
        return
    if args.uz_pulse:
        max_features.post_uzbekistan_pulse()
        return
    if args.scanner_52w:
        max_features.post_52w_scanner()
        return
    if args.market_pulse_now:
        post_live_market_reaction()
        return

    missing = [n for n, v in (("GEMINI_API_KEY", GEMINI_API_KEY), ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)) if not v]
    if "GEMINI_API_KEY" in missing or (not DRY_RUN and missing):
        sys.exit(f".env faylida yetishmayapti: {', '.join(missing)}")

    log.info("MARKETPULSE bot ishga tushdi (DRY_RUN=%s)", DRY_RUN)
    if args.once:
        run_once()
        return
    while True:
        try:
            run_once()
        except Exception:  # noqa: BLE001
            log.exception("Kutilmagan xato")
        time.sleep(CHECK_INTERVAL_MIN * 60)


if __name__ == "__main__":
    main()
