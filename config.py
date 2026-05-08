"""
User-tunable parameters that drive trade-plan math.

Edit these when your capital changes, your risk tolerance shifts, or you
want to experiment with stricter / looser plan generation. Everything that
affects how plans are sized lives here.
"""

from __future__ import annotations

# ---------------------------------------------------------------- capital ----

# Total capital allocated to swing trading (separate from long-term holdings).
# Update when you scale up the account.
SWING_CAPITAL_INR = 10_000

# Max number of concurrent open positions. With small capital, splitting too
# thin makes brokerage eat returns. Currently 2 max per the user's plan.
MAX_CONCURRENT_POSITIONS = 2

# ---------------------------------------------------------------- risk ----

# Max fraction of total capital risked on a single trade.
# Standard ranges: 1% (very conservative), 2% (beginner-friendly default), 3%
# (aggressive). At ₹10k → 2% = ₹200 max loss per trade if stop hits.
MAX_RISK_PER_TRADE_FRAC = 0.02

# Minimum risk:reward ratio (Target1 vs stop) required to surface a trade plan.
# Below this the math doesn't justify the trade — system will mark setup as
# "READY but R:R too tight" rather than offering a plan.
MIN_RISK_REWARD_RATIO = 2.0

# ---------------------------------------------------------------- sizing ----

# Per-slot capital budget. With 2 concurrent positions on ₹10k, this caps each
# slot at 35% of total capital (~₹3,500), leaving a buffer for brokerage,
# slippage, and the inevitable late-entry on a third opportunity.
PER_SLOT_BUDGET_INR = SWING_CAPITAL_INR * (1.0 / MAX_CONCURRENT_POSITIONS) * 0.70

# ---------------------------------------------------------------- math knobs ----

# ATR period for volatility / stop placement.
ATR_PERIOD = 14

# Lookback window for "recent swing high/low" support and resistance levels.
SWING_LOOKBACK_DAYS = 20

# Stop placement: prefer just-below-swing-low if it gives at least
# MIN_STOP_DISTANCE_ATR worth of distance from entry. Otherwise fall back to
# entry - 2*ATR. Prevents stops landing inside normal noise.
MIN_STOP_DISTANCE_ATR = 1.0
ATR_STOP_FALLBACK_MULT = 2.0
SWING_LOW_BUFFER = 0.99  # 1% below swing low to absorb fakeouts

# Target levels (multiples of ATR above entry).
ATR_TARGET_1_MULT = 2.0
ATR_TARGET_2_MULT = 4.0
