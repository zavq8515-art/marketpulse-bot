"""Kuzatiladigan RSS manbalar.

`official=True` — rasmiy davlat tashkiloti (ularning suratlari erkin foydalanishga
ko'proq mos va ma'lumoti birlamchi manba hisoblanadi).
Yangi manba qo'shish uchun shu ro'yxatga qator qo'shing.
"""

GN = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="

SOURCES = [
    # --- Rasmiy manbalar ---
    {"name": "Federal Reserve", "url": "https://www.federalreserve.gov/feeds/press_all.xml", "official": True},
    {"name": "BLS", "url": "https://www.bls.gov/feed/bls_latest.rss", "official": True},
    {"name": "BEA", "url": "https://apps.bea.gov/rss/rss.xml", "official": True},
    {"name": "U.S. Treasury", "url": GN + "site:home.treasury.gov+when:2d", "official": True},
    {"name": "EIA", "url": "https://www.eia.gov/rss/todayinenergy.xml", "official": True},
    {"name": "SEC", "url": "https://www.sec.gov/news/pressreleases.rss", "official": True},

    # --- Moliyaviy nashrlar ---
    {"name": "CNBC Finance", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"},
    {"name": "CNBC Economy", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"},
    {"name": "CNBC Earnings", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135"},
    {"name": "CNBC Top News", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"},
    {"name": "CNBC Technology", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910"},
    {"name": "MarketWatch", "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"},
    {"name": "MarketWatch Pulse", "url": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"},
    {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
    {"name": "Investing.com", "url": "https://www.investing.com/rss/news_25.rss"},

    # --- Reuters / AP / Bloomberg (Google News orqali) ---
    {"name": "Reuters", "url": GN + "site:reuters.com+(markets+OR+stocks+OR+fed+OR+oil+OR+treasury)+when:1d"},
    {"name": "AP", "url": GN + "site:apnews.com+(stocks+OR+economy+OR+fed+OR+oil)+when:1d"},
    {"name": "Bloomberg", "url": GN + "site:bloomberg.com+(markets+OR+stocks+OR+fed)+when:1d"},

    # --- Kripto ---
    {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
    {"name": "The Block", "url": "https://www.theblock.co/rss.xml"},
]

# Shu domenlardagi suratlar kanalda ishlatilishi mumkin (rasmiy / ochiq litsenziya).
# Boshqa saytlar uchun brend karta yasaladi.
ALLOWED_IMAGE_DOMAINS = (
    "federalreserve.gov",
    "treasury.gov",
    "bls.gov",
    "bea.gov",
    "eia.gov",
    "sec.gov",
    "whitehouse.gov",
    "nasa.gov",
    "energy.gov",
    "commerce.gov",
    "wikimedia.org",
)
