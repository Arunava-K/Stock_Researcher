"""
Generate the daily research universe.

Pulls NIFTY Midcap 150 + Smallcap 250 from NSE archives, applies a liquidity
gate from the latest bhavcopy, excludes the big-10 IT services, and picks
TARGET_SIZE names with a bias toward less-covered (lower-turnover) names
within the liquid pool. Saves to universe.json.

Run this manually when you want to refresh. run.py reads the saved file.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pandas as pd
import requests

from bhavcopy import fetch_latest_bhavcopy

INDEX_URLS = [
    "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
]

# Big-10 mainstream Indian IT services. Excluded per user thesis (AI eroding
# the contract-services revenue model). Mid-tier IT services and IT product /
# SaaS / platforms are NOT excluded — those stay in the universe.
EXCLUDE_IT_SERVICES_BIG10 = {
    "TCS", "INFY", "WIPRO", "HCLTECH", "LTIM",
    "TECHM", "MPHASIS", "COFORGE", "PERSISTENT", "LTTS",
}

MIN_TURNOVER_LACS = 200  # ₹2 cr daily turnover floor
TARGET_SIZE = 30
RANDOM_SEED = 42  # fixed so universe is stable across runs

# "Less-covered" bias: take only the bottom QUANTILE_BIAS by turnover within
# the liquid pool, then random-sample within that. 1.0 = no bias (full pool).
QUANTILE_BIAS = 0.60

OUTPUT = Path(__file__).parent / "universe.json"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*;q=0.8",
}


def fetch_index(url: str) -> pd.DataFrame:
    resp = requests.get(url, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    df = pd.read_csv(io.BytesIO(resp.content))
    df.columns = [c.strip() for c in df.columns]
    return df


def main() -> int:
    print("Fetching NIFTY Midcap 150 + Smallcap 250 ...")
    frames = [fetch_index(u) for u in INDEX_URLS]
    indices = pd.concat(frames, ignore_index=True)
    indices = indices.drop_duplicates(subset=["Symbol"])
    print(f"  combined: {len(indices)} unique tickers")

    before = len(indices)
    indices = indices[~indices["Symbol"].isin(EXCLUDE_IT_SERVICES_BIG10)]
    print(f"  after big-10 IT exclusion: {len(indices)} (-{before - len(indices)})")

    print("Fetching bhavcopy for liquidity gate ...")
    bhav, bhav_date = fetch_latest_bhavcopy()
    print(f"  bhavcopy date: {bhav_date}")

    bhav_eq = bhav[bhav["SERIES"] == "EQ"][["SYMBOL", "TURNOVER_LACS", "CLOSE_PRICE"]].copy()
    bhav_eq.columns = ["Symbol", "Turnover_Lacs", "Close"]
    bhav_eq["Turnover_Lacs"] = pd.to_numeric(bhav_eq["Turnover_Lacs"], errors="coerce")
    bhav_eq["Close"] = pd.to_numeric(bhav_eq["Close"], errors="coerce")

    merged = indices.merge(bhav_eq, on="Symbol", how="inner")
    missing = len(indices) - len(merged)
    if missing:
        print(f"  {missing} indices tickers missing from bhavcopy (probably suspended / new listings)")

    liquid = merged[merged["Turnover_Lacs"] >= MIN_TURNOVER_LACS].copy()
    print(f"  liquid pool (turnover ≥ ₹{MIN_TURNOVER_LACS} lacs): {len(liquid)}")

    if len(liquid) < TARGET_SIZE:
        print(f"FATAL: liquid pool ({len(liquid)}) smaller than target ({TARGET_SIZE})", file=sys.stderr)
        return 1

    cutoff = liquid["Turnover_Lacs"].quantile(QUANTILE_BIAS)
    less_covered = liquid[liquid["Turnover_Lacs"] <= cutoff]
    print(f"  bottom-{int(QUANTILE_BIAS * 100)}% turnover pool (cutoff ₹{cutoff:,.0f} lacs): {len(less_covered)}")

    pool = less_covered if len(less_covered) >= TARGET_SIZE else liquid
    if pool is liquid:
        print("  bias pool too small — falling back to full liquid pool")

    picked = pool.sample(n=TARGET_SIZE, random_state=RANDOM_SEED).sort_values("Symbol")

    universe = [
        {
            "ticker": f"{row['Symbol']}.NS",
            "symbol": row["Symbol"],
            "name": row["Company Name"],
            "industry": row["Industry"],
            "turnover_lacs_at_pick": float(row["Turnover_Lacs"]),
            "close_at_pick": float(row["Close"]),
        }
        for _, row in picked.iterrows()
    ]

    payload = {
        "generated_on": bhav_date.isoformat(),
        "criteria": {
            "indices": ["NIFTY Midcap 150", "NIFTY Smallcap 250"],
            "exclude_it_big10": sorted(EXCLUDE_IT_SERVICES_BIG10),
            "min_turnover_lacs": MIN_TURNOVER_LACS,
            "target_size": TARGET_SIZE,
            "selection_bias": f"bottom {int(QUANTILE_BIAS * 100)}% by turnover within liquid pool",
            "random_seed": RANDOM_SEED,
        },
        "universe": universe,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwrote {OUTPUT} ({len(universe)} tickers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
