"""Yangi O'zbek Alifbosi konverteri va imlo nazorati.

Almashtirish qoidalari:
    O‘ / o‘  ->  Ö / ö
    G‘ / g‘  ->  Ğ / ğ
    Sh / sh  ->  Ş / ş
    Ch / ch  ->  Ç / ç

HTML teglar (<...>), URL havolalar (https://..., t.me/...),
aksiya tiker heshteglari (#SHOP, #CHWY...), @username lar va
inglizcha/xalqaro moliya/brend atamalari (MarketWatch, Berkshire, Cash Flow,
Goldman Sachs, Washington, FedWatch, Blockchain, Short Squeeze va h.k.)
BUZILMASDAN asl holatida saqlanadi!
"""
import re

# Inglizcha / xalqaro moliya, brend va shaxs nomlari (Sh/Ch harflari o'zgartirilmaydi)
ENGLISH_KEEP_WORDS = {
    "washington", "sachs", "schwab", "berkshire", "chevron", "chicago", "china",
    "chinese", "chip", "chips", "chipotle", "chewy", "chart", "charts", "cash",
    "short", "shorts", "share", "shares", "ishares", "marketwatch", "fedwatch",
    "watch", "watchlist", "tech", "fintech", "biotech", "cleantech", "blockchain",
    "exchange", "research", "benchmark", "chatgpt", "shopify", "shell", "shein",
    "shiba", "flash", "crash", "switch", "launch", "search", "speech", "march",
    "branch", "check", "choice", "channel", "show", "shift", "shock", "sharp",
    "push", "fresh", "british", "english", "turkish", "charles", "richard",
    "michael", "christopher", "mitchell", "warsh", "marshall", "deutsche",
    "schneider", "bosch", "porsche", "roche", "schlumberger", "hershey",
    "oshkosh", "ash", "hash", "dash", "finish", "wish", "dish", "fish", "rush",
    "slash", "crush", "wash", "stockwatch", "yahoo", "schwab", "chase", "chubb",
    "charter", "chevron", "cheniere", "church", "richmond", "michigan",
    "massachusetts", "manchester", "chelsea", "champions", "coach", "reach",
    "teach", "each", "much", "such", "which", "high", "approach", "stockcharts",
    "tradingview", "crunch", "techcrunch", "pitchbook", "reuters", "bloomberg",
    "nasdaq", "nyse", "cboe", "edgar", "openinsider", "forexfactory", "cbu",
    "blackrock", "vanguard", "citadel", "bridgewater", "hathaway", "microsoft",
    "alphabet", "nvidia", "apple", "tesla", "palantir", "servicenow", "broadcom",
    "qualcomm", "crowdstrike", "salesforce", "synopsys", "intuit", "intuitive",
    "eli", "lilly", "vertex", "regeneron", "stryker", "danaher", "zoetis",
    "caterpillar", "deere", "eaton", "honeywell", "costco", "walmart", "procter",
    "gamble", "exxon", "exxonmobil", "boeing", "uber", "adobe", "oracle", "micron",
    "applied", "materials", "lam", "kla", "cadence", "arista", "networks",
    "palo", "alto", "novartis", "astrazeneca", "pfizer", "abbott", "thermo",
    "fisher", "johnson", "starbucks", "disney", "nike", "ford", "rivian",
    "coinbase", "robinhood", "anchorage", "kalshi", "morpho", "bitcoin", "ethereum",
    "solana", "ripple", "tether", "binance", "blackwell", "hopper", "geforce",
    "cuda", "iphone", "macbook", "icloud", "waymo", "megapack", "optimus",
    "cybertruck", "gigafactory", "hollywood", "wall", "street", "treasury",
    "federal", "reserve", "fomc", "cpi", "ppi", "pce", "nfp", "gdp", "pmi",
    "eps", "pe", "roe", "roa", "ebitda", "etf", "ipo", "sec", "bls", "bea",
    "eia", "cftc", "opec", "vix", "dxy", "wti", "brent", "usd", "eur", "gbp",
    "rub", "uzs", "premarket", "afterhours", "intraday", "overbought", "oversold",
    "breakout", "retest", "support", "resistance", "bull", "bear", "swing",
    "scalping", "hodl", "halving", "yield", "curve", "spread", "heatmap",
    "movers", "gainers", "losers", "unusual", "volume", "scanner", "radar",
    "smart", "money", "insider", "earnings", "calendar", "guidance", "consensus",
    "fear", "greed", "neutral", "extreme", "sentiment", "momentum", "dividend",
    "buyback", "split", "liquidity", "moat", "rebalancing", "allocation",
    "compound", "interest", "inflation", "recession", "tariff", "tariffs",
    "sanctions", "geopolitics", "oil", "gold", "copper", "silver", "crypto",
    "marketpulse", "marketpulsezk",
}

# Himoyalangan tokenlar: HTML teglar, URL lar, #heshteglar, @username lar
_PROTECTED_RE = re.compile(
    r"(<[^>]+>|https?://\S+|t\.me/\S+|#[A-Za-z0-9_]+|@[A-Za-z0-9_]+)",
    re.IGNORECASE,
)

# Inglizcha egalik shakllari (IPO's, CEO's, CFO's, S&P's) o' -> ö bo'lib ketmasligi uchun
_ENG_POSSESSIVE_RE = re.compile(r"\b(IPO|CEO|CFO|CTO|COO|NGO|WHO|NATO|UNESCO)['’`ʼ]s\b")

