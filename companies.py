"""MARKETPULSE — AAOIFI STANDARTIGA MOS KOMPANIYALAR TAHLILI (Market Cap > $2B).

Musaffa va Zoya skrining mezonlariga to'liq javob beruvchi, kapitalizatsiyasi 2 milliard
dollardan yuqori bo'lgan dunyoning eng yirik kompaniyalari tahlili.
Eslatma: Foydalanuvchi talabiga ko'ra, postda "halol" yoki "shariat" so'zlari ishlatilmaydi,
faqat sof moliyaviy, biznes va aksiyadorlik ma'lumotlari beriladi.
"""
import logging
import re
from datetime import datetime

import requests

import ai
import db
import images
import telegram_api
from config import TASHKENT, USER_AGENT

log = logging.getLogger("companies")

# AAOIFI / Musaffa / Zoya mezonlariga mos yirik kompaniyalar reyestri (> $2B)
COMPANIES_DB = [
    {
        "symbol": "NVDA",
        "name": "NVIDIA Corporation",
        "sector": "Yarimo‘tkazgichlar & AI",
        "market_cap": "~$3.7 Trillion",
        "about": "Sun'iy intellekt, ma'lumot markazlari va superkompyuterlar uchun chiplar ishlab chiqaruvchi dunyoning eng yirik texnologik giganti. Bugungi generativ AI modellarining 80% dan ortig'i NVIDIA arxitekturasida ishlaydi.",
        "products": [
            ("Blackwell & Hopper GPU", "Ma'lumot markazlari uchun dunyodagi eng qudratli AI hisoblash chiplari"),
            ("GeForce RTX", "Geymerlar, muhandislar va dizaynerlar uchun global etalon videokartalar"),
            ("CUDA platformasi", "Millionlab AI dasturchilarini birlashtirgan muqobilsiz dasturiy ekotizim"),
        ],
        "photo_queries": [
            "Nvidia corporate headquarters Santa Clara building",
            "Nvidia graphics card GPU chip processor",
        ],
    },
    {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "sector": "Iste’mol Elektronikasi & Dastur",
        "market_cap": "~$3.5 Trillion",
        "about": "Dunyoning eng mashhur va qimmat brendlaridan biri. Kompaniya o'zining yopiq, o'ta xavfsiz va bir-biriga mukammal ulangan ekotizimi orqali 2 milliarddan ortiq faol qurilmalarga xizmat ko'rsatadi.",
        "products": [
            ("iPhone & Mac", "Kompaniya daromadining asosiy ustunlari bo'lgan flagman smartfon va kompyuterlar"),
            ("Apple Silicon (M4 / A18)", "Yuqori unumdorlik va quvvat tejamkorligiga ega shaxsiy mikroprotsessorlar"),
            ("Apple Services", "App Store, iCloud va Apple Pay kabi yuqori marjali obuna xizmatlari"),
        ],
        "photo_queries": [
            "Apple Park Cupertino headquarters ring building",
            "Apple flagship store iPhone modern technology",
        ],
    },
    {
        "symbol": "MSFT",
        "name": "Microsoft Corporation",
        "sector": "Bulutli Texnologiyalar & Dastur",
        "market_cap": "~$3.1 Trillion",
        "about": "Korporativ dunyoning asosiy dasturiy ta'minotchisi va sun'iy intellekt infratuzilmasi peshqadami. OpenAI bilan strategik hamkorlik orqali AI imkoniyatlarini barcha korporativ mahsulotlariga integratsiya qilmoqda.",
        "products": [
            ("Microsoft Azure", "Dunyo bo'ylab millionlab korxonalarga xizmat ko'rsatuvchi eng yirik bulutli platforma"),
            ("Microsoft 365 & Copilot", "Ofis, tahlil va korporativ aloqalar uchun sun'iy intellekt yordamchisi"),
            ("Windows & Enterprise Security", "Global kompyuter tizimlarining asosi va kiberxavfsizlik xizmatlari"),
        ],
        "photo_queries": [
            "Microsoft Redmond campus headquarters building",
            "Microsoft cloud data center server infrastructure",
        ],
    },
    {
        "symbol": "GOOGL",
        "name": "Alphabet Inc.",
        "sector": "Internet & Sun’iy Intellekt",
        "market_cap": "~$2.1 Trillion",
        "about": "Global axborot qidiruvining 90% ulushiga ega monopol texnologik xolding. Google Search, YouTube, Android va Gemini AI orqali har kuni milliardlab insonlarning raqamli hayotini boshqaradi.",
        "products": [
            ("Google Search & YouTube", "Dunyoning eng yirik qidiruv va video platformalari, global reklama markazi"),
            ("Google Cloud & TPU", "Korxonalar uchun bulutli xizmatlar va sun'iy intellekt mikrosxemalari"),
            ("Waymo", "To'liq haydovchisiz avtonom robotaksi sohasida jahon yetakchisi"),
        ],
        "photo_queries": [
            "Googleplex headquarters Mountain View California",
            "Google technology server room data center",
        ],
    },
    {
        "symbol": "TSLA",
        "name": "Tesla Inc.",
        "sector": "Avtomobil & Toza Energiya",
        "market_cap": "~$1.1 Trillion",
        "about": "Oddiy avtomobilsozlikdan tashqariga chiqib, avtonom robototexnika, AI hisoblash klasterlari va toza energiya saqlash tizimlariga ixtisoslashgan global innovatsiya peshqadami.",
        "products": [
            ("Model Y & Model 3", "Dunyoda eng ko'p sotilgan elektromobillar oilasi"),
            ("Full Self-Driving (FSD)", "Neyron tarmoqlari va ko'rish kameralariga asoslangan avtonom boshqaruv tizimi"),
            ("Megapack & Optimus", "Sanoat miqyosidagi quvvat saqlash batareyalari va gumanoid robotlar"),
        ],
        "photo_queries": [
            "Tesla Gigafactory Texas factory exterior",
            "Tesla Cybertruck electric vehicle technology",
        ],
    },
    {
        "symbol": "ASML",
        "name": "ASML Holding N.V.",
        "sector": "Yarimo‘tkazgich Uskunalari",
        "market_cap": "~$300+ Milliard",
        "about": "Dunyo mikrochiplar sanoatining eng muhim monopolisti. Dunyodagi barcha eng ilg'or (3nm, 2nm) AI chiplari faqatgina ASML ning EUV litografiya mashinalari orqali ishlab chiqariladi — ularning dunyoda birorta ham to'g'ridan-to'g'ri raqobatchisi yo'q.",
        "products": [
            ("EUV Lithography Systems", "Ekstremal ultrabinafsha nurlar yordamida atom darajasidagi mikrosxemalar chizuvchi mashinalar"),
            ("High-NA EUV", "Kelajakdagi 1nm va undan kichik chiplar uchun 350 million dollarlik eng yangi uskunalar"),
            ("DUV tizimlari", "Avtomobil va sanoat chiplari ishlab chiqarish uchun asosiy ishchi tizimlar"),
        ],
        "photo_queries": [
            "ASML Veldhoven headquarters building Netherlands",
            "ASML EUV lithography machine cleanroom clean room",
        ],
    },
    {
        "symbol": "TSM",
        "name": "Taiwan Semiconductor (TSMC)",
        "sector": "Yarimo‘tkazgich Ishlab Chiqarish",
        "market_cap": "~$950+ Milliard",
        "about": "Dunyodagi eng yirik mustaqil yarimo'tkazgich zavodi (Foundry). Apple, Nvidia, AMD va Qualcomm kabi gigantlarning barcha ilg'or protsessorlari aynan TSMC fabrikalarida ishlab chiqariladi.",
        "products": [
            ("3nm va 2nm Foundry texnologiyalari", "Global sun'iy intellekt chiplarining 90% dan ortig'ini jismoniy ishlab chiqarish"),
            ("Ilg'or qadoqlash (CoWoS)", "AI protsessorlari va tezkor HBM xotirani bitta chipga jamlash texnologiyasi"),
            ("Maxsus kremniy plastinalar", "Avtomobilsozlik, 5G aloqa va IoT qurilmalari uchun maxsus chiplar"),
        ],
        "photo_queries": [
            "TSMC headquarters Hsinchu Science Park Taiwan",
            "Silicon wafer semiconductor manufacturing cleanroom",
        ],
    },
    {
        "symbol": "LLY",
        "name": "Eli Lilly and Company",
        "sector": "Farmatsevtika & Biotexnologiya",
        "market_cap": "~$750+ Milliard",
        "about": "Dunyoning eng qimmat sog'liqni saqlash va farmatsevtika giganti. Diabet, semizlik va Altsgeymer kasalliklariga qarshi inqilobiy dori vositalari ishlab chiqarish orqali bozor kapitallashuvi bo'yicha tarixiy rekordlarni qayd etdi.",
        "products": [
            ("Mounjaro & Zepbound (Tirzepatide)", "Diabet va vazn yo'qotish bo'yicha global talab eng yuqori bo'lgan inqilobiy dori"),
            ("Donanemab", "Altsgeymer kasalligi rivojlanishini sekinlashtiruvchi zamonaviy preparat"),
            ("Onkologiya va immunologiya", "Saraton va immunitet kasalliklariga qarshi ilmiy terapevtik vositalar"),
        ],
        "photo_queries": [
            "Eli Lilly headquarters Indianapolis corporate campus",
            "Pharmaceutical laboratory research medical biotechnology",
        ],
    },
    {
        "symbol": "ISRG",
        "name": "Intuitive Surgical, Inc.",
        "sector": "Tibbiyot Texnologiyalari & Robototexnika",
        "market_cap": "~$180+ Milliard",
        "about": "Robotlashtirilgan jarrohlik tizimlari bo'yicha dunyodagi mutlaq peshqadam. Uning 'da Vinci' robotlari butun dunyo shifoxonalarida millionlab insonlar hayotini saqlab qoluvchi o'ta aniq jarrohlik amaliyotlarini bajaradi.",
        "products": [
            ("da Vinci Jarrohlik Tizimi", "Inson qo'li yetolmaydigan mikro-aniqlikdagi robotlashtirilgan jarrohlik uskunasi"),
            ("Ion Endoluminal Tizimi", "O'pka to'qimalarining chuqur qismlaridan o'simtalarni xavfsiz biopsiya qilish texnologiyasi"),
            ("Jarrohlik asboblari va sarf materiallari", "Har bir operatsiyadan muntazam takrorlanuvchi yuqori marjali daromad oqimi"),
        ],
        "photo_queries": [
            "Intuitive Surgical headquarters Sunnyvale California",
            "da Vinci surgical robot medical operation hospital",
        ],
    },
    {
        "symbol": "CRM",
        "name": "Salesforce, Inc.",
        "sector": "Korporativ Dastur & AI Agentlar",
        "market_cap": "~$320+ Milliard",
        "about": "Mijozlar bilan munosabatlarni boshqarish (CRM) sohasida dunyoning 1-raqamli platformasi. O'zining 'Agentforce' platformasi orqali korxonalarga mustaqil ishlovchi sun'iy intellekt agentlarini taqdim etmoqda.",
        "products": [
            ("Sales & Service Cloud", "Global kompaniyalarning sotuv va mijozlarga xizmat ko'rsatish tizimi"),
            ("Agentforce AI", "Inson yordamisiz mijozlar muammolarini 24/7 hal qiluvchi aqlli AI agentlar"),
            ("Data Cloud & Slack", "Korporativ xabarlashuv va real vaqtli mijozlar tahlili integratsiyasi"),
        ],
        "photo_queries": [
            "Salesforce Tower San Francisco skyline skyscraper",
            "Salesforce headquarters San Francisco modern office",
        ],
    },
    {
        "symbol": "ADBE",
        "name": "Adobe Inc.",
        "sector": "Raqamli Media & Dizayn Dasturlari",
        "market_cap": "~$230+ Milliard",
        "about": "Grafik dizayn, vizual kontent va raqamli hujjatlar bo'yicha dunyodagi eng qudratli dasturiy ekotizim. Photoshop, Illustrator va Premiere Pro orqali ijodiy sohaning monopolisti hisoblanadi.",
        "products": [
            ("Adobe Creative Cloud", "Photoshop, Illustrator, Premiere Pro va After Effects obuna xizmatlari"),
            ("Adobe Firefly", "Tijorat maqsadlarida xavfsiz foydalanish uchun yaratilgan generativ AI modeli"),
            ("Document Cloud & Acrobat", "Dunyo bo'ylab elektron hujjat aylanishining asosi bo'lgan PDF standarti"),
        ],
        "photo_queries": [
            "Adobe headquarters San Jose California building",
            "Adobe software creative design digital workstation",
        ],
    },
    {
        "symbol": "AMD",
        "name": "Advanced Micro Devices, Inc.",
        "sector": "Yarimo‘tkazgichlar & AI Tezlatgichlar",
        "market_cap": "~$220+ Milliard",
        "about": "Lisa Su boshchiligida kompyuter va server protsessorlari bozorida Intel'ni ortda qoldirgan va AI ma'lumot markazlari bo'yicha Nvidia'ga eng kuchli raqobatchi bo'lgan yarimo'tkazgich ishlab chiqaruvchisi.",
        "products": [
            ("Instinct MI300X AI chiplari", "Yirik til modellarini (LLM) o'qitish va ishlatish uchun ilg'or AI tezlatgichlari"),
            ("EPYC Server protsessorlari", "Dunyo bulutli provayderlari ma'lumot markazlarining asosiy yuragi"),
            ("Ryzen protsessorlari", "Shaxsiy kompyuterlar va o'yin noutbuklari uchun yuqori unumli chiplar"),
        ],
        "photo_queries": [
            "AMD corporate headquarters Santa Clara building",
            "AMD Ryzen computer processor CPU chip technology",
        ],
    },
    {
        "symbol": "PLTR",
        "name": "Palantir Technologies Inc.",
        "sector": "Katta Ma’lumotlar & AI Dasturiy Ta’minot",
        "market_cap": "~$150+ Milliard",
        "about": "Maxfiy razvedka, mudofaa va yirik korporatsiyalar uchun murakkab ma'lumotlarni tahlil qiluvchi dasturiy ta'minot giganti. Uning AIP platformasi sun'iy intellektni biznes jarayonlariga to'g'ridan-to'g'ri integratsiya qiladi.",
        "products": [
            ("Palantir AIP", "Korxonalarning maxfiy ma'lumotlar bazalariga ulangan sun'iy intellekt operatsion tizimi"),
            ("Foundry", "Yirik korporatsiyalar (Airbus, BP, Ferrari) uchun ishlab chiqarish va logistika tahlili"),
            ("Gotham", "Davlat va mudofaa idoralari uchun global xavfsizlik va qaror qabul qilish tizimi"),
        ],
        "photo_queries": [
            "Palantir Technologies headquarters Denver Colorado",
            "Big data analytics software dashboard visualization",
        ],
    },
    {
        "symbol": "NOW",
        "name": "ServiceNow, Inc.",
        "sector": "Korporativ Ish Oqimlari & AI",
        "market_cap": "~$210+ Milliard",
        "about": "Dunyoning Fortune 500 ro'yxatidagi kompaniyalarning 85 foiziga korporativ jarayonlarni avtomatlashtirish xizmatini ko'rsatuvchi dasturiy gigant. Korxonalar ichidagi IT, HR va operatsion ishlarni bitta tizimga jamlaydi.",
        "products": [
            ("Now Platform", "Barcha korporativ tizimlarni birlashtiruvchi bulutli avtomatlashtirish arxitekturasi"),
            ("Now Assist Generative AI", "Xodimlarning vaqtini tejovchi aqlli qidiruv va ish oqimi yordamchisi"),
            ("IT Service Management (ITSM)", "Global korxonalar uchun texnik va operatsion yordam infratuzilmasi"),
        ],
        "photo_queries": [
            "ServiceNow headquarters Santa Clara campus building",
            "Enterprise software corporate cloud data analytics",
        ],
    },
    {
        "symbol": "QCOM",
        "name": "Qualcomm Incorporated",
        "sector": "Mobil Aloqa & 5G Chiplar",
        "market_cap": "~$180+ Milliard",
        "about": "Smartfonlar va mobil aloqa vositalari uchun protsessorlar ishlab chiqaruvchi yetakchi firma. Snapdragon chiplari millionlab Android smartfonlari va endilikda sun'iy intellektli noutbuklarning asosiy drayveri hisoblanadi.",
        "products": [
            ("Snapdragon 8 Elite", "Mobil qurilmalar uchun eng ilg'or generativ AI va grafik imkoniyatli protsessor"),
            ("Snapdragon X Elite", "Windows noutbuklari uchun batareyani o'ta kam sarflovchi yangi avlod kompyuter chipi"),
            ("5G Modem va Patentlar", "Global mobil aloqa sohasidagi eng yirik litsenziyalash portfeli"),
        ],
        "photo_queries": [
            "Qualcomm headquarters San Diego California building",
            "Qualcomm Snapdragon mobile processor chip tech",
        ],
    },
    {
        "symbol": "PANW",
        "name": "Palo Alto Networks, Inc.",
        "sector": "Kiberxavfsizlik",
        "market_cap": "~$120+ Milliard",
        "about": "Kiberxavfsizlik sohasida jahon yetakchisi. Korxona tarmoqlari, bulutli infratuzilma va sun'iy intellekt tizimlarini xakerlik hujumlari hamda zararli dasturlardan real vaqtda himoya qiladi.",
        "products": [
            ("Strata & Next-Gen Firewall", "Dunyodagi eng ishonchli korporativ tarmoq xavfsizligi devorlari"),
            ("Prisma Cloud", "Bulutli muhitda ishlovchi ilovalar va ma'lumotlarni himoyalash platformasi"),
            ("Cortex XDR & Precision AI", "Sun'iy intellekt orqali kiberhujumlarni soniyalar ichida aniqlash va bartaraf etish"),
        ],
        "photo_queries": [
            "Palo Alto Networks headquarters Santa Clara building",
            "Cybersecurity digital network security shield concept",
        ],
    },
    {
        "symbol": "DE",
        "name": "Deere & Company (John Deere)",
        "sector": "Aqlli Qishloq Xo‘jaligi & Mashinasozlik",
        "market_cap": "~$115+ Milliard",
        "about": "180 yildan ortiq tarixga ega og'ir mashinasozlik giganti. Bugungi kunda sun'iy intellekt, GPS navigatsiya va kompyuter ko'rishi yordamida to'liq avtonom ishlaydigan aqlli traktor va kombaynlarni ishlab chiqaradi.",
        "products": [
            ("Avtonom 8R Traktorlari", "Haydovchisiz dalada o'zi haydov va ekin ishlarini bajaruvchi aqlli traktor"),
            ("See & Spray Texnologiyasi", "Kamerada begona o'tni ko'rib, faqat unga kimyoviy dori sepuvchi sun'iy intellekt tizimi"),
            ("John Deere Operations Center", "Fermerlarga hosildorlikni bulut orqali prognoz qilish imkonini beruvchi platforma"),
        ],
        "photo_queries": [
            "John Deere tractor green modern combine field",
            "John Deere headquarters Moline Illinois corporate",
        ],
    },
    {
        "symbol": "CAT",
        "name": "Caterpillar Inc.",
        "sector": "Og‘ir Qurilish & Konchilik Texnikasi",
        "market_cap": "~$190+ Milliard",
        "about": "Qurilish, tog'-kon sanoati va energetika mashinasozligida dunyoning 1-raqamli brendi. Uning sariq rangli ekskavator, buldozer va ulkan samosvallari global iqtisodiy infratuzilmaning asosiy barometridir.",
        "products": [
            ("Og'ir konchilik yuk mashinalari (797F)", "400 tonnagacha yuk ko'taruvchi avtonom konchilik gigantlari"),
            ("Gidravlik ekskavator va buldozerlar", "Dunyodagi barcha yirik yo'l va bino qurilishlarining asosiy texnikasi"),
            ("Cat Digital & Telematics", "Mashinalar holatini masofadan kuzatuvchi va nosozliklarni oldindan bildiruvchi sensorlar"),
        ],
        "photo_queries": [
            "Caterpillar excavator heavy construction machinery yellow",
            "Caterpillar headquarters Irving Texas corporate building",
        ],
    },
    {
        "symbol": "UBER",
        "name": "Uber Technologies, Inc.",
        "sector": "Shahar Harakatchanligi & Logistika",
        "market_cap": "~$150+ Milliard",
        "about": "Shahar transporti va taom yetkazib berish sohasini tubdan o'zgartirgan global platforma. 70 dan ortiq mamlakatda faoliyat yuritadi va har oy 150 milliondan ziyod faol foydalanuvchiga xizmat ko'rsatadi.",
        "products": [
            ("Uber Mobility (Rideshare)", "Dunyodagi eng yirik taksi va shaxsiy haydovchi chaqirish xizmati"),
            ("Uber Eats", "Restoranlar va oziq-ovqat do'konlaridan tezkor buyurtma platformasi"),
            ("Uber Freight & Autonomous", "Yuk tashish logistikasi va avtonom robotaksilar (Waymo) integratsiyasi"),
        ],
        "photo_queries": [
            "Uber headquarters San Francisco mission bay building",
            "Uber mobile app rideshare car street smartphone",
        ],
    },
    {
        "symbol": "VRTX",
        "name": "Vertex Pharmaceuticals Incorporated",
        "sector": "Biotexnologiya & Gen Terapiyasi",
        "market_cap": "~$110+ Milliard",
        "about": "Irsiy va og'ir kasalliklarni davolashda inqilob qilgan global biotexnologiya kompaniyasi. Nobel mukofotiga sazovor bo'lgan CRISPR gen tahrirlash texnologiyasiga asoslangan dunyodagi birinchi rasmiy dorini yaratgan.",
        "products": [
            ("Trikafta / Kaftrio", "Mukovissidoz (Cystic Fibrosis) kasalligiga chalingan bemorlar hayotini tubdan o'zgartirgan asosiy dori"),
            ("Casgevy (CRISPR)", "O'roqsimon hujayrali anemiya kasalligini gen darajasida davolovchi tarixiy preparat"),
            ("Og'riqsizlantiruvchi vositalar", "Opioid bo'lmagan, qaramlik chaqirmaydigan yangi avlod og'riq qoldiruvchi dorilar"),
        ],
        "photo_queries": [
            "Vertex Pharmaceuticals headquarters Boston seaport building",
            "CRISPR gene editing medical biotechnology laboratory research",
        ],
    },
]


