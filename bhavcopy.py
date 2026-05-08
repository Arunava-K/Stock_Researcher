"""
NSE end-of-day bhavcopy fetcher.

The bhavcopy is the authoritative EOD OHLCV file NSE publishes daily ~6:30pm IST.
URL pattern (as of late 2025):
    https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv

CSV columns (note leading spaces, normalised below):
    SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE,
    LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS,
    NO_OF_TRADES, DELIV_QTY, DELIV_PER

When NSE rotates this URL pattern (happens ~every 12–18 months), update
BHAVCOPY_URL — that's the single point of change.
"""

from __future__ import annotations

import io
from datetime import date, timedelta

import pandas as pd
import requests

BHAVCOPY_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _try_fetch(d: date) -> pd.DataFrame | None:
    url = BHAVCOPY_URL.format(ddmmyyyy=d.strftime("%d%m%Y"))
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
    except requests.RequestException:
        return None
    if resp.status_code != 200 or len(resp.content) < 10_000:
        return None
    df = pd.read_csv(io.BytesIO(resp.content))
    df.columns = [c.strip() for c in df.columns]
    if "SYMBOL" not in df.columns or "CLOSE_PRICE" not in df.columns:
        return None
    for col in ("SYMBOL", "SERIES"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    return df


def fetch_latest_bhavcopy(today: date | None = None,
                          max_walkback_days: int = 7) -> tuple[pd.DataFrame, date]:
    """
    Return (df, date) for the most recent trading day on/before `today`
    with a published bhavcopy.

    Skips weekends. Walks back up to `max_walkback_days` days, which covers
    long weekends + a 1-2 day holiday cluster.

    Raises RuntimeError if nothing found in the window.
    """
    today = today or date.today()
    last_error_dates: list[str] = []
    for offset in range(max_walkback_days):
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:  # Sat/Sun
            continue
        df = _try_fetch(d)
        if df is not None:
            return df, d
        last_error_dates.append(d.isoformat())
    raise RuntimeError(
        f"No NSE bhavcopy found in last {max_walkback_days} days "
        f"(tried weekdays: {', '.join(last_error_dates)})"
    )


def lookup_eq(bhav_df: pd.DataFrame, symbol: str) -> dict | None:
    """Look up an equity-series row for a given NSE symbol (e.g. 'HFCL')."""
    match = bhav_df[(bhav_df["SYMBOL"] == symbol) & (bhav_df["SERIES"] == "EQ")]
    if match.empty:
        return None
    row = match.iloc[0]
    return {
        "open": float(row["OPEN_PRICE"]),
        "high": float(row["HIGH_PRICE"]),
        "low": float(row["LOW_PRICE"]),
        "close": float(row["CLOSE_PRICE"]),
        "volume": int(row["TTL_TRD_QNTY"]),
        "prev_close": float(row["PREV_CLOSE"]),
    }
