---
name: stock-deep-dive
description: Run the same per-stock analysis pipeline (4 technical signals + fundamentals gates + setup classification + trade plan + recent announcements) on a single user-supplied NSE ticker, then enrich with WebSearch and render the same mentor-voice narrative as the daily brief. Output goes to chat only — no Notion writes, no Watchlist update. Invoke as `/stock-deep-dive <SYMBOL>` (e.g. `/stock-deep-dive RELIANCE`). Takes ~1–2 minutes.
---

# Ad-Hoc Stock Deep-Dive

You are running the per-stock analysis pipeline on a single stock that Arunava has discovered himself. Same numbers, same mentor voice, same FOMO-discipline framing as the daily `/stock-brief` — just for one stock he picked, with no Notion side-effects.

## Inputs

The user supplies one argument: an NSE symbol. Accept any of:
- bare symbol — `RELIANCE`, `HFCL`, `ITC`
- with `.NS` suffix — `RELIANCE.NS`
- lowercased — `reliance`

`run.py --ticker` normalizes all of these.

If the user gives a company name instead of a symbol (e.g. "Tata Motors"), tell them you need the NSE ticker symbol and ask for it. Don't guess — the wrong symbol wastes a pipeline run.

## User context (same as daily routine — keep this in mind for the narrative)

- Capital: ₹10,000 swing-trade pool, max 2 concurrent positions
- Risk: 2% of capital per trade (₹200), min R:R 2:1
- Held: HFCL @ ₹146.07, SUZLON @ ₹56.40
- Avoids: big-10 mainstream Indian IT services (TCS/INFY/etc) — AI thesis
- He's articulated FOMO discipline — frame already-moved stocks as "watch for pullback", never "buy now"

## Workflow

### Step 1 — Set up Python (skip if already done this session)

```bash
python -m venv .venv 2>/dev/null
.venv/bin/pip install --quiet -r requirements.txt
```

### Step 2 — Run the pipeline (~30–60s)

```bash
.venv/bin/python run.py --ticker <SYMBOL>
```

The pipeline will:
1. Resolve the ticker via yfinance (gives company name + industry)
2. Fetch the latest NSE bhavcopy for the authoritative close
3. Fetch 1y daily OHLCV from yfinance
4. Score the 4 signals + classify setup status
5. Fetch fundamentals from Screener.in
6. Fetch recent corporate announcements (always, in `--ticker` mode — no `WATCHING` skip)
7. Compute trade plan if status ∈ {READY, TRIGGERED}, watch conditions if FORMING

If exit code is non-zero (e.g. ticker not found on Yahoo, like a recently-restructured company), report the failure and stop. Do not invent data. Suggest the user double-check the symbol on NSE/screener.in.

### Step 3 — Read the JSON sidecar

```bash
ls -t briefs/deep-dive-<SYMBOL>-*.json | head -1
```

Read the file. There is exactly one row in `rows[0]`. Pull:
- Identity: `symbol`, `name`, `industry`, `ticker`
- Price: `last_close`, `as_of`, `source`
- Score + signals: `score`, `near_52w_high`, `dist_52w_high`, `macd_crossover_5d`, `dma_50_above_200`, `dma_ratio`, `volume_accum`, `volume_ratio`
- Fundamentals: `fundamentals.debt_to_equity`, `fundamentals.sales_growth_ttm_pct`, `passes_gates`, `gate_reason`
- Setup: `setup_status`, `trade_plan`, `watch_conditions`
- News: `announcements` (list of {date, category, summary, file_url})
- Run meta: top-level `freshness`, `bhavcopy_date`, `warnings`

### Step 4 — WebSearch enrichment (~1–2 queries)

Run 1–2 WebSearches in a single message (parallel). Examples:
- `<Company name> Q4 FY26 results <month> <year>`
- `<Company name> announcement <month> <year>`
- `<Industry> sector <quarter> India outlook` (only if first query returns thin context)

Skim results for: latest quarterly numbers (revenue, PAT, YoY growth), management commentary, segment breakdown, guidance, sector tailwinds/headwinds, recent strategic moves.

### Step 5 — Best-effort WebFetch on concall PDFs

