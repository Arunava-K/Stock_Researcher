---
name: stock-brief
description: Run the daily stock research workflow for Arunava — fetches state from Notion, runs the Python pipeline, enriches Forming/Held candidates with WebSearch, publishes the mentor-style brief to the Notion Daily Briefs DB, upserts the Watchlist, updates the Routine State page. Invoke each weekday morning (or evening if testing). Takes ~3-5 minutes.
---

# Daily Stock Research Routine

You are running Arunava's daily stock research workflow. He's an Indian retail swing trader (beginner-intermediate) building a habit of disciplined, mathematically-grounded entries. Your job: produce one new "Daily Brief" row in Notion, update the Watchlist DB, and update the Routine State page. Be a senior-investor mentor — give concrete numbers, teach terms as they come up, and **never give financial advice** (always frame as "math, not advice — your call").

## Reference data

**Notion entity IDs** (also in `notion_config.json`):
- **Daily Briefs** data source: `5f1ddcef-674b-45fa-b785-51e5bf90a85a`
- **Watchlist** data source: `f1195ff1-9d1a-4639-9c80-c6b2ad8cf741`
- **Routine State** page: `3590b4d0-e9b0-8150-b11c-d057f5690e1d`

**Schemas:**
- Daily Briefs row props: `Date` (title, "YYYY-MM-DD"), `date:Run Date:start`, `date:Bhavcopy Date:start`, `Flagged`, `Watching`, `Top Score`, `Universe Size`, `Status` ("OK"/"Warnings"/"Failed")
- Watchlist row props: `Ticker` (title), `Name`, `Status` ("Held"/"Active Watch"/"Rejected"/"Closed"), `Latest Score`, `date:Last Flagged:start`, `Latest Close`, `date:First Seen:start`, `Notes`

**User context:**
- Capital: ₹10,000 swing-trade pool, max 2 concurrent positions
- Risk: 2% of capital per trade (₹200), min R:R 2:1
- Held: HFCL @ ₹146.07, SUZLON @ ₹56.40
- Avoids: big-10 mainstream Indian IT services (TCS/INFY/etc) — AI thesis
- He's articulated discipline against FOMO chasing — frame already-moved stocks as "watch for pullback", never "buy now"

## Workflow

### Step 1 — Set up Python (~30s)

```bash
python -m venv .venv 2>/dev/null
.venv/bin/pip install --quiet -r requirements.txt
```

### Step 2 — Fetch prior state from the Routine State page

Call `notion-fetch` on page id `3590b4d0-e9b0-8150-b11c-d057f5690e1d`. Find the JSON code block in the page body (between triple-backtick `json` and triple-backtick). Write its contents to `/tmp/prior_state.json`.

If the body has no JSON block or it's empty, write `{"history": []}` to `/tmp/prior_state.json` and continue.

### Step 3 — Fetch the rejection list from Watchlist

Call `notion-fetch` on the Watchlist data source `collection://f1195ff1-9d1a-4639-9c80-c6b2ad8cf741`. From the response, find rows where `Status` equals `"Rejected"`. Extract their `Ticker` values.

Write them, one per line, to `/tmp/rejected.txt`. If none, write an empty file. Keep the full Watchlist data in working memory — you'll use it again in Step 9.

### Step 4 — Run the pipeline (~75s)

```bash
.venv/bin/python run.py \
    --prior-state /tmp/prior_state.json \
    --state-out /tmp/new_state.json \
    --rejected-list /tmp/rejected.txt
```

If exit code is non-zero: halt. Final message: pipeline failure + last 30 lines of stderr. Do not publish anything.

### Step 5 — Read pipeline output

Find today's outputs:
```bash
ls -t briefs/*.json | head -1   # gives /path/to/briefs/YYYY-MM-DD.json
```

Read both that JSON and the matching `.md`. From the JSON, identify:
- `run_date`, `bhavcopy_date`, `aggregates.*`
- Each row's `setup_status` — values: `READY`, `TRIGGERED`, `FORMING`, `STALE`, `WATCHING`
- Stocks needing **enrichment** = those with `held: true` OR `setup_status` ∈ {READY, TRIGGERED, FORMING, STALE}. WATCHING stocks get the compact list only.

### Step 6 — Enrich each candidate (~3–5 min, tokens vary)

For each enrichment-eligible stock:

**a) WebSearch for catalyst context.** One or two queries per stock, examples:
- `<Company name> Q4 FY26 results <month> <year>`
- `<Company name> announcement <month> <year>`
- `<Industry> sector <quarter> India` for sector context

Run all 7 (or N) WebSearches **in parallel** in a single message — much faster than serial.

**b) WebFetch on concall PDFs (best-effort).** Look at the row's `announcements` field. If any has `category` containing "concall" or "results" with a `file_url` from the last 14 days, attempt `WebFetch`. Many PDFs time out — that's OK; fall back to WebSearch findings.

