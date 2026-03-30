"""Interaction sync — bridge browser localStorage to backend profile.

The HTML frontend tracks clicks/favs in localStorage.
This module:
  1. Reads exported interaction data (from canvas eval or file)
  2. Updates profile.json with short-term preference signals
  3. Feeds new keywords back into query builder

Called automatically during each fetch cycle.
"""

from __future__ import annotations
import json
import os
import time
from pathlib import Path
from collections import Counter

INTERACTION_FILE = Path("~/.omnifeed/interactions.json").expanduser()
PROFILE_PATH = Path("~/.omnifeed/profile.json").expanduser()


def sync_interactions_from_file(filepath: str = None):
    """Read exported interactions and update profile."""
    path = Path(filepath) if filepath else INTERACTION_FILE
    if not path.exists():
        return

    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return

    if not data.get("total"):
        return

    _update_profile_from_interactions(data)


def sync_interactions_from_data(data: dict):
    """Direct sync from in-memory interaction data."""
    if not data or not data.get("total"):
        return

    # Save to file for persistence
    INTERACTION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(INTERACTION_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    _update_profile_from_interactions(data)


def _update_profile_from_interactions(ix: dict):
    """Merge interaction signals into profile.json."""
    if not PROFILE_PATH.exists():
        return

    with open(PROFILE_PATH) as f:
        profile = json.load(f)

    # Extract preference signals
    plat_pref = ix.get("platform_preference", {})
    cat_pref = ix.get("category_preference", {})
    tag_aff = ix.get("tag_affinity", {})

    # Update profile topics with interaction signals
    topics = profile.get("topics", {})
    for tag, count in tag_aff.items():
        tag_lower = tag.lower()
        current = topics.get(tag_lower, 0)
        # Interaction boost: small but cumulative
        boost = min(2.0, count * 0.3)
        topics[tag_lower] = min(10, current + boost)

    profile["topics"] = topics
    profile["platforms_affinity"] = plat_pref
    profile["category_affinity"] = cat_pref
    profile["interaction_updated"] = int(time.time())
    profile["interaction_total"] = ix.get("total", 0)

    # Regenerate keywords from updated topics
    sorted_t = sorted(topics.items(), key=lambda x: x[1], reverse=True)
    profile["keywords_precise"] = [t for t, w in sorted_t if w >= 5][:20]
    profile["keywords_broad"] = [t for t, w in sorted_t if 2 <= w < 5][:20]

    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def get_interaction_keywords() -> list[str]:
    """Get additional search keywords from interaction history."""
    if not INTERACTION_FILE.exists():
        return []

    try:
        with open(INTERACTION_FILE) as f:
            data = json.load(f)
        tag_aff = data.get("tag_affinity", {})
        # Top interacted tags → new search keywords
        sorted_tags = sorted(tag_aff.items(), key=lambda x: x[1], reverse=True)
        return [t for t, c in sorted_tags[:10] if c >= 2]
    except Exception:
        return []
