"""Gemini API orqali: (1) yangiliklarni saralash, (2) o'zbekcha post yozish."""
import json
import logging
import time

import requests

from config import GEMINI_API_KEY, GEMINI_MODEL, TASHKENT

log = logging.getLogger("ai")
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _call(prompt, temperature=0.4, retries=3):
    url = API.format(model=GEMINI_MODEL)
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    for attempt in range(retries):
        try:
            r = requests.post(url, params={"key": GEMINI_API_KEY}, json=body, timeout=90)
            if r.status_code in (400, 401, 403):
                log.error("Gemini API kaliti yoki so'rov noto'g'ri: %s", r.text[:300])
                return None
            if r.status_code == 429 or r.status_code >= 500:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
            data = r.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(text)
        except Exception as e:  # noqa: BLE001
            log.warning("Gemini xatosi (%d-urinish): %s", attempt + 1, e)
            time.sleep(5 * (attempt + 1))
    return None


TRIAGE_PROMPT = """Sen MARKETPULSE (o'zbek tilidagi moliyaviy Telegram kanal) bosh muharririsan.
Hozirgi vaqt (Toshkent): {now}

Vazifang: quyidagi YANGI kelgan xabarlardan kanalga chiqarishga arziydiganlarini tanlash.

KANAL MAVZULARI: AQSH fond bozori, makroiqtisodiyot (CPI, PCE, NFP, GDP, PMI...), Fed va foiz stavkalari,
Treasury/obligatsiyalar, dollar va Forex, neft/oltin/xomashyo, bozorga ta'sir qiluvchi geosiyosat,
kripto (BTC, ETH, ETF oqimlari, regulyatsiya), yirik kompaniyalar (earnings, guidance, M&A, IPO), AI va chip sektori.

QAT'IY QOIDALAR:
1. Faqat HAQIQATAN YANGI fakt bo'lsa tanla. Quyidagi "OXIRGI 48 SOATDA CHIQQAN POSTLAR" bilan solishtir.
   Agar xabar o'sha mavzuni yangi raqam/qaror/voqeasiz takrorlasa (masalan "Hormuzda keskinlik davom etmoqda",
   "neft narxi yana o'zgardi", "BTC bosim ostida") — novelty past bo'ladi va TANLAMA.
2. Kundalik shovqin, fikr-mulohaza maqolalari (opinion), "5 ta aksiya sotib oling", reklamalar, shaxsiy moliya
   maslahatlari, sport/madaniyat — TANLAMA.
3. Bir xil voqea haqidagi bir nechta xabardan faqat bittasini tanla. Afzallik: rasmiy manba > maqolasi ochiq o'qiladigan
   manbalar (CNBC, AP, MarketWatch, Yahoo Finance, Investing.com, CoinDesk) > pullik saytlar (Bloomberg, Reuters, WSJ, FT).
4. importance (1-10): bozorga ta'sir kuchi. 9-10 = Fed qarori, CPI/NFP chiqishi, katta bozor qulashi, urush/sanksiya kabi;
   7-8 = yirik kompaniya hisoboti, muhim regulyatsiya, keskin narx harakati sababi; <7 = kichik yangilik.
5. novelty (1-10): kanal uchun qanchalik yangi.

OXIRGI 48 SOATDA CHIQQAN POSTLAR:
{recent}

YANGI XABARLAR:
{items}

Javobni faqat JSON ko'rinishida qaytar:
{{"selected": [{{"index": <raqam>, "importance": <1-10>, "novelty": <1-10>, "topic": "<qisqa mavzu kaliti, inglizcha, masalan 'fed-rate-decision-dec' yoki 'nvda-earnings-q3'>", "reason": "<1 jumla>"}}]}}
Hech narsa arzimasa: {{"selected": []}}
"""