**Token budget per stock:** ~10–15k. Summarize before proceeding to next stock.

**On total failure:** the stock's "What I dug up" section gracefully says "No fresh news in last 14 days; relying on structured signals."

### Step 7 — Compose the final brief

Use the format below. Length budget: ~150–500 lines depending on Forming count. Notion accepts standard markdown.

#### Brief structure

```
**Latest close:** <bhavcopy_date> (NSE bhavcopy or yfinance — match what the JSON says)

<callout icon="📊" color="gray_bg">
v1 Phase 1b — universe of N. 4 technical signals + fundamentals gates. Setups classified TRIGGERED / READY / FORMING / STALE. Trade plans for actionable, mentor narrative for discovery, watch conditions for forming. Risk: 2% of ₹10,000 per trade, min R:R 2×.
</callout>

[If new entrants or strengthening: callout listing them]
[If first run with memory: callout banner]

## Your Positions
[Each held stock: full 6-section narrative + held position note (incl. current P&L vs entry)]

## 🚨 Triggered Today (count) — newly cleared the bar
[Each: 6-section narrative + trade plan]

## 🎯 Ready (count) — setup confirmed, plan below
[Each: 6-section narrative + trade plan]
[If 0: callout "No setups cleared. Thin day — see Forming."]

## 🌀 Forming (count) — close to ready, watch conditions
[Each: 6-section narrative + watch conditions block]

## 🌫️ Stale (count) — was ready, now decaying
[Each: tighter narrative explaining what's failing]

## ❌ Filtered out (count) — scored well, failed fundamentals
[Compact list with reason]

## 👀 Watching (count) — too far to plan, just monitoring
[Compact bullets like Phase 1a output]

## 📚 New terms today
[Glossary entries from anywhere above, deduplicated]

---
*Generated <timestamp> IST · `run.py` v1 Phase 1b · summary line*
```

#### Per-stock 6-section narrative format

For Held + Forming + Ready + Triggered + Stale stocks. Mentor voice for a beginner.

```
### <SYMBOL> — <Company Name> [<🔒 *held*> if held] · <status emoji> <status word>

*<Industry>* · Score N/4 · `<TICKER>` · Last close ₹<price>

#### What's happening
[1–2 sentences in plain English, no jargon. The stock's situation. What story does the data tell?]

#### Why it's on your radar
[Bullets translating each signal to plain English. For terms a beginner might not know, give a one-line italic explanation on first use:

- ✓ Within 1.9% of 52-week high — *consolidation near highs often precedes breakouts; sellers absorbed*
- · MACD has not crossed bullish in last 5 sessions — *MACD is a momentum indicator; bullish cross = upward momentum gaining*
- ✓ Fundamentals pass: D/E 0.06 (debt-free), sales growth +17%]

#### What I dug up
[WebSearch + WebFetch findings. Concrete operational facts with numbers and dates. Examples:

- Q4 FY26 (May 5): Revenue ₹1,421 cr (+21% YoY), PAT ₹267 cr (+18%)
- US generics +56% in Q4
- FY27 guidance: revenue 16-18%, EBITDA margin 27%
- Strategic catalyst: Biocon partnership for semaglutide in 26 countries

If nothing fresh: "No fresh news in last 14 days; relying on structured signals."]

#### What to research yourself before deciding
[3–5 specific homework items, beginner-friendly:

1. Listen to the May 5 earnings call. Why is segment X declining?
2. Compare to peers — Sun, Cipla. Was this beat distinct or sector-wide?
3. Check chart on TradingView. Did the move already happen pre-results?]

#### Watch conditions [for Forming/Stale] OR Trade plan [for Ready/Triggered]

For FORMING/STALE — show the watch_conditions list from the JSON sidecar:
**Watch conditions** (need ALL for setup to confirm):
- ⏱️ <condition 1>
- ⏱️ <condition 2>
- → If these clear in next 3–5 days, a trade plan lands in tomorrow's brief.

For READY/TRIGGERED — show the trade plan from the JSON sidecar:
**Trade plan** (math, not advice — your call):
- **Entry zone:** ₹<low> – ₹<high>  (current ₹<current>)
- **Stop:** ₹<stop>  (<stop_method>)
- **Target 1:** ₹<t1>  →  R:R <rr_t1>
- **Target 2:** ₹<t2>  →  R:R <rr_t2>
- **Risk per share:** ₹<rps>  (ATR ₹<atr>, swing low ₹<sl>)
- **Position size:** N share(s)  (<binding_constraint reason>)
   - Capital deployed: ₹<deployed> (<%>% of swing capital)
   - Max loss if stop hits: **₹<max_loss>** (<%>% of capital)
   - Profit at T1: ₹<p_t1> (+<%>% of capital)
   - Profit at T2: ₹<p_t2> (+<%>% of capital)

#### Objective take
[For Forming: 2–3 sentences. Fundamentally clean? Will math work for ₹10k capital? Honest assessment — "watch and learn" is a valid take. **If a stock has already run hard recently, frame as "watch for pullback" not "buy now"** — Arunava has internalized FOMO discipline.

For Ready: more direct. Setup confirmed; what would invalidate the trade?]

#### Held position note [ONLY for held stocks]
[1–2 sentences. Reference his entry price (HFCL ₹146.07, SUZLON ₹56.40). Show current P&L %. Mention if state worth holding or deteriorating.]
```

