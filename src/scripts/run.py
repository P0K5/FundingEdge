"""Main polling loop. Run during trading hours.

Usage:
    python src/scripts/run.py --paper         # paper trading mode (default)
    python src/scripts/run.py --paper --once  # single poll then exit
"""
import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from src.config import (
    STATIONS, STATION_TZ, POLL_INTERVAL_SECONDS, LOG_DIR,
    CANDIDATES_CSV, SNAPSHOTS_JSONL,
    RISK_DAILY_LOSS_LIMIT_EUR, RISK_MAX_OPEN_POSITIONS,
    RISK_DRAWDOWN_STOP_PCT, RISK_MIN_LIQUIDITY, STARTING_CAPITAL_EUR,
)
from src.data.metar import fetch_all_metars_today, compute_daily_high, now_local, sunset_local
from src.data.nws import fetch_nws_forecast_high
from src.data.open_meteo import fetch_secondary_forecast
from src.data.polymarket import get_weather_markets
from src.model.envelope import WeatherState
from src.risk.manager import RiskManager
from src.strategy.scanner import scan_markets


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def _append_snapshot(snap: dict) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    with open(SNAPSHOTS_JSONL, "a") as f:
        f.write(json.dumps(snap, default=str) + "\n")


def _append_candidate(row: dict) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    new_file = not CANDIDATES_CSV.exists()
    with open(CANDIDATES_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new_file:
            w.writeheader()
        w.writerow(row)


# ---------------------------------------------------------------------------
# Poll loop
# ---------------------------------------------------------------------------

def poll_once(risk_manager) -> None:
    """Run one full poll: build weather states, fetch markets, scan, log candidates."""
    ts = datetime.now(timezone.utc).isoformat()
    print(f"\n=== Poll at {ts} ===")

    # 1. Build weather state for each station
    weather: dict[str, WeatherState] = {}
    for station, lat, lon, city, _ in STATIONS:
        metars = fetch_all_metars_today(station)
        if not metars:
            print(f"[{station}] no METAR data, skipping")
            continue

        result = compute_daily_high(metars, STATION_TZ[station])
        if not result:
            print(f"[{station}] could not compute daily high, skipping")
            continue
        high_f, high_time = result

        latest = metars[0]
        latest_temp_c = latest.get("temp")
        if latest_temp_c is None:
            print(f"[{station}] latest METAR missing temp, skipping")
            continue

        obs_str = latest.get("reportTime") or latest.get("obsTime")
        if not obs_str:
            print(f"[{station}] latest METAR missing time, skipping")
            continue

        try:
            from dateutil import parser as dtparse
            latest_temp_f = (float(latest_temp_c) * 9 / 5) + 32
            latest_time = dtparse.parse(obs_str)
            if latest_time.tzinfo is None:
                latest_time = latest_time.replace(tzinfo=timezone.utc)
        except Exception as e:
            print(f"[{station}] METAR parse error: {e}, skipping")
            continue

        forecast_nws = fetch_nws_forecast_high(lat, lon)
        forecast_secondary = fetch_secondary_forecast(lat, lon)

        weather[station] = WeatherState(
            station=station,
            now_local=now_local(station),
            sunset_local=sunset_local(station, lat, lon),
            current_high_f=high_f,
            current_high_time=high_time,
            latest_temp_f=latest_temp_f,
            latest_temp_time=latest_time,
            forecast_high_f=forecast_nws,
            secondary_forecast_f=forecast_secondary,
        )
        print(f"[{station}] high={high_f:.1f}°F latest={latest_temp_f:.1f}°F nws={forecast_nws}")

    if not weather:
        print("[run] No weather data for any station — skipping market scan")
        return

    # 2. Fetch Polymarket markets
    try:
        markets = get_weather_markets()
    except Exception as e:
        print(f"[polymarket] error: {e} — skipping this poll")
        return
    print(f"[polymarket] {len(markets)} weather markets fetched")

    # 3. Scan for candidates
    candidates, snapshots = scan_markets(weather, markets)

    # 4. Log all snapshots
    for snap in snapshots:
        _append_snapshot(snap)

    # 5. Process candidates
    n_flagged = 0
    for cand in candidates:
        liquidity = cand.bracket.yes_ask_size + cand.bracket.no_ask_size
        allowed, reason = risk_manager.allow_trade(
            capital=STARTING_CAPITAL_EUR,
            liquidity_contracts=liquidity,
        )
        if not allowed:
            print(f"  [risk] blocked: {reason}")
            continue

        risk_manager.open_position()

        n_flagged += 1
        row = {
            "ts": ts,
            "station": cand.station,
            "ticker": cand.bracket.ticker,
            "bracket_low": cand.bracket.low_f,
            "bracket_high": cand.bracket.high_f,
            "yes_ask": cand.bracket.yes_ask_cents,
            "no_ask": cand.bracket.no_ask_cents,
            "p_yes": round(cand.p_yes, 4),
            "ev_yes": round(cand.ev_yes, 2),
            "ev_no": round(cand.ev_no, 2),
            "flagged_side": cand.side,
            "flagged_edge": round(cand.edge_cents, 2),
            "flagged_price": cand.price_cents,
            "flagged_confidence": round(cand.confidence, 4),
            "minutes_to_settlement": round(cand.minutes_to_settlement, 1),
        }
        _append_candidate(row)
        risk_manager.close_position()
        risk_manager.record_pnl(0.0)

    print(
        f"[scan] {len(markets)} markets, {len(snapshots)} evaluated, "
        f"{len(candidates)} candidates, {n_flagged} logged"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="MeteoEdge polling loop")
    parser.add_argument(
        "--paper", action="store_true", default=True,
        help="Paper trading mode (default; no real orders placed)",
    )
    parser.add_argument(
        "--once", action="store_true", default=False,
        help="Run a single poll then exit (for testing)",
    )
    parser.add_argument(
        "--live", action="store_true", default=False,
        help="LIVE trading mode — NOT YET IMPLEMENTED (see E3-2)",
    )
    args = parser.parse_args()

    if args.live:
        raise NotImplementedError(
            "Live trading not yet implemented — see Epic 3, issue E3-2. "
            "Run with --paper for paper trading."
        )

    mode = "PAPER" if args.paper else "LIVE"
    print(f"MeteoEdge starting in {mode} mode.")
    print("Logs will be written to ./logs/")

    risk_manager = RiskManager(
        daily_loss_limit_eur=RISK_DAILY_LOSS_LIMIT_EUR,
        max_open_positions=RISK_MAX_OPEN_POSITIONS,
        drawdown_stop_pct=RISK_DRAWDOWN_STOP_PCT,
        min_market_liquidity=RISK_MIN_LIQUIDITY,
        starting_capital=STARTING_CAPITAL_EUR,
    )

    if args.once:
        poll_once(risk_manager)
        print("[run] --once mode: exiting after single poll.")
        return

    print(f"Polling every {POLL_INTERVAL_SECONDS}s. Press Ctrl-C to stop.")
    while True:
        try:
            poll_once(risk_manager)
        except KeyboardInterrupt:
            print("\n[run] Stopping.")
            break
        except Exception as e:
            print(f"[run] Unhandled error in poll: {e}")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
