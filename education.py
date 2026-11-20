"""MARKETPULSE AKADEMIYA — 100 QADAMDA INVESTITSIYA VA TREYDING

Noldan professional darajagacha 100 ta mukammal darslik o'quv dasturi.
Har bir darsda:
- Hayotiy oddiy analogiya (yosh bola ham tushunadigan do'kon/bozor misolida)
- Asosiy darslik tushunchasi
- Inglizcha-o'zbekcha terminlar lug'ati
- Real kompaniya/tarixiy keys (Apple, Nvidia, Warren Buffett)
- Treyder/investor uchun oltin qoida
"""

import json
import logging
from datetime import datetime

import ai
import db
import images
import telegram_api
from config import TASHKENT
from lessons_data import LESSONS

log = logging.getLogger("education")


def get_lesson(lesson_id: int) -> dict:
    """Berilgan ID bo'yicha dars ma'lumotini qaytaradi."""
    for l in LESSONS:
        if l["id"] == lesson_id:
            return l
    return {
        "id": lesson_id,
        "module": "Professional Treyderlik va Investitsiya",
        "title": f"{lesson_id}-dars: Bozor amaliyoti va strategiyalari",
        "analogy": "Real bozor amaliyoti va strategiyalari",
        "terms": [("Risk Management", "Risk boshqaruvi", "Kapitalni asrash qoidasi")],
        "core_concept": "Moliya bozorlarida barqaror natijaga erishish uchun nazariya va amaliyot uyg'unligi.",
        "case_study": "Wall Street gigantlari tajribasi.",
        "golden_rule": "Bozorga intizom bilan yondashing.",
        "photo_query": "Wall Street stock market trading desk",
    }


LESSON_WRITER_PROMPT = """Sen MARKETPULSE AKADEMIYA bosh murabbiysisan.
Mavzu: "100 QADAMDA INVESTITSIYA VA TREYDING" o'quv dasturi.

QUYIDAGI DARS ASOSIDA TELEGRAM POST TAYYORLA:
Dars raqami: #{id}
Modul: {module}
Mavzu: {title}
Hayotiy analogiya: {analogy}
Terminlar: {terms}
Asosiy darslik: {core_concept}
Real keys: {case_study}
Oltin qoida: {golden_rule}

QAT'IY QOIDALAR:
1. O'zbek tilida, Lotin yozuvida (o‘, g‘, sh, ch to'g'ri bo'lsin).
2. Tili shunday sodda, hayotiy va qiziqarli bo'lsinki, hatto 12 yoshli bola yoki moliyaga umuman aloqasi yo'q inson ham bir o'qishda tushunib, hayratda qolsin!
3. Har bir termin (inglizcha nomi) + (o'zbekcha tarjimasi) + (oddiy tushuntirish) bilan aniq ajratib ko'rsatilsin.
4. Telegram HTML formatida (<b>, <i>).
5. Post uzunligi Telegram fotosurati tagiga (caption) to'liq sig'ishi uchun 850-1000 belgi oralig'ida bo'lsin.
6. Emoji me'yorida, chiroyli va o'qishni osonlashtiradigan qilib ishlatilsin.

POST FORMATI:
🎓 <b>MARKETPULSE AKADEMIYA | DARS #{id}</b>
📌 <b>{title}</b>

🧩 <b>Oddiy tushuntirganda:</b>
[Hayotiy, esda qoladigan ajoyib analogiya orqali 2-3 jumla]

📖 <b>Darsning mag'zi:</b>
[Asosiy tushunchaning sodda va chuqur tushuntirilishi]

🔍 <b>Lug'at / Terminlar:</b>
• <b>Termin (Tarjima):</b> Oddiy qisqa ma'nosi.

📊 <b>Real keys:</b>
[Tarixiy yoki real kompaniya misoli]

💡 <b>Oltin qoida:</b>
[1-2 jumla xulosa]

<i>Manba: MarketPulse Akademiya</i>

JSON formatida qaytar:
{{"post_html": "...", "summary_uz": "...", "card_title": "{title}", "card_points": ["Termin 1", "Termin 2", "Asosiy qoida"], "photo_query": "{photo_query}"}}
"""


