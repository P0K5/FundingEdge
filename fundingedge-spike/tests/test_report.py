"""Unit tests for report.py — verifies report generation from cycles.csv.

Tests synthetic cycles.csv files with different scenarios: all wins (green light),
all losses (red light), mixed results (inconclusive), empty file, and missing file.
"""
import csv
import sys
import os
from pathlib import Path
import importlib

# Ensure the fundingedge-spike package root is on the path when running from
# the repo root (e.g. pytest fundingedge-spike/tests/...)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_cycles(path: Path, rows: list[dict]) -> None:
    """Write a synthetic cycles.csv to the given path."""
    if not rows:
        path.write_text("")
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _make_cycle(hedge_id: str, symbol: str, net_pnl_usd: float, net_bps: float) -> dict:
    """Build a minimal cycle record for testing."""
    return {
        "hedge_id": hedge_id,
        "symbol": symbol,
        "opened_at": "2026-01-01T00:00:00+00:00",
        "closed_at": "2026-01-04T00:00:00+00:00",
        "hold_hours": "72.0",
        "funding_events": "9",
        "accrued_funding_usd": "1.5",
        "basis_pnl_usd": "0.0",
        "fees_usd": "1.25",
        "net_pnl_usd": str(net_pnl_usd),
        "net_bps": str(net_bps),
        "entry_basis_bps": "2.0",
        "exit_basis_bps": "2.0",
        "entry_rate_bps": "3.0",
        "exit_rate_bps": "3.0",
        "reason": "target_hold_reached_72h",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_green_light(tmp_path, monkeypatch, capsys):
    """All wins (30 cycles, 100% win rate, positive median bps) → GREEN LIGHT."""
    cycles_file = tmp_path / "cycles.csv"
    rows = [_make_cycle(f"h{i}", "BTCUSDT", 1.0, 20.0) for i in range(30)]
    _write_cycles(cycles_file, rows)

    monkeypatch.setattr(config, "CYCLES_CSV", cycles_file)

    import report
    importlib.reload(report)
    report.main()
    out = capsys.readouterr().out

    assert "GREEN LIGHT" in out


def test_red_light(tmp_path, monkeypatch, capsys):
    """All losses (35 cycles, 0% win rate) → RED LIGHT."""
    cycles_file = tmp_path / "cycles.csv"
    rows = [_make_cycle(f"h{i}", "BTCUSDT", -1.0, -20.0) for i in range(35)]
    _write_cycles(cycles_file, rows)

    monkeypatch.setattr(config, "CYCLES_CSV", cycles_file)

    import report
    importlib.reload(report)
    report.main()
    out = capsys.readouterr().out

    assert "RED LIGHT" in out


def test_inconclusive(tmp_path, monkeypatch, capsys):
    """Mixed wins/losses with too few cycles (5 total) → INCONCLUSIVE."""
    cycles_file = tmp_path / "cycles.csv"
    rows = [
        _make_cycle("h0", "BTCUSDT", 1.0, 15.0),
        _make_cycle("h1", "BTCUSDT", -0.5, -10.0),
        _make_cycle("h2", "ETHUSDT", 0.8, 12.0),
        _make_cycle("h3", "ETHUSDT", -0.3, -5.0),
        _make_cycle("h4", "BTCUSDT", 2.0, 25.0),
    ]
    _write_cycles(cycles_file, rows)

    monkeypatch.setattr(config, "CYCLES_CSV", cycles_file)

    import report
    importlib.reload(report)
    report.main()
    out = capsys.readouterr().out

    assert "INCONCLUSIVE" in out


def test_empty_file(tmp_path, monkeypatch, capsys):
    """cycles.csv exists but has zero data rows → graceful handling."""
    cycles_file = tmp_path / "cycles.csv"
    _write_cycles(cycles_file, [])

    monkeypatch.setattr(config, "CYCLES_CSV", cycles_file)

    import report
    importlib.reload(report)
    report.main()
    out = capsys.readouterr().out

    assert "Zero closed cycles" in out


def test_missing_file(tmp_path, monkeypatch, capsys):
    """cycles.csv path does not exist → graceful handling."""
    cycles_file = tmp_path / "does_not_exist.csv"
    monkeypatch.setattr(config, "CYCLES_CSV", cycles_file)

    import report
    importlib.reload(report)
    report.main()
    out = capsys.readouterr().out

    assert "No cycles logged yet" in out
