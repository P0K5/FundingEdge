"""Read-only Binance API wrapper. Spike-scoped: no signing needed for public endpoints."""
import httpx
from config import HTTP_TIMEOUT_SECONDS, USER_AGENT

SPOT_BASE = "https://api.binance.com"
FUTURES_BASE = "https://fapi.binance.com"


def _get(url: str, params: dict | None = None) -> dict | list:
    r = httpx.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()


def get_spot_book_ticker(symbol: str) -> dict:
    """Best bid/ask + sizes for spot."""
    return _get(f"{SPOT_BASE}/api/v3/ticker/bookTicker", {"symbol": symbol})


def get_perp_book_ticker(symbol: str) -> dict:
    """Best bid/ask + sizes for USDⓈ-M perp."""
    return _get(f"{FUTURES_BASE}/fapi/v1/ticker/bookTicker", {"symbol": symbol})


def get_premium_index(symbol: str) -> dict:
    """Mark price, index price, last funding rate, predicted next rate, funding time."""
    return _get(f"{FUTURES_BASE}/fapi/v1/premiumIndex", {"symbol": symbol})


def get_funding_history(symbol: str, start_ms: int, end_ms: int, limit: int = 1000) -> list[dict]:
    """Historical realised funding rates — used for persistence score."""
    params = {"symbol": symbol, "startTime": start_ms, "endTime": end_ms, "limit": limit}
    return _get(f"{FUTURES_BASE}/fapi/v1/fundingRate", params)
