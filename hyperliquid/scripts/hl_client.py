#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["hyperliquid-python-sdk", "eth-account"]
# ///
"""HyperLiquid CLI — unified perps, spot, and transfers.

All output is JSON to stdout. Supports read-only mode (no private key).

Run with: uv run hl_client.py <command> [args]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# Add scripts directory to path for co-located imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _get_services(require_address: bool = False):
    """Create HLServices from environment variables."""
    from hl_services import HLServices

    account_address = os.environ.get("EVM_WALLET_ADDRESS", "")
    private_key = os.environ.get("EVM_PRIVATE_KEY") or None  # None = read-only
    testnet = os.environ.get("HL_TESTNET", "").lower() in ("true", "1", "yes")
    builder_address = os.environ.get("HL_BUILDER_ADDRESS")
    builder_fee_bps = os.environ.get("HL_BUILDER_FEE_BPS")

    if require_address and not account_address:
        _out({"success": False, "error": "EVM_WALLET_ADDRESS must be set. Run 'config' to check."})
        sys.exit(1)

    return HLServices(
        account_address=account_address,
        private_key=private_key,
        testnet=testnet,
        builder_address=builder_address,
        builder_fee_bps=int(builder_fee_bps) if builder_fee_bps else None,
    )


def _normalize_coin(coin: str) -> str:
    """Normalize coin ticker. Preserves '/' for spot pairs."""
    c = coin.strip().upper()
    if c.startswith("$"):
        c = c[1:]
    # Don't strip suffixes from spot pairs like TOKEN/USDC
    if "/" in c:
        return c
    for suffix in ("-PERP", "PERP", "/USDT", "/USDC", "/USD", "-USD", "USDT", "USDC"):
        if len(c) > len(suffix) and c.endswith(suffix):
            c = c[: -len(suffix)]
            break
    return c


def _out(data):
    print(json.dumps(data, default=str))


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_config(args):
    svc = _get_services()
    _out(svc.show_config())


async def cmd_account(args):
    svc = _get_services(require_address=True)
    _out(await svc.get_account_summary())


async def cmd_positions(args):
    svc = _get_services(require_address=True)
    if args.coin:
        _out(await svc.get_position_by_coin(_normalize_coin(args.coin)))
    else:
        _out(await svc.get_open_positions())


async def cmd_orders(args):
    svc = _get_services(require_address=True)
    _out(await svc.get_open_orders())


async def cmd_balance(args):
    svc = _get_services(require_address=True)
    _out(await svc.get_spot_balances())


async def cmd_fees(args):
    svc = _get_services(require_address=True)
    _out(await svc.get_user_fees())


async def cmd_portfolio(args):
    svc = _get_services(require_address=True)
    _out(await svc.get_portfolio())


async def cmd_market_info(args):
    svc = _get_services()
    coin = _normalize_coin(args.coin)
    _out(await svc.get_market_info_full(coin=coin))


async def cmd_orderbook(args):
    svc = _get_services()
    _out(await svc.get_orderbook(coin=_normalize_coin(args.coin), depth=args.depth))


async def cmd_all_markets(args):
    svc = _get_services()
    _out(await svc.get_all_markets())


async def cmd_candles(args):
    svc = _get_services()
    _out(await svc.get_candles(coin=_normalize_coin(args.coin), interval=args.interval, days=args.days))


async def cmd_funding(args):
    svc = _get_services()
    if args.coins:
        coins = [_normalize_coin(c) for c in args.coins.split(",")]
        _out(await svc.get_funding_comparison(coins=coins))
    elif args.coin:
        coin = _normalize_coin(args.coin)
        current = await svc.get_current_funding(coin=coin)
        history = await svc.get_funding_history(coin=coin, days=args.days)
        if current.get("success") and history.get("success"):
            _out({"success": True, "coin": coin, "current": current.get("funding"), "history": history.get("funding_history")})
        else:
            _out(current if not current.get("success") else history)
    else:
        _out(await svc.get_funding_comparison(coins=None))


async def cmd_trades(args):
    svc = _get_services(require_address=True)
    coin = _normalize_coin(args.coin) if args.coin else None
    if args.source == "market":
        if not coin:
            _out({"success": False, "error": "--coin required for market trades"})
            return
        _out(await svc.get_recent_trades(coin=coin, limit=args.limit))
    elif coin:
        _out(await svc.get_user_trades_by_coin(coin=coin, days=args.days))
    else:
        _out(await svc.get_trade_history(days=args.days))


async def cmd_historical_orders(args):
    svc = _get_services(require_address=True)
    _out(await svc.get_historical_orders())


async def cmd_calc_size(args):
    svc = _get_services(require_address=True)
    coin = _normalize_coin(args.coin)
    if args.percent is not None:
        _out(await svc.calculate_size_from_percent_margin(
            coin=coin, percent=args.percent, basis=args.basis,
            leverage=args.leverage, use_as=args.use_as,
        ))
    elif args.usd is not None:
        _out(await svc.calculate_token_amount(coin=coin, usd=args.usd))
    else:
        _out({"success": False, "error": "Provide either --percent or --usd"})


async def cmd_order(args):
    svc = _get_services(require_address=True)
    coin = _normalize_coin(args.coin)
    is_buy = args.side.lower() in ("buy", "long")

    if args.sz is not None and args.sz <= 0:
        _out({"success": False, "error": "Size must be positive"})
        return
    if args.usd is not None and args.usd <= 0:
        _out({"success": False, "error": "USD amount must be positive"})
        return

    # Simple market order (no limit, no TP/SL, not reduce-only)
    is_simple_market = (
        args.limit_px is None
        and args.tp_px is None
        and args.sl_px is None
        and not args.reduce_only
    )
    if is_simple_market and args.slippage == 0.05:
        _out(await svc.market_open_position(coin=coin, is_buy=is_buy, sz=args.sz, usd=args.usd))
    else:
        _out(await svc.place_order(
            coin=coin, is_buy=is_buy, sz=args.sz, limit_px=args.limit_px,
            reduce_only=args.reduce_only, tp_px=args.tp_px, sl_px=args.sl_px,
            usd=args.usd, slippage=args.slippage,
        ))


async def cmd_close(args):
    svc = _get_services(require_address=True)
    _out(await svc.market_close_position(
        coin=_normalize_coin(args.coin), sz=args.sz, slippage=args.slippage,
    ))


async def cmd_modify(args):
    svc = _get_services(require_address=True)
    _out(await svc.modify_order(
        coin=_normalize_coin(args.coin), oid=args.oid,
        new_sz=args.new_sz, new_limit_px=args.new_limit_px,
    ))


async def cmd_cancel(args):
    svc = _get_services(require_address=True)
    coin = _normalize_coin(args.coin) if args.coin else None
    if args.oid is not None:
        if not coin:
            _out({"success": False, "error": "--coin is required when cancelling by --oid"})
            return
        _out(await svc.cancel_order(coin=coin, oid=args.oid))
    else:
        _out(await svc.cancel_all_orders(coin=coin))


async def cmd_tpsl(args):
    svc = _get_services(require_address=True)
    _out(await svc.set_position_tpsl(
        coin=_normalize_coin(args.coin), tp_px=args.tp_px, sl_px=args.sl_px,
        position_size=args.position_size,
    ))


async def cmd_leverage(args):
    svc = _get_services(require_address=True)
    _out(await svc.update_leverage(
        coin=_normalize_coin(args.coin), leverage=args.leverage,
        is_cross=args.cross,
    ))


async def cmd_twap(args):
    svc = _get_services(require_address=True)
    coin = _normalize_coin(args.coin)
    if args.cancel is not None:
        _out(await svc.cancel_twap(coin=coin, twap_id=args.cancel))
    else:
        is_buy = args.side.lower() in ("buy", "long")
        if args.sz is None or args.sz <= 0:
            _out({"success": False, "error": "--sz is required for TWAP orders"})
            return
        if args.minutes is None or args.minutes <= 0:
            _out({"success": False, "error": "--minutes is required for TWAP orders"})
            return
        _out(await svc.place_twap_order(
            coin=coin, is_buy=is_buy, sz=args.sz,
            minutes=args.minutes, randomize=not args.no_randomize,
        ))


async def cmd_schedule_cancel(args):
    svc = _get_services(require_address=True)
    if args.clear:
        _out(await svc.schedule_cancel_all(timestamp_ms=None))
    else:
        if args.timestamp is None:
            _out({"success": False, "error": "Provide --timestamp (unix ms) or --clear"})
            return
        _out(await svc.schedule_cancel_all(timestamp_ms=args.timestamp))


async def cmd_spot_order(args):
    svc = _get_services(require_address=True)
    coin = args.coin.strip().upper()  # Preserve TOKEN/USDC format
    is_buy = args.side.lower() in ("buy", "long")

    if args.sz is not None and args.sz <= 0:
        _out({"success": False, "error": "Size must be positive"})
        return
    if args.usd is not None and args.usd <= 0:
        _out({"success": False, "error": "USD amount must be positive"})
        return

    _out(await svc.place_spot_order(
        coin=coin, is_buy=is_buy, sz=args.sz,
        limit_px=args.limit_px, usd=args.usd,
    ))


async def cmd_transfer(args):
    svc = _get_services(require_address=True)
    if args.amount <= 0:
        _out({"success": False, "error": "Amount must be positive"})
        return
    to_perp = args.direction.lower() in ("to-perp", "spot-to-perp")
    _out(await svc.transfer_between_wallets(amount=args.amount, to_perp=to_perp))


async def cmd_send(args):
    svc = _get_services(require_address=True)
    if args.amount <= 0:
        _out({"success": False, "error": "Amount must be positive"})
        return
    if not args.to:
        _out({"success": False, "error": "--to address is required"})
        return
    _out(await svc.send_usd(amount=args.amount, destination=args.to))


async def cmd_withdraw(args):
    svc = _get_services(require_address=True)
    if args.amount <= 0:
        _out({"success": False, "error": "Amount must be positive"})
        return
    if not args.to:
        _out({"success": False, "error": "--to address is required"})
        return
    _out(await svc.withdraw_to_evm(amount=args.amount, destination=args.to))


# ---------------------------------------------------------------------------
# Argparse setup
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="HyperLiquid CLI — perps, spot, transfers")
    sub = parser.add_subparsers(dest="command", required=True)

    # config
    sub.add_parser("config", help="Show configuration status")

    # account
    sub.add_parser("account", help="Full account overview")

    # positions
    p = sub.add_parser("positions", help="Open positions")
    p.add_argument("--coin", default=None)

    # orders
    sub.add_parser("orders", help="Pending orders (rich format)")

    # balance
    sub.add_parser("balance", help="Spot wallet balances")

    # fees
    sub.add_parser("fees", help="Fee schedule and volume")

    # portfolio
    sub.add_parser("portfolio", help="PnL performance history")

    # market-info
    p = sub.add_parser("market-info", help="Full market data for a coin")
    p.add_argument("--coin", required=True)

    # orderbook
    p = sub.add_parser("orderbook", help="Order book snapshot")
    p.add_argument("--coin", required=True)
    p.add_argument("--depth", type=int, default=20)

    # all-markets
    sub.add_parser("all-markets", help="All markets with prices, funding, OI")

    # candles
    p = sub.add_parser("candles", help="OHLCV candle data")
    p.add_argument("--coin", required=True)
    p.add_argument("--interval", default="1h", help="1m, 5m, 15m, 1h, 4h, 1d")
    p.add_argument("--days", type=int, default=1)

    # funding
    p = sub.add_parser("funding", help="Funding rates")
    p.add_argument("--coin", default=None)
    p.add_argument("--coins", default=None, help="Comma-separated list for comparison")
    p.add_argument("--days", type=int, default=7)

    # trades
    p = sub.add_parser("trades", help="Trade history")
    p.add_argument("--source", default="user", choices=["user", "market"])
    p.add_argument("--coin", default=None)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--limit", type=int, default=100)

    # historical-orders
    sub.add_parser("historical-orders", help="Order history")

    # calc-size
    p = sub.add_parser("calc-size", help="Calculate position size")
    p.add_argument("--coin", required=True)
    p.add_argument("--percent", type=float, default=None)
    p.add_argument("--usd", type=float, default=None)
    p.add_argument("--basis", default="available")
    p.add_argument("--leverage", type=float, default=None)
    p.add_argument("--use-as", default="margin")

    # order
    p = sub.add_parser("order", help="Place perp order")
    p.add_argument("--coin", required=True)
    p.add_argument("--side", required=True, choices=["buy", "sell", "long", "short"])
    p.add_argument("--sz", type=float, default=None)
    p.add_argument("--usd", type=float, default=None)
    p.add_argument("--limit-px", type=float, default=None)
    p.add_argument("--reduce-only", action="store_true")
    p.add_argument("--slippage", type=float, default=0.05)
    p.add_argument("--tp-px", type=float, default=None)
    p.add_argument("--sl-px", type=float, default=None)

    # close
    p = sub.add_parser("close", help="Close perp position")
    p.add_argument("--coin", required=True)
    p.add_argument("--sz", type=float, default=None)
    p.add_argument("--slippage", type=float, default=0.05)

    # modify
    p = sub.add_parser("modify", help="Modify existing order")
    p.add_argument("--coin", required=True)
    p.add_argument("--oid", type=int, required=True)
    p.add_argument("--new-sz", type=float, required=True)
    p.add_argument("--new-limit-px", type=float, required=True)

    # cancel
    p = sub.add_parser("cancel", help="Cancel orders")
    p.add_argument("--coin", default=None)
    p.add_argument("--oid", type=int, default=None)

    # tpsl
    p = sub.add_parser("tpsl", help="Set TP/SL on existing position")
    p.add_argument("--coin", required=True)
    p.add_argument("--tp-px", type=float, default=None)
    p.add_argument("--sl-px", type=float, default=None)
    p.add_argument("--position-size", type=float, default=None)

    # leverage
    p = sub.add_parser("leverage", help="Update leverage")
    p.add_argument("--coin", required=True)
    p.add_argument("--leverage", type=int, required=True)
    p.add_argument("--cross", action="store_true", default=True)
    p.add_argument("--isolated", action="store_false", dest="cross")

    # twap
    p = sub.add_parser("twap", help="Place or cancel TWAP order")
    p.add_argument("--coin", required=True)
    p.add_argument("--side", choices=["buy", "sell", "long", "short"], default=None)
    p.add_argument("--sz", type=float, default=None)
    p.add_argument("--minutes", type=int, default=None)
    p.add_argument("--no-randomize", action="store_true")
    p.add_argument("--cancel", type=int, default=None, help="TWAP ID to cancel")

    # schedule-cancel
    p = sub.add_parser("schedule-cancel", help="Dead man's switch — cancel all orders at time")
    p.add_argument("--timestamp", type=int, default=None, help="Unix timestamp in ms")
    p.add_argument("--clear", action="store_true", help="Clear existing schedule")

    # spot-order
    p = sub.add_parser("spot-order", help="Place spot order")
    p.add_argument("--coin", required=True, help="TOKEN or TOKEN/USDC")
    p.add_argument("--side", required=True, choices=["buy", "sell"])
    p.add_argument("--sz", type=float, default=None)
    p.add_argument("--usd", type=float, default=None)
    p.add_argument("--limit-px", type=float, default=None)

    # transfer
    p = sub.add_parser("transfer", help="Transfer USDC between spot and perp")
    p.add_argument("--amount", type=float, required=True)
    p.add_argument("--direction", required=True, choices=["to-perp", "to-spot", "spot-to-perp", "perp-to-spot"])

    # send
    p = sub.add_parser("send", help="Send USDC to another address")
    p.add_argument("--amount", type=float, required=True)
    p.add_argument("--to", required=True, help="Destination address")

    # withdraw
    p = sub.add_parser("withdraw", help="Withdraw USDC to EVM via bridge")
    p.add_argument("--amount", type=float, required=True)
    p.add_argument("--to", required=True, help="Destination EVM address")

    args = parser.parse_args()

    # Dispatch
    handler = {
        "config": cmd_config,
        "account": cmd_account,
        "positions": cmd_positions,
        "orders": cmd_orders,
        "balance": cmd_balance,
        "fees": cmd_fees,
        "portfolio": cmd_portfolio,
        "market-info": cmd_market_info,
        "orderbook": cmd_orderbook,
        "all-markets": cmd_all_markets,
        "candles": cmd_candles,
        "funding": cmd_funding,
        "trades": cmd_trades,
        "historical-orders": cmd_historical_orders,
        "calc-size": cmd_calc_size,
        "order": cmd_order,
        "close": cmd_close,
        "modify": cmd_modify,
        "cancel": cmd_cancel,
        "tpsl": cmd_tpsl,
        "leverage": cmd_leverage,
        "twap": cmd_twap,
        "schedule-cancel": cmd_schedule_cancel,
        "spot-order": cmd_spot_order,
        "transfer": cmd_transfer,
        "send": cmd_send,
        "withdraw": cmd_withdraw,
    }[args.command]

    try:
        asyncio.run(handler(args))
    except Exception as e:
        _out({"success": False, "error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
