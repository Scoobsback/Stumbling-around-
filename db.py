"""
SQLite storage layer for the stumble app's content pool.

Two tables:
  sources  -- the RSS feeds / sites we pull from
  items    -- individual stumble-able links, deduped by url_hash

Deliberately simple (no ORM) so it's easy to swap for Postgres later --
just replace the connect() call and the ? placeholders with %s.
"""

import sqlite3
import hashlib
from contextlib import contextmanager

DB_PATH = "stumble.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    site_url    TEXT NOT NULL,
    feed_url    TEXT NOT NULL UNIQUE,
    category    TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     INTEGER NOT NULL REFERENCES sources(id),
    url           TEXT NOT NULL,
    url_hash      TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    excerpt       TEXT,
    image_url     TEXT,
    tags          TEXT NOT NULL,        -- comma-separated, e.g. "design,craft"
    published_at  TEXT,
    ingested_at   TEXT NOT NULL DEFAULT (datetime('now')),
    quality_score INTEGER NOT NULL DEFAULT 0,  -- bumped by manual curation later
    is_dead       INTEGER NOT NULL DEFAULT 0   -- flip on when link-checker finds a 404
);

CREATE INDEX IF NOT EXISTS idx_items_tags ON items(tags);
CREATE INDEX IF NOT EXISTS idx_items_dead ON items(is_dead);

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL UNIQUE,   -- no login needed for v1, just a device fingerprint
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tag_scores (
    user_id     INTEGER NOT NULL REFERENCES users(id),
    tag         TEXT NOT NULL,
    score       INTEGER NOT NULL DEFAULT 0,  -- +1 per thumbs up, -1 per thumbs down on that tag
    PRIMARY KEY (user_id, tag)
);

CREATE TABLE IF NOT EXISTS seen_items (
    user_id     INTEGER NOT NULL REFERENCES users(id),
    item_id     INTEGER NOT NULL REFERENCES items(id),
    reaction    TEXT,                         -- 'up', 'down', or NULL if just shown/skipped
    seen_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, item_id)
);
"""


def url_hash(url: str) -> str:
    """Stable dedupe key -- strips nothing fancy, just normalizes trailing slash."""
    normalized = url.strip().rstrip("/")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@contextmanager
def get_conn(path: str = DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path: str = DB_PATH):
    with get_conn(path) as conn:
        conn.executescript(SCHEMA)


def upsert_source(conn, name: str, site_url: str, feed_url: str, category: str) -> int:
    cur = conn.execute(
        """INSERT INTO sources (name, site_url, feed_url, category)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(feed_url) DO UPDATE SET name=excluded.name, category=excluded.category
           RETURNING id""",
        (name, site_url, feed_url, category),
    )
    return cur.fetchone()["id"]


def insert_item(conn, source_id: int, url: str, title: str, excerpt: str,
                 image_url: str, tags: list[str], published_at: str | None) -> bool:
    """Returns True if inserted, False if it was a duplicate (already seen)."""
    h = url_hash(url)
    try:
        conn.execute(
            """INSERT INTO items
               (source_id, url, url_hash, title, excerpt, image_url, tags, published_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (source_id, url, h, title, excerpt, image_url, ",".join(tags), published_at),
        )
        return True
    except sqlite3.IntegrityError:
        return False  # duplicate url_hash -- already in the pool


def get_or_create_user(conn, device_id: str) -> int:
    cur = conn.execute(
        """INSERT INTO users (device_id) VALUES (?)
           ON CONFLICT(device_id) DO UPDATE SET device_id=excluded.device_id
           RETURNING id""",
        (device_id,),
    )
    return cur.fetchone()["id"]


def record_reaction(conn, user_id: int, item_id: int, tags: list[str], reaction: str):
    """reaction is 'up' or 'down'. Bumps the score for every tag on this item."""
    conn.execute(
        """INSERT INTO seen_items (user_id, item_id, reaction) VALUES (?, ?, ?)
           ON CONFLICT(user_id, item_id) DO UPDATE SET reaction=excluded.reaction""",
        (user_id, item_id, reaction),
    )
    delta = 1 if reaction == "up" else -1
    for tag in tags:
        conn.execute(
            """INSERT INTO tag_scores (user_id, tag, score) VALUES (?, ?, ?)
               ON CONFLICT(user_id, tag) DO UPDATE SET score = score + ?""",
            (user_id, tag, delta, delta),
        )


def get_tag_scores(conn, user_id: int) -> dict:
    rows = conn.execute(
        "SELECT tag, score FROM tag_scores WHERE user_id = ?", (user_id,)
    ).fetchall()
    return {row["tag"]: row["score"] for row in rows}
