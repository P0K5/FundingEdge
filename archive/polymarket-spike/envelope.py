"""Envelope and edge calculations. This is the heart of the strategy."""
from dataclasses import dataclass, field
from datetime import datetime
from math import erf, sqrt
from config import DEFAULT_CLIMB_LOOKUP, FORECAST_STDDEV_F


@dataclass
class WeatherState:
    station: str
    now_local: datetime
    sunset_local: datetime
    current_high_f: float
    current_high_time: datetime
    latest_temp_f: float
    latest_temp_time: datetime
    forecast_high_f: float | None


@dataclass
class Bracket:
    ticker: str          # Polymarket condition_id (hex string)
    low_f: float         # inclusive lower bound (°F)
    high_f: float        # inclusive upper bound (°F)
    yes_ask_cents: int   # price to buy YES, in cents (1–99)
    yes_ask_size: int
    no_ask_cents: int    # price to buy NO, in cents (1–99)
    no_ask_size: int
    # Polymarket-specific: token IDs for CLOB orderbook queries
    yes_token_id: str | None = field(default=None)
    no_token_id: str | None = field(default=None)


def p_normal_between(low: float, high: float, mean: float, stddev: float) -> float:
    """P(low <= X <= high) for X ~ N(mean, stddev^2)."""
    def cdf(x): return 0.5 * (1 + erf((x - mean) / (stddev * sqrt(2))))
    return max(0.0, min(1.0, cdf(high) - cdf(low)))


def expected_additional_rise(station: str, now_local: datetime) -> float:
    """Look up the p95 additional daily high rise possible from `now` to end of day."""
    hour = now_local.hour
    if hour >= 20:
        return 0.0
    return DEFAULT_CLIMB_LOOKUP.get(hour, 0.0)


def compute_envelope(state: WeatherState) -> tuple[float, float]:
    """Return (min_plausible_high, max_plausible_high) for the rest of the day."""
    min_high = state.current_high_f
    additional = expected_additional_rise(state.station, state.now_local)
    max_high = max(
        state.current_high_f,
        state.latest_temp_f + additional,
    )
    return min_high, max_high


def true_probability_yes(bracket: Bracket, state: WeatherState) -> float:
    """
    Compute P(daily high falls in this bracket).
    Returns values in [0, 1].
    """
    lo, hi = bracket.low_f, bracket.high_f
    min_env, max_env = compute_envelope(state)

    if hi < state.current_high_f:
        return 0.0

    if lo > max_env:
        return 0.0

    if lo <= state.current_high_f and hi >= max_env:
        return 1.0

    forecast_mean = state.forecast_high_f if state.forecast_high_f is not None else (
        (state.current_high_f + max_env) / 2
    )
    forecast_mean = max(min_env, min(max_env, forecast_mean))
    return p_normal_between(lo, hi, forecast_mean, FORECAST_STDDEV_F)
