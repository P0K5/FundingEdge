"""Summarize hit rate, net yield, and per-symbol attribution after N days."""
import csv
import statistics
from collections import defaultdict
from config import CYCLES_CSV


def main() -> None:
    if not CYCLES_CSV.exists():
        print("No cycles logged yet. Run spike.py first.")
        return

    rows = list(csv.DictReader(open(CYCLES_CSV)))
    n = len(rows)
    if n == 0:
        print("Zero closed cycles.")
        return

    wins = sum(1 for r in rows if float(r["net_pnl_usd"]) > 0)
    win_rate = wins / n
    net_pnl = [float(r["net_pnl_usd"]) for r in rows]
    net_bps = [float(r["net_bps"]) for r in rows]
    total_pnl = sum(net_pnl)
    median_bps = statistics.median(net_bps)
    mean_bps = statistics.mean(net_bps)
    stdev_bps = statistics.pstdev(net_bps) if n > 1 else 0.0

    by_symbol = defaultdict(list)
    for r in rows:
        by_symbol[r["symbol"]].append(r)

    print("\n=== FundingEdge Spike Report ===")
    print(f"Closed virtual cycles: {n}")
    print(f"Wins: {wins}  Win rate: {win_rate:.2%}")
    print(f"Total net P&L (USD): {total_pnl:+.2f}")
    print(f"Median net yield per cycle: {median_bps:+.2f} bps")
    print(f"Mean net yield per cycle:   {mean_bps:+.2f} bps (stdev {stdev_bps:.2f})")
    print("\nBy symbol:")
    for symbol, items in sorted(by_symbol.items()):
        w = sum(1 for r in items if float(r["net_pnl_usd"]) > 0)
        avg_bps = statistics.mean(float(r["net_bps"]) for r in items)
        print(f"  {symbol}: {len(items)} cycles, {w} wins ({w/len(items):.1%}), avg {avg_bps:+.2f} bps")

    print("\n" + "=" * 40)
    if n >= 30 and win_rate >= 0.60 and median_bps > 0:
        print(f"GREEN LIGHT: {win_rate:.2%} win rate on {n} cycles, median {median_bps:+.2f} bps. Proceed to full build.")
    elif n >= 30 and win_rate >= 0.55:
        print(f"YELLOW: win rate {win_rate:.2%} is marginal. Run 1 more week. Investigate per-symbol patterns.")
    elif n < 30:
        print(f"INCONCLUSIVE: only {n} cycles. Run until n >= 30 before deciding.")
    else:
        print(f"RED LIGHT: win rate {win_rate:.2%} < 55% on {n} cycles. Do not proceed. Revisit spec.")


if __name__ == "__main__":
    main()
