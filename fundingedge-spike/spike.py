"""Main polling loop + virtual hedge bookkeeping."""
import argparse
import sys
from binance_client import get_spot_book_ticker


def smoke_test() -> None:
    """Smoke test: fetch spot book ticker for BTCUSDT and exit cleanly."""
    try:
        result = get_spot_book_ticker("BTCUSDT")
        print(f"Spot book ticker for BTCUSDT: {result}")
        print("Smoke test passed.")
        sys.exit(0)
    except Exception as e:
        print(f"Smoke test failed: {e}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="FundingEdge spike: observe-only virtual hedge tracker")
    parser.add_argument("--smoke-test", action="store_true", help="Run smoke test (fetch data for 1 symbol and exit)")
    args = parser.parse_args()

    if args.smoke_test:
        smoke_test()
    else:
        print("Use --smoke-test to verify connectivity, or implement main() for the full loop")
        sys.exit(0)


if __name__ == "__main__":
    main()