def generate_lesson_post(lesson_data: dict) -> dict:
    """Gemini orqali darsni qiziqarli va professional qilib yozadi."""
    terms_txt = "; ".join(f"{eng} ({uzb}): {desc}" for eng, uzb, desc in lesson_data.get("terms", []))
    prompt = LESSON_WRITER_PROMPT.format(
        id=lesson_data["id"],
        module=lesson_data["module"],
        title=lesson_data["title"],
        analogy=lesson_data["analogy"],
        terms=terms_txt,
        core_concept=lesson_data["core_concept"],
        case_study=lesson_data["case_study"],
        golden_rule=lesson_data["golden_rule"],
        photo_query=lesson_data.get("photo_query", "Wall street financial markets"),
    )
    res = ai._call(prompt, temperature=0.4)
    if not res or not res.get("post_html"):
        # Fallback agar sun'iy intellekt javob bermasa
        html = f"""🎓 <b>MARKETPULSE AKADEMIYA | DARS #{lesson_data['id']}</b>
📌 <b>{lesson_data['title']}</b>

🧩 <b>Oddiy tushuntirganda:</b>
{lesson_data['analogy']}

📖 <b>Darsning mag'zi:</b>
{lesson_data['core_concept']}

🔍 <b>Lug'at / Terminlar:</b>
"""
        for eng, uzb, desc in lesson_data.get("terms", []):
            html += f"• <b>{eng} ({uzb}):</b> {desc}\n"
        html += f"""
📊 <b>Real keys:</b>
{lesson_data['case_study']}

💡 <b>Oltin qoida:</b>
{lesson_data['golden_rule']}

<i>Manba: MarketPulse Akademiya</i>
"""
        return {
            "post_html": html.strip(),
            "summary_uz": lesson_data["title"],
            "card_title": lesson_data["title"],
            "card_points": [t[0] for t in lesson_data.get("terms", [])[:3]],
            "photo_query": lesson_data.get("photo_query", "Wall Street financial stock market"),
        }

    # Postni tekshirish: Manba bo'lishi shart
    html = res["post_html"]
    if "manba" not in html.lower():
        html += "\n\n<i>Manba: MarketPulse Akademiya</i>"
    res["post_html"] = html.strip()
    return res


def get_next_lesson_id() -> int:
    """Navbatdagi dars ID raqamini aniqlaydi."""
    last_id = 0
    for lid in range(1, 101):
        if db.is_feature_done("academy_lesson", f"lesson_{lid}"):
            last_id = lid
        else:
            break
    return last_id + 1


def publish_lesson(lesson_id: int = None, dry_run: bool = False) -> bool:
    """Darsni tayyorlab Telegram kanalga yuboradi."""
    if lesson_id is None:
        lesson_id = get_next_lesson_id()

    if lesson_id > 100:
        log.info("100 ta darsning barchasi allaqachon muvaffaqiyatli yakunlangan!")
        return False

    lesson_data = get_lesson(lesson_id)
    log.info("Akademiya darsi tayyorlanmoqda: #%d - %s", lesson_id, lesson_data["title"])

    post = generate_lesson_post(lesson_data)
    if not post or not post.get("post_html"):
        log.error("Dars matni yaratilmadi!")
        return False

    # Maxsus akademiya surati (haqiqiy mavzuli foto yoki oltin brend karta)
    img = images.pick_academy_image(lesson_id, lesson_data, post)

    if dry_run:
        print("\n" + "=" * 60)
        print(f"[DRY RUN - DARS #{lesson_id}]")
        print(post["post_html"])
        print("=" * 60)
        return True

    try:
        res = telegram_api.send_post(post["post_html"], img)
        if isinstance(res, dict) and res.get("message_id"):
            db.save_academy_link(lesson_id, int(res["message_id"]))
        db.mark_feature_done("academy_lesson", f"lesson_{lesson_id}")
        db.add_post(
            None,
            f"academy-lesson-{lesson_id}",
            f"Dars #{lesson_id}: {lesson_data['title']}",
            "",
        )
        log.info("Akademiya darsi #%d muvaffaqiyatli kanalga chiqarildi!", lesson_id)
        return True
    except Exception as e:  # noqa: BLE001
        log.error("Telegramga darsni yuborishda xato: %s", e)
        return False


