"""HyperLiquid service layer — perps, spot, and transfers.

Self-contained module using hyperliquid-python-sdk and eth-account.
Supports read-only mode when no private key is provided.
"""

from __future__ import annotations

import logging
import math
import os
import secrets
import time
from typing import Any

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils.signing import (
    order_request_to_order_wire,
    order_wires_to_order_action,
    sign_l1_action,
)
from hyperliquid.utils.types import Cloid

MAINNET_API_URL = "https://api.hyperliquid.xyz"
DEFAULT_BUILDER_ADDRESS = "0x7f66d958f6018c45e6ccca0339731a808d976e63"
DEFAULT_BUILDER_FEE_BPS = 5

logger = logging.getLogger("hl_services")


# ---------------------------------------------------------------------------
# URL wrapper — keeps gateway URL but signs with mainnet chain ID
# ---------------------------------------------------------------------------
class _MainnetProxyUrl(str):
    def __eq__(self, other: object) -> bool:
        if str(other) == MAINNET_API_URL:
            return True
        return str.__eq__(self, other)

    def __hash__(self) -> int:
        return hash(MAINNET_API_URL)


# ---------------------------------------------------------------------------
# HyperLiquid service layer
# ---------------------------------------------------------------------------
class HLServices:
    """Thin wrapper around hyperliquid-python-sdk with read-only support."""

    def __init__(
        self,
        account_address: str,
        private_key: str | None = None,
        testnet: bool = False,
        builder_address: str | None = None,
        builder_fee_bps: int | None = None,
    ):
        self.account_address = account_address
        self.testnet = testnet
        self.read_only = private_key is None

        base_url = os.environ.get("HYPERLIQUID_BASE_URL") or MAINNET_API_URL
        self.read_url = base_url
        self.write_url = base_url

        self.info = Info(self.read_url, skip_ws=True)

        if not self.read_only:
            from eth_account import Account

            self.wallet = Account.from_key(private_key)
            exchange_url = (
                _MainnetProxyUrl(self.write_url)
                if not testnet and self.write_url != MAINNET_API_URL
                else self.write_url
            )
            self.exchange = Exchange(
                self.wallet, exchange_url, account_address=self.account_address
            )
        else:
            self.wallet = None
            self.exchange = None

        self.builder_address = builder_address or DEFAULT_BUILDER_ADDRESS
        self.builder_fee_bps = (
            builder_fee_bps if builder_fee_bps is not None else DEFAULT_BUILDER_FEE_BPS
        )

        # Caches
        self._meta_cache: dict[str, Any] = {"value": None, "ts": 0.0}
        self._mids_cache: dict[str, Any] = {"value": None, "ts": 0.0}
        self._user_state_cache: dict[str, Any] = {"value": None, "ts": 0.0}
        self._open_orders_cache: dict[str, Any] = {"value": None, "ts": 0.0}
        self._asset_cache: dict[str, Any] = {}
        self._asset_ctxs_cache: dict[str, Any] = {"value": None, "ts": 0.0}
        self._spot_meta_cache: dict[str, Any] = {"value": None, "ts": 0.0}
        self._abstraction_cache: dict[str, Any] = {"value": None, "ts": 0.0}

    # -- Read-only guard --

    def _require_signing(self) -> dict[str, Any] | None:
        if self.read_only:
            return {"success": False, "error": "Trading requires EVM_PRIVATE_KEY to be set"}
        return None

    # -- Caching helpers --

    def _now(self) -> float:
        return time.time()

    def _get_meta(self, ttl: float = 60.0):
        if self._meta_cache["value"] is not None and (self._now() - self._meta_cache["ts"]) < ttl:
            return self._meta_cache["value"]
        meta = self.info.meta()
        self._meta_cache = {"value": meta, "ts": self._now()}
        return meta

    def _get_meta_and_asset_ctxs(self, ttl: float = 5.0):
        if self._asset_ctxs_cache["value"] is not None and (self._now() - self._asset_ctxs_cache["ts"]) < ttl:
            return self._asset_ctxs_cache["value"]
        data = self.info.meta_and_asset_ctxs()
        self._asset_ctxs_cache = {"value": data, "ts": self._now()}
        return data

    def _get_spot_meta(self, ttl: float = 60.0):
        if self._spot_meta_cache["value"] is not None and (self._now() - self._spot_meta_cache["ts"]) < ttl:
            return self._spot_meta_cache["value"]
        data = self.info.spot_meta_and_asset_ctxs()
        self._spot_meta_cache = {"value": data, "ts": self._now()}
        return data

    def _get_abstraction_mode(self, ttl: float = 300.0) -> str:
        """Get account abstraction mode. Returns 'standard', 'unified', or 'portfolio'."""
        if not self.account_address:
            return "unknown"
        if self._abstraction_cache["value"] is not None and (self._now() - self._abstraction_cache["ts"]) < ttl:
            return self._abstraction_cache["value"]
        try:
            raw = self.info.query_user_abstraction_state(self.account_address)
            # raw is one of: "default", "i", "u", "p", "dexAbstraction"
            mode_map = {
                "default": "unified",
                "i": "standard",
                "u": "unified",
                "p": "portfolio",
                "dexAbstraction": "standard",
                "disabled": "standard",
                "unifiedAccount": "unified",
                "portfolioMargin": "portfolio",
            }
            mode = mode_map.get(raw, "standard") if isinstance(raw, str) else "standard"
        except Exception:
            mode = "unknown"
        self._abstraction_cache = {"value": mode, "ts": self._now()}
        return mode

    def _is_unified(self) -> bool:
        """Check if account uses unified or portfolio margin."""
        return self._get_abstraction_mode() in ("unified", "portfolio")

    def _get_all_mids(self, ttl: float = 1.0):
        if self._mids_cache["value"] is not None and (self._now() - self._mids_cache["ts"]) < ttl:
            return self._mids_cache["value"]
        mids = self.info.all_mids()
        self._mids_cache = {"value": mids, "ts": self._now()}
        return mids

    def _get_user_state(self, ttl: float = 2.0):
        if (
            self._user_state_cache["value"] is not None
            and (self._now() - self._user_state_cache["ts"]) < ttl
        ):
            return self._user_state_cache["value"]
        state = self.info.user_state(self.account_address)
        self._user_state_cache = {"value": state, "ts": self._now()}
        return state

    def _get_open_orders_cached(self, ttl: float = 2.0):
        if (
            self._open_orders_cache["value"] is not None
            and (self._now() - self._open_orders_cache["ts"]) < ttl
        ):
            return self._open_orders_cache["value"]
        orders = self.info.open_orders(self.account_address)
        self._open_orders_cache = {"value": orders, "ts": self._now()}
        return orders

    def _invalidate_write_caches(self):
        self._user_state_cache = {"value": None, "ts": 0.0}
        self._open_orders_cache = {"value": None, "ts": 0.0}

    def _get_name_to_asset(self, coin: str):
        if coin in self._asset_cache:
            return self._asset_cache[coin]
        asset = self.info.name_to_asset(coin)
        self._asset_cache[coin] = asset
        return asset

    def _get_sz_decimals(self, coin: str) -> int:
        meta = self._get_meta()
        for asset in meta["universe"]:
            if asset["name"] == coin:
                return asset.get("szDecimals", 3)
        return 3

    def _get_builder_config(self) -> dict[str, Any] | None:
        if not self.builder_address or self.builder_fee_bps <= 0:
            return None
        fee_tenths = self.builder_fee_bps * 10
        return {"b": self.builder_address, "f": fee_tenths}

    def _new_cloid(self) -> Cloid:
        return Cloid(f"0x{secrets.token_hex(16)}")

    def _make_cloid(self, raw: str | None = None) -> Cloid | None:
        if raw is None:
            return None
        if raw.startswith("0x") and len(raw) == 34:
            try:
                int(raw[2:], 16)
                return Cloid(raw)
            except ValueError:
                pass
        return self._new_cloid()

    def _validate_exchange_response(self, response: Any, action: str) -> dict[str, Any] | None:
        if not isinstance(response, dict):
            return None
        if response.get("status") == "err":
            error_msg = response.get("response", "Unknown exchange error")
            return {"success": False, "error": f"Exchange rejected {action}: {error_msg}"}
        if response.get("status") == "ok":
            resp_data = response.get("response", {})
            if isinstance(resp_data, dict) and resp_data.get("type") == "order":
                statuses = resp_data.get("data", {}).get("statuses", [])
                errors = [s["error"] for s in statuses if isinstance(s, dict) and "error" in s]
                if errors:
                    return {"success": False, "error": f"Order failed: {'; '.join(errors)}"}
        return None

    # -- Price helpers --

    def _round_price(self, coin: str, price: float) -> float:
        """Round to HL's 5 significant figures."""
        if price <= 0:
            return price
        magnitude = math.floor(math.log10(abs(price)))
        sig_figs = 5
        factor = 10 ** (sig_figs - 1 - magnitude)
        return round(price * factor) / factor

    def _slippage_price(self, coin: str, is_buy: bool, slippage: float) -> float:
        mids = self._get_all_mids()
        mid = float(mids[coin])
        if is_buy:
            return self._round_price(coin, mid * (1 + slippage))
        return self._round_price(coin, mid * (1 - slippage))

    def _get_mid_price(self, coin: str) -> float:
        return float(self._get_all_mids()[coin])

    # -- Size helpers --

    def _resolve_size(self, coin: str, sz: float | None, usd: float | None, reference_price: float) -> float | None:
        """Resolve order size from sz or usd, rounding to szDecimals."""
        if sz is not None and sz > 0:
            sz_decimals = self._get_sz_decimals(coin)
            return round(sz, sz_decimals)
        if usd is not None and usd > 0 and reference_price > 0:
            raw = usd / reference_price
            sz_decimals = self._get_sz_decimals(coin)
            return round(raw, sz_decimals)
        return None

    def _resolve_limit_price(self, coin: str, is_buy: bool, limit_px: float | None, slippage: float) -> float:
        """Resolve limit price — use given price or compute from slippage."""
        if limit_px is not None:
            return self._round_price(coin, limit_px)
        slp = slippage if slippage != 0.0 else 0.05
        return self._slippage_price(coin, is_buy, slp)

    # -- Bulk orders with grouping --

    def _bulk_orders_with_grouping(self, order_requests, grouping="na", builder=None):
        order_wires = []
        for order in order_requests:
            wire = order_request_to_order_wire(order, self._get_name_to_asset(order["coin"]))
            order_wires.append(wire)

        timestamp = int(time.time() * 1000)
        order_action = order_wires_to_order_action(order_wires, None)
        order_action["grouping"] = grouping

        builder_config = builder if builder is not None else self._get_builder_config()
        if builder_config:
            builder_config["b"] = builder_config["b"].lower()
            order_action["builder"] = builder_config

        expires_after = self.exchange.expires_after
        signature = sign_l1_action(
            self.exchange.wallet,
            order_action,
            self.exchange.vault_address,
            timestamp,
            expires_after,
            not self.testnet,
        )
        result = self.exchange._post_action(order_action, signature, timestamp)
        self._invalidate_write_caches()
        return result

    # -----------------------------------------------------------------------
    # TRADING — Perps
    # -----------------------------------------------------------------------

    async def place_order(
        self,
        coin: str,
        is_buy: bool,
        sz: float | None = None,
        limit_px: float | None = None,
        order_type: dict | None = None,
        reduce_only: bool = False,
        cloid: str | None = None,
        tp_px: float | None = None,
        sl_px: float | None = None,
        usd: float | None = None,
        slippage: float = 0.0,
    ) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            side = "BUY" if is_buy else "SELL"
            is_market = limit_px is None and order_type is None

            # Resolve limit price
            if limit_px is not None:
                limit_px_final = self._round_price(coin, limit_px)
                if order_type is None:
                    order_type = {"limit": {"tif": "Gtc"}}
            elif is_market:
                # Market order — use best bid/ask or slippage
                if slippage != 0.0:
                    limit_px_final = self._slippage_price(coin, is_buy, slippage)
                else:
                    book = self.info.l2_snapshot(coin)
                    if is_buy:
                        best_ask = (
                            float(book["levels"][1][0]["px"])
                            if book and len(book.get("levels", [])) > 1 and book["levels"][1]
                            else self._get_mid_price(coin)
                        )
                        limit_px_final = self._round_price(coin, best_ask)
                    else:
                        best_bid = (
                            float(book["levels"][0][0]["px"])
                            if book and len(book.get("levels", [])) > 0 and book["levels"][0]
                            else self._get_mid_price(coin)
                        )
                        limit_px_final = self._round_price(coin, best_bid)
                order_type = {"limit": {"tif": "Ioc"}}
            else:
                limit_px_final = self._slippage_price(coin, is_buy, 0.05)

            if order_type is None:
                order_type = {"limit": {"tif": "Gtc"}}

            # Resolve size
            final_sz = self._resolve_size(coin, sz, usd, limit_px_final)
            if final_sz is None or final_sz <= 0:
                return {"success": False, "error": "Order size must be provided via --sz or --usd"}

            # Round TP/SL
            if tp_px is not None:
                tp_px = self._round_price(coin, float(tp_px))
            if sl_px is not None:
                sl_px = self._round_price(coin, float(sl_px))

            # Bracket order
            if tp_px is not None or sl_px is not None:
                return await self._place_bracket_order(
                    coin, is_buy, final_sz, limit_px_final, tp_px, sl_px, reduce_only, cloid
                )

            builder_config = self._get_builder_config()
            order_result = self.exchange.order(
                coin, is_buy, float(final_sz), float(limit_px_final), order_type,
                reduce_only, cloid=self._make_cloid(cloid), builder=builder_config,
            )
            self._invalidate_write_caches()

            error = self._validate_exchange_response(order_result, f"place {side} order for {coin}")
            if error:
                return error

            return {
                "success": True,
                "result": order_result,
                "details": {
                    "coin": coin, "side": side, "size": float(final_sz),
                    "limit_price": float(limit_px_final), "order_type": order_type,
                    "reduce_only": reduce_only,
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _place_bracket_order(
        self, coin, is_buy, sz, limit_px, tp_px, sl_px, reduce_only, cloid
    ) -> dict[str, Any]:
        try:
            order_requests = []
            entry_order = {
                "coin": coin, "is_buy": is_buy, "sz": float(sz),
                "limit_px": float(limit_px), "order_type": {"limit": {"tif": "Gtc"}},
                "reduce_only": reduce_only,
            }
            entry_cloid = self._make_cloid(cloid)
            if entry_cloid:
                entry_order["cloid"] = entry_cloid
            order_requests.append(entry_order)

            if tp_px is not None:
                tp_order = {
                    "coin": coin, "is_buy": not is_buy, "sz": float(sz),
                    "limit_px": float(tp_px),
                    "order_type": {"trigger": {"triggerPx": float(tp_px), "isMarket": False, "tpsl": "tp"}},
                    "reduce_only": True,
                }
                if entry_cloid:
                    tp_order["cloid"] = self._new_cloid()
                order_requests.append(tp_order)

            if sl_px is not None:
                sl_order = {
                    "coin": coin, "is_buy": not is_buy, "sz": float(sz),
                    "limit_px": float(sl_px),
                    "order_type": {"trigger": {"triggerPx": float(sl_px), "isMarket": True, "tpsl": "sl"}},
                    "reduce_only": True,
                }
                if entry_cloid:
                    sl_order["cloid"] = self._new_cloid()
                order_requests.append(sl_order)

            bulk_result = self._bulk_orders_with_grouping(order_requests, grouping="normalTpsl")
            error = self._validate_exchange_response(bulk_result, f"place bracket order for {coin}")
            if error:
                return error

            return {
                "success": True, "result": bulk_result,
                "details": {
                    "coin": coin, "side": "BUY" if is_buy else "SELL", "size": float(sz),
                    "entry_price": float(limit_px),
                    "take_profit_price": float(tp_px) if tp_px else None,
                    "stop_loss_price": float(sl_px) if sl_px else None,
                    "grouping": "normalTpsl",
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def market_open_position(
        self, coin: str, is_buy: bool, sz: float | None = None,
        usd: float | None = None, cloid: str | None = None,
    ) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            price = self._get_mid_price(coin)
            final_sz = self._resolve_size(coin, sz, usd, price)
            if final_sz is None or final_sz <= 0:
                return {"success": False, "error": "Size must be provided via --sz or --usd"}

            builder_config = self._get_builder_config()
            result = self.exchange.market_open(
                coin, is_buy, float(final_sz), cloid=self._make_cloid(cloid), builder=builder_config,
            )
            self._invalidate_write_caches()

            error = self._validate_exchange_response(result, f"market open {coin}")
            if error:
                return error

            return {
                "success": True, "result": result,
                "details": {"coin": coin, "side": "BUY" if is_buy else "SELL", "size": float(final_sz)},
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def market_close_position(
        self, coin: str, sz: float | None = None, slippage: float = 0.05,
    ) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            builder_config = self._get_builder_config()
            result = self.exchange.market_close(
                coin, sz=sz, slippage=slippage, builder=builder_config,
            )
            self._invalidate_write_caches()

            error = self._validate_exchange_response(result, f"market close {coin}")
            if error:
                return error

            return {"success": True, "result": result, "details": {"coin": coin, "closed_size": sz or "full"}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_position_tpsl(
        self, coin: str, tp_px: float | None = None, sl_px: float | None = None,
        position_size: float | None = None,
    ) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            user_state = self._get_user_state()
            positions = user_state.get("assetPositions", [])
            pos = None
            for p in positions:
                if p["position"]["coin"] == coin and p["position"]["szi"] != "0":
                    pos = p["position"]
                    break
            if pos is None:
                return {"success": False, "error": f"No open position for {coin}"}

            current_size = abs(float(pos["szi"]))
            is_long = float(pos["szi"]) > 0
            sz = float(position_size) if position_size else current_size

            if tp_px is not None:
                tp_px = self._round_price(coin, float(tp_px))
            if sl_px is not None:
                sl_px = self._round_price(coin, float(sl_px))

            order_requests = []
            if tp_px is not None:
                order_requests.append({
                    "coin": coin, "is_buy": not is_long, "sz": sz,
                    "limit_px": float(tp_px),
                    "order_type": {"trigger": {"triggerPx": float(tp_px), "isMarket": False, "tpsl": "tp"}},
                    "reduce_only": True,
                })
            if sl_px is not None:
                order_requests.append({
                    "coin": coin, "is_buy": not is_long, "sz": sz,
                    "limit_px": float(sl_px),
                    "order_type": {"trigger": {"triggerPx": float(sl_px), "isMarket": True, "tpsl": "sl"}},
                    "reduce_only": True,
                })

            if not order_requests:
                return {"success": False, "error": "Provide at least one of --tp-px or --sl-px"}

            result = self._bulk_orders_with_grouping(order_requests, grouping="positionTpsl")
            error = self._validate_exchange_response(result, f"set TP/SL for {coin}")
            if error:
                return error

            return {
                "success": True, "result": result,
                "details": {"coin": coin, "tp_px": tp_px, "sl_px": sl_px, "size": sz},
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def cancel_order(self, coin: str, oid: int) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            result = self.exchange.cancel(coin, oid)
            self._invalidate_write_caches()
            error = self._validate_exchange_response(result, f"cancel order {oid}")
            if error:
                return error
            return {"success": True, "result": result, "details": {"coin": coin, "oid": oid}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def cancel_all_orders(self, coin: str | None = None) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            open_orders = self._get_open_orders_cached()
            orders_to_cancel = (
                [o for o in open_orders if o["coin"] == coin] if coin else open_orders
            )
            if not orders_to_cancel:
                return {"success": True, "details": {"cancelled": 0, "failed": 0}}

            cancel_requests = [{"coin": o["coin"], "oid": o["oid"]} for o in orders_to_cancel]
            result = self.exchange.bulk_cancel(cancel_requests)
            self._invalidate_write_caches()

            error = self._validate_exchange_response(result, "bulk cancel orders")
            if error:
                return error

            statuses = (
                result.get("response", {}).get("data", {}).get("statuses", [])
                if isinstance(result.get("response"), dict) else []
            )
            failed = sum(1 for s in statuses if isinstance(s, dict) and "error" in s)
            return {"success": True, "result": result, "details": {"cancelled": len(cancel_requests) - failed, "failed": failed}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def modify_order(self, coin: str, oid: int, new_sz: float, new_limit_px: float) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            open_orders = self._get_open_orders_cached()
            matching = [o for o in open_orders if o["oid"] == oid]
            if not matching:
                return {"success": False, "error": f"Order {oid} not found"}
            is_buy = matching[0]["side"] == "B"

            result = self.exchange.modify_order(
                oid, coin, is_buy, float(new_sz), float(new_limit_px), {"limit": {"tif": "Gtc"}},
            )
            self._invalidate_write_caches()
            error = self._validate_exchange_response(result, f"modify order {oid}")
            if error:
                return error
            return {"success": True, "result": result, "details": {"oid": oid, "new_sz": new_sz, "new_limit_px": new_limit_px}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def update_leverage(self, coin: str, leverage: int, is_cross: bool = True) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            result = self.exchange.update_leverage(leverage, coin, is_cross)
            return {"success": True, "result": result, "details": {"coin": coin, "leverage": leverage, "mode": "cross" if is_cross else "isolated"}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -- TWAP --

    async def place_twap_order(
        self, coin: str, is_buy: bool, sz: float, minutes: int, randomize: bool = True,
    ) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            twap_action = {
                "type": "twapOrder",
                "twap": {
                    "a": self._get_name_to_asset(coin),
                    "b": is_buy,
                    "s": str(sz),
                    "r": randomize,
                    "m": minutes,
                    "t": False,
                },
            }
            timestamp = int(time.time() * 1000)
            signature = sign_l1_action(
                self.exchange.wallet,
                twap_action,
                self.exchange.vault_address,
                timestamp,
                self.exchange.expires_after,
                not self.testnet,
            )
            result = self.exchange._post_action(twap_action, signature, timestamp)
            error = self._validate_exchange_response(result, f"TWAP order for {coin}")
            if error:
                return error
            return {
                "success": True, "result": result,
                "details": {"coin": coin, "side": "BUY" if is_buy else "SELL", "size": sz, "minutes": minutes, "randomize": randomize},
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def cancel_twap(self, coin: str, twap_id: int) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            twap_action = {
                "type": "twapCancel",
                "a": self._get_name_to_asset(coin),
                "t": twap_id,
            }
            timestamp = int(time.time() * 1000)
            signature = sign_l1_action(
                self.exchange.wallet,
                twap_action,
                self.exchange.vault_address,
                timestamp,
                self.exchange.expires_after,
                not self.testnet,
            )
            result = self.exchange._post_action(twap_action, signature, timestamp)
            error = self._validate_exchange_response(result, f"cancel TWAP {twap_id}")
            if error:
                return error
            return {"success": True, "result": result, "details": {"twap_id": twap_id}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def schedule_cancel_all(self, timestamp_ms: int | None = None) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            result = self.exchange.schedule_cancel(timestamp_ms)
            if timestamp_ms is None:
                return {"success": True, "result": result, "details": {"action": "cleared"}}
            return {"success": True, "result": result, "details": {"action": "set", "cancel_at": timestamp_ms}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -----------------------------------------------------------------------
    # TRADING — Spot
    # -----------------------------------------------------------------------

    async def place_spot_order(
        self, coin: str, is_buy: bool, sz: float | None = None,
        limit_px: float | None = None, usd: float | None = None,
    ) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            # Spot uses TOKEN/USDC format for the SDK
            if "/" not in coin:
                coin = f"{coin}/USDC"

            mids = self._get_all_mids()
            # Try to find mid price for spot pair (SDK may use @-prefixed key)
            mid_key = None
            for k in mids:
                if k.upper() == coin.upper() or k == f"@{self._get_name_to_asset(coin.split('/')[0])}":
                    mid_key = k
                    break
            ref_price = float(mids[mid_key]) if mid_key else self._get_mid_price(coin.split("/")[0])

            if limit_px is not None:
                price = self._round_price(coin, limit_px)
                ot = {"limit": {"tif": "Gtc"}}
            else:
                slp = 0.05
                if is_buy:
                    price = self._round_price(coin, ref_price * (1 + slp))
                else:
                    price = self._round_price(coin, ref_price * (1 - slp))
                ot = {"limit": {"tif": "Ioc"}}

            final_sz = self._resolve_size(coin.split("/")[0], sz, usd, price)
            if final_sz is None or final_sz <= 0:
                return {"success": False, "error": "Size must be provided via --sz or --usd"}

            builder_config = self._get_builder_config()
            result = self.exchange.order(
                coin, is_buy, float(final_sz), float(price), ot,
                builder=builder_config,
            )
            self._invalidate_write_caches()
            error = self._validate_exchange_response(result, f"spot order {coin}")
            if error:
                return error

            return {
                "success": True, "result": result,
                "details": {"coin": coin, "side": "BUY" if is_buy else "SELL", "size": float(final_sz), "price": float(price)},
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -----------------------------------------------------------------------
    # TRANSFERS
    # -----------------------------------------------------------------------

    async def transfer_between_wallets(self, amount: float, to_perp: bool = True) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            result = self.exchange.usd_class_transfer(amount, to_perp)
            direction = "spot → perp" if to_perp else "perp → spot"
            return {"success": True, "result": result, "details": {"amount": amount, "direction": direction}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def send_usd(self, amount: float, destination: str) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            result = self.exchange.usd_transfer(amount, destination)
            return {"success": True, "result": result, "details": {"amount": amount, "to": destination}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def withdraw_to_evm(self, amount: float, destination: str) -> dict[str, Any]:
        if err := self._require_signing():
            return err
        try:
            result = self.exchange.withdraw_from_bridge(amount, destination)
            return {"success": True, "result": result, "details": {"amount": amount, "to": destination}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -----------------------------------------------------------------------
    # READ — Account & Positions
    # -----------------------------------------------------------------------

    async def get_account_summary(self) -> dict[str, Any]:
        try:
            account_mode = self._get_abstraction_mode()
            user_state = self._get_user_state()
            margin = user_state.get("marginSummary", {})
            positions = user_state.get("assetPositions", [])
            open_positions = [
                {
                    "coin": p["position"]["coin"],
                    "size": p["position"]["szi"],
                    "entry_price": p["position"]["entryPx"],
                    "unrealized_pnl": p["position"]["unrealizedPnl"],
                    "margin_used": p["position"]["marginUsed"],
                    "return_on_equity": p["position"].get("returnOnEquity"),
                }
                for p in positions if p["position"]["szi"] != "0"
            ]

            account_value = float(margin.get("accountValue", 0))
            total_margin_used = float(margin.get("totalMarginUsed", 0))

            result: dict[str, Any] = {
                "success": True,
                "account_mode": account_mode,
                "perp_balance": {
                    "total_equity": margin.get("accountValue"),
                    "available_margin": str(round(account_value - total_margin_used, 2)),
                    "total_margin_used": margin.get("totalMarginUsed"),
                    "total_notional": margin.get("totalNtlPos"),
                    "withdrawable": margin.get("withdrawable"),
                },
                "positions": open_positions,
                "total_positions": len(open_positions),
            }

            # For unified/portfolio accounts, include spot balances in the overview
            if account_mode in ("unified", "portfolio"):
                try:
                    spot_state = self.info.spot_user_state(self.account_address)
                    spot_balances = [
                        {
                            "coin": b["coin"],
                            "total": b["total"],
                            "hold": b["hold"],
                        }
                        for b in spot_state.get("balances", [])
                        if float(b.get("total", 0)) != 0
                    ]
                    result["spot_balances"] = spot_balances
                    result["note"] = (
                        "Unified account: spot and perp balances are shared. "
                        "USDC balance backs both perp margin and spot trades."
                    )
                except Exception:
                    pass  # spot query failed, perp data still valid

            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_open_positions(self) -> dict[str, Any]:
        try:
            user_state = self._get_user_state()
            positions = user_state.get("assetPositions", [])
            formatted = []
            for p in positions:
                pos = p["position"]
                if pos["szi"] == "0":
                    continue
                formatted.append({
                    "coin": pos["coin"],
                    "size": pos["szi"],
                    "entry_price": pos["entryPx"],
                    "unrealized_pnl": pos["unrealizedPnl"],
                    "return_on_equity": pos.get("returnOnEquity"),
                    "margin_used": pos["marginUsed"],
                    "liquidation_px": pos.get("liquidationPx"),
                    "leverage": pos.get("leverage"),
                    "cumulative_funding": pos.get("cumFunding"),
                })
            return {"success": True, "positions": formatted, "total_positions": len(formatted)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_position_by_coin(self, coin: str) -> dict[str, Any]:
        try:
            user_state = self._get_user_state()
            for p in user_state.get("assetPositions", []):
                pos = p["position"]
                if pos["coin"] == coin and pos["szi"] != "0":
                    return {
                        "success": True,
                        "position": {
                            "coin": coin, "size": pos["szi"], "entry_price": pos["entryPx"],
                            "unrealized_pnl": pos["unrealizedPnl"], "margin_used": pos["marginUsed"],
                            "return_on_equity": pos.get("returnOnEquity"),
                            "liquidation_px": pos.get("liquidationPx"),
                            "leverage": pos.get("leverage"),
                            "cumulative_funding": pos.get("cumFunding"),
                        },
                    }
            return {"success": True, "position": None, "message": f"No open position for {coin}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_open_orders(self) -> dict[str, Any]:
        try:
            orders = self.info.frontend_open_orders(self.account_address)
            formatted = [
                {
                    "order_id": o.get("oid"), "coin": o.get("coin"),
                    "side": "buy" if o.get("side") == "B" else "sell",
                    "size": o.get("sz"), "orig_size": o.get("origSz"),
                    "limit_price": o.get("limitPx"),
                    "reduce_only": o.get("reduceOnly", False),
                    "order_type": o.get("orderType", "unknown"),
                    "trigger_condition": o.get("triggerCondition"),
                    "trigger_px": o.get("triggerPx"),
                    "is_position_tpsl": o.get("isPositionTpsl", False),
                }
                for o in orders
            ]
            return {"success": True, "orders": formatted, "total_orders": len(formatted)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -----------------------------------------------------------------------
    # READ — Market Data
    # -----------------------------------------------------------------------

    async def get_market_info_full(self, coin: str) -> dict[str, Any]:
        try:
            data = self._get_meta_and_asset_ctxs()
            meta_list = data[0]["universe"] if isinstance(data, list) and len(data) >= 2 else []
            ctx_list = data[1] if isinstance(data, list) and len(data) >= 2 else []

            for i, asset in enumerate(meta_list):
                if asset["name"] == coin:
                    ctx = ctx_list[i] if i < len(ctx_list) else {}
                    mids = self._get_all_mids()
                    return {
                        "success": True,
                        "coin": coin,
                        "asset_info": asset,
                        "mid_price": mids.get(coin),
                        "mark_price": ctx.get("markPx"),
                        "oracle_price": ctx.get("oraclePx"),
                        "funding_rate": ctx.get("funding"),
                        "open_interest": ctx.get("openInterest"),
                        "volume_24h": ctx.get("dayNtlVlm"),
                        "premium": ctx.get("premium"),
                        "prev_day_px": ctx.get("prevDayPx"),
                    }

            return {"success": False, "error": f"Asset {coin} not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_market_data(self, coin: str) -> dict[str, Any]:
        try:
            mids = self._get_all_mids()
            book = self.info.l2_snapshot(coin)
            data: dict[str, Any] = {"coin": coin, "mid_price": mids.get(coin)}

            if book and "levels" in book:
                bids = book["levels"][0] if len(book["levels"]) > 0 else []
                asks = book["levels"][1] if len(book["levels"]) > 1 else []
                if bids:
                    data["best_bid"] = bids[0]["px"]
                if asks:
                    data["best_ask"] = asks[0]["px"]

            return {"success": True, "market_data": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_orderbook(self, coin: str, depth: int = 20) -> dict[str, Any]:
        try:
            book = self.info.l2_snapshot(coin)
            if not book or "levels" not in book:
                return {"success": False, "error": f"No orderbook for {coin}"}
            bids = book["levels"][0][:depth] if len(book["levels"]) > 0 else []
            asks = book["levels"][1][:depth] if len(book["levels"]) > 1 else []
            return {"success": True, "coin": coin, "bids": bids, "asks": asks}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_all_markets(self) -> dict[str, Any]:
        try:
            data = self._get_meta_and_asset_ctxs()
            meta_list = data[0]["universe"] if isinstance(data, list) and len(data) >= 2 else []
            ctx_list = data[1] if isinstance(data, list) and len(data) >= 2 else []
            mids = self._get_all_mids()

            markets = []
            for i, asset in enumerate(meta_list):
                ctx = ctx_list[i] if i < len(ctx_list) else {}
                markets.append({
                    "name": asset["name"],
                    "szDecimals": asset.get("szDecimals"),
                    "maxLeverage": asset.get("maxLeverage"),
                    "mid_price": mids.get(asset["name"]),
                    "mark_price": ctx.get("markPx"),
                    "funding_rate": ctx.get("funding"),
                    "open_interest": ctx.get("openInterest"),
                    "volume_24h": ctx.get("dayNtlVlm"),
                })
            return {"success": True, "markets": markets, "total": len(markets)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_candles(self, coin: str, interval: str = "1h", days: int = 1) -> dict[str, Any]:
        try:
            now_ms = int(time.time() * 1000)
            start_ms = now_ms - (days * 86400 * 1000)
            candles = self.info.candles_snapshot(coin, interval, start_ms, now_ms)
            return {"success": True, "coin": coin, "interval": interval, "candles": candles}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_current_funding(self, coin: str) -> dict[str, Any]:
        try:
            data = self._get_meta_and_asset_ctxs()
            meta_list = data[0]["universe"] if isinstance(data, list) and len(data) >= 2 else []
            ctx_list = data[1] if isinstance(data, list) and len(data) >= 2 else []
            mids = self._get_all_mids()

            for i, asset in enumerate(meta_list):
                if asset["name"] == coin:
                    ctx = ctx_list[i] if i < len(ctx_list) else {}
                    return {
                        "success": True,
                        "funding": {
                            "coin": coin,
                            "funding_rate": ctx.get("funding"),
                            "mid_price": mids.get(coin),
                            "open_interest": ctx.get("openInterest"),
                        },
                    }
            return {"success": False, "error": f"Asset {coin} not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_funding_history(self, coin: str, days: int = 7) -> dict[str, Any]:
        try:
            now_ms = int(time.time() * 1000)
            start_ms = now_ms - (days * 86400 * 1000)
            history = self.info.funding_history(coin, start_ms, now_ms)
            return {"success": True, "funding_history": history}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_funding_comparison(self, coins: list[str] | None = None) -> dict[str, Any]:
        try:
            data = self._get_meta_and_asset_ctxs()
            meta_list = data[0]["universe"] if isinstance(data, list) and len(data) >= 2 else []
            ctx_list = data[1] if isinstance(data, list) and len(data) >= 2 else []

            result = {}
            for i, asset in enumerate(meta_list):
                name = asset["name"]
                if coins is None or name in coins:
                    ctx = ctx_list[i] if i < len(ctx_list) else {}
                    result[name] = ctx.get("funding")
            return {"success": True, "funding_rates": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -----------------------------------------------------------------------
    # READ — Trade History & Portfolio
    # -----------------------------------------------------------------------

    async def get_trade_history(self, days: int = 7) -> dict[str, Any]:
        try:
            now_ms = int(time.time() * 1000)
            start_ms = now_ms - (days * 86400 * 1000)
            fills = self.info.user_fills_by_time(self.account_address, start_ms, now_ms)
            return {"success": True, "trades": fills[:100], "total": len(fills)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_user_trades_by_coin(self, coin: str, days: int = 7) -> dict[str, Any]:
        try:
            result = await self.get_trade_history(days=days)
            if not result.get("success"):
                return result
            trades = [t for t in result["trades"] if t.get("coin") == coin]
            return {"success": True, "trades": trades, "total": len(trades)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_recent_trades(self, coin: str, limit: int = 100) -> dict[str, Any]:
        try:
            trades = self.info.recent_trades(coin)
            return {"success": True, "trades": trades[:limit]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_historical_orders(self) -> dict[str, Any]:
        try:
            orders = self.info.historical_orders(self.account_address)
            return {"success": True, "orders": orders[:100], "total": len(orders)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_portfolio(self) -> dict[str, Any]:
        try:
            portfolio = self.info.portfolio(self.account_address)
            return {"success": True, "portfolio": portfolio}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_user_fees(self) -> dict[str, Any]:
        try:
            fees = self.info.user_fees(self.account_address)
            return {"success": True, "fees": fees}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -----------------------------------------------------------------------
    # READ — Spot
    # -----------------------------------------------------------------------

    async def get_spot_balances(self) -> dict[str, Any]:
        try:
            state = self.info.spot_user_state(self.account_address)
            account_mode = self._get_abstraction_mode()
            result: dict[str, Any] = {"success": True, "account_mode": account_mode, "spot_state": state}
            if account_mode in ("unified", "portfolio"):
                result["note"] = "Unified account: USDC balance is shared with perp margin."
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_spot_meta(self) -> dict[str, Any]:
        try:
            data = self._get_spot_meta()
            return {"success": True, "spot_meta": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -----------------------------------------------------------------------
    # READ — Position Sizing
    # -----------------------------------------------------------------------

    async def calculate_size_from_percent_margin(
        self, coin: str, percent: float, basis: str = "available",
        is_buy: bool | None = None, leverage: float | None = None, use_as: str = "margin",
    ) -> dict[str, Any]:
        try:
            user_state = self._get_user_state()
            margin = user_state.get("marginSummary", {})

            if basis == "total":
                base_amount = float(margin.get("accountValue", 0))
            else:
                base_amount = float(margin.get("accountValue", 0)) - float(margin.get("totalMarginUsed", 0))

            usd_amount = base_amount * (percent / 100)

            if use_as == "margin" and leverage:
                usd_amount *= leverage

            price = self._get_mid_price(coin)
            final_sz = self._resolve_size(coin, None, usd_amount, price)

            return {
                "success": True, "coin": coin, "size": final_sz, "usd_notional": usd_amount,
                "price_used": price, "percent": percent, "basis": basis,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def calculate_token_amount(self, coin: str, usd: float) -> dict[str, Any]:
        try:
            price = self._get_mid_price(coin)
            final_sz = self._resolve_size(coin, None, usd, price)
            return {"success": True, "coin": coin, "size": final_sz, "usd": usd, "price_used": price}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -----------------------------------------------------------------------
    # UTILITY
    # -----------------------------------------------------------------------

    def show_config(self) -> dict[str, Any]:
        addr = self.account_address
        masked_addr = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr or "(not set)"
        account_mode = self._get_abstraction_mode() if addr else "unknown"
        config: dict[str, Any] = {
            "account_address": masked_addr,
            "account_mode": account_mode,
            "has_private_key": not self.read_only,
            "read_only": self.read_only,
            "testnet": self.testnet,
            "builder_address": self.builder_address,
            "builder_fee_bps": self.builder_fee_bps,
            "base_url": self.read_url,
        }
        if account_mode in ("unified", "portfolio"):
            config["note"] = (
                "Unified account: spot and perp balances are shared. "
                "Daily action limit: 50k."
            )
        return {"success": True, "config": config}