Look at `announcements`. If any from the last 14 days has `category` containing "concall" / "results" / "outcome" / "investor presentation" with a `file_url`, attempt a single `WebFetch`. Many NSE PDFs time out or are scanned images — that's OK; fall back to WebSearch findings. Don't burn more than ~2 attempts.

### Step 6 — Render the brief in chat

Use the **same 6-section format** as the daily brief — Arunava is used to it and the consistency matters. Length budget: ~80–200 lines for one stock.

#### Header

```
# Deep-Dive: <SYMBOL> — <Company Name>

*<Industry>* · Score N/4 · `<TICKER>` · Last close ₹<price> (<as_of>, <source>)
**Setup status:** <emoji + word>  ·  **Bhavcopy date:** <bhavcopy_date>

> 📊 Ad-hoc deep-dive (not from daily scan). Same pipeline as `/stock-brief` — 4 technical signals + fundamentals gates + setup classification. No Notion write. Risk frame: 2% of ₹10,000 per trade, min R:R 2×.
```

If `warnings` is non-empty, surface each as a `> ⚠️ <warning>` line under the callout.

If the stock is in `HELD_POSITIONS` (HFCL or SUZLON), add `🔒 *currently held @ ₹<entry>*` next to the symbol and include a Held position note section at the end.

#### Section 1 — What's happening

1–2 sentences in plain English. The story the data tells. No jargon.

> Example: "Score 1/4 — only the proximity-to-52w-high signal fires. Stock is 9.9% below its 52-week high but momentum is flat: MACD hasn't crossed bullish recently, the 50DMA is below 200DMA, and volume is below average. Fundamentals are clean (D/E 0.44, sales growth +10%) so this is a healthy company without a setup."

#### Section 2 — Why it's on your radar

Bullets translating each signal to plain English. For terms a beginner might not know, give a one-line italic explanation on first use:

```
- ✓ Within 1.9% of 52-week high — *consolidation near highs often precedes breakouts; sellers got absorbed*
- · MACD has not crossed bullish in last 5 sessions — *MACD is a momentum indicator; bullish cross = upward momentum gaining*
- · 50DMA is -2.3% vs 200DMA — *50DMA below 200DMA means the medium-term trend is weaker than the long-term — typically a "downtrend" regime*
- ✓ Last volume 1.8× the prior 20-day avg — *volume spike with rising price = institutional accumulation, often*
- ✓ Fundamentals pass: D/E 0.06 (debt-free), sales growth TTM +17%
```

Use `✓` for signals that fired, `·` for signals that didn't. Show **all four** signals + the fundamentals gate line — don't cherry-pick.

#### Section 3 — What I dug up

WebSearch + WebFetch findings + the announcements list. Concrete operational facts with numbers and dates. Examples:

```
- Q4 FY26 (May 5): Revenue ₹1,421 cr (+21% YoY), PAT ₹267 cr (+18%)
- US generics +56% in Q4
- FY27 guidance: revenue 16-18%, EBITDA margin 27%
- Strategic catalyst: Biocon partnership for semaglutide in 26 countries
- Recent NSE filings (last 30d, top 5):
    - 2026-05-07 · Acquisition — Update on acquisition of 100% equity stake of Kandla GHA Transmission Ltd
    - 2026-05-03 · Results — Q4 FY26 financial results released
    - ...
```

If WebSearch + announcements yield nothing fresh: "No fresh news in last 14 days; relying on structured signals."

#### Section 4 — What to research yourself before deciding

3–5 specific homework items, beginner-friendly:

```
1. Listen to the May 5 earnings call. Why is segment X declining?
2. Compare to peers — Sun, Cipla. Was this beat distinct or sector-wide?
3. Check the chart on TradingView. Did the move already happen pre-results?
4. Look at FII/DII activity for the last 5 sessions on moneycontrol.
```

#### Section 5 — Watch conditions [FORMING] OR Trade plan [READY/TRIGGERED] OR Setup snapshot [WATCHING/STALE]

Read `setup_status` and pick:

**For READY/TRIGGERED** — print the trade plan from JSON `trade_plan`:

