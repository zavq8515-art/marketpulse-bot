# MARKETPULSE avtomatik yangilik boti

Bot eng mashhur moliyaviy saytlarni (Reuters, AP, Bloomberg, CNBC, MarketWatch, Investing.com, CoinDesk, The Block, Fed, BLS, BEA, EIA, SEC) **har 10 daqiqada** tekshiradi. Faqat **yangi va muhim** xabarlarni tanlaydi, o'zbekcha post yozadi va surati bilan [@MarketPulseZK](https://t.me/MarketPulseZK) kanaliga yuboradi.

## Takrorlanishga qarshi himoya

| Qatlam | Nima qiladi |
|---|---|
| Havola va sarlavha bazasi | Bir marta ko'rilgan xabar qayta olinmaydi |
| AI muharrir | Oxirgi 48 soatdagi postlar bilan solishtiradi. Yangi fakt bo'lmasa (masalan, "Hormuzda vaziyat o'zgarmadi"), post chiqmaydi |
| Muhimlik filtri | Faqat `MIN_IMPORTANCE` (standart 7/10) va undan yuqori baholi xabarlar o'tadi |
| Mavzu kaliti | Bir mavzu (masalan `nvda-earnings-q3`) qayta chiqmaydi |
| Narx ogohlantirishlari | Har kuni narx "snapshot"i chiqmaydi. Post faqat keskin harakatda chiqadi (BTC ±4%, neft ±3%, S&P ±1.2%, 10Y ±10 bp...) |

## Sozlash (bir marta)

1. **Bot yarating:** Telegramda @BotFather → `/newbot` → tokenni nusxalang.
2. **Botni kanalga admin qiling:** kanal → Administratorlar → botni qo'shing → "Post yuborish" huquqini bering.
3. **Gemini kalitini oling:** https://aistudio.google.com/apikey (bepul).
4. `.env.example` faylidan nusxa olib, nomini `.env` qiling va uchta qiymatni kiriting.
5. Tekshiring: `run.bat --check`. Natijada "Post yubora oladimi: HA" chiqishi kerak.

## Ishga tushirish

- `run.bat --once`: bir marta tekshiradi.
- `run.bat`: doimiy ishlaydi (oyna ochiq tursin).

`.env` faylida `DRY_RUN=true` bo'lsa, postlar kanalga **yuborilmaydi**. Ular `data/preview/` papkasiga saqlanadi va siz ularni oldindan ko'rib chiqasiz. Natija yoqsa, `DRY_RUN=false` qiling.

## Asosiy sozlamalar (`.env`)

| Sozlama | Standart | Ma'nosi |
|---|---|---|
| `CHECK_INTERVAL_MIN` | 10 | Tekshiruv oralig'i (daqiqa) |
| `MAX_POSTS_PER_DAY` | 20 | Kunlik limit |
| `MIN_GAP_MIN` | 15 | Postlar orasidagi minimal oraliq. Breaking news (9–10 baho) bu cheklovga bo'ysunmaydi |
| `MIN_IMPORTANCE` | 7 | Muhimlik chegarasi. Ko'paytirsangiz postlar kamayadi |
| `QUIET_HOURS` | 01-07 | Tungi tinchlik (Toshkent vaqti) |

Manba qo'shish uchun `sources.py`, narx chegaralarini o'zgartirish uchun `market.py` → `WATCHLIST` ni tahrirlang.

## Fayllar

- `main.py`: asosiy sikl
- `fetcher.py`: RSS va maqola matni
- `ai.py`: Gemini (saralash va post yozish)
- `images.py`: rasmiy surat yoki brend karta
- `market.py`: keskin narx harakatlari
- `telegram_api.py`: kanalga yuborish
- `db.py`: takrorlanishga qarshi baza

> MarketPulse materiallari axborot va ta'limiy maqsadlarda taqdim etiladi va individual investitsiya tavsiyasi hisoblanmaydi.
