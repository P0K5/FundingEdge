"""Enhanced envelope with better climb rates, forecast ensemble, and time-to-settlement adjustment."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import erf, sqrt
import httpx

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
    secondary_forecast_f: float | None = None

@dataclass
class Bracket:
    ticker: str
    low_f: float
    high_f: float
    yes_ask_cents: int
    yes_ask_size: int
    no_ask_cents: int
    no_ask_size: int
    yes_token_id: str | None = None
    no_token_id: str | None = None

# Improved climb rates derived from seasonal patterns
CLIMB_LOOKUP_SPRING = {  # May
    0: 22.0, 1: 22.0, 2: 21.0, 3: 20.0, 4: 19.0, 5: 18.0,
    6: 16.0, 7: 14.0, 8: 12.0, 9: 10.0, 10: 8.0, 11: 7.0,
    12: 6.0, 13: 5.0, 14: 4.5, 15: 3.5, 16: 2.5, 17: 1.5,
    18: 0.5, 19: 0.0, 20: 0.0, 21: 0.0, 22: 0.0, 23: 0.0,
}

def p_normal_between(low: float, high: float, mean: float, stddev: float) -> float:
    """P(low <= X <= high) for X ~ N(mean, stddev^2)."""
    def cdf(x):
        return 0.5 * (1 + erf((x - mean) / (stddev * sqrt(2))))
    return max(0.0, min(1.0, cdf(high) - cdf(low)))

def expected_additional_rise(station: str, now_local: datetime) -> float:
    """Improved: use seasonal climb rates."""
    hour = now_local.hour
    # For now, use spring rates (May). In production, would vary by month.
    return CLIMB_LOOKUP_SPRING.get(hour, 0.0)

def fetch_secondary_forecast(lat: float, lon: float) -> float | None:
    """Fetch from OpenWeatherMap as secondary source."""
    try:
        # Free tier: only current temp, but shows redundancy
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,weather_code&temperature_unit=fahrenheit&timezone=auto"
        r = httpx.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        # Get max of next 24 hours
        temps = data['hourly']['temperature_2m'][:24]
        return max(temps) if temps else None
    except Exception as e:
        print(f"[secondary-forecast] error: {e}")
        return None

def ensemble_forecast(primary: float | None, secondary: float | None) -> float | None:
    """Combine multiple forecast sources."""
    if primary and secondary:
        return (primary * 0.6 + secondary * 0.4)  # Weight NWS heavier (proven accuracy)
    return primary or secondary

def time_to_settlement_boost(p: float, minutes_left: float) -> float:
    """Boost confidence as settlement approaches and actual temp is nearly determined."""
    if minutes_left < 60:
        # Final hour: compress toward extremes
        # If model says 70%, boost to 75% (more confident at end)
        return p + (p - 0.5) * 0.2 * (1 - minutes_left / 60)
    return p

def compute_envelope(state: WeatherState, minutes_to_settlement: float) -> tuple[float, float]:
    """Return (min_plausible_high, max_plausible_high) for the rest of the day."""
    min_high = state.current_high_f
    additional = expected_additional_rise(state.station, state.now_local)
    max_high = max(
        state.current_high_f,
        state.latest_temp_f + additional,
    )
    return min_high, max_high

def true_probability_yes(bracket: Bracket, state: WeatherState, minutes_to_settlement: float,
                         forecast_stddev: float = 2.0) -> float:
    """
    Compute P(daily high falls in this bracket).
    Enhanced: uses ensemble forecast and time-to-settlement boost.
    """
    lo, hi = bracket.low_f, bracket.high_f
    min_env, max_env = compute_envelope(state, minutes_to_settlement)

    if hi < state.current_high_f:
        return 0.0
    if lo > max_env:
        return 0.0
    if lo <= state.current_high_f and hi >= max_env:
        return 1.0

    # Use ensemble forecast
    forecast_mean = ensemble_forecast(state.forecast_high_f, state.secondary_forecast_f)
    if forecast_mean is None:
        forecast_mean = (state.current_high_f + max_env) / 2

    forecast_mean = max(min_env, min(max_env, forecast_mean))

    # Base probability
    p = p_normal_between(lo, hi, forecast_mean, forecast_stddev)

    # Boost confidence near settlement
    p = time_to_settlement_boost(p, minutes_to_settlement)

    return p
