"""Gemini API orqali: (1) yangiliklarni saralash, (2) o'zbekcha post yozish."""
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import json
import logging
import re
import time

import requests

from config import GEMINI_API_KEY, GEMINI_MODEL, TASHKENT

log = logging.getLogger("ai")
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
]


def _call(prompt, temperature=0.4, retries=5):
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    models = list(dict.fromkeys(FALLBACK_MODELS))
    for attempt in range(retries):
        model = models[attempt % len(models)]
        url = API.format(model=model)
        try:
            r = requests.post(url, params={"key": GEMINI_API_KEY}, json=body, timeout=40)
            if r.status_code in (401, 403):
                log.error("Gemini API kaliti yaroqsiz (HTTP %d): %s", r.status_code, r.text[:200])
                return None
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code} ({model}): {r.text[:160]}")
            data = r.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(text)
        except Exception as e:  # noqa: BLE001
            log.warning("Gemini xatosi (%d-urinish, %s): %s", attempt + 1, model, e)
            time.sleep(2 * (attempt + 1))
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
    # Har bir tekshiruvda eng yangi 40 ta xabarni 20 tadan bo'lib tahlil qilamiz
    items = sorted(items, key=lambda x: x.get("published") or "", reverse=True)[:40]
    any_ok = False
    for start in range(0, len(items), 20):
        chunk = items[start : start + 20]
        items_txt = "\n".join(
            f"{start + i}. [{it['source']}{' (RASMIY)' if it['official'] else ''}] {it['title']} — {it['summary'][:160]}"
            for i, it in enumerate(chunk)
        )
        res = _call(TRIAGE_PROMPT.format(now=now, recent=recent_txt, items=items_txt), temperature=0.1)
        if res is not None:
            any_ok = True
            if isinstance(res.get("selected"), list):
                selected.extend(res["selected"])
    return selected if any_ok else None


TICKER_MAP = {
    # Mega-cap Tech
    "apple": "AAPL",
    "tesla": "TSLA",
    "nvidia": "NVDA",
    "microsoft": "MSFT",
    "alphabet": "GOOGL",
    "google": "GOOGL",
    "amazon": "AMZN",
    "meta": "META",
    "facebook": "META",
    # Semiconductors
    "tsmc": "TSM",
    "taiwan semiconductor": "TSM",
    "broadcom": "AVGO",
    "asml": "ASML",
    "amd": "AMD",
    "advanced micro devices": "AMD",
    "qualcomm": "QCOM",
    "intel": "INTC",
    "applied materials": "AMAT",
    "lam research": "LRCX",
    "synopsys": "SNPS",
    "cadence": "CDNS",
    "kla": "KLAC",
    "arm": "ARM",
    "micron": "MU",
    "super micro": "SMCI",
    "smci": "SMCI",
    # Software & Cloud
    "adobe": "ADBE",
    "salesforce": "CRM",
    "oracle": "ORCL",
    "servicenow": "NOW",
    "intuit": "INTU",
    "palo alto": "PANW",
    "crowdstrike": "CRWD",
    "snowflake": "SNOW",
    "palantir": "PLTR",
    "cisco": "CSCO",
    "arista": "ANET",
    # Healthcare & Biotech
    "eli lilly": "LLY",
    "lilly": "LLY",
    "johnson & johnson": "JNJ",
    "abbott": "ABT",
    "thermo fisher": "TMO",
    "danaher": "DHR",
    "intuitive surgical": "ISRG",
    "stryker": "SYK",
    "vertex": "VRTX",
    "regeneron": "REGN",
    "pfizer": "PFE",
    "astrazeneca": "AZN",
    "novartis": "NVS",
    "novo nordisk": "NVO",
    "zoetis": "ZTS",
    # Industrials & Auto
    "caterpillar": "CAT",
    "deere": "DE",
    "john deere": "DE",
    "eaton": "ETN",
    "honeywell": "HON",
    "boeing": "BA",
    "general electric": "GE",
    "uber": "UBER",
    "ford": "F",
    "general motors": "GM",
    "rivian": "RIVN",
    # Consumer & Retail
    "walmart": "WMT",
    "costco": "COST",
    "procter & gamble": "PG",
    "nike": "NKE",
    "starbucks": "SBUX",
    "disney": "DIS",
    # Energy
    "exxon": "XOM",
    "exxonmobil": "XOM",
    "chevron": "CVX",
    # Financial & Crypto
    "coinbase": "COIN",
    "robinhood": "HOOD",
    "berkshire": "BRK",
}


