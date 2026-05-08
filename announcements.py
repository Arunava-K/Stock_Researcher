"""
NSE corporate announcements fetcher.

Pulls the last N days of company-level disclosures from NSE's public API.
Used by the daily routine to surface recent material events on held positions
and flagged candidates.

The endpoint is a JSON API that returns a list of announcement records.
Reasonably stable historically, but if NSE rotates the URL we'll see fetch
failures in the brief — they degrade gracefully (announcement section is
suppressed for that stock with a warning).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import requests

API_URL = "https://www.nseindia.com/api/corporate-announcements"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}


def fetch_announcements(symbol: str, days: int = 30,
                        as_of: date | None = None) -> Optional[list[dict]]:
    """Return announcements for the last `days` days. Sorted most-recent first.

    Returns None on fetch / parse failure.
    """
    today = as_of or date.today()
    from_d = (today - timedelta(days=days)).strftime("%d-%m-%Y")
    to_d = today.strftime("%d-%m-%Y")

    params = {
        "index": "equities",
        "from_date": from_d,
        "to_date": to_d,
        "symbol": symbol,
    }

    try:
        resp = requests.get(API_URL, headers=_HEADERS, params=params, timeout=20)
    except requests.RequestException:
        return None

    if resp.status_code != 200:
        return None

    try:
        data = resp.json()
    except (ValueError, KeyError):
        return None

    if not isinstance(data, list):
        return None

    out = []
    for item in data:
        out.append({
            "date":      item.get("an_dt", ""),       # "04-May-2026 17:37:17"
            "sort_date": item.get("sort_date", ""),   # "2026-05-04 17:37:17"
            "category":  item.get("desc", ""),
            "summary":   item.get("attchmntText", ""),
            "file_url":  item.get("attchmntFile"),
        })

    out.sort(key=lambda x: x.get("sort_date") or "", reverse=True)
    return out


# --- Categorisation for the brief ---------------------------------------------
#
# NSE's `desc` field is a long human label like "Analysts/Institutional Investor
# Meet/Con. Call Updates". We bucket these into a small set of swing-trade-relevant
# categories to surface what matters most.

# Order matters — first match wins. Specific patterns before generic ones.
_CATEGORY_MAP: list[tuple[str, str]] = [
    # High-signal — likely market-moving
    ("concall",     "analysts/institutional investor meet"),
    ("concall",     "investor presentation"),
    ("concall",     "con. call"),
    ("concall",     "earnings call"),
    ("results",     "financial results"),
    ("results",     "quarterly results"),
    ("orders",      "bagging/receiving of orders"),
    ("orders",      "award of order"),
    ("orders",      "order receipt"),
    ("orders",      "contract"),
    ("m&a",         "acquisition"),
    ("m&a",         "scheme of arrangement"),
    ("m&a",         "amalgamation"),
    ("m&a",         "merger"),
    ("m&a",         "demerger"),
    ("capex",       "capacity expansion"),
    ("capex",       "capex"),
    ("capex",       "commissioning"),
    ("capex",       "plant"),
    ("rating",      "credit rating"),
    ("rating",      "rating"),
    # Medium-signal
    ("insider",     "sast"),
    ("insider",     "insider trading"),
    ("insider",     "disclosure under reg"),
    ("corp_action", "dividend"),
    ("corp_action", "bonus"),
    ("corp_action", "buyback"),
    ("corp_action", "stock split"),
    # Noise / procedural — usually skippable
    ("rumour",      "rumour"),
    ("rumour",      "clarification"),
    ("regulatory",  "sebi"),
    ("regulatory",  "compliance"),
    ("regulatory",  "newspaper publication"),
]


# Visual tagging for the brief — one short label per category, ordered by
# rough swing-trade importance.
CATEGORY_LABEL = {
    "concall":     "📞 concall",
    "results":     "📊 results",
    "orders":      "📦 orders",
    "m&a":         "🤝 M&A",
    "capex":       "🏗️ capex",
    "rating":      "🏷️ rating",
    "insider":     "🕵️ insider",
    "corp_action": "💰 corp action",
    "rumour":      "🗣️ rumour",
    "regulatory":  "📜 regulatory",
    "other":       "·",
}


def categorize(announcement: dict) -> str:
    desc = (announcement.get("category") or "").lower()
    for tag, needle in _CATEGORY_MAP:
        if needle in desc:
            return tag
    return "other"


if __name__ == "__main__":
    import sys, json
    syms = sys.argv[1:] or ["HFCL", "SUZLON"]
    for sym in syms:
        print(f"== {sym} ==")
        anns = fetch_announcements(sym, days=30)
        if anns is None:
            print("  fetch failed")
            continue
        print(f"  {len(anns)} announcements in last 30 days")
        for a in anns[:5]:
            cat = categorize(a)
            print(f"  [{cat}] {a['date']:<22} {a['category'][:60]}")
        print()