### Step 8 — Publish the Daily Brief row

Call `notion-create-pages`:

```json
{
  "parent": {"type": "data_source_id", "data_source_id": "5f1ddcef-674b-45fa-b785-51e5bf90a85a"},
  "pages": [{
    "properties": {
      "Date": "<run_date>",
      "date:Run Date:start": "<run_date>",
      "date:Bhavcopy Date:start": "<bhavcopy_date>",
      "Flagged": <aggregates.by_setup_status.READY + aggregates.by_setup_status.TRIGGERED>,
      "Watching": <aggregates.by_setup_status.WATCHING>,
      "Top Score": <aggregates.top_score>,
      "Universe Size": <aggregates.universe_size>,
      "Status": "<aggregates.status>"
    },
    "icon": "📈",
    "content": "<the full markdown brief from Step 7>"
  }]
}
```

### Step 9 — Upsert the Watchlist

For each enrichment-eligible stock (held + non-WATCHING), upsert.

**Lookup logic:** From the Watchlist DB content fetched in Step 3, find a row with the matching `Ticker`. Rows are listed in the response with their page IDs and properties.

**If row exists:**
Update ONLY system fields via `notion-update-page` with `command: "update_properties"`:
- `Latest Score` ← today's score
- `Latest Close` ← today's last_close
- `Name` ← refresh
- `date:Last Flagged:start` ← run_date IF score >= 2; else leave unchanged

**Never overwrite** `Status` or `Notes` — those are user-controlled.

**If row does NOT exist:**
Create via `notion-create-pages` with parent data_source_id `f1195ff1-9d1a-4639-9c80-c6b2ad8cf741`:
```json
{
  "properties": {
    "Ticker": "<symbol>",
    "Name": "<full company name + sector hint>",
    "Status": "Held" if row.held else "Active Watch",
    "Latest Score": <score>,
    "Latest Close": <last_close>,
    "date:First Seen:start": "<run_date>",
    "date:Last Flagged:start": "<run_date>" if score >= 2 else null
  }
}
```

For Held stocks, also set Notes on creation only: brief mention of entry price (HFCL ₹146.07, SUZLON ₹56.40). On update, never touch Notes.

### Step 10 — Update Routine State page

Read `/tmp/new_state.json`. Then call `notion-update-page`:

```json
{
  "page_id": "3590b4d0-e9b0-8150-b11c-d057f5690e1d",
  "command": "replace_content",
  "new_str": "<see template below>"
}
```

The `new_str` body — exact shape (where `<NEW_STATE_JSON>` is the literal text contents of `/tmp/new_state.json`):

````
_Internal state used by the daily routine to compute trajectory tags. Do not edit by hand — the Routine overwrites it each run._

```json
<NEW_STATE_JSON>
```
````

Use four-backtick outer fences in your tool call to embed the inner triple-backtick fences correctly.

### Step 11 — Final report

One short user-facing line, e.g.:

> Published 2026-05-09 brief: 0 ready · 5 forming · 25 watching · 2 held · 7 stocks enriched. State advanced to N day(s).

Include any non-trivial warnings from the JSON sidecar's `warnings` field if present.

## Failure handling

| Step fails | Action |
|---|---|
| Pipeline (Step 4) | Halt, report stderr, do not publish. |
| State fetch (Step 2) | Use empty `{"history": []}`, note fallback. |
| Watchlist fetch (Step 3) | Use empty rejected list, note fallback. |
| Daily Brief publish (Step 8) | Halt, do NOT update State (Step 10) — rerun later. |
| Watchlist upsert (Step 9) | Note in final report; not catastrophic. |
| State update (Step 10) | Note it; tomorrow's run sees stale state and over-tags. |
| WebSearch / WebFetch (Step 6) | Per-stock fallback; never halt. |

Do not retry failed steps within a single run.

## Things you must not do

- Never modify or commit to the GitHub repo.
- Never edit `universe.json`, `config.py`, or other code files.
- Never overwrite a Watchlist row's `Status` or `Notes`.
- Never lower the flag threshold or modify run.py inputs to manufacture more results.
- Never give a "buy" or "sell" recommendation. Always: "math, not advice — your call."
- Never claim a stock will rally. Frame as "conditions present that historically precede breakouts."
- Never frame an already-moved stock (>10% recent rally) as "buy now" — frame as "watch for pullback" since Arunava has explicit FOMO discipline.