def inject_ticker_hashtags(html: str) -> str:
    """Postda kompaniya nomi uchrasa va uning #TIKER heshtegi hali bo'lmasa, avtomatik qo'shadi."""
    if not html:
        return html
    lower_html = html.lower()
    found_tickers = []
    for name, ticker in TICKER_MAP.items():
        pattern = rf"\b{re.escape(name)}\b"
        if re.search(pattern, lower_html):
            hashtag = f"#{ticker}"
            if hashtag.lower() not in lower_html:
                found_tickers.append(hashtag)

    if not found_tickers:
        return html

    unique_tickers = list(dict.fromkeys(found_tickers))
    tickers_str = " ".join(unique_tickers)

    if "<i>manba" in lower_html:
        html = re.sub(r"(<i>\s*Manba)", f"{tickers_str}\n\n\\1", html, count=1, flags=re.IGNORECASE)
    else:
        html += f"\n\n{tickers_str}"

    return html.strip()


def clean_post_html(html: str, source_name: str = "", url: str = "") -> str:
    """Post matnini tozalash:
    1. 'Investor uchun ma'nosi' bo'limini olib tashlaydi.
    2. Kompaniya tilga olingan bo'lsa, #TIKER heshtegini ta'minlaydi.
    3. 'Manba' qatori doim mavjud bo'lishini 100% kafolatlaydi.
    """
    if not html:
        return html

    # 1. 'Investor uchun ma'nosi' bo'limini va uning matnini qirqib tashlash
    pattern = r"(?:💡\s*)?(?:<blockquote>\s*)?(?:<b>\s*)?(?:💡\s*)?(?:Investor\s+uchun\s+ma[’'‘`]nosi:?)\s*(?:</b>)?.*?(?=(?:<i>\s*Manba|</blockquote>|\Z))"
    html = re.sub(pattern, "", html, flags=re.DOTALL | re.IGNORECASE).strip()
    html = re.sub(r"<blockquote>\s*</blockquote>", "", html).strip()

    # Bo'sh qatorlarni ixchamlashtirish
    html = re.sub(r"\n{3,}", "\n\n", html).strip()

    # 2. Kompaniya aksiya tiker heshteglarini ta'minlash (#TSLA, #NVDA va h.k.)
    html = inject_ticker_hashtags(html)

    # 3. 'Manba' doim bo'lishini ta'minlash
    if "manba" not in html.lower():
        if source_name and url:
            html += f'\n\n<i>Manba: <a href="{url}">{source_name}</a></i>'
        elif source_name:
            html += f"\n\n<i>Manba: {source_name}</i>"
        elif url:
            html += f'\n\n<i>Manba: <a href="{url}">{url}</a></i>'

    return html.strip()