def triage(items, recent):
    if not items:
        return []
    from datetime import datetime

    now = datetime.now(TASHKENT).strftime("%Y-%m-%d %H:%M")
    recent_txt = "\n".join(f"- [{p['topic']}] {p['summary']}" for p in recent) or "(hali post yo'q)"
    selected = []
    # Juda ko'p xabar bo'lsa bo'laklab yuboramiz
    for start in range(0, len(items), 60):
        chunk = items[start : start + 60]
        items_txt = "\n".join(
            f"{start + i}. [{it['source']}{' (RASMIY)' if it['official'] else ''}] {it['title']} — {it['summary'][:200]}"
            for i, it in enumerate(chunk)
        )
        res = _call(TRIAGE_PROMPT.format(now=now, recent=recent_txt, items=items_txt), temperature=0.1)
        if res is None:
            return None  # AI ishlamadi — xabarlar keyingi safar qayta ko'riladi
        if isinstance(res.get("selected"), list):
            selected.extend(res["selected"])
    return selected


WRITER_PROMPT = """Sen MARKETPULSE — o'zbek tilidagi professional moliyaviy Telegram kanal tahlilchisisan.
Shior: "Murakkab moliya → oddiy til → kuchli signal."
Hozirgi vaqt (Toshkent, UTC+5): {now}. AQSH (New York) vaqti: {ny}.

QUYIDAGI MAQOLA ASOSIDA BITTA TELEGRAM POST YOZ.

QAT'IY QOIDALAR:
- Faqat o'zbek tilida, LOTIN yozuvida (o' g' sh ch harflari to'g'ri: o‘, g‘).
- HECH QANDAY raqam, narx, foiz yoki faktni to'qib chiqarma. Faqat maqolada bor ma'lumotni ishlat.
  Maqolada raqam bo'lmasa, raqam yozma.
- Narx qaysi vaqtga tegishli ekanini aniq yoz (yopilish narxi / intraday / premarket / after-hours), agar maqolada bor bo'lsa.
- Vaqtlarni Toshkent vaqtida ber (ET dan aylantirsang, aynan shu sanadagi farqni hisobga ol).
- Tasdiqlanmagan xabar bo'lsa "xabarlarga ko‘ra" / "manbalarga ko‘ra" deb yoz, fakt sifatida berma.
- Moliyaviy terminni inglizcha qoldirsang, birinchi marta qavs ichida qisqa izoh ber (masalan: EPS (aksiya boshiga foyda)).
- Yangilikni qayta aytish bilan cheklanma: albatta "Investor uchun ma’nosi" qismida bozorga ta'sirini tushuntir.
- Shaxs yoki kompaniya tilga olinsa, kimligini qisqa ayt (masalan: "NVIDIA bosh direktori Jensen Huang", "Fed raisi").
  O'quvchi kontekstsiz tushunmaydigan jumla yozma.
- Qo'shimcha kontekst uchun "SHU MAVZUDAGI BOSHQA XABARLAR" bo'limidan ham foydalan (u yerdagi faktlar ham manba hisoblanadi).
- AI qolipidagi so'zlardan qoch ("Ushbu maqolada", "Xulosa qilib aytganda", "muhim ahamiyatga ega" kabi). Tabiiy, qisqa yoz.
- Emoji me'yorida (2-4 ta).
- Telegram HTML formatida yoz: faqat <b>, <i>, <a href="...">, <blockquote> teglari. Markdown ishlatma.
- post_html uzunligi 950 belgidan OSHMASIN (surat ostiga sig'ishi kerak).

POST TUZILISHI (post_html):
<emoji> <b>QISQA SARLAVHA KATTA HARFDA</b>

2-4 qisqa jumla yoki 2-4 ta "•" bilan boshlanuvchi qator: nima bo'ldi, asosiy raqamlar.

<b>💡 Investor uchun ma’nosi:</b> 1-2 jumla.

<i>Manba: <a href="{url}">{source}</a></i>

MAQOLA:
Manba: {source}
Havola: {url}
Sarlavha: {title}
Matn:
{text}

SHU MAVZUDAGI BOSHQA XABARLAR (boshqa manbalardan):
{related}

Javobni faqat JSON ko'rinishida qaytar:
{{
  "post_html": "<yuqoridagi formatdagi post>",
  "summary_uz": "<postning 1 jumlali mazmuni — keyingi takrorlarni aniqlash uchun>",
  "card_title": "<surat kartasi uchun 3-7 so'zli sarlavha, o'zbekcha>",
  "card_points": ["<kartada ko'rsatiladigan 0-3 ta qisqa raqamli fakt, masalan 'S&P 500: −1.2%'. Raqam bo'lmasa bo'sh ro'yxat>"],
  "category": "<bittasi: MARKETS, MACRO, FED, BONDS, FOREX, COMMODITIES, GEOPOLITICS, CRYPTO, COMPANY, TECH>",
  "photo_query": "<maqoladagi asosiy kompaniya, shaxs, mahsulot yoki birja nomi ingliz tilida, Wikipedia'dan haqiqiy suratini topish uchun: masalan 'Nvidia', 'Jensen Huang', 'Boeing 737', 'New York Stock Exchange', 'Federal Reserve Eccles Building', 'Crude oil tanker'>"
}}
"""


