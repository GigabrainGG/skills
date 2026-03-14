#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "pydantic", "py-clob-client", "eth-account", "web3"]
# ///
"""Polymarket CLI - thin argparse wrapper around PMClient.

All output is JSON to stdout. Self-contained - imports from co-located
pm_services.py which uses httpx and py-clob-client directly.

Run with: uv run pm_client.py <command> [args]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# Add scripts directory to path for co-located imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _get_client():
    """Create PMClient from environment variables."""
    from pm_services import PMClient

    return PMClient(
        private_key=os.environ.get("EVM_PRIVATE_KEY", ""),
        funder_address=os.environ.get("EVM_WALLET_ADDRESS", ""),
    )


def _out(data):
    print(json.dumps(data, default=str))


def _format_market(m) -> dict:
    """Convert Market model to a clean dict for JSON output."""
    return {
        "question": m.question,
        "yes_price": m.yes_price,
        "volume": m.volume_24hr or m.volume_num or m.volume or 0,
        "liquidity": m.liquidity_num or m.liquidity or 0,
        "end_date": m.end_date.isoformat() if m.end_date else None,
        "category": m.category,
        "neg_risk": m.neg_risk,
        "outcomes": m.outcomes,
        "tokens": [
            {"outcome": t.outcome, "price": t.price, "token_id": t.token_id}
            for t in (m.tokens or [])
        ],
    }


async def cmd_search(args):
    client = _get_client()
    if args.tag:
        markets = await client.get_markets(limit=args.limit, tag=args.tag)
    else:
        markets = await client.search_markets(args.query, limit=args.limit)
    _out({"success": True, "markets": [_format_market(m) for m in markets]})


async def cmd_trending(args):
    client = _get_client()
    if args.sort == "liquidity":
        markets = await client.get_high_liquidity(limit=args.limit)
    elif args.sort == "ending":
        markets = await client.get_ending_soon(limit=args.limit)
    else:
        markets = await client.get_trending(limit=args.limit)
    _out({"success": True, "markets": [_format_market(m) for m in markets]})


async def cmd_odds(args):
    client = _get_client()
    markets = await client.search_markets(args.query, limit=3)
    if not markets:
        _out({"success": True, "markets": [], "message": f"No markets found for '{args.query}'"})
        return

    results = []
    for m in markets:
        result = {"question": m.question, "outcomes": []}
        if m.tokens:
            for t in m.tokens:
                result["outcomes"].append({"name": t.outcome, "price": t.price, "pct": f"{t.price * 100:.1f}%"})
        elif m.yes_price is not None:
            result["outcomes"].append({"name": "Yes", "price": m.yes_price, "pct": f"{m.yes_price * 100:.1f}%"})
            result["outcomes"].append({"name": "No", "price": 1 - m.yes_price, "pct": f"{(1 - m.yes_price) * 100:.1f}%"})
        result["volume"] = m.volume_24hr or m.volume or 0
        result["liquidity"] = m.liquidity_num or m.liquidity or 0
        result["end_date"] = m.end_date.isoformat() if m.end_date else None
        results.append(result)

    _out({"success": True, "markets": results})


async def cmd_orderbook(args):
    client = _get_client()
    # Resolve token_id from query + outcome
    markets = await client.search_markets(args.query, limit=3)
    if not markets:
        _out({"success": False, "error": f"No markets found for '{args.query}'"})
        return

    market = markets[0]
    token_id = market.get_token_id(args.outcome)
    if not token_id:
        available = market.outcomes or ([t.outcome for t in market.tokens] if market.tokens else [])
        _out({"success": False, "error": f"Outcome '{args.outcome}' not found. Available: {available}"})
        return

    book = client.get_orderbook(token_id)
    midpoint = client.get_midpoint(token_id)
    spread = client.get_spread(token_id)
    _out({
        "success": True,
        "market": market.question,
        "outcome": args.outcome,
        "midpoint": midpoint,
        "spread": spread,
        "bids": (book.get("bids") or [])[:args.depth],
        "asks": (book.get("asks") or [])[:args.depth],
    })


async def cmd_buy(args):
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS."})
        return

    markets = await client.search_markets(args.query, limit=5)
    if not markets:
        _out({"success": False, "error": f"No markets found for '{args.query}'"})
        return

    market = markets[0]
    token_id = market.get_token_id(args.outcome)
    if not token_id:
        available = market.outcomes or ([t.outcome for t in market.tokens] if market.tokens else [])
        _out({"success": False, "error": f"Outcome '{args.outcome}' not found. Available: {available}"})
        return

    if args.market_order:
        order_id = client.market_buy(token_id=token_id, amount_usd=args.amount_usd, neg_risk=market.neg_risk)
        _out({
            "success": True, "action": "market_buy", "market": market.question,
            "outcome": args.outcome, "amount_usd": args.amount_usd, "order_id": order_id,
        })
    else:
        if not args.price:
            _out({"success": False, "error": "Limit orders require --price"})
            return
        if not (0.01 <= args.price <= 0.99):
            _out({"success": False, "error": "Price must be between 0.01 and 0.99"})
            return
        shares = args.amount_usd / args.price
        order_id = client.buy(token_id=token_id, price=args.price, size=shares, neg_risk=market.neg_risk)
        _out({
            "success": True, "action": "limit_buy", "market": market.question,
            "outcome": args.outcome, "price": args.price,
            "shares": round(shares, 2), "cost_usd": args.amount_usd, "order_id": order_id,
        })


async def cmd_sell(args):
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS."})
        return

    if not (0.01 <= args.price <= 0.99):
        _out({"success": False, "error": "Price must be between 0.01 and 0.99"})
        return

    markets = await client.search_markets(args.query, limit=5)
    if not markets:
        _out({"success": False, "error": f"No markets found for '{args.query}'"})
        return

    market = markets[0]
    token_id = market.get_token_id(args.outcome)
    if not token_id:
        available = market.outcomes or ([t.outcome for t in market.tokens] if market.tokens else [])
        _out({"success": False, "error": f"Outcome '{args.outcome}' not found. Available: {available}"})
        return

    order_id = client.sell(token_id=token_id, price=args.price, size=args.shares, neg_risk=market.neg_risk)
    _out({
        "success": True, "action": "limit_sell", "market": market.question,
        "outcome": args.outcome, "price": args.price,
        "shares": args.shares, "proceeds_usd": round(args.shares * args.price, 2), "order_id": order_id,
    })


async def cmd_balance(args):
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS."})
        return
    balance = client.get_usdc_balance()
    _out({"success": True, "usdc_balance": balance})


async def cmd_positions(args):
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS."})
        return
    positions = await client.get_positions()
    formatted = []
    for p in positions:
        size = float(p.get("size", 0))
        if abs(size) < 0.01:
            continue
        formatted.append({
            "title": p.get("title", ""),
            "outcome": p.get("outcome", ""),
            "size": size,
            "avg_price": float(p.get("avgPrice", 0)),
            "current_price": float(p.get("curPrice", 0)),
            "initial_value": float(p.get("initialValue", 0)),
            "current_value": float(p.get("currentValue", 0)),
            "pnl": float(p.get("cashPnl", 0)),
            "pnl_pct": float(p.get("percentPnl", 0)),
            "end_date": p.get("endDate", ""),
        })
    _out({"success": True, "positions": formatted})


async def cmd_trades(args):
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS."})
        return
    trades = await client.get_trades(limit=args.limit)
    _out({"success": True, "trades": trades})


async def cmd_my_orders(args):
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS."})
        return
    orders = client.get_open_orders()
    _out({"success": True, "orders": orders})


async def cmd_cancel_order(args):
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS."})
        return
    if args.all:
        count = client.cancel_all()
        _out({"success": True, "action": "cancel_all", "canceled": count})
    else:
        if not args.order_id:
            _out({"success": False, "error": "Provide --order-id or --all"})
            return
        success = client.cancel(args.order_id)
        _out({"success": success, "order_id": args.order_id, "action": "cancel"})


async def cmd_check_order(args):
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS."})
        return
    info = client.is_filled(args.order_id)
    info["success"] = True
    _out(info)


def main():
    parser = argparse.ArgumentParser(description="Polymarket CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # search
    p = sub.add_parser("search", help="Search markets")
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--tag", default=None, help="Filter by tag (crypto, politics, sports, etc.)")

    # trending
    p = sub.add_parser("trending", help="Trending markets")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--sort", default="volume", choices=["volume", "liquidity", "ending"])

    # odds
    p = sub.add_parser("odds", help="Get odds for a specific event")
    p.add_argument("--query", required=True)

    # orderbook
    p = sub.add_parser("orderbook", help="Get order book depth")
    p.add_argument("--query", required=True, help="Market search query")
    p.add_argument("--outcome", default="Yes", help="Outcome (Yes/No)")
    p.add_argument("--depth", type=int, default=10, help="Number of levels")

    # buy
    p = sub.add_parser("buy", help="Buy outcome shares")
    p.add_argument("--query", required=True, help="Market search query")
    p.add_argument("--outcome", required=True, help="Outcome to buy (e.g. Yes, No)")
    p.add_argument("--price", type=float, default=None, help="Limit price 0.01-0.99 (omit for market order)")
    p.add_argument("--amount-usd", type=float, required=True, help="USD amount to spend")
    p.add_argument("--market-order", action="store_true", help="Use FOK market order instead of limit")

    # sell
    p = sub.add_parser("sell", help="Sell outcome shares")
    p.add_argument("--query", required=True, help="Market search query")
    p.add_argument("--outcome", required=True, help="Outcome to sell")
    p.add_argument("--price", type=float, required=True, help="Limit price 0.01-0.99")
    p.add_argument("--shares", type=float, required=True, help="Number of shares to sell")

    # balance
    sub.add_parser("balance", help="Check USDC.e balance (trading-ready)")

    # positions
    sub.add_parser("positions", help="View current positions and P&L")

    # trades
    p = sub.add_parser("trades", help="View recent trade history")
    p.add_argument("--limit", type=int, default=20)

    # my-orders
    sub.add_parser("my-orders", help="List open orders")

    # cancel-order
    p = sub.add_parser("cancel-order", help="Cancel orders")
    p.add_argument("--order-id", default=None, help="Specific order to cancel")
    p.add_argument("--all", action="store_true", help="Cancel all open orders")

    # check-order
    p = sub.add_parser("check-order", help="Check order fill status")
    p.add_argument("--order-id", required=True)

    args = parser.parse_args()

    handler = {
        "search": cmd_search,
        "trending": cmd_trending,
        "odds": cmd_odds,
        "orderbook": cmd_orderbook,
        "buy": cmd_buy,
        "sell": cmd_sell,
        "balance": cmd_balance,
        "positions": cmd_positions,
        "trades": cmd_trades,
        "my-orders": cmd_my_orders,
        "cancel-order": cmd_cancel_order,
        "check-order": cmd_check_order,
    }[args.command]

    try:
        asyncio.run(handler(args))
    except Exception as e:
        _out({"success": False, "error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
