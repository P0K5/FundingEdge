"""Polymarket CLOB client initialisation.

Required env vars:
  POLYMARKET_API_KEY   — L1 wallet private key (hex string, no 0x prefix)
  POLYMARKET_CHAIN_ID  — 137 for Polygon mainnet, 80002 for Amoy testnet
  POLYMARKET_HOST      — https://clob.polymarket.com (default)
"""
import os

from py_clob_client.client import ClobClient


def get_clob_client() -> ClobClient:
    host = os.environ.get("POLYMARKET_HOST", "https://clob.polymarket.com")
    key = os.environ["POLYMARKET_API_KEY"]  # Raise if missing — fail fast
    chain_id = int(os.environ.get("POLYMARKET_CHAIN_ID", "137"))
    return ClobClient(host=host, key=key, chain_id=chain_id)


def check_clob_health() -> bool:
    """Return True if the CLOB API is reachable and auth is valid."""
    try:
        client = get_clob_client()
        resp = client.get_ok()
        return resp in (True, "OK") or (isinstance(resp, dict) and resp.get("status") == "OK")
    except Exception as e:
        print(f"[clob-health] {e}")
        return False