def process_weekend_academy() -> bool:
    """Haftaning shanba va yakshanba kunlari 3 tadan (jami 6 ta) dars chiqarish jadvali.
    
    Slot 1: 10:00 - 13:00 (Ertalabki dars)
    Slot 2: 14:00 - 17:00 (Tushdan keyingi dars)
    Slot 3: 18:00 - 21:00 (Kechki dars)
    """
    now = datetime.now(TASHKENT)
    weekday = now.weekday()  # 5=Sat, 6=Sun
    if weekday not in (5, 6):
        return False

    hour = now.hour
    slot = None
    if 10 <= hour < 14:
        slot = 1
    elif 14 <= hour < 18:
        slot = 2
    elif 18 <= hour < 22:
        slot = 3

    if slot is None:
        return False

    today_str = now.strftime("%Y-%m-%d")
    slot_key = f"{today_str}_slot_{slot}"

    if db.is_feature_done("academy_slot", slot_key):
        return False

    log.info("Shanba/Yakshanba Akademiya darsi vaqti keldi: %s (Slot %d)", today_str, slot)
    next_id = get_next_lesson_id()
    if next_id > 100:
        log.info("100 ta darsning barchasi tugagan.")
        return False

    if publish_lesson(next_id):
        db.mark_feature_done("academy_slot", slot_key)
        return True
    return False


def post_weekend_announcement(dry_run: bool = False) -> bool:
    """Har juma kechki vaqtda shanba va yakshanba kuni chiqadigan 6 ta Akademiya darsini anons qiladi."""
    start_id = get_next_lesson_id()
    if start_id > 100:
        log.info("100 ta dars yakunlangan, juma anonsi o'tkazib yuborildi.")
        return False

    upcoming = [get_lesson(lid) for lid in range(start_id, min(start_id + 6, 101))]
    if not upcoming:
        return False

    sat_lessons = upcoming[:3]
    sun_lessons = upcoming[3:6]

    sat_txt = "\n".join(f"• <b>Dars #{l['id']}:</b> {l['title']}" for l in sat_lessons)
    sun_txt = "\n".join(f"• <b>Dars #{l['id']}:</b> {l['title']}" for l in sun_lessons) if sun_lessons else ""

    end_id = upcoming[-1]["id"]
    html = (
        f"🎓 <b>ERTAGA — MARKETPULSE WEEKEND AKADEMIYA!</b>\n"
        f"<i>“100 qadamda noldan professional investitsiya va treyding” (#{start_id}–#{end_id}-darslar)</i>\n\n"
        f"📅 <b>SHANBA DARS JADVALI (10:00 • 14:00 • 18:00):</b>\n"
        f"{sat_txt}\n\n"
        + (f"📅 <b>YAKSHANBA DARS JADVALI (10:00 • 14:00 • 18:00):</b>\n{sun_txt}\n\n" if sun_txt else "")
        + "🤝 <b>Kanalni qo‘llab-quvvatlang:</b> Ushbu bepul va mukammal darslar muntazam davom etishi hamda yanada ko‘proq insonlar moliyaviy savodxonlikka erishishi uchun kanal havolasini yaqinlaringiz va do‘stlaringizga ulashing!\n\n"
        '<i>Manba: <a href="https://t.me/MarketPulseZK">MarketPulse Akademiya</a></i>'
    )

    card_points = [f"#{l['id']}: {l['title'][:42]}" for l in upcoming[:3]]
    img = images.academy_card(
        lesson_id=start_id,
        title=f"WEEKEND AKADEMIYA: #{start_id}–#{end_id}-DARSLAR ANONSI",
        module_name="SHANBA & YAKSHANBA",
        points=card_points,
    )

    if dry_run:
        print("\n" + "=" * 60)
        print("[DRY RUN - JUMA AKADEMIYA ANONSI]")
        print(html)
        print("=" * 60)
        return True

    telegram_api.send_post(html, img)
    db.add_post(None, f"academy-announce-{datetime.now(TASHKENT).strftime('%Y-W%W')}", f"Weekend Akademiya anonsi (#{start_id}-#{end_id})", "")
    log.info("Juma kechki Akademiya anonsi (#%d-#%d) muvaffaqiyatli chiqarildi!", start_id, end_id)
    return True


