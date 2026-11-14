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

💡 <b>Investor uchun oltin qoida:</b>
[1-2 jumla xulosa]

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

💡 <b>Investor uchun oltin qoida:</b>
{lesson_data['golden_rule']}
"""
        return {
            "post_html": html.strip(),
            "summary_uz": lesson_data["title"],
            "card_title": lesson_data["title"],
            "card_points": [t[0] for t in lesson_data.get("terms", [])[:3]],
            "photo_query": lesson_data.get("photo_query", "Wall Street financial stock market"),
        }
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
        telegram_api.send_post(post["post_html"], img)
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
