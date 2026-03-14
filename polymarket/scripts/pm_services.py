"""Polymarket service layer - market data and trading.

Self-contained module using:
- Gamma API (httpx) for market discovery
- CLOB API (py-clob-client) for trading
- Data API (httpx) for positions/trades

No daemon-specific dependencies.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("pm_services")

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

SortBy = Literal[
    "volume", "volume24hr", "liquidity", "startDate", "endDate", "createdAt", "updatedAt"
]


class Token(BaseModel):
    token_id: str = Field(alias="token_id")
    outcome: str
    price: float
    winner: bool | None = None

    class Config:
        populate_by_name = True


class Market(BaseModel):
    id: str = Field(alias="id")
    condition_id: str | None = Field(default=None, alias="conditionId")
    slug: str | None = None
    question: str
    description: str | None = None
    end_date_iso: str | None = Field(default=None, alias="endDate")
    expiration_date: str | None = Field(default=None, alias="expirationDate")
    resolution_date: str | None = Field(default=None, alias="resolutionDate")
    category: str | None = None
    group_slug: str | None = Field(default=None, alias="groupSlug")
    market_slug: str | None = Field(default=None, alias="marketSlug")
    tags: list[str] | None = None
    rules: str | None = Field(default=None, alias="rules")
    active: bool = True
    closed: bool = False
    archived: bool = False
    resolved: bool = False
    neg_risk: bool = Field(default=False, alias="negRisk")
    tokens: list[Token] | None = None
    outcomes: list[str] | None = None
    outcome_prices: list[float] | None = Field(default=None, alias="outcomePrices")
    clob_token_ids: list[str] | None = Field(default=None, alias="clobTokenIds")
    volume: float | None = None
    volume_24hr: float | None = Field(default=None, alias="volume24hr")
    liquidity: float | None = None
    volume_num: float | None = Field(default=None, alias="volumeNum")
    liquidity_num: float | None = Field(default=None, alias="liquidityNum")

    class Config:
        populate_by_name = True

    @field_validator("outcomes", mode="before")
    @classmethod
    def parse_outcomes(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

    @field_validator("outcome_prices", mode="before")
    @classmethod
    def parse_outcome_prices(cls, v):
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return [float(p) for p in parsed] if parsed else None
            except (json.JSONDecodeError, ValueError):
                return None
        elif isinstance(v, list):
            try:
                return [float(p) for p in v]
            except (ValueError, TypeError):
                return None
        return v

    @field_validator("clob_token_ids", mode="before")
    @classmethod
    def parse_clob_token_ids(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

    @property
    def yes_price(self) -> float | None:
        if self.tokens:
            for token in self.tokens:
                if token.outcome.lower() == "yes":
                    return token.price
        if self.outcomes and self.outcome_prices:
            for i, outcome in enumerate(self.outcomes):
                if outcome.lower() == "yes" and i < len(self.outcome_prices):
                    return self.outcome_prices[i]
        if self.outcome_prices and len(self.outcome_prices) >= 1:
            return self.outcome_prices[0]
        return None

    @property
    def end_date(self) -> datetime | None:
        date_str = self.end_date_iso or self.expiration_date or self.resolution_date
        if date_str:
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    def get_token_id(self, outcome: str) -> str | None:
        """Resolve an outcome name (Yes/No/etc.) to its CLOB token_id."""
        outcome_lower = outcome.strip().lower()
        if self.tokens:
            for token in self.tokens:
                if token.outcome.lower() == outcome_lower:
                    return token.token_id
        if self.outcomes and self.clob_token_ids:
            for i, o in enumerate(self.outcomes):
                if o.lower() == outcome_lower and i < len(self.clob_token_ids):
                    return self.clob_token_ids[i]
        return None


# ---------------------------------------------------------------------------
# API URLs
# ---------------------------------------------------------------------------
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"
DATA_API_URL = "https://data-api.polymarket.com"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class PMClient:

    def __init__(
        self,
        timeout: int = 30,
        private_key: str = "",
        funder_address: str = "",
    ):
        self.timeout = timeout
        self._http: httpx.AsyncClient | None = None
        self._clob = None
        self._wallet_address: str = funder_address
        if private_key and funder_address:
            self._init_clob(private_key, funder_address)

    def _init_clob(self, private_key: str, funder_address: str) -> None:
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.constants import POLYGON

            self._clob = ClobClient(
                host=CLOB_API_URL,
                key=private_key,
                chain_id=POLYGON,
                funder=funder_address,
                signature_type=0,  # EOA wallet
            )
            creds = self._clob.create_or_derive_api_creds()
            self._clob.set_api_creds(creds)

            from eth_account import Account
            self._wallet_address = Account.from_key(private_key).address
            logger.info(f"CLOB client initialized for {self._wallet_address}")
        except Exception as e:
            logger.error(f"Failed to initialize CLOB client: {e}")
            self._clob = None

    @property
    def has_trading(self) -> bool:
        return self._clob is not None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self.timeout)
        return self._http

    async def close(self):
        if self._http:
            await self._http.aclose()
            self._http = None

    async def _get(self, url: str, params: dict | None = None) -> Any:
        resp = await self.http.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    # -- Gamma API (market discovery) --

    async def get_markets(
        self, limit: int = 100, active: bool = True, tag: str | None = None,
        sort_by: SortBy | None = None, ascending: bool = False,
        min_liquidity: float | None = None, min_volume: float | None = None,
    ) -> list[Market]:
        params: dict[str, Any] = {"limit": limit * 3, "active": active, "closed": False}
        if tag:
            params["tag"] = tag
        if sort_by:
            params["order"] = sort_by
            params["ascending"] = ascending
        data = await self._get(f"{GAMMA_API_URL}/markets", params)
        markets = []
        for item in data if isinstance(data, list) else data.get("data", []):
            try:
                m = Market.model_validate(item)
                if m.yes_price is None:
                    continue
                if min_liquidity and (m.liquidity_num or m.liquidity or 0) < min_liquidity:
                    continue
                if min_volume and (m.volume or m.volume_num or 0) < min_volume:
                    continue
                markets.append(m)
                if len(markets) >= limit:
                    break
            except Exception:
                continue
        return markets

    async def search_markets(self, query: str, limit: int = 20, sort_by: SortBy | None = "volume") -> list[Market]:
        params: dict[str, Any] = {"query": query, "limit": limit * 3, "active": True, "closed": False}
        if sort_by:
            params["order"] = sort_by
            params["ascending"] = False
        data = await self._get(f"{GAMMA_API_URL}/markets", params)
        markets = []
        for item in data if isinstance(data, list) else data.get("data", []):
            try:
                m = Market.model_validate(item)
                if m.closed or m.archived or m.yes_price is None:
                    continue
                markets.append(m)
                if len(markets) >= limit:
                    break
            except Exception:
                continue
        return markets

    async def get_events(self, query: str | None = None, limit: int = 20, tag: str | None = None) -> list[dict]:
        """Search events via Gamma API. Returns raw event dicts with nested markets."""
        params: dict[str, Any] = {"limit": limit, "active": True, "closed": False}
        if query:
            params["query"] = query
        if tag:
            params["tag"] = tag
        params["order"] = "volume24hr"
        params["ascending"] = False
        data = await self._get(f"{GAMMA_API_URL}/events", params)
        return data if isinstance(data, list) else data.get("data", [])

    async def get_trending(self, limit: int = 20) -> list[Market]:
        markets = await self.get_markets(limit=limit * 3, active=True)
        def vol(m: Market) -> float:
            return m.volume_24hr or m.volume_num or m.volume or 0
        with_vol = [m for m in markets if vol(m) > 0]
        with_vol.sort(key=vol, reverse=True)
        return with_vol[:limit]

    async def get_high_volume(self, limit: int = 20) -> list[Market]:
        return await self.get_markets(limit=limit, sort_by="volume", min_volume=100000)

    async def get_ending_soon(self, limit: int = 20, min_volume: float = 50000) -> list[Market]:
        return await self.get_markets(limit=limit, sort_by="endDate", ascending=True, min_volume=min_volume)

    async def get_high_liquidity(self, limit: int = 20, min_liquidity: float = 50000) -> list[Market]:
        return await self.get_markets(limit=limit, sort_by="liquidity", min_liquidity=min_liquidity)

    async def get_recently_updated(self, limit: int = 20) -> list[Market]:
        return await self.get_markets(limit=limit, sort_by="updatedAt")

    # -- CLOB API (prices, orderbook) --

    def get_orderbook(self, token_id: str) -> dict:
        """Get order book for a token from CLOB (no auth needed)."""
        from py_clob_client.client import ClobClient
        read_client = ClobClient(host=CLOB_API_URL)
        book = read_client.get_order_book(token_id)
        if isinstance(book, dict):
            return book
        return {"bids": [], "asks": []}

    def get_midpoint(self, token_id: str) -> float | None:
        """Get midpoint price from CLOB."""
        from py_clob_client.client import ClobClient
        read_client = ClobClient(host=CLOB_API_URL)
        mid = read_client.get_midpoint(token_id)
        try:
            return float(mid) if mid else None
        except (ValueError, TypeError):
            return None

    def get_spread(self, token_id: str) -> dict | None:
        """Get bid-ask spread from CLOB."""
        from py_clob_client.client import ClobClient
        read_client = ClobClient(host=CLOB_API_URL)
        spread = read_client.get_spread(token_id)
        return spread if isinstance(spread, dict) else None

    def get_tick_size(self, token_id: str) -> float:
        """Get minimum price increment for a token."""
        from py_clob_client.client import ClobClient
        read_client = ClobClient(host=CLOB_API_URL)
        try:
            tick = read_client.get_tick_size(token_id)
            return float(tick) if tick else 0.01
        except Exception:
            return 0.01

    # -- Data API (positions, trades) --

    async def get_positions(self) -> list[dict]:
        """Get current positions from Data API."""
        if not self._wallet_address:
            return []
        try:
            data = await self._get(
                f"{DATA_API_URL}/positions",
                params={"user": self._wallet_address.lower(), "sizeThreshold": "0.01"},
            )
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    async def get_trades(self, limit: int = 50) -> list[dict]:
        """Get recent trades from Data API."""
        if not self._wallet_address:
            return []
        try:
            data = await self._get(
                f"{DATA_API_URL}/trades",
                params={"user": self._wallet_address.lower(), "limit": limit},
            )
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return []

    # -- CLOB Trading --

    def _require_trading(self) -> None:
        if not self.has_trading:
            raise RuntimeError(
                "Polymarket trading not configured. "
                "Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS."
            )

    def _round_to_tick(self, price: float, tick_size: float) -> float:
        """Round price to nearest valid tick."""
        if tick_size <= 0:
            tick_size = 0.01
        return round(round(price / tick_size) * tick_size, 4)

    def buy(self, token_id: str, price: float, size: float, neg_risk: bool = False) -> str:
        """Place a limit buy order (GTC). Returns order_id."""
        from py_clob_client.clob_types import OrderArgs
        from py_clob_client.order_builder.constants import BUY
        return self._place_order(token_id, price, size, BUY, neg_risk)

    def sell(self, token_id: str, price: float, size: float, neg_risk: bool = False) -> str:
        """Place a limit sell order (GTC). Returns order_id."""
        from py_clob_client.clob_types import OrderArgs
        from py_clob_client.order_builder.constants import SELL
        return self._place_order(token_id, price, size, SELL, neg_risk)

    def market_buy(self, token_id: str, amount_usd: float, neg_risk: bool = False) -> str:
        """Place a market buy order (FOK). Spends amount_usd. Returns order_id."""
        from py_clob_client.clob_types import MarketOrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY
        self._require_trading()
        args = MarketOrderArgs(token_id=token_id, amount=amount_usd)
        signed = self._clob.create_market_order(args)
        resp = self._clob.post_order(signed, OrderType.FOK)
        return self._extract_order_id(resp)

    def _place_order(self, token_id: str, price: float, size: float, side: str, neg_risk: bool) -> str:
        from py_clob_client.clob_types import OrderArgs, OrderType

        self._require_trading()

        # Validate and round price to tick size
        tick = self.get_tick_size(token_id)
        price = self._round_to_tick(price, tick)
        size = math.floor(size * 100) / 100

        if size <= 0:
            raise ValueError("Size must be > 0 after rounding")
        if not (0.01 <= price <= 0.99):
            raise ValueError(f"Price {price} out of range (0.01-0.99)")

        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=side,
        )

        signed_order = self._clob.create_order(order_args)
        try:
            resp = self._clob.post_order(signed_order, OrderType.GTC)
        except Exception as e:
            error_msg = str(e)
            if "allowance" in error_msg.lower() or "insufficient" in error_msg.lower():
                from py_clob_client.clob_types import AssetType, BalanceAllowanceParams
                asset_type = AssetType.NEG_RISK if neg_risk else AssetType.CONDITIONAL
                self._clob.update_balance_allowance(BalanceAllowanceParams(asset_type=asset_type))
                resp = self._clob.post_order(signed_order, OrderType.GTC)
            else:
                raise

        return self._extract_order_id(resp)

    def _extract_order_id(self, resp: Any) -> str:
        if isinstance(resp, dict):
            order_id = resp.get("orderID") or resp.get("id", "")
            if not resp.get("success", True) and not order_id:
                raise RuntimeError(f"Order failed: {resp}")
            return order_id
        return str(resp)

    def cancel(self, order_id: str) -> bool:
        self._require_trading()
        try:
            resp = self._clob.cancel(order_id)
            if isinstance(resp, dict):
                return resp.get("canceled", False) or resp.get("success", False)
            return True
        except Exception as e:
            logger.error(f"Cancel failed for {order_id}: {e}")
            return False

    def cancel_all(self) -> int:
        self._require_trading()
        try:
            resp = self._clob.cancel_all()
            if isinstance(resp, dict):
                return resp.get("canceled", 0)
            return 0
        except Exception as e:
            logger.error(f"Cancel all failed: {e}")
            return 0

    def is_filled(self, order_id: str) -> dict[str, Any]:
        self._require_trading()
        try:
            order = self._clob.get_order(order_id)
            if isinstance(order, dict):
                status = order.get("status", "unknown")
                size_matched = float(order.get("size_matched", 0) or order.get("sizeMatched", 0))
                original_size = float(order.get("original_size", 0) or order.get("originalSize", 0))
                price = float(order.get("price", 0))
                return {
                    "order_id": order_id, "status": status,
                    "filled": status == "MATCHED",
                    "partially_filled": size_matched > 0 and status != "MATCHED",
                    "shares_matched": size_matched, "shares_total": original_size,
                    "price": price, "side": order.get("side", ""),
                }
            return {"order_id": order_id, "status": "unknown", "filled": False}
        except Exception as e:
            logger.error(f"Failed to check order {order_id}: {e}")
            return {"order_id": order_id, "status": "error", "filled": False, "error": str(e)}

    def get_open_orders(self) -> list[dict[str, Any]]:
        self._require_trading()
        try:
            orders = self._clob.get_orders()
            if not isinstance(orders, list):
                return []
            result = []
            for o in orders:
                if not isinstance(o, dict):
                    continue
                status = o.get("status", "")
                if status in ("LIVE", "ACTIVE", ""):
                    result.append({
                        "order_id": o.get("id") or o.get("orderID", ""),
                        "token_id": o.get("asset_id") or o.get("tokenID", ""),
                        "side": o.get("side", ""),
                        "price": float(o.get("price", 0)),
                        "size": float(o.get("original_size", 0) or o.get("originalSize", 0)),
                        "size_matched": float(o.get("size_matched", 0) or o.get("sizeMatched", 0)),
                        "status": status,
                    })
            return result
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    def get_usdc_balance(self) -> float:
        """Get USDC.e balance from CLOB (trading-ready balance)."""
        self._require_trading()
        try:
            raw = self._clob.get_balance()
            return float(raw) / 1_000_000 if raw else 0.0
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return 0.0
