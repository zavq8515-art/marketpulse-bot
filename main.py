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
import db
import education
import fetcher
import images
import market
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
        idx = s.get("index")
        if not isinstance(idx, int) or not 0 <= idx < len(items):
            continue
        topic = (s.get("topic") or "").strip().lower()
        if s.get("importance", 0) < MIN_IMPORTANCE or s.get("novelty", 0) < MIN_NOVELTY:
            continue
        if topic in recent_topics or topic in seen_topics:
            continue
        seen_topics.add(topic)
        chosen.append((items[idx], s, topic))

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


def process_price_moves(budget):
    """Barcha keskin harakatlarni BITTA postga jamlaydi."""
    moves = market.check_moves()
    if not moves or budget <= 0:
        return 0

    def close_levels():
        for a in moves:
            step = 1 if a["level"] > 0 else -1
            for lvl in range(step, a["level"] + step, step):  # pastroq darajalarni ham yopamiz
                db.mark_price_alert(a["symbol"], a["day"], lvl)

    post = ai.write_price_alert(moves, db.recent_titles(), db.recent_posts(12))
    if not post:
        return 0
    if post.get("skip") or not post.get("post_html"):
        log.info("Narx harakatlari allaqachon yoritilgan, post chiqmadi")
        close_levels()
        return 0
    crypto_only = all(a["symbol"] in ("BTC-USD", "ETH-USD") for a in moves)
    image = images.pick_image(
        {"image": None},
        {
            "photo_query": "New York Stock Exchange trading floor" if not crypto_only else "Data center server room",
            "card_title": post.get("card_title") or "Bozorda keskin harakat",
            "card_points": post.get("card_points") or [f"{a['name']}: {a['move_desc']}" for a in moves[:3]],
            "category": "CRYPTO" if crypto_only else "MARKETS",
        },
    )
    if publish(post["post_html"], image, "price_moves"):
        close_levels()
        topic = "price-" + "-".join(f"{a['symbol']}{a['level']:+d}" for a in moves)
        db.add_post(None, topic[:120], post.get("summary_uz", ""), "")
        return 1
    return 0


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


def run_once():
    if in_quiet_hours():
        log.info("Tungi tinchlik vaqti (%s), o'tkazib yuborildi", QUIET_HOURS)
        return

    # 1. Rejalashtirilgan doimiy postlar
    try:
        process_scheduled_features()
    except Exception as e:  # noqa: BLE001
        log.warning("Rejalashtirilgan postlar tekshiruvida xato: %s", e)

    # 2. Yangiliklar va keskin narx harakatlari
    budget = min(MAX_POSTS_PER_RUN, MAX_POSTS_PER_DAY - db.posts_today_count(TASHKENT))
    if budget <= 0:
        log.info("Kunlik limit (%d) tugadi", MAX_POSTS_PER_DAY)
        return
    n = process_news(budget)
    if budget - n > 0 and gap_ok():
        n += process_price_moves(budget - n)
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