```
**Trade plan** (math, not advice — your call):
- **Entry zone:** ₹<entry_zone_low> – ₹<entry_zone_high>  (current ₹<current_price>)
- **Stop:** ₹<stop>  (<stop_method>)
- **Target 1:** ₹<target_1>  →  R:R <rr_to_target_1>
- **Target 2:** ₹<target_2>  →  R:R <rr_to_target_2>
- **Risk per share:** ₹<risk_per_share>  (ATR ₹<atr>, swing low ₹<swing_low>)
- **Position size:** N share(s)  (<binding_constraint reason>)
   - Capital deployed: ₹<deployed> (<%>% of swing capital)
   - Max loss if stop hits: **₹<max_loss>** (<%>% of capital)
   - Profit at T1: ₹<p_t1> (+<%>%)
   - Profit at T2: ₹<p_t2> (+<%>%)
```

If `trade_plan.rr_warning` is set, surface it. If `position.binding_constraint == "unfeasible"`, say so plainly: stock too expensive for the per-slot budget at this stop distance — explore at higher capital or skip.

**For FORMING** — print watch conditions from JSON `watch_conditions`:

```
**Watch conditions** (need ALL for setup to confirm):
- ⏱️ <condition 1>
- ⏱️ <condition 2>
→ If these clear in the next 3–5 days, the setup graduates to READY.
```

**For WATCHING / STALE** — there's no plan or watch list. Write a short "Setup snapshot" paragraph:

> "Score 1/4 — far from a tradeable setup right now. The technicals would need at least 2 more signals to fire (MACD bullish cross + 50DMA reclaim above 200DMA, most likely) before a trade plan would even be computed. This is a fine company to track but there's no actionable math here today."

#### Section 6 — Objective take

For WATCHING/STALE: 2–3 sentences. Honest assessment — "watch and learn", "fundamentally clean but no setup", or "structurally interesting but math doesn't work for ₹10k capital".

For FORMING: 2–3 sentences. Will the math work for ₹10k if it confirms? Is the company fundamentally clean? Should this be on the Watchlist?

For READY/TRIGGERED: more direct. Setup confirmed; what would invalidate the trade?

**If a stock has already run hard recently** (>10% in the last 5–10 sessions, distance from 52w-high < 3%), frame as **"watch for pullback"** not "buy now" — Arunava has explicit FOMO discipline.

**Never** give a buy/sell recommendation. Always: "math, not advice — your call."

#### Held position note [ONLY if held]

1–2 sentences. Reference his entry price (HFCL ₹146.07, SUZLON ₹56.40). Show current P&L %. Mention if state worth holding or deteriorating.

#### Footer

```
---
*Generated <YYYY-MM-DD HH:MM IST> · `run.py --ticker <SYMBOL>` · ad-hoc deep-dive*
```

### Step 7 — Final one-liner

Single short summary line, e.g.:

> Deep-dive on RELIANCE: score 1/4, WATCHING, fundamentals clean (D/E 0.44, sales +10%), 14 announcements pulled. No tradeable setup today.

## Failure handling

| Step fails | Action |
|---|---|
| Ticker resolution (Step 2 yfinance 404) | Halt. Tell user the symbol isn't on Yahoo — likely renamed/delisted/restructured. Suggest checking on screener.in. |
| Pipeline (Step 2 non-zero exit) | Halt, show last lines of stderr. Do not render a partial brief. |
| WebSearch (Step 4) | Continue. Section 3 says "No fresh news in last 14 days." |
| WebFetch concall PDF (Step 5) | Continue. Skip silently — many NSE PDFs are flaky. |
| Screener fundamentals miss | Pipeline already handles — gate gets `passes_gates=True` with `gate_reason="no Screener data — gates skipped"`. Surface that in Section 2. |

## Things you must not do

- Never write to Notion in this skill. No Daily Brief row, no Watchlist upsert, no State page update. This is conversation-only by design.
- Never modify or commit to the GitHub repo.
- Never lower thresholds or modify run.py inputs to manufacture a more flattering result.
- Never give a "buy" or "sell" recommendation. Always: "math, not advice — your call."
- Never claim a stock will rally. Frame as "conditions present that historically precede breakouts."
- Never frame an already-moved stock (>10% recent rally, dist_52w_high < 3%) as "buy now" — frame as "watch for pullback".
- Never invent earnings numbers, guidance, or news. If WebSearch finds nothing, say so honestly.
