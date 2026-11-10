"""RSS manbalardan yangi xabarlarni yig'ish va maqola matni / suratini olish."""
import html
import logging
import re
from calendar import timegm
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import feedparser
import requests

import db
from config import MAX_NEWS_AGE_HOURS, USER_AGENT
from sources import SOURCES

log = logging.getLogger("fetcher")
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}


def _clean(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _published(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(timegm(t), tz=timezone.utc)
    return None


def _entry_image(e):
    for m in e.get("media_content") or []:
        if m.get("url"):
            return m["url"]
    for m in e.get("media_thumbnail") or []:
        if m.get("url"):
            return m["url"]
    for link in e.get("links") or []:
        if (link.get("type") or "").startswith("image/") and link.get("href"):
            return link["href"]
    return None


def fetch_new_items():
    """Barcha manbalardan hali ko'rilmagan va yangi xabarlarni qaytaradi."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_NEWS_AGE_HOURS)
    items, local_ids = [], set()
    for src in SOURCES:
        try:
            resp = requests.get(src["url"], headers=HEADERS, timeout=20)
            feed = feedparser.parse(resp.content)
        except Exception as e:  # noqa: BLE001
            log.warning("Manba o'qilmadi: %s (%s)", src["name"], e)
            continue
        for e in feed.entries[:30]:
            title = _clean(e.get("title"))
            url = e.get("link", "")
            if not title or not url:
                continue
            pub = _published(e)
            if not pub or pub < cutoff:  # sanasiz yoki eski xabarlar o'tkazib yuboriladi
                continue
            item_id = db.news_id(title, url)
            tid = db.title_id(title)
            if item_id in local_ids or tid in local_ids or db.is_seen(item_id) or db.is_seen(tid):
                continue
            local_ids.update((item_id, tid))
            items.append(
                {
                    "id": item_id,
                    "title": title,
                    "url": url,
                    "summary": _clean(e.get("summary"))[:500],
                    "source": src["name"],
                    "official": src.get("official", False),
                    "published": pub.isoformat() if pub else None,
                    "rss_image": _entry_image(e),
                }
            )
    log.info("Yangi xabarlar: %d ta", len(items))
    return items


def _resolve_google_news(url):
    """Google News havolasini asl maqola havolasiga aylantirishga urinadi."""
    if "news.google.com" not in url:
        return url
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if "news.google.com" not in r.url:
            return r.url
    except Exception:  # noqa: BLE001
        pass
    return url


def fetch_article(item):
    """Maqola matni va og:image ni oladi. Bo'lmasa RSS qisqacha matnidan foydalanadi."""
    url = _resolve_google_news(item["url"])
    text, image = "", None
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        page = r.text
        m = re.search(
            r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)',
            page,
            re.I,
        ) or re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)',
            page,
            re.I,
        )
        if m:
            image = html.unescape(m.group(1))
        try:
            import trafilatura

            text = trafilatura.extract(page, include_comments=False, include_tables=True) or ""
        except Exception:  # noqa: BLE001
            text = ""
    except Exception as e:  # noqa: BLE001
        log.info("Maqola ochilmadi (%s): %s", item["source"], e)
    if len(text) < 200:
        text = f"{item['title']}. {item['summary']}"
    if not image or "lh3.googleusercontent.com" in image or "gstatic.com" in image:
        image = item.get("rss_image")
    return {"url": url, "text": text[:6000], "image": image, "domain": urlparse(url).netloc}
