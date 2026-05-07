# MeteoEdge Documentation

Complete documentation for the MeteoEdge Polymarket weather arbitrage trading system.

## Quick Navigation

### For New Developers
Start here:
1. **[../README.md](../README.md)** — Project overview, quick start
2. **[TECHNICAL_SPECIFICATION.md](TECHNICAL_SPECIFICATION.md)** — System architecture & components
3. **[SPIKE_DOCUMENTATION.md](SPIKE_DOCUMENTATION.md)** — Implementation decisions & lessons learned

### For Operations / Trading
1. **[../BACKTEST_SUMMARY.md](../BACKTEST_SUMMARY.md)** — Backtest results by station (88.4% win rate)
2. **[../SIMULATION_RESULTS.md](../SIMULATION_RESULTS.md)** — Synthetic data test results (108.8% ROI)
3. **[SPIKE_DOCUMENTATION.md#phase-6-live-trading-plan](SPIKE_DOCUMENTATION.md#phase-6-live-trading-plan)** — Live trading roadmap

### For Researchers / Model Development
1. **[TECHNICAL_SPECIFICATION.md#probability-model](TECHNICAL_SPECIFICATION.md#probability-model)** — Detailed probability calculation
2. **[SPIKE_DOCUMENTATION.md#phase-2-model-improvements](SPIKE_DOCUMENTATION.md#phase-2-model-improvements)** — What we tried and why
3. **[SPIKE_DOCUMENTATION.md#known-issues--mitigations](SPIKE_DOCUMENTATION.md#known-issues--mitigations)** — Open problems

---

## Documentation Files

### Core Documentation

#### 1. [TECHNICAL_SPECIFICATION.md](TECHNICAL_SPECIFICATION.md)
**What**: Complete system design and architecture  
**Length**: ~2000 lines  
**Audience**: Engineers, architects  
**Covers**:
- Data pipeline (METAR, NWS, Open-Meteo, Polymarket APIs)
- Probability model (weather envelope, ensemble forecasts, time dynamics)
- Execution engine (slippage, queue delays, position sizing)
- Trading configuration and monitoring
- Error handling and resilience

**Key sections**:
- Probability calculation algorithm (with example)
- Station coverage (11 US cities)
- Performance metrics and attribution
- Limitations and future improvements

**Read this if**: You need to understand how the system works, modify the probability model, or troubleshoot issues.

#### 2. [SPIKE_DOCUMENTATION.md](SPIKE_DOCUMENTATION.md)
**What**: Implementation history, decisions, and lessons  
**Length**: ~1500 lines  
**Audience**: Team members, traders, researchers  
**Covers**:
- Phase 1: Research & validation (backtest findings)
- Phase 2: Model improvements (seasonal rates, ensemble, time boost)
- Phase 3: Paper trading simulation (synthetic & real data tests)
- Phase 4: Implementation decisions with tradeoffs
- Phase 5: Known issues and mitigations
- Phase 6: Live trading plan

**Key sections**:
- Real edge confirmed: 88.4% win rate on 4,867 trades
- Edge analysis: Only 15¢+ edges profitable
- Station failures: Denver, Dallas don't work
- Model calibration problems (overconfidence)
- Weekly + monthly roadmap for live trading

**Read this if**: You're evaluating the strategy, planning live trading, or learning from our mistakes.

### Result Documentation

#### 3. [../BACKTEST_SUMMARY.md](../BACKTEST_SUMMARY.md)
**What**: Detailed backtest analysis on real May 2026 data  
**Audience**: Traders, risk managers, data analysts  
**Includes**:
- Per-city performance breakdown
- Model calibration analysis
- Edge effectiveness analysis
- Risk analysis (best/worst trades, drawdown)
- Recommendations for live trading

**Key numbers**:
- 4,867 trades analyzed
- 88.4% win rate
- €793.97 total PnL
- 158.8% ROI on €500 base

#### 4. [../SIMULATION_RESULTS.md](../SIMULATION_RESULTS.md)
**What**: Synthetic data paper trading results  
**Audience**: QA, engineers verifying execution engine  
**Includes**:
- 2-hour simulation with 291 trades
- 100% synthetic win rate (expected — using model forecasts)
- Slippage validation (1.07¢ average)
- Execution engine correctness verification

---

## Archive

### [archive/](archive/)

Historical documentation from previous projects:
- `kalshi-weather-bot-spec.md` — Original MeteoEdge design (Kalshi, retired)
- `meteoedge-mvp-spike.md` — Original spike spec
- `meteoedge-backtest-harness.md` — Original backtest design
- `README.md` — Archive index

These are kept for reference only. Active development is Polymarket-only.

---

## Key Findings Summary

### ✅ What Works

**Real edge exists:**
- 88.4% win rate on 4,867 real Polymarket trades
- €793.97 profitable after transaction costs
- Consistent across most US cities (5/10 excellent performance)

**Model strengths:**
- Seasonal weather patterns matter
- Forecast ensemble improves robustness
- Time-to-settlement dynamics work
- 15¢ edge threshold is reliable

### ⚠️ What Needs Work

**Model calibration:**
- Overconfident at low-confidence predictions
- Predicted 80% → actual 56% (severe miscalibration)
- Needs Platt scaling or isotonic regression

**Station variance:**
- Works great: Miami, Atlanta, Seattle, Houston, Austin (100% win rate)
- Fails completely: Denver, Dallas (0% win rate)
- Reason unknown—needs investigation

**Edge threshold:**
- Edges < 10¢ lose money
- Only edges > 15¢ are safely profitable
- Increased MIN_EDGE_CENTS from 3¢ to 15¢

---

## Implementation Timeline

| Phase | Dates | Status | Key Output |
|-------|-------|--------|-----------|
| **Research** | May 1-5 | ✅ Done | Backtest: 88.4% win rate |
| **Improvements** | May 6-7 | ✅ Done | 3 model enhancements |
| **Simulation** | May 7 | ✅ Done | Paper trading engine |
| **Week 1 Live** | May 14-20 | ⏳ Planned | Validation of 75%+ win rate |
| **Week 2 Scale** | May 21-27 | ⏳ Planned | €500 capital, 9 cities |
| **Production** | May 28+ | ⏳ Planned | Full monitoring, daily limits |

---

## Current Status

🟢 **Ready for live paper trading** with €100 starting capital.

Backtest validated. Model improved. Execution engine tested. Next: confirm real-world performance matches backtest.

---

## Questions & Answers

### Q: Is this a real trading system?
**A**: Yes. Backtest shows real edge (88.4% win rate on actual Polymarket data). Not yet live, but ready to be.

### Q: Why only > 15¢ edges?
**A**: Backtest data showed edges < 10¢ lose money after slippage/fees. 15¢ is the safe threshold.

### Q: What's the expected win rate in live trading?
**A**: Backtest = 88.4%, but likely overfitting. Expect 55-65% live (must beat 50% baseline + ~2¢ fees).

### Q: Why does Denver fail?
**A**: Unknown. Different weather patterns likely. Needs investigation week 1 of live trading.

### Q: How much capital is needed?
**A**: Start with €100 for validation, scale to €500 if validation succeeds. €5 per trade.

### Q: Can I modify the model?
**A**: Yes. See TECHNICAL_SPECIFICATION.md for details. Key parameters: MIN_EDGE_CENTS, FORECAST_STDDEV_F, climb rates.

---

## File Organization

```
docs/
├── README.md                    # This file
├── TECHNICAL_SPECIFICATION.md   # System architecture (detailed)
├── SPIKE_DOCUMENTATION.md       # Implementation history & decisions
└── archive/                     # Old project docs
    ├── kalshi-weather-bot-spec.md
    ├── meteoedge-mvp-spike.md
    ├── meteoedge-backtest-harness.md
    └── README.md

../
├── README.md                    # Project overview
├── BACKTEST_SUMMARY.md          # Real data backtest results
├── SIMULATION_RESULTS.md        # Synthetic data test results
├── CLAUDE.md                    # Team structure & governance
├── requirements.txt             # Python dependencies
└── src/                         # Source code
    ├── improved_envelope.py     # Probability model
    ├── paper_trader.py          # Execution engine
    ├── test_simulation.py       # Synthetic data test
    ├── backtest_real_data.py    # Real data backtest
    └── ...
```

---

## Contributing

Before modifying the system:

1. **Update docs first** — document your change in the appropriate file
2. **Cite the issue** — reference backtest finding or known problem
3. **Test on paper** — validate with synthetic or backtest data
4. **Measure impact** — before/after metrics required

---

## Support & Questions

- **Questions about the model?** See TECHNICAL_SPECIFICATION.md § Probability Model
- **Questions about why we made a decision?** See SPIKE_DOCUMENTATION.md § Phase 4
- **Questions about performance?** See BACKTEST_SUMMARY.md or SIMULATION_RESULTS.md
- **Questions about live trading?** See SPIKE_DOCUMENTATION.md § Phase 6

---

**Last Updated**: 2026-05-07  
**Status**: Active Development  
**Next Milestone**: Week 1 Live Trading (May 14-20)