def write_post(item, article, related=None):
    from datetime import datetime

    from config import NEW_YORK

    related_txt = "\n".join(f"- [{r['source']}] {r['title']} — {r['summary'][:300]}" for r in (related or [])[:6])
    prompt = WRITER_PROMPT.format(
        related=related_txt or "(yo'q)",
        now=datetime.now(TASHKENT).strftime("%Y-%m-%d %H:%M"),
        ny=datetime.now(NEW_YORK).strftime("%Y-%m-%d %H:%M %Z"),
        url=article["url"],
        source=item["source"],
        title=item["title"],
        text=article["text"],
    )
    res = _call(prompt, temperature=0.5)
    if not res or not res.get("post_html"):
        return None
    return res


PRICE_PROMPT = """Sen MARKETPULSE tahlilchisisan. Hozirgi vaqt (Toshkent): {now}. AQSH vaqti: {ny}.
Quyidagi aktivlar keskin harakat qildi (Yahoo Finance, oldingi yopilishga nisbatan INTRADAY o'zgarish):
{moves}

Shu bilan bog'liq bo'lishi mumkin bo'lgan oxirgi sarlavhalar:
{headlines}

Kanalda oxirgi 12 soatda chiqqan postlar:
{recent}

Agar shu harakatlar kanalda allaqachon yoritilgan bo'lsa va yangi qo'shimcha yo'q bo'lsa: {{"skip": true}} qaytar.
Aks holda BITTA qisqa Telegram post yoz (o'zbek, lotin, Telegram HTML: <b>, <i>). 800 belgidan oshmasin.
- Sarlavha: "⚡️ <b>BOZORDA KESKIN HARAKAT</b>" yoki mazmunga mos boshqa qisqa sarlavha.
- Raqamlarni faqat yuqoridagidan ol, to'qima. INTRADAY ekanini va ma'lumot vaqtini ko'rsat.
- Sabab sarlavhalarda aniq ko'rinsa ayt, aniq bo'lmasa "aniq sabab hali rasman tasdiqlanmagan" de.
- "💡 Investor uchun ma’nosi" qatori bo'lsin.
JSON: {{"skip": false, "post_html": "...", "summary_uz": "...", "card_title": "...", "card_points": ["eng muhim 3 ta harakat, masalan 'S&P 500: +2.3%'"]}}
"""


def write_price_alert(moves, headlines, recent):
    from datetime import datetime

    from config import NEW_YORK

    prompt = PRICE_PROMPT.format(
        now=datetime.now(TASHKENT).strftime("%Y-%m-%d %H:%M"),
        ny=datetime.now(NEW_YORK).strftime("%Y-%m-%d %H:%M %Z"),
        moves="\n".join(f"- {m['name']}: {m['price']} ({m['move_desc']})" for m in moves),
        headlines="\n".join(f"- {h}" for h in headlines[:20]) or "(yo'q)",
        recent="\n".join(f"- {p['summary']}" for p in recent) or "(yo'q)",
    )
    return _call(prompt, temperature=0.3)
