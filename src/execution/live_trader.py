"""Live order execution via Polymarket CLOB."""
from typing import Literal

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, Side


class LiveTrader:
    def __init__(self, client: ClobClient):
        self.client = client

    def place_order(
        self,
        token_id: str,
        side: str,          # "YES" or "NO" — we always BUY the token
        price_cents: int,   # e.g. 72 → 0.72 USDC per contract
        size_usdc: float,   # e.g. 5.0 → spend up to €5 (denominated in USDC)
    ) -> str:
        """Place a GTC limit order. Returns order_id string."""
        price = round(price_cents / 100, 4)
        size = round(size_usdc / price, 2)  # contracts = USDC / price_per_contract
        args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=Side.BUY,  # Always BUY YES or NO tokens — never short
        )
        resp = self.client.create_and_post_order(args)
        order_id = resp.get("orderID") or resp.get("id")
        if not order_id:
            raise RuntimeError(f"Order placement failed: {resp}")
        return order_id

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Returns True if cancelled."""
        try:
            resp = self.client.cancel(order_id)
            return resp.get("canceled") == [order_id]
        except Exception as e:
            print(f"[live] cancel {order_id[:12]}… error: {e}")
            return False

    def check_fill(self, order_id: str) -> Literal["open", "filled", "cancelled"]:
        """Return current status of an order. Never raises."""
        try:
            order = self.client.get_order(order_id)
            status = (order.get("status") or "").lower()
            if status in ("matched", "filled"):
                return "filled"
            if status in ("cancelled", "canceled"):
                return "cancelled"
            return "open"
        except Exception as e:
            print(f"[live] check_fill {order_id[:12]}… error: {e}")
            return "open"  # Assume still open on error — will retry
