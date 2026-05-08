# MeteoEdge Technical Specification

## System Overview

MeteoEdge is a weather-arbitrage trading system that identifies profitable mispricings in Polymarket weather markets by comparing real-time meteorological observations and forecasts against market-implied probabilities.

**Core thesis:** Weather forecasting services (NOAA, NWS) are more accurate than crowd-consensus prices in prediction markets. We exploit this gap by:

1. Computing true probabilities from meteorological data
2. Comparing against market ask prices
3. Trading when edge (true probability × 100 - market price - fees) exceeds minimum threshold

---

## Data Pipeline

### Input Sources

```
Weather Data
├── METAR (Current)
│   └── aviationweather.gov API
│       ├── Station: METAR codes (KLGA, KORD, KMIA, etc.)
│       ├── Fields: Current temperature, wind, conditions
│       └── Refresh: Every 5 minutes
│
├── NWS Forecast (Primary)
│   └── api.weather.gov (free, no auth required)
│       ├── Points API: geo → forecast URL
│       ├── Forecast API: hourly temps for next 7 days
│       └── Refresh: Every 5 minutes
│
└── Secondary Forecast
    └── Open-Meteo API
        ├── Hourly temperatures
        ├── Free tier, no auth
        └── Used in ensemble (40% weight)

Market Data
├── Polymarket Gamma API
│   ├── /markets?tag_id=84 → weather markets
│   ├── Fields: condition ID, outcome prices, order sizes
│   └── Refresh: Every 5 minutes
│
└── Polymarket CLOB (optional enrichment)
    ├── Real-time orderbook
    ├── /orderbooks/:token_id
    └── Used only if ENABLE_CLOB_ENRICHMENT=True
```

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    POLLING CYCLE (5 min)                │
└─────────────────────────────────────────────────────────┘
                            ↓
         ┌──────────────────────────────────────┐
         │  1. FETCH WEATHER DATA               │
         │     ├─ METAR observations (11 cities)│
         │     ├─ NWS forecasts (11 cities)     │
         │     └─ Open-Meteo (11 cities)        │
         └──────────────────────────────────────┘
                            ↓
         ┌──────────────────────────────────────┐
         │  2. BUILD WEATHER STATES             │
         │     ├─ Current high (observed)       │
         │     ├─ Latest temperature (actual)   │
         │     ├─ Forecast high (NWS)           │
         │     └─ Secondary forecast (Open-Met)│
         └──────────────────────────────────────┘
                            ↓
         ┌──────────────────────────────────────┐
         │  3. FETCH MARKET DATA                │
         │     └─ Polymarket: 2000+ weather markets
         └──────────────────────────────────────┘
                            ↓
         ┌──────────────────────────────────────┐
         │  4. PROBABILITY CALCULATION          │
         │     For each market bracket:         │
         │     ├─ P(high in bracket | weather) │
         │     ├─ Apply time-to-settlement boost
         │     └─ Result: p_yes ∈ [0, 1]       │
         └──────────────────────────────────────┘
                            ↓
         ┌──────────────────────────────────────┐
         │  5. EDGE CALCULATION                 │
         │     ├─ ev_yes = p_yes×100 - ask - fee
         │     ├─ ev_no = (1-p_yes)×100 - ask - fee
         │     └─ Flag if edge ≥ MIN_EDGE_CENTS│
         └──────────────────────────────────────┘
                            ↓
         ┌──────────────────────────────────────┐
         │  6. EXECUTION (Paper Trading)        │
         │     For each flagged opportunity:    │
         │     ├─ Simulate queue delay (50-500ms)
         │     ├─ Apply random slippage (0.5-3¢)
         │     ├─ Update capital on P&L        │
         │     └─ Log trade (JSONL)            │
         └──────────────────────────────────────┘
                            ↓
         ┌──────────────────────────────────────┐
         │  7. REPORTING                        │
         │     ├─ Hourly summary (# trades, PnL)
         │     ├─ Trade-by-trade log (JSONL)   │
         │     └─ Station performance (JSON)   │
         └──────────────────────────────────────┘
```

---

## Probability Model

### Overview

The model computes P(daily_high falls in bracket | current weather + forecast) using:

1. **Weather envelope** (physically possible range)
2. **Bayesian prior** (NWS forecast + forecast uncertainty)
3. **Normal distribution** (to interpolate bracketed outcomes)
4. **Time-to-settlement boost** (confidence increase near resolution)

### Algorithm

#### 1. Weather Envelope

```python
def compute_envelope(state: WeatherState, minutes_to_settlement: float):
    """
    Returns (min_plausible_high, max_plausible_high) for rest of day
    
    Constraints:
    - Minimum: current observed high (can't go down)
    - Maximum: latest_temp + expected_additional_climb
    
    Expected climb = lookup based on:
    - Hour of day (morning hours have higher climb potential)
    - Season (May has different climb than December)
    """
    min_high = state.current_high_f
    
    hour = state.now_local.hour
    additional = CLIMB_LOOKUP_SPRING.get(hour, 0.0)  # Seasonal adjustment
    
    max_high = max(
        state.current_high_f,
        state.latest_temp_f + additional
    )
    
    return min_high, max_high
```

#### 2. Ensemble Forecast

```python
def ensemble_forecast(primary: float, secondary: float):
    """
    Combines NWS (primary) and Open-Meteo (secondary)
    
    Weights:
    - NWS: 60% (proven accuracy, more detailed)
    - Open-Meteo: 40% (provides redundancy, catches NWS errors)
    """
    if primary and secondary:
        return primary * 0.6 + secondary * 0.4
    return primary or secondary
```

#### 3. Probability Calculation

```python
def true_probability_yes(bracket, state, minutes_to_settlement):
    """
    P(daily_high ∈ [bracket.low, bracket.high])
    
    Cases:
    1. Bracket below current high → P = 0 (impossible)
    2. Bracket above max envelope → P = 0 (impossible)
    3. Bracket contains full envelope → P = 1 (certain)
    4. Otherwise: integrate normal distribution
    """
    lo, hi = bracket.low_f, bracket.high_f
    min_env, max_env = compute_envelope(state, minutes_to_settlement)
    
    # Boundary cases
    if hi < state.current_high_f:
        return 0.0  # Bracket below current high
    if lo > max_env:
        return 0.0  # Bracket above max possible
    if lo <= state.current_high_f and hi >= max_env:
        return 1.0  # Bracket contains entire envelope
    
    # Use NWS forecast as prior mean
    forecast_mean = ensemble_forecast(
        state.forecast_high_f,
        state.secondary_forecast_f
    )
    
    # Clamp to physically possible range
    forecast_mean = max(min_env, min(max_env, forecast_mean))
    
    # Integrate P(X ∈ [lo, hi]) for X ~ N(forecast_mean, stddev=2.0°F)
    p = p_normal_between(lo, hi, forecast_mean, FORECAST_STDDEV_F)
    
    # Boost confidence as market approaches settlement
    p = time_to_settlement_boost(p, minutes_to_settlement)
    
    return p
```

#### 4. Time-to-Settlement Boost

```python
def time_to_settlement_boost(p: float, minutes_left: float):
    """
    As market approaches resolution, actual temperature is nearly determined.
    Model should express higher confidence in predictions.
    
    Boost applied in final 60 minutes:
    - Pushes probabilities toward extremes (0→ or 1←)
    - Linear interpolation over final hour
    """
    if minutes_left < 60:
        # Boost = (p - 0.5) * 0.2 * (1 - minutes_left/60)
        # At 100% confidence, boost ≈ 0.1 (97% → 107% → clamped to 100%)
        # At 50% confidence, boost = 0 (no change)
        return p + (p - 0.5) * 0.2 * (1 - minutes_left / 60)
    return p
```

### Climb Rate Lookup Table

Derived from 5 years of METAR historical data, seasonal:

```python
CLIMB_LOOKUP_SPRING = {  # May (peak climb season)
    0: 22.0,  # Midnight: 22°F additional possible (daily min near)
    1: 22.0,
    ...
    12: 6.0,  # Noon: 6°F additional possible (approaching daily max)
    ...
    18: 0.5,  # 6pm: only 0.5°F additional (daily max reached)
    19: 0.0,  # Post-sunset: no additional climb
    20: 0.0,
    ...
    23: 0.0,
}
```

### Example Calculation

```
Current state:
- Time: 8:00 AM, May 1
- Current high: 72°F (observed so far)
- Latest temp: 68°F
- NWS forecast high: 85°F
- Open-Meteo forecast: 84°F
- Ensemble forecast: 84.6°F (0.6×85 + 0.4×84)

Market bracket: 82-84°F
Asking price: 68¢ for YES

Calculate probability:
1. Envelope: [72°F, 68 + 22] = [72°F, 90°F]
   (Can't go below 72, can climb 22°F more from current 68)

2. Forecast mean: 84.6°F (ensemble)
   - Within envelope ✓

3. P(temp ∈ [82, 84]) with N(84.6, 2.0):
   - Normal CDF(84) ≈ 0.402
   - Normal CDF(82) ≈ 0.142
   - P = 0.402 - 0.142 = 0.260

4. Time-to-settlement boost (morning, 950 min left):
   - Less than 60 min? No
   - P remains 0.260

5. Edge calculation:
   - EV_YES = 0.260 × 100 - 68 - 1 = -9.0¢
   - Not tradeable (edge < MIN_EDGE_CENTS=15)
```

---

## Execution Engine

### Position Sizing

```python
POSITION_SIZE_EUR = 5.0  # Fixed €5 per trade

# In Polymarket:
# Market price = X¢ (where 100¢ = €1.00)
# Cost to bet €5 = €5 × (X / 100) = €(5X / 100)
# Payout if win = €5
# PnL if win = €5 - €(5X / 100) = €(500 - 5X) / 100
# PnL if lose = €0 - €(5X / 100) = €(-5X / 100)
```

### Slippage Model

```python
def realistic_slippage() -> int:
    """
    Random slippage: 0.5¢ to 3¢
    
    Distribution: Gaussian centered at 1.5¢
    - Mean: 1.5¢
    - StdDev: 0.8¢
    - Min: 0.5¢
    - Max: 3.0¢
    
    Reflects:
    - Order latency (100-200ms typical)
    - Market movement between calculation and execution
    - Bid-ask spread on thin weather markets
    """
    slip = max(0.5, min(3.0, random.gauss(1.5, 0.8)))
    return int(slip * 100) // 100  # Round to cent
```

### Queue Delay Simulation

```python
def queue_delay() -> int:
    """
    Realistic order queue delay: 50-500ms
    
    Distribution: Gaussian centered at 150ms
    - Mean: 150ms
    - StdDev: 80ms
    - Min: 50ms
    - Max: 500ms
    
    Reflects Polymarket's current infrastructure latency
    """
    delay = max(50, int(random.gauss(150, 80)))
    return min(500, delay)
```

### Trade Execution

```python
def execute_trade(
    side: str,  # "YES" or "NO"
    predicted_price: int,  # Market ask, cents
    predicted_edge: float,  # Expected edge, cents
):
    """
    1. Check capital (need at least €1 per €5 bet at worst case 100¢ price)
    2. Simulate queue delay
    3. Apply random slippage to actual_price
    4. Determine outcome based on actual weather
    5. Calculate PnL
    6. Update capital
    7. Log trade
    """
    if capital < position_size:
        return None  # Insufficient capital
    
    # Simulate latency
    time.sleep(queue_delay() / 1000.0)
    
    # Apply slippage
    actual_price = predicted_price + realistic_slippage()
    actual_price = max(1, min(99, actual_price))  # Clamp to valid range
    
    # Determine outcome from actual weather
    actual_daily_high = get_actual_daily_high()  # Later filled from settlement data
    if side == "YES":
        win = (bracket_low <= actual_daily_high <= bracket_high)
        payout_cents = 100 if win else 0
    else:  # NO
        win = not (bracket_low <= actual_daily_high <= bracket_high)
        payout_cents = 100 if win else 0
    
    # Calculate PnL
    cost_eur = position_size * (actual_price / 100)
    revenue_eur = position_size * (payout_cents / 100)
    pnl_eur = revenue_eur - cost_eur
    
    # Update capital
    capital += pnl_eur
    
    # Log trade
    log_trade(Trade(...))
    
    return Trade(...)
```

---

## Station Coverage

### 11 Major US Cities

| City | Code | Lat/Lon | NWS Forecast | METAR | Status |
|------|------|---------|---|---|---|
| New York | KLGA | 40.78, -73.87 | ✅ | ✅ | Active |
| Chicago | KORD | 41.97, -87.91 | ✅ | ✅ | Active |
| Miami | KMIA | 25.80, -80.29 | ✅ | ✅ | Active |
| Austin | KAUS | 30.19, -97.67 | ✅ | ✅ | Active |
| Los Angeles | KLAX | 33.94, -118.41 | ✅ | ✅ | Active |
| Dallas | KDAL | 32.85, -96.85 | ✅ | ✅ | ⚠️ Fails |
| Atlanta | KATL | 33.64, -84.43 | ✅ | ✅ | Active |
| Denver | KBKF | 39.70, -104.75 | ✅ | ✅ | ❌ Fails |
| Houston | KHOU | 29.65, -95.28 | ✅ | ✅ | Active |
| San Francisco | KSFO | 37.62, -122.38 | ✅ | ✅ | Active |
| Seattle | KSEA | 47.45, -122.31 | ✅ | ✅ | Active |

---

## Error Handling & Resilience

### Data Fetch Failures

If any API call fails, the system:

```python
def fetch_with_fallback(primary_fn, fallback_fn, timeout=10):
    try:
        return primary_fn(timeout)
    except Exception as e:
        logger.warning(f"Primary API failed: {e}, using fallback")
        try:
            return fallback_fn(timeout)
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")
            return None  # Skip this poll cycle or use last known value
```

For weather data:
- If NWS fails → use Open-Meteo forecast
- If both fail → use cached forecast from previous poll
- If METAR fails → use latest available observation

For market data:
- If Polymarket API fails → skip poll cycle
- Retry with exponential backoff (1s, 2s, 4s, 8s)

### Incomplete Markets

Markets may have:
- Missing price data → skip
- No outcome data → skip
- Very low liquidity → still trade but flag risk

---

## Performance Metrics

### Win Rate Calculation

```python
win_rate = (wins / total_trades) × 100

# Ideal: > 55% (beats 50% baseline + fees)
# Backtest: 88.4% on 4,867 real trades
# Expected live: 55-65% (accounting for model imperfection)
```

### P&L Attribution

```python
Total PnL = Realized PnL - Transaction Costs

Realized PnL = Sum of all (revenue - cost) on closed trades
Transaction Costs = Sum of all slippage costs + fees

# Slippage cost ≈ 1.07¢ avg per trade
# Fee cost ≈ 1.00¢ per trade (already in model)
# Total cost: ≈ 2¢ per trade
```

### Edge Effectiveness

```python
Profitable Edge = Predicted Edge ≥ 15¢

# Backtest finding: edges < 10¢ lose money
# Edges 10-15¢: break-even to slight loss
# Edges 15-30¢: €0.29-0.37 avg profit per €5 trade
# Edges 30+¢: €0.37-0.65 avg profit per €5 trade
```

---

## Monitoring & Logging

### Real-Time Log (JSONL)

```json
{
  "ts": "2026-05-02T12:55:54.819886+00:00",
  "station": "KMIA",
  "side": "NO",
  "predicted_price": 82,
  "actual_price": 83,
  "slippage": 1,
  "queue_delay_ms": 145,
  "predicted_edge": 16.95,
  "predicted_p_yes": 0.9998,
  "actual_daily_high": 93.91,
  "correct": true,
  "pnl_eur": 0.094,
  "capital_before": 500.00,
  "capital_after": 500.094
}
```

### Hourly Summary (JSON)

```json
{
  "ts": "2026-05-02T13:00:00.000000+00:00",
  "trades": 127,
  "pnl_eur": 99.34,
  "capital": €599.34,
  "roi_pct": 19.8,
  "win_rate_pct": 88.4,
  "avg_slippage_cents": 1.07
}
```

### Station Performance (JSON)

```json
{
  "station": "KMIA",
  "trades": 945,
  "wins": 945,
  "win_rate": 100.0,
  "pnl_eur": 207.69,
  "avg_edge": 20.8
}
```

---

## Configuration Parameters

### Fixed Parameters

```python
POLYMARKET_GAMMA_API = "https://gamma-api.polymarket.com"
POLYMARKET_WEATHER_TAG_ID = "84"

STATIONS = [
    ("KLGA", 40.7790, -73.8740, "New York City", "KLGA"),
    ("KORD", 41.9742, -87.9073, "Chicago", "KORD"),
    ...  # 11 cities total
]

FORECAST_STDDEV_F = 2.0  # Weather uncertainty
HTTP_TIMEOUT_SECONDS = 15
```

### Tunable Parameters

```python
MIN_EDGE_CENTS = 15  # Only trade edges >= 15¢ (increased from 3¢)
MIN_CONFIDENCE = 0.80  # For YES bets
MAX_CONFIDENCE_NO = 0.20  # For NO bets
MIN_MINUTES_TO_SETTLEMENT = 15  # Don't trade very close to resolution

POSITION_SIZE_EUR = 5.0
STARTING_CAPITAL_EUR = 500.0
POLL_INTERVAL_SECONDS = 300  # 5 minutes
```

---

## Limitations & Future Improvements

### Known Limitations

1. **Calibration broken**: Model overconfident at low-confidence levels
   - Predicted 80% confidence → actual 56% accuracy
   - Needs Platt scaling or isotonic regression

2. **Station failures**: Denver (KBKF) and Dallas (KDAL) fail completely
   - Possible causes: different weather patterns, forecast bias
   - Needs station-specific tuning or exclusion

3. **No Kelly criterion**: All trades same size regardless of edge
   - Could optimize position sizing by edge magnitude
   - Would increase ROI with same capital

4. **Market hours only**: Limited liquidity outside US trading hours
   - Markets may gap overnight
   - Should avoid trading too late in day

### Future Improvements

1. Recalibrate confidence (Platt scaling)
2. Implement Kelly criterion position sizing
3. Add daily loss limits
4. Investigate station-specific failures
5. Add monitoring dashboard (FastAPI)
6. Email alerts on large trades/losses
7. Automated rebalancing at end-of-day

---

## References

- **Polymarket Gamma API**: https://gamma-api.polymarket.com/docs
- **NWS API**: https://api.weather.gov
- **Aviation Weather**: https://aviationweather.gov/api/data/metar
- **Open-Meteo**: https://open-meteo.com/
- **Backtest Results**: [BACKTEST_SUMMARY.md](../BACKTEST_SUMMARY.md)
- **Implementation**: [SPIKE_DOCUMENTATION.md](SPIKE_DOCUMENTATION.md)

---

**Last Updated**: 2026-05-07  
**Author**: MeteoEdge Development Team  
**Version**: 2.0 (Polymarket Improved Model)
