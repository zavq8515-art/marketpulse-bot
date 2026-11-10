"""SQLite: ko'rilgan yangiliklar va chiqarilgan postlar tarixi (takrorlanishga qarshi)."""
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

from config import DB_PATH


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS seen (
                id TEXT PRIMARY KEY,
                title TEXT,
                url TEXT,
                source TEXT,
                seen_at TEXT
            );
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id TEXT,
                topic TEXT,
                summary TEXT,
                url TEXT,
                posted_at TEXT
            );
            CREATE TABLE IF NOT EXISTS price_alerts (
                symbol TEXT,
                day TEXT,
                level INTEGER,
                PRIMARY KEY (symbol, day, level)
            );
            """
        )


def now_utc():
    return datetime.now(timezone.utc)


def news_id(title, url):
    key = (url or "").split("?")[0].strip().lower() or (title or "").strip().lower()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def title_id(title):
    norm = "".join(ch for ch in (title or "").lower() if ch.isalnum())
    return "t:" + hashlib.sha1(norm.encode("utf-8")).hexdigest()


def is_seen(item_id):
    with _conn() as c:
        return c.execute("SELECT 1 FROM seen WHERE id=?", (item_id,)).fetchone() is not None


def mark_seen(item):
    with _conn() as c:
        for key in (item["id"], title_id(item["title"])):
            c.execute(
                "INSERT OR IGNORE INTO seen (id, title, url, source, seen_at) VALUES (?,?,?,?,?)",
                (key, item["title"], item["url"], item["source"], now_utc().isoformat()),
            )


def add_post(news_id_, topic, summary, url):
    with _conn() as c:
        c.execute(
            "INSERT INTO posts (news_id, topic, summary, url, posted_at) VALUES (?,?,?,?,?)",
            (news_id_, topic, summary, url, now_utc().isoformat()),
        )


def recent_posts(hours=48):
    since = (now_utc() - timedelta(hours=hours)).isoformat()
    with _conn() as c:
        rows = c.execute(
            "SELECT topic, summary, posted_at FROM posts WHERE posted_at>=? ORDER BY posted_at DESC",
            (since,),
        ).fetchall()
    return [dict(r) for r in rows]


def posts_today_count(tz):
    start_local = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    since = start_local.astimezone(timezone.utc).isoformat()
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM posts WHERE posted_at>=?", (since,)).fetchone()[0]


def last_post_time():
    with _conn() as c:
        row = c.execute("SELECT posted_at FROM posts ORDER BY posted_at DESC LIMIT 1").fetchone()
    return datetime.fromisoformat(row[0]) if row else None


def recent_titles(hours=3, limit=40):
    since = (now_utc() - timedelta(hours=hours)).isoformat()
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT title FROM seen WHERE seen_at>=? ORDER BY seen_at DESC LIMIT ?",
            (since, limit),
        ).fetchall()
    return [r[0] for r in rows]


def price_alert_done(symbol, day, level):
    with _conn() as c:
        return c.execute(
            "SELECT 1 FROM price_alerts WHERE symbol=? AND day=? AND level=?", (symbol, day, level)
        ).fetchone() is not None


def mark_price_alert(symbol, day, level):
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO price_alerts VALUES (?,?,?)", (symbol, day, level))