def post_academy_archive(dry_run: bool = False) -> bool:
    """Shu kungacha o'tilgan barcha Akademiya darslarini alohida bosiladigan giperhavolalar bilan
    bitta tartibli mundarija (kutubxona) posti sifatida kanalga chiqaradi.
    """
    last_done = get_next_lesson_id() - 1
    if last_done < 1:
        log.info("Hali birorta Akademiya darsi o'tilmagan, arxiv chiqarilmadi.")
        return False

    links_map = db.get_academy_links()
    channel_slug = "MarketPulseZK"

    lines = []
    for lid in range(1, last_done + 1):
        lesson = get_lesson(lid)
        title = lesson["title"]
        msg_id = links_map.get(lid)
        if msg_id:
            url = f"https://t.me/{channel_slug}/{msg_id}"
            lines.append(f'• <a href="{url}"><b>#{lid}-dars:</b> {title}</a>')
        else:
            lines.append(f"• <b>#{lid}-dars:</b> {title}")

    # Agar darslar soni 60+ ga yetib matn 3600 belgidan oshsa, qismlarga bo'lib yuboradi
    chunks = []
    cur_chunk = []
    cur_len = 0
    for line in lines:
        if cur_len + len(line) + 1 > 3200 and cur_chunk:
            chunks.append(cur_chunk)
            cur_chunk = []
            cur_len = 0
        cur_chunk.append(line)
        cur_len += len(line) + 1
    if cur_chunk:
        chunks.append(cur_chunk)

    total_parts = len(chunks)
    for part_idx, chunk_lines in enumerate(chunks, 1):
        part_suffix = f" ({part_idx}/{total_parts}-qism)" if total_parts > 1 else ""
        header = (
            f"📚 <b>MARKETPULSE AKADEMIYA — OLTIN DARSLAR KUTUBXONASI{part_suffix}</b>\n"
            f"<i>Noldan professional investor va treyderlik sari shu kungacha o‘tilgan barcha darslar (#1–#{last_done}):</i>\n\n"
            f"👇 <b>Istalgan dars ustiga bosing va to‘g‘ridan-to‘g‘ri o‘qing:</b>\n\n"
        )
        body = "\n".join(chunk_lines)
        closing = (
            "\n\n💡 <i>Yangi kelgan obunachilar darslarni #1-darsdan boshlab ketma-ket o‘qib chiqishlari mumkin. "
            "Bilim ulashish — eng yaxshi investitsiya, kanalimizni do‘stlaringizga ham yuboring!</i>\n\n"
            '<i>Manba: <a href="https://t.me/MarketPulseZK">MarketPulse Akademiya</a></i>'
        )
        html = header + body + closing

        if dry_run:
            print("\n" + "=" * 60)
            print(f"[DRY RUN - AKADEMIYA ARXIVI {part_idx}/{total_parts}]")
            print(html)
            print("=" * 60)
        else:
            telegram_api.send_post(html, image_bytes=None)

    if not dry_run:
        db.add_post(None, f"academy-archive-{datetime.now(TASHKENT).strftime('%Y-W%W')}", f"Akademiya kutubxonasi (#1-#{last_done})", "")
        log.info("Juma kechki Akademiya darslari kutubxonasi (#1-#%d) muvaffaqiyatli chiqarildi!", last_done)
    return True
