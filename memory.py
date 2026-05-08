"""
Trajectory tracking — pure functions over a JSON state object.

State shape:
    {
        "history": [
            {
                "bhavcopy_date": "2026-05-07",
                "rows": [
                    {"symbol": "HFCL", "score": 3, "passes_gates": true, "held": true},
                    ...
                ]
            },
            ...
        ]
    }

History is ordered most-recent first (index 0 = most recent prior trading day).
Capped at MAX_HISTORY_DAYS so the JSON stays small enough to live inside a
single Notion page body.

The cloud Routine is responsible for persisting this state — fetching it from
the Notion "Routine State" page before run.py executes and writing it back
after. This module is pure: no I/O, no DB.
"""

from __future__ import annotations

MAX_HISTORY_DAYS = 7  # rolling window for streak detection


def annotate_trajectory(rows: list[dict], current_bhavcopy_date: str,
                        threshold: int, prior_state: dict | None) -> None:
    """
    Mutate `rows` in place, adding trajectory fields:
        prev_score, score_delta, streak_days, trajectory_tag

    `prior_state` is the JSON object loaded from the Notion State page
    (or None on the very first run).
    """
    history = (prior_state or {}).get("history", [])

    if not history:
        for r in rows:
            r["prev_score"] = None
            r["score_delta"] = None
            r["streak_days"] = 0
            r["trajectory_tag"] = None
        return

    # Build per-symbol lookups: most-recent prior score, and the consecutive-clear streak.
    most_recent = history[0]
    prev_by_symbol: dict[str, dict] = {}
    if most_recent.get("bhavcopy_date") and most_recent["bhavcopy_date"] < current_bhavcopy_date:
        for entry in most_recent.get("rows", []):
            prev_by_symbol[entry["symbol"]] = entry

    # Streak: count consecutive prior days where the symbol cleared (score >= threshold AND passes_gates).
    streak_by_symbol: dict[str, int] = {}
    for r in rows:
        sym = r["symbol"]
        streak = 0
        for snap in history:
            if snap.get("bhavcopy_date") and snap["bhavcopy_date"] >= current_bhavcopy_date:
                continue  # ignore today or future entries (defensive)
            entry = next((e for e in snap.get("rows", []) if e["symbol"] == sym), None)
            if entry is None:
                break
            if entry["score"] >= threshold and entry.get("passes_gates", True):
                streak += 1
            else:
                break
        streak_by_symbol[sym] = streak

    for r in rows:
        sym = r["symbol"]
        prev = prev_by_symbol.get(sym)
        prev_score = prev["score"] if prev else None
        prev_passes = prev.get("passes_gates", True) if prev else None
        delta = (r["score"] - prev_score) if prev_score is not None else None

        r["prev_score"] = prev_score
        r["score_delta"] = delta
        r["streak_days"] = streak_by_symbol.get(sym, 0)

        clears_today = r["score"] >= threshold and r.get("passes_gates", True)
        cleared_prev = (
            prev_score is not None
            and prev_score >= threshold
            and (prev_passes if prev_passes is not None else True)
        )

        if prev_score is None:
            r["trajectory_tag"] = None
        elif clears_today and not cleared_prev:
            r["trajectory_tag"] = "NEW"
        elif delta is not None and delta >= 1 and clears_today:
            r["trajectory_tag"] = "STRONGER"
        elif delta is not None and delta <= -1 and cleared_prev:
            r["trajectory_tag"] = "WEAKER"
        elif r["streak_days"] >= 3 and clears_today:
            r["trajectory_tag"] = "STREAK"
        else:
            r["trajectory_tag"] = None


def build_new_state(today_rows: list[dict], today_bhavcopy_date: str,
                    prior_state: dict | None,
                    max_days: int = MAX_HISTORY_DAYS) -> dict:
    """
    Return a new state object with today's snapshot prepended to history,
    trimmed to `max_days`. Drops any prior entries with the same date
    (idempotent re-runs of the same trading day).
    """
    history = (prior_state or {}).get("history", [])
    history = [s for s in history if s.get("bhavcopy_date") != today_bhavcopy_date]

    today_compact = [
        {
            "symbol": r["symbol"],
            "score": int(r["score"]),
            "passes_gates": bool(r.get("passes_gates", True)),
            "held": bool(r["held"]),
        }
        for r in today_rows
    ]

    new_history = [{"bhavcopy_date": today_bhavcopy_date, "rows": today_compact}] + history
    return {"history": new_history[:max_days]}