WRITER_PROMPT = """Sen MARKETPULSE — o'zbek tilidagi professional moliyaviy Telegram kanal tahlilchisisan.
Shior: "Murakkab moliya → oddiy til → kuchli signal."
Hozirgi vaqt (Toshkent, UTC+5): {now}. AQSH (New York) vaqti: {ny}.

QUYIDAGI MAQOLA ASOSIDA BITTA TELEGRAM POST YOZ.

QAT'IY QOIDALAR:
- Faqat o'zbek tilida, LOTIN yozuvida (o' g' sh ch harflari to'g'ri: o‘, g‘).
- HECH QANDAY raqam, narx, foiz yoki faktni to'qib chiqarma. Faqat maqolada bor ma'lumotni ishlat.
  Maqolada raqam bo'lmasa, raqam yozma.
- Agar biror kompaniya yoki aksiya tilga olinsa, ALBATTA uning birja tikerini heshteg formatida ko'rsat (masalan: #TSLA, #AAPL, #NVDA, #MSFT, #AMZN, #GOOGL). Sarlavhada yoki post matnida tiker heshtegi bo'lsin.
- Narx qaysi vaqtga tegishli ekanini aniq yoz (yopilish narxi / intraday / premarket / after-hours), agar maqolada bor bo'lsa.
- Vaqtlarni Toshkent vaqtida ber (ET dan aylantirsang, aynan shu sanadagi farqni hisobga ol).
- Tasdiqlanmagan xabar bo'lsa "xabarlarga ko‘ra" / "manbalarga ko‘ra" deb yoz, fakt sifatida berma.
- Moliyaviy terminni inglizcha qoldirsang, birinchi marta qavs ichida qisqa izoh ber (masalan: EPS (aksiya boshiga foyda)).
- "Investor uchun ma'nosi" degan bo'lim yoki jumlani UMUMAN YOZMA (olib tashlangan). Yangilik tafsilotlari va raqamlarni aniq va lo'nda tushuntir.
- Har bir post oxirida DOIM manba ko'rsatilsin: <i>Manba: <a href="{url}">{source}</a></i>. Manbani aslo tushirib qoldirma!
- Shaxs yoki kompaniya tilga olinsa, kimligini qisqa ayt (masalan: "NVIDIA (#NVDA) bosh direktori Jensen Huang", "Fed raisi").
  O'quvchi kontekstsiz tushunmaydigan jumla yozma.
- Qo'shimcha kontekst uchun "SHU MAVZUDAGI BOSHQA XABARLAR" bo'limidan ham foydalan (u yerdagi faktlar ham manba hisoblanadi).
- AI qolipidagi so'zlardan qoch ("Ushbu maqolada", "Xulosa qilib aytganda", "muhim ahamiyatga ega" kabi). Tabiiy, qisqa yoz.
- Emoji me'yorida (2-4 ta).
- Telegram HTML formatida yoz: faqat <b>, <i>, <a href="...">, <blockquote> teglari. Markdown ishlatma.
- post_html uzunligi 900 belgidan OSHMASIN (surat ostiga sig'ishi kerak).

POST TUZILISHI (post_html):
<emoji> <b>QISQA SARLAVHA (#TIKER BILAN) KATTA HARFDA</b>

2-4 qisqa jumla yoki 2-4 ta "•" bilan boshlanuvchi qator: nima bo'ldi, asosiy raqamlar, voqea tafsilotlari.

<i>Manba: <a href="{url}">{source}</a></i>

2-4 qisqa jumla yoki 2-4 ta "•" bilan boshlanuvchi qator: nima bo'ldi, asosiy raqamlar, voqea tafsilotlari.

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
    res["post_html"] = clean_post_html(res["post_html"], source_name=item.get("source", ""), url=article.get("url", ""))
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
- "Investor uchun ma'nosi" bo'limini UMUMAN YOZMA (olib tashlangan).
- Post oxirida albatta: <i>Manba: Yahoo Finance / MarketPulse</i> bo'lsin.
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
    res = _call(prompt, temperature=0.3)
    if res and res.get("post_html"):
        res["post_html"] = clean_post_html(res["post_html"], source_name="Yahoo Finance / MarketPulse")
    return res


DAILY_CLOSE_PROMPT = """Sen MARKETPULSE tahlilchisisan.
Hozirgi sana va vaqt (Toshkent, UTC+5): {now}.

Bugungi AQSH va global moliya bozorlari yopilish / kunlik natijalari:
{indices}

So'nggi muhim bozor sarlavhalari (sabablar va voqealar):
{headlines}