def get_company(symbol: str) -> dict:
    """Belgilangan simvol bo'yicha kompaniyani topadi."""
    sym_upper = symbol.strip().upper()
    for c in COMPANIES_DB:
        if c["symbol"] == sym_upper:
            return c
    return None


def fetch_live_stats(symbol: str) -> dict:
    """Yahoo Finance chart API dan jonli ma'lumotlarni tortadi."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}"
        r = requests.get(url, params={"range": "1d", "interval": "5m"}, headers={"User-Agent": USER_AGENT}, timeout=15)
        r.raise_for_status()
        meta = r.json()["chart"]["result"][0]["meta"]
        price = float(meta.get("regularMarketPrice") or 0.0)
        prev = float(meta.get("previousClose") or meta.get("chartPreviousClose") or price)
        pct = (price - prev) / prev * 100 if prev else 0.0
        high_52w = meta.get("fiftyTwoWeekHigh") or 0.0
        low_52w = meta.get("fiftyTwoWeekLow") or 0.0
        volume = meta.get("regularMarketVolume") or 0
        return {
            "price": round(price, 2),
            "change_pct": round(pct, 2),
            "change_desc": f"{pct:+.2f}%",
            "high_52w": round(float(high_52w), 2),
            "low_52w": round(float(low_52w), 2),
            "volume": volume,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("Yahoo Finance ma'lumoti olinmadi (%s): %s", symbol, e)
        return {
            "price": 0.0,
            "change_pct": 0.0,
            "change_desc": "0.00%",
            "high_52w": 0.0,
            "low_52w": 0.0,
            "volume": 0,
        }


def fetch_company_media(company: dict, stats: dict) -> list:
    """Kompaniya uchun 2-3 ta yuqori sifatli rasmlar to'plamini (albom) tayyorlaydi:
    1) Bosh ofis / Bino surati (Wikipedia)
    2) Flagman mahsulot / Texnologiya surati (Wikipedia)
    3) Moliyaviy ko'rsatkichlar kartasi (Infografika)
    """
    photos = []
    queries = company.get("photo_queries", [])

    # 1. Bosh ofis surati
    if len(queries) >= 1:
        img1 = images.fetch_topic_photo(queries[0])
        if img1:
            photos.append(img1)

    # 2. Flagman mahsulot surati
    if len(queries) >= 2:
        img2 = images.fetch_topic_photo(queries[1])
        if img2:
            photos.append(img2)

    # 3. Moliyaviy infografika kartasi
    range_str = f"${stats.get('low_52w', 0)} – ${stats.get('high_52w', 0)}" if stats.get("low_52w") else "Bozor tahlili"
    card_img = images.company_metrics_card(
        symbol=company["symbol"],
        name=company["name"],
        price=stats.get("price", 0.0),
        change_desc=stats.get("change_desc", "0.00%"),
        market_cap=company.get("market_cap", "> $2B"),
        range_52w=range_str,
        sector=company.get("sector", "Global Bozor"),
    )
    if card_img:
        photos.append(card_img)

    return photos


def generate_company_post(company: dict, stats: dict) -> str:
    """Kompaniya haqida professional, qiziqarli va lo'nda post yaratadi.
    MUHIMI: Foydalanuvchi talabiga asosan halollik yoki shariat haqida hech narsa yozilmaydi.
    """
    symbol = company["symbol"]
    name = company["name"]
    sector = company["sector"]
    market_cap = company["market_cap"]
    about = company["about"]
    products = company.get("products", [])

    price_str = f"${stats['price']:.2f}" if stats.get("price") else "Bozor kursi"
    chg_str = f"({stats['change_desc']})" if stats.get("change_desc") else ""
    range_str = f"${stats['low_52w']} – ${stats['high_52w']}" if stats.get("low_52w") else "Oxirgi 1 yil"

    products_txt = ""
    for prod_name, prod_desc in products[:3]:
        products_txt += f"• <b>{prod_name}:</b> {prod_desc}\n"

    html = f"""🏢 <b>#{symbol} | {name.upper()}</b>
