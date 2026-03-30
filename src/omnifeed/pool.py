"""Content pool — maintains a pre-fetched candidate pool for instant refresh.

Architecture:
  pool.json (~600 items, 24h TTL)
    ↓
  Each "refresh" = re-rank pool + surface 50 unseen items → <0.3s
    ↓
  Background refill every 2h keeps pool fresh

Pool lifecycle:
  1. `omnifeed pool refill` — fetch all channels, merge into pool (dedup)
  2. `omnifeed fetch` — draws from pool if available, else fetches live
  3. Frontend "refresh" button — calls pool.draw() via pre-rendered pages
"""

from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Optional
from dataclasses import asdict

from .models import FeedItem, Engagement


POOL_DIR = Path("~/.omnifeed/pool").expanduser()
POOL_FILE = POOL_DIR / "pool.json"
SEEN_FILE = POOL_DIR / "seen.json"
MAX_POOL_SIZE = 3000
ITEM_TTL_HOURS = 72
MAX_PAGES = 5  # pre-render up to 5 refresh pages


def _now_ms() -> int:
    return int(time.time() * 1000)


def _load_pool() -> list[dict]:
    if not POOL_FILE.exists():
        return []
    try:
        with open(POOL_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save_pool(items: list[dict]):
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    with open(POOL_FILE, "w") as f:
        json.dump(items, f, ensure_ascii=False)


def _load_seen() -> set[str]:
    if not SEEN_FILE.exists():
        return set()
    try:
        with open(SEEN_FILE) as f:
            data = json.load(f)
            # Expire old seen entries (keep last 48h)
            cutoff = _now_ms() - 48 * 3600 * 1000
            return {k for k, ts in data.items() if ts > cutoff}
    except Exception:
        return set()


def _save_seen(seen: dict[str, int]):
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    # Only keep last 48h
    cutoff = _now_ms() - 48 * 3600 * 1000
    cleaned = {k: v for k, v in seen.items() if v > cutoff}
    with open(SEEN_FILE, "w") as f:
        json.dump(cleaned, f)


def pool_stats() -> dict:
    """Get pool statistics."""
    pool = _load_pool()
    seen = _load_seen()
    now = _now_ms()
    fresh = [p for p in pool if now - p.get("_pool_ts", 0) < ITEM_TTL_HOURS * 3600 * 1000]
    unseen = [p for p in fresh if p["id"] not in seen]

    return {
        "total": len(pool),
        "fresh": len(fresh),
        "stale": len(pool) - len(fresh),
        "seen": len(seen),
        "unseen": len(unseen),
        "refreshes_available": len(unseen) // 50,
        "pool_file": str(POOL_FILE),
    }


def pool_add(items: list[FeedItem]) -> int:
    """Add items to the pool. Returns number of new items added."""
    pool = _load_pool()
    existing_ids = {p["id"] for p in pool}
    now = _now_ms()

    added = 0
    for item in items:
        if item.id not in existing_ids:
            d = item.to_dict()
            d["_pool_ts"] = now  # When added to pool
            # Ensure source_type is always set
            if not d.get("source_type"):
                d["source_type"] = "unknown"
            pool.append(d)
            existing_ids.add(item.id)
            added += 1

    # Evict stale items first, then oldest if over limit
    cutoff = now - ITEM_TTL_HOURS * 3600 * 1000
    pool = [p for p in pool if now - p.get("_pool_ts", 0) < ITEM_TTL_HOURS * 3600 * 1000]
    if len(pool) > MAX_POOL_SIZE:
        pool.sort(key=lambda p: p.get("_pool_ts", 0), reverse=True)
        pool = pool[:MAX_POOL_SIZE]

    _save_pool(pool)
    return added


def pool_draw(count: int = 50, mark_seen: bool = True) -> list[FeedItem]:
    """Draw unseen items from pool. Fast (<10ms)."""
    pool = _load_pool()
    seen_set = _load_seen()
    seen_dict = {}
    if SEEN_FILE.exists():
        try:
            with open(SEEN_FILE) as f:
                seen_dict = json.load(f)
        except Exception:
            seen_dict = {}

    now = _now_ms()
    cutoff = now - ITEM_TTL_HOURS * 3600 * 1000

    # Filter: fresh + unseen
    candidates = [p for p in pool
                  if p["id"] not in seen_set
                  and now - p.get("_pool_ts", 0) < ITEM_TTL_HOURS * 3600 * 1000]

    # Take top N (pool is already ranked)
    drawn = candidates[:count]

    if mark_seen:
        for d in drawn:
            seen_dict[d["id"]] = now
        _save_seen(seen_dict)

    # Convert back to FeedItem
    items = []
    for d in drawn:
        eng = d.get("engagement", {})
        item = FeedItem(
            id=d["id"], platform=d["platform"],
            native_id=d.get("native_id", ""),
            title=d.get("title", ""), content=d.get("content", ""),
            author=d.get("author", ""), cover=d.get("cover", ""),
            url=d.get("url", ""), timestamp=d.get("timestamp", 0),
            engagement=Engagement(**eng) if isinstance(eng, dict) else Engagement(),
            category=d.get("category", ""),
            recommend_reason=d.get("recommend_reason", ""),
            tags=d.get("tags", []),
            source_type=d.get("source_type") or "unknown",
        )
        items.append(item)

    return items


def prerender_pages(all_ranked_items: list[FeedItem], output_dir: str, page_size: int = 50):
    """Pre-render multiple pages of content as JSON for instant frontend refresh.
    
    Produces: page_0.json, page_1.json, ..., page_N.json
    Frontend loads next page on "refresh" click — zero latency.
    """
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    pages = []
    for i in range(0, len(all_ranked_items), page_size):
        chunk = all_ranked_items[i:i + page_size]
        page_data = [item.to_dict() for item in chunk]
        pages.append(page_data)

    # Write page files
    for idx, page in enumerate(pages[:MAX_PAGES]):
        (out / f"page_{idx}.json").write_text(
            json.dumps(page, ensure_ascii=False), encoding="utf-8"
        )

    # Write manifest
    manifest = {
        "total_pages": min(len(pages), MAX_PAGES),
        "page_size": page_size,
        "total_items": len(all_ranked_items),
        "generated_at": int(time.time()),
    }
    (out / "pages_manifest.json").write_text(json.dumps(manifest))

    return len(pages)