# O'zbekcha keng tarqalgan imloviy xatolar tuzatmasi
_TYPO_FIXES = [
    (r"\bsotiboldi\b", "sotib oldi"),
    (r"\bsotibolish\b", "sotib olish"),
    (r"\bbo'libo'tdi\b", "bo‘lib o‘tdi"),
    (r"\bshu\s+bilan\s+birga\s+shu\s+bilan\s+birga\b", "shu bilan birga"),
    (r"  +", " "),
]


def _convert_word(word: str) -> str:
    """Bitta so'zni inglizcha istisnolarni saqlagan holda yangi o'zbek alifbosiga o'giradi."""
    if not word:
        return word

    # Inglizcha egalik (CEO's, IPO's) -> buzilmaydi
    if _ENG_POSSESSIVE_RE.fullmatch(word):
        return word

    # So'zning sof harfli o'zagini tekshiramiz (masalan "MarketWatch'ning" -> "marketwatch")
    alpha_core = re.sub(r"[^A-Za-z]", "", word.split("'")[0].split("’")[0].split("‘")[0]).lower()
    is_english_core = alpha_core in ENGLISH_KEEP_WORDS

    # 1. O‘/o‘ va G‘/g‘ (faqat inglizcha bo'lmagan so'zlarda yoki o'zbek qo'shimchalarida)
    # Apostrofning barcha variantlari: ‘ (U+2018), ’ (U+2019), ' (U+0027), ` (U+0060), ʼ (U+02BC)
    if not is_english_core:
        word = re.sub(r"O['`‘’ʼ]", "Ö", word)
        word = re.sub(r"o['`‘’ʼ]", "ö", word)
        word = re.sub(r"G['`‘’ʼ]", "Ğ", word)
        word = re.sub(r"g['`‘’ʼ]", "ğ", word)

    # 2. Sh/sh va Ch/ch (inglizcha so'zlarning o'zagiga tegmaymiz!)
    if is_english_core:
        # Agar inglizcha so'zga o'zbekcha qo'shimcha ulangan bo'lsa (masalan "Washington'ga", "Tech'chilar"):
        # Faqat apostrofdan keyingi o'zbekcha qo'shimcha qismini o'giramiz
        m = re.match(r"^([A-Za-z]+)([`'‘’ʼ-].+)$", word)
        if m:
            stem, suffix = m.group(1), m.group(2)
            suffix = re.sub(r"O['`‘’ʼ]", "Ö", suffix)
            suffix = re.sub(r"o['`‘’ʼ]", "ö", suffix)
            suffix = re.sub(r"G['`‘’ʼ]", "Ğ", suffix)
            suffix = re.sub(r"g['`‘’ʼ]", "ğ", suffix)
            suffix = suffix.replace("SH", "Ş").replace("Sh", "Ş").replace("sh", "ş")
            suffix = suffix.replace("CH", "Ç").replace("Ch", "Ç").replace("ch", "ç")
            return stem + suffix
        return word

    # O'zbekcha so'zlarda Sh -> Ş, Ch -> Ç
    # Katta/kichik registrni to'g'ri saqlaymiz:
    # SH -> Ş, Sh -> Ş, sh -> ş | CH -> Ç, Ch -> Ç, ch -> ç
    word = word.replace("SH", "Ş").replace("Sh", "Ş").replace("sh", "ş")
    word = word.replace("CH", "Ç").replace("Ch", "Ç").replace("ch", "ç")
    return word


def to_new_uzbek(text: str) -> str:
    """Matnni (HTML teglar, havolalar, #TIKER va inglizcha brendlarni buzmasdan)
    100% Yangi O'zbek Alifbosiga (Ö ö, Ğ ğ, Ş ş, Ç ç) o'giradi.
    """
    if not text:
        return text

    parts = _PROTECTED_RE.split(text)
    out = []
    for idx, seg in enumerate(parts):
        # Juft indeks = oddiy matn, toq indeks = himoyalangan token (HTML, URL, #TIKER, @user)
        if idx % 2 == 1:
            out.append(seg)
            continue

        # Imloviy xatolarni tozalash
        for pat, repl in _TYPO_FIXES:
            seg = re.sub(pat, repl, seg, flags=re.IGNORECASE)

        # Har bir so'zni alohida xavfsiz o'girish
        converted = re.sub(
            r"[A-Za-zÖöĞğŞşÇç]+(?:['`‘’ʼ-][A-Za-zÖöĞğŞşÇç]+)*['`‘’ʼ]?",
            lambda m: _convert_word(m.group(0)),
            seg,
        )
        out.append(converted)

    return "".join(out)


def to_classic_uzbek_for_tts(text: str) -> str:
    """Microsoft Edge TTS (uz-UZ-SardorNeural) talaffuzi 100% tabiiy chiqishi uchun
    Yangi Alifboni (Ö, Ğ, Ş, Ç) faqat ovoz sintezi paytida klassik o‘/g‘/sh/ch ga o'giradi.
    """
    if not text:
        return text
    return (
        text.replace("Ö", "O‘")
        .replace("ö", "o‘")
        .replace("Ğ", "G‘")
        .replace("ğ", "g‘")
        .replace("Ş", "Sh")
        .replace("ş", "sh")
        .replace("Ç", "Ch")
        .replace("ç", "ch")
    )