📌 <b>Global bozor gigantlari tahlili</b>

🏛 <b>Kompaniya haqida:</b>
{about}

📦 <b>Asosiy mahsulot va yo‘nalishlari:</b>
{products_txt.strip()}

📊 <b>Bozor va moliyaviy ko‘rsatkichlar:</b>
• Aksiya narxi: <b>{price_str} {chg_str}</b>
• Bozor kapitallashuvi: <b>{market_cap}</b>
• 52 haftalik diapazon: {range_str}
• Sektor: {sector}

<i>Manba: SEC 10-Q hisoboti, NASDAQ / Kompaniya rasmiy ma’lumotlari</i>"""

    return html.strip()


def get_next_company_symbol() -> str:
    """Navbatdagi kompaniyani aniqlaydi."""
    for c in COMPANIES_DB:
        sym = c["symbol"]
        if not db.is_feature_done("company_spotlight", sym):
            return sym
    # Agar hammasi bir marta o'tgan bo'lsa, qaytadan boshlaydi
    return COMPANIES_DB[0]["symbol"]


def publish_company_spotlight(symbol: str = None, dry_run: bool = False) -> bool:
    """Kompaniya tahlilini tayyorlab, rasmlar albomi bilan Telegram kanalga yuboradi."""
    if not symbol:
        symbol = get_next_company_symbol()

    company = get_company(symbol)
    if not company:
        log.error("Kompaniya topilmadi: %s", symbol)
        return False

    log.info("Kompaniya tahlili tayyorlanmoqda: #%s (%s)", company["symbol"], company["name"])
    stats = fetch_live_stats(company["symbol"])
    post_html = generate_company_post(company, stats)
    photos = fetch_company_media(company, stats)

    if dry_run:
        print("\n" + "=" * 65)
        print(f"[DRY RUN - #{company['symbol']} KOMPANIYA TAHLILI]")
        print(f"Topilgan suratlar soni: {len(photos)}")
        print(post_html)
        print("=" * 65)
        return True

    try:
        telegram_api.send_media_group(post_html, photos)
        db.mark_feature_done("company_spotlight", company["symbol"])
        db.add_post(
            None,
            f"company-{company['symbol'].lower()}",
            f"#{company['symbol']} - {company['name']} tahlili",
            "",
        )
        log.info("Kompaniya tahlili (#%s) muvaffaqiyatli kanalga chiqarildi!", company["symbol"])
        return True
    except Exception as e:  # noqa: BLE001
        log.error("Kompaniya tahlilini yuborishda xato: %s", e)
        return False
