"""
Setup-status classifier and trade-plan generator.

Given a scored row + recent OHLC history, classifies setup as
FORMING / READY / TRIGGERED / STALE / WATCHING and (for actionable statuses)
returns a concrete trade plan: entry zone, stop, two targets, position size,
risk/reward, and capital deployment.

This module is pure math. The narrative is added later by Claude reading the
JSON sidecar. None of the numbers here are advice — they're calculations
based on the user's stated capital and risk parameters.
"""

from __future__ import annotations

import math

import pandas as pd

import config


# ---------------------------------------------------------------- indicators

def atr(df: pd.DataFrame, period: int = config.ATR_PERIOD) -> float | None:
    """Average True Range — volatility measure used for stop placement."""
    if len(df) < period + 1:
        return None
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(),
         (high - prev_close).abs(),
         (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    # Wilder's smoothing approximated with simple rolling mean
    return float(tr.tail(period).mean())


def swing_high(df: pd.DataFrame, lookback: int = config.SWING_LOOKBACK_DAYS) -> float | None:
    if len(df) < lookback:
        return None
    return float(df["High"].tail(lookback).max())


def swing_low(df: pd.DataFrame, lookback: int = config.SWING_LOOKBACK_DAYS) -> float | None:
    if len(df) < lookback:
        return None
    return float(df["Low"].tail(lookback).min())


# ---------------------------------------------------------------- status

def classify_status(row: dict, flag_threshold: int) -> str:
    """
    READY      score ≥ threshold AND fundamentals pass
    TRIGGERED  same as READY but newly transitioned today (trajectory == NEW)
    FORMING    score ≥ threshold-1 AND fundamentals pass (one signal away)
    STALE      previously cleared threshold but no longer (trajectory == WEAKER)
    WATCHING   anything else
    """
    score = row["score"]
    passes = row.get("passes_gates", True)
    traj = row.get("trajectory_tag")

    cleared_today = score >= flag_threshold and passes

    if cleared_today and traj == "NEW":
        return "TRIGGERED"
    if cleared_today:
        return "READY"
    if score >= (flag_threshold - 1) and passes:
        return "FORMING"
    if traj == "WEAKER" and (row.get("prev_score") or 0) >= flag_threshold:
        return "STALE"
    return "WATCHING"


# ---------------------------------------------------------------- watch conditions

def watch_conditions(row: dict) -> list[str]:
    """Plain-English list of what's missing for a stock to clear setup."""
    out = []
    if not row["near_52w_high"]:
        dist = row["dist_52w_high"] * 100
        out.append(f"price closes within 10% of 52w high (currently {dist:.1f}% below)")
    if not row["macd_crossover_5d"]:
        out.append("MACD bullish crossover (currently no crossover in last 5 sessions)")
    if not row["dma_50_above_200"]:
        out.append("50-day MA crosses above 200-day MA (currently below — broader trend not up)")
    if not row["volume_accum"]:
        ratio = row.get("volume_ratio")
        cur = f"currently {ratio:.2f}× the 20d average" if ratio is not None else "currently below threshold"
        out.append(f"volume > 1.5× the 20-day average on a green close ({cur})")
    return out


# ---------------------------------------------------------------- trade plan

def _ceil_int(x: float) -> int:
    return int(math.floor(x))


def compute_trade_plan(row: dict, df: pd.DataFrame) -> dict | None:
    """
    Build a concrete trade plan from row data + OHLC history.

    Returns None if essential math can't be computed (insufficient history,
    zero division, etc.).

    Returned dict shape:
        {
            "entry_zone_low": float, "entry_zone_high": float, "current_price": float,
            "stop": float, "stop_method": str (for explainability),
            "target_1": float, "target_2": float,
            "atr": float, "swing_low": float, "swing_high": float,
            "risk_per_share": float,
            "rr_to_target_1": float, "rr_to_target_2": float,
            "position": {
                "ideal_shares": int,
                "max_affordable_shares": int,
                "shares": int,                  # min of the two
                "binding_constraint": str,      # "risk_budget" | "slot_budget" | "unfeasible"
                "capital_deployed_inr": float,
                "max_loss_inr": float,
                "expected_profit_t1_inr": float,
                "expected_profit_t2_inr": float,
                "max_loss_pct_of_capital": float,
                "expected_return_t1_pct_of_capital": float,
                "expected_return_t2_pct_of_capital": float,
            },
            "rr_warning": str | None,            # populated if R:R below MIN_RR
        }
    """
    last_close = float(row["last_close"])
    a = atr(df)
    sl = swing_low(df)
    sh = swing_high(df)

    if a is None or sl is None or sh is None or a <= 0:
        return None

    # --- stop placement -------------------------------------------------------
    # Two candidates: just-below-20d-swing-low (technical) and entry-2*ATR
    # (volatility). Take whichever is HIGHER — closer to entry, less risk per
    # share. For stocks in strong rallies with no recent pullback, the swing
    # low is far below entry and ATR-based stop wins. For stocks with recent
    # consolidation, swing-low wins (real support level).
    swing_stop = sl * config.SWING_LOW_BUFFER
    atr_stop = last_close - (config.ATR_STOP_FALLBACK_MULT * a)
    stop = max(swing_stop, atr_stop)

    if stop == swing_stop:
        stop_method = f"1% below 20d swing low (₹{sl:.2f})"
    else:
        stop_method = f"{config.ATR_STOP_FALLBACK_MULT:g}× ATR below current price (swing low too far for sized stop)"

    # Sanity: stop must be at least 1*ATR below entry (don't put it inside noise)
    min_stop = last_close - a
    if stop > min_stop:
        stop = min_stop
        stop_method = "1× ATR below entry (other candidates inside noise)"

    if stop <= 0 or stop >= last_close:
        return None

    risk_per_share = last_close - stop

    # --- targets --------------------------------------------------------------
    # Pure ATR multiples. Don't cap at swing_high — for a breakout setup, the
    # swing high IS the breakout level, not a ceiling. If the user wants to
    # take partial profits earlier, that's their call to make manually.
    target_1 = last_close + config.ATR_TARGET_1_MULT * a
    target_2 = last_close + config.ATR_TARGET_2_MULT * a

    rr_t1 = (target_1 - last_close) / risk_per_share
    rr_t2 = (target_2 - last_close) / risk_per_share

    # The MIN_RR threshold applies to Target 2 (the "worthwhile trade" target).
    # Target 1 is a partial-profit-taking level and is typically 1:1 or 1.5:1.
    rr_warning = None
    if rr_t2 < config.MIN_RISK_REWARD_RATIO:
        rr_warning = f"R:R to T2 is {rr_t2:.2f}, below {config.MIN_RISK_REWARD_RATIO:.1f}× threshold — math doesn't justify the trade"

    # --- position sizing ------------------------------------------------------

    risk_budget = config.SWING_CAPITAL_INR * config.MAX_RISK_PER_TRADE_FRAC
    ideal_shares = _ceil_int(risk_budget / risk_per_share) if risk_per_share > 0 else 0
    max_affordable_shares = _ceil_int(config.PER_SLOT_BUDGET_INR / last_close) if last_close > 0 else 0

    shares = min(ideal_shares, max_affordable_shares)
    if shares <= 0:
        binding = "unfeasible"
    elif shares == max_affordable_shares and max_affordable_shares < ideal_shares:
        binding = "slot_budget"
    else:
        binding = "risk_budget"

    capital_deployed = shares * last_close
    max_loss_inr = shares * risk_per_share
    profit_t1 = shares * (target_1 - last_close)
    profit_t2 = shares * (target_2 - last_close)

    cap = config.SWING_CAPITAL_INR

    return {
        "entry_zone_low": round(last_close * 0.99, 2),
        "entry_zone_high": round(last_close * 1.005, 2),
        "current_price": round(last_close, 2),
        "stop": round(stop, 2),
        "stop_method": stop_method,
        "target_1": round(target_1, 2),
        "target_2": round(target_2, 2),
        "atr": round(a, 2),
        "swing_low": round(sl, 2),
        "swing_high": round(sh, 2),
        "risk_per_share": round(risk_per_share, 2),
        "rr_to_target_1": round(rr_t1, 2),
        "rr_to_target_2": round(rr_t2, 2),
        "rr_warning": rr_warning,
        "position": {
            "ideal_shares": ideal_shares,
            "max_affordable_shares": max_affordable_shares,
            "shares": shares,
            "binding_constraint": binding,
            "capital_deployed_inr": round(capital_deployed, 2),
            "max_loss_inr": round(max_loss_inr, 2),
            "expected_profit_t1_inr": round(profit_t1, 2),
            "expected_profit_t2_inr": round(profit_t2, 2),
            "max_loss_pct_of_capital": round(100 * max_loss_inr / cap, 2),
            "expected_return_t1_pct_of_capital": round(100 * profit_t1 / cap, 2),
            "expected_return_t2_pct_of_capital": round(100 * profit_t2 / cap, 2),
        },
    }