Quyidagi tuzilishda bitta Telegram post yoz (o'zbek tilida, lotin yozuvida, Telegram HTML: <b>, <i>). 950 belgidan oshmasin:
📊 <b>MARKETPULSE | KUNLIK BOZOR YAKUNI</b>
📅 {date}

📉 <b>AQSH FOND BOZORI:</b>
• S&P 500: [narx] ([o'zgarish])
• Nasdaq: [narx] ([o'zgarish])
• Dow Jones: [narx] ([o'zgarish])
• Russell 2000: [narx] ([o'zgarish])
• VIX (qo‘rquv indeksi): [qiymat]

💵 <b>OBLIGATSIYA, DOLLAR VA XOMASHYO:</b>
• US 10Y Yield: [qiymat]
• DXY (dollar indeksi): [qiymat]
• Brent neft: [narx]
• Oltin: [narx]
• Bitcoin: [narx]

📌 <b>Kunning asosiy drayveri:</b> 1-2 jumla (nima sababdan bozor ko'tarildi yoki tushdi).

<i>Manba: NYSE, NASDAQ, CME / MarketPulse</i>

Qat'iy qoidalar:
- Faqat yuqoridagi aniq raqamlarni ishlat, narxlarni to'qima.
- "Investor uchun ma'nosi" bo'limini UMUMAN YOZMA (olib tashlangan).
- Agar biror ko'rsatkich ro'yxatda bo'lmasa, uni yozma.
JSON: {{"post_html": "...", "summary_uz": "Kunlik bozor yakunlari: asosiy indekslar va xomashyo harakati.", "card_title": "Bozor yakunlari", "card_points": ["S&P 500: ...", "Nasdaq: ...", "Brent: ..."], "photo_query": "New York Stock Exchange trading floor"}}
"""


def write_daily_close(indices, headlines):
    from datetime import datetime

    now = datetime.now(TASHKENT)
    prompt = DAILY_CLOSE_PROMPT.format(
        now=now.strftime("%Y-%m-%d %H:%M"),
        date=now.strftime("%d.%m.%Y"),
        indices="\n".join(f"- {i['name']}: {i['price']} ({i['change']})" for i in indices),
        headlines="\n".join(f"- {h}" for h in headlines[:20]) or "(yo'q)",
    )
    res = _call(prompt, temperature=0.3)
    if res and res.get("post_html"):
        res["post_html"] = clean_post_html(res["post_html"], source_name="NYSE, NASDAQ, CME / MarketPulse")
    return res


SECTOR_ETF_PROMPT = """Sen MARKETPULSE tahlilchisisan.
Hozirgi vaqt (Toshkent): {now}.

AQSH fond bozorining asosiy 11 ta SEKTOR ETFlari natijalari (yuqoridan pastga saralangan):
{sectors}

So'nggi bozor sarlavhalari:
{headlines}

Telegram post yoz (o'zbek, lotin, HTML: <b>, <i>). 950 belgidan oshmasin:
🏛 <b>MARKETPULSE | SEKTOR ETFLARI TAHLILI</b>
📅 {date}

🟢 <b>Yetakchi sektorlar (eng yaxshi natija):</b>
• [Top 3-4 sektor nomi va % o'zgarishi]

🔴 <b>Orqada qolgan sektorlar:</b>
• [Eng ko'p pasaygan 3-4 sektor nomi va % o'zgarishi]

📊 <b>Sektorlar rotatsiyasi tahlili:</b>
2-3 jumla: kapital qayerga oqmoqda (mudofaa sektorlarimi yoki texnologiyagami).

<i>Manba: S&P Dow Jones Indices / SPDR</i>

Qat'iy qoidalar:
- "Investor uchun ma'nosi" bo'limini UMUMAN YOZMA (olib tashlangan).
JSON: {{"post_html": "...", "summary_uz": "Sektor ETFlari haftalik/kunlik rotatsiya tahlili.", "card_title": "Sektor ETFlari", "card_points": ["Yetakchi: ...", "Tushuvchi: ..."], "photo_query": "Wall Street stock exchange floor"}}
"""


def write_sector_etfs(sectors, headlines):
    from datetime import datetime

    now = datetime.now(TASHKENT)
    prompt = SECTOR_ETF_PROMPT.format(
        now=now.strftime("%Y-%m-%d %H:%M"),
        date=now.strftime("%d.%m.%Y"),
        sectors="\n".join(f"- {s['name']} ({s['symbol']}): ${s['price']} ({s['change_desc']})" for s in sectors),
        headlines="\n".join(f"- {h}" for h in headlines[:20]) or "(yo'q)",
    )
    res = _call(prompt, temperature=0.3)
    if res and res.get("post_html"):
        res["post_html"] = clean_post_html(res["post_html"], source_name="S&P Dow Jones Indices / SPDR")
    return res


CRYPTO_PULSE_PROMPT = """Sen MARKETPULSE tahlilchisisan.
Hozirgi vaqt (Toshkent): {now}.

Kripto bozori asosiy aktivlari:
{cryptos}

Kriptoga oid so'nggi yangiliklar va sarlavhalar:
{headlines}

Telegram post yoz (o'zbek, lotin, HTML: <b>, <i>). 900 belgidan oshmasin:
₿ <b>MARKETPULSE | KRIPTO PULSE</b>
📅 {date}

• Bitcoin (BTC): [narx] ([o'zgarish])
• Ethereum (ETH): [narx] ([o'zgarish])
• Solana va boshqa altcoinlar harakati

📌 <b>Bozor omillari:</b> ETF oqimlari, likvidlik yoki regulyatsiya yangiliklari.

<i>Manba: CoinMarketCap, Yahoo Finance / MarketPulse</i>

Qat'iy qoidalar:
- "Investor uchun ma'nosi" bo'limini UMUMAN YOZMA (olib tashlangan).
JSON: {{"post_html": "...", "summary_uz": "Bitcoin va kripto bozori sharhi.", "card_title": "Kripto Pulse", "card_points": ["Bitcoin: ...", "Ethereum: ..."], "photo_query": "Bitcoin cryptocurrency blockchain"}}
"""


def write_crypto_pulse(cryptos, headlines):
    from datetime import datetime

    now = datetime.now(TASHKENT)
    prompt = CRYPTO_PULSE_PROMPT.format(
        now=now.strftime("%Y-%m-%d %H:%M"),
        date=now.strftime("%d.%m.%Y"),
        cryptos="\n".join(f"- {c['name']} ({c['symbol']}): ${c['price']} ({c['change_desc']})" for c in cryptos),
        headlines="\n".join(f"- {h}" for h in headlines[:20]) or "(yo'q)",
    )
    res = _call(prompt, temperature=0.3)
    if res and res.get("post_html"):
        res["post_html"] = clean_post_html(res["post_html"], source_name="CoinMarketCap, Yahoo Finance / MarketPulse")
    return res


WEEKLY_GAZETTE_PROMPT = """Sen MARKETPULSE bosh tahlilchisisan.
Sana: {date}.

Hafta yakunlari bo'yicha asosiy bozor ko'rsatkichlari:
{market_data}

Haftaning eng muhim yangiliklari va sarlavhalari:
{headlines}

MARKETPULSE "HAFTALIK INVESTOR GAZETASI" posti (o'zbek, lotin, HTML: <b>, <i>). 950 belgidan oshmasin:
📰 <b>MARKETPULSE | HAFTALIK INVESTOR GAZETASI</b>
📅 {date}

1️⃣ <b>NIMA BO‘LDI?</b>
Haftaning eng muhim 2-3 ta voqeasi qisqa sarhisobi.

2️⃣ <b>NEGA BO‘LDI?</b>
Asosiy fundamental sabablar (Fed, inflyatsiya, geosiyosat, korporativ daromadlar).

3️⃣ <b>BOZOR REAKSIYASI:</b>
Indekslar, xomashyo va obligatsiyalar yakuniy holati.

4️⃣ <b>KEYINGI HAFTA REJASI:</b>
Kelayotgan haftada kutilayotgan muhim iqtisodiy voqealar.

<i>Manba: Bloomberg, Reuters, Wall Street Journal</i>

Qat'iy qoidalar:
- "Investor uchun ma'nosi" bo'limini UMUMAN YOZMA (olib tashlangan).
JSON: {{"post_html": "...", "summary_uz": "Haftalik bozor sarhisobi va kelgusi hafta rejalari.", "card_title": "Haftalik Gazeta", "card_points": ["Hafta yakunlari", "Asosiy signallar", "Kelgusi hafta"], "photo_query": "New York Stock Exchange traders floor"}}
"""


def write_weekly_gazette(indices, headlines):
    from datetime import datetime

    now = datetime.now(TASHKENT)
    prompt = WEEKLY_GAZETTE_PROMPT.format(
        now=now.strftime("%Y-%m-%d %H:%M"),
        date=now.strftime("%d.%m.%Y"),
        market_data="\n".join(f"- {i['name']}: {i['price']} ({i['change']})" for i in indices),
        headlines="\n".join(f"- {h}" for h in headlines[:30]) or "(yo'q)",
    )
    res = _call(prompt, temperature=0.3)
    if res and res.get("post_html"):
        res["post_html"] = clean_post_html(res["post_html"], source_name="Bloomberg, Reuters, Wall Street Journal")
    return res
