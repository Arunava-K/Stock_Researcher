"""
Screener.in scraper for fundamentals.

Returns two key metrics per ticker:
  - debt_to_equity:   computed from balance sheet as Borrowings / (Equity + Reserves)
  - sales_growth_ttm: parsed from the front-page "Compounded Sales Growth → TTM" cell

Tries the consolidated page first, falls back to standalone if the
consolidated URL 404s (some smaller companies don't have consolidated
financials). Returns None when scrape fails — callers must handle that.

Scraping is fragile by nature: if Screener changes their HTML, the parsers
here will need updating. Failure modes are explicit (None) rather than silent.
"""

from __future__ import annotations

import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

CONSOLIDATED_URL = "https://www.screener.in/company/{symbol}/consolidated/"
STANDALONE_URL = "https://www.screener.in/company/{symbol}/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.5",
}

# Be polite — Screener doesn't rate-limit aggressively but burst scraping is rude.
_INTER_REQUEST_SLEEP_SEC = 0.5


def _fetch(symbol: str) -> Optional[str]:
    """Try consolidated first, then standalone. Return HTML or None."""
    for url_template in (CONSOLIDATED_URL, STANDALONE_URL):
        url = url_template.format(symbol=symbol)
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=20)
        except requests.RequestException:
            continue
        if resp.status_code == 200 and len(resp.content) > 5000:
            return resp.text
    return None


def _parse_sales_growth_ttm(html: str) -> Optional[float]:
    """
    The front-page "Compounded Sales Growth" widget has rows for 10Y / 5Y / 3Y / TTM.
    We want the TTM number. Parsed as a regex against the raw HTML — Screener's
    structure here is a flat label/value table.
    """
    m = re.search(
        r'Compounded Sales Growth[\s\S]*?TTM[^0-9\-]*?(-?\d+(?:\.\d+)?)\s*%',
        html,
    )
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _last_numeric_cell(cells) -> Optional[float]:
    """Return the value of the last <td> in the row that parses as a number."""
    for c in reversed(cells):
        txt = c.get_text(strip=True).replace(",", "").replace("\xa0", "")
        # Strip any trailing operator buttons like "+"
        txt = re.sub(r"[^\d.\-]", "", txt)
        if not txt:
            continue
        try:
            return float(txt)
        except ValueError:
            continue
    return None


def _compute_debt_to_equity(html: str) -> Optional[float]:
    """Find the balance-sheet section and compute Borrowings / (Equity + Reserves)."""
    soup = BeautifulSoup(html, "lxml")
    bs_section = soup.find("section", id="balance-sheet")
    if bs_section is None:
        return None

    table = bs_section.find("table")
    if table is None:
        return None

    def find_row_values(*labels: str):
        targets = {l.lower() for l in labels}
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            first = cells[0].get_text(strip=True)
            # Strip trailing "+" button text if present
            first = first.split("+")[0].strip().rstrip(":")
            if first.lower() in targets:
                return cells[1:]  # skip label cell
        return None

    eq_cells = find_row_values("Equity Capital")
    res_cells = find_row_values("Reserves")
    # Screener uses "Borrowings" for most companies; some (notably finance NBFCs)
    # render the row as "Borrowing" (singular). Accept both.
    borr_cells = find_row_values("Borrowings", "Borrowing")

    if not all([eq_cells, res_cells, borr_cells]):
        return None

    eq_val = _last_numeric_cell(eq_cells)
    res_val = _last_numeric_cell(res_cells)
    borr_val = _last_numeric_cell(borr_cells)

    if None in (eq_val, res_val, borr_val):
        return None

    total_equity = eq_val + res_val
    if total_equity <= 0:
        return None
    return borr_val / total_equity


def fetch_one(symbol: str) -> Optional[dict]:
    """Fetch fundamentals for a single ticker.

    Returns None ONLY when the page can't be fetched at all. If the page exists
    but has empty/missing data (recent IPOs without history, sectors where
    Screener doesn't compute certain ratios), returns a dict with None fields —
    callers should treat None fields as "unknown", not "fail".
    """
    html = _fetch(symbol)
    if html is None:
        return None

    return {
        "symbol": symbol,
        "debt_to_equity": _compute_debt_to_equity(html),
        "sales_growth_ttm_pct": _parse_sales_growth_ttm(html),
    }


def fetch_many(symbols: list[str], on_progress=None) -> dict[str, dict | None]:
    """Fetch fundamentals for many tickers. Polite sleep between requests.

    on_progress is an optional callback (i, total, symbol, result) for logging.
    """
    out: dict[str, dict | None] = {}
    for i, sym in enumerate(symbols, 1):
        if i > 1:
            time.sleep(_INTER_REQUEST_SLEEP_SEC)
        result = fetch_one(sym)
        out[sym] = result
        if on_progress:
            on_progress(i, len(symbols), sym, result)
    return out


if __name__ == "__main__":
    # Quick smoke test
    import sys
    syms = sys.argv[1:] or ["HFCL", "ATUL", "AJANTPHARM"]
    for sym in syms:
        r = fetch_one(sym)
        print(f"{sym}: {r}")
