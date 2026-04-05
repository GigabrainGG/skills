#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "pydantic", "py-clob-client", "web3>=6.0.0,<7", "setuptools<74"]
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
import re
import sys

# Add scripts directory to path for co-located imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _get_client():
    """Create PMClient from environment variables."""
    from pm_services import PMClient

    return PMClient(
        private_key=os.environ.get("EVM_PRIVATE_KEY", ""),
        funder_address=os.environ.get("POLY_FUNDER_ADDRESS", os.environ.get("EVM_WALLET_ADDRESS", "")),
        signature_type=int(os.environ.get("POLY_SIGNATURE_TYPE", "0")),
        builder_api_key=os.environ.get("POLY_BUILDER_API_KEY", ""),
        builder_secret=os.environ.get("POLY_BUILDER_SECRET", ""),
        builder_passphrase=os.environ.get("POLY_BUILDER_PASSPHRASE", ""),
        builder_signer_url=os.environ.get("POLY_BUILDER_SIGNER_URL", ""),
        builder_signer_token=os.environ.get("POLY_BUILDER_SIGNER_TOKEN", ""),
    )


def _out(data):
    print(json.dumps(data, default=str))


def _parse_jsonish(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _parse_tristate_bool(value: str | None) -> bool | None:
    if value is None or value == "any":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"Unsupported boolean selector: {value}")


def _format_quality(market) -> dict:
    """Extract quality info from a market."""
    q = market.quality
    return {
        "tradability_score": q.tradability_score,
        "liquidity_usd": q.liquidity_usd,
        "volume_24h_usd": q.volume_24h_usd,
        "spread_pct": q.spread_pct,
        "is_tradable": q.is_tradable,
        "warnings": q.warnings,
    }


def _format_market(m) -> dict:
    """Convert Market model to a clean dict for JSON output, including quality."""
    data = {
        "slug": m.slug or m.market_slug,
        "market_slug": m.market_slug,
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
        "quality": _format_quality(m),
    }
    return data


def _format_candidate(m) -> dict:
    data = _format_market(m)
    data["outcomes"] = m.outcomes or [t.outcome for t in (m.tokens or [])]
    data["condition_id"] = m.condition_id
    return data


def _format_public_market(raw_market: dict) -> dict:
    return {
        "id": raw_market.get("id"),
        "slug": raw_market.get("slug") or raw_market.get("marketSlug"),
        "question": raw_market.get("question") or raw_market.get("title") or "",
        "condition_id": raw_market.get("conditionId"),
        "active": raw_market.get("active"),
        "closed": raw_market.get("closed"),
        "archived": raw_market.get("archived"),
        "accepting_orders": raw_market.get("acceptingOrders"),
        "ready": raw_market.get("ready"),
        "yes_price": raw_market.get("lastTradePrice"),
        "best_bid": raw_market.get("bestBid"),
        "best_ask": raw_market.get("bestAsk"),
        "spread": raw_market.get("spread"),
        "volume": raw_market.get("volume24hr") or raw_market.get("volume") or 0,
        "liquidity": raw_market.get("liquidityClob") or raw_market.get("liquidity") or 0,
        "comment_count": raw_market.get("commentCount"),
        "open_interest": raw_market.get("openInterest"),
        "outcomes": _parse_jsonish(raw_market.get("outcomes")),
        "token_ids": _parse_jsonish(raw_market.get("clobTokenIds")),
    }


def _format_public_event(event: dict, market_limit: int = 3) -> dict:
    return {
        "id": event.get("id"),
        "slug": event.get("slug"),
        "title": event.get("title") or event.get("question") or event.get("slug") or "",
        "description": event.get("description"),
        "active": event.get("active"),
        "closed": event.get("closed"),
        "archived": event.get("archived"),
        "volume": event.get("volume24hr") or event.get("volume") or 0,
        "liquidity": event.get("liquidityClob") or event.get("liquidity") or 0,
        "open_interest": event.get("openInterest"),
        "comment_count": event.get("commentCount"),
        "end_date": event.get("endDate"),
        "markets": [_format_public_market(market) for market in (event.get("markets") or [])[:market_limit]],
    }


def _normalize_selector(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


async def _resolve_market(client, query: str | None, outcome: str | None, market_slug: str | None):
    search_query = market_slug or query
    if not search_query:
        return None, {
            "success": False,
            "error": "Provide --query or --market-slug",
        }

    selector = market_slug or query

    # Exact slug lookup bypasses fuzzy search entirely.
    if market_slug:
        exact_market = await client.get_market_by_slug(market_slug)
        if exact_market is None:
            fallback_markets = await client.search_markets(search_query, limit=8)
            return None, {
                "success": False,
                "error": f"No market matched slug '{market_slug}'",
                "candidates": [_format_candidate(m) for m in fallback_markets[:5]],
            }

        if outcome and not exact_market.get_token_id(outcome):
            available = exact_market.outcomes or [t.outcome for t in (exact_market.tokens or [])]
            return None, {
                "success": False,
                "error": f"Outcome '{outcome}' not found in market '{market_slug}'",
                "candidates": [{**_format_candidate(exact_market), "outcomes": available}],
            }

        return exact_market, None

    markets = await client.search_markets(search_query, limit=8)
    if not markets:
        return None, {
            "success": False,
            "error": f"No markets found for '{selector}'",
        }

    if query:
        exact_matches = [
            m for m in markets
            if _normalize_selector(m.question) == _normalize_selector(query)
            or _normalize_selector(m.slug) == _normalize_selector(query)
            or _normalize_selector(m.market_slug) == _normalize_selector(query)
        ]
        if len(exact_matches) == 1:
            markets = exact_matches
        elif len(exact_matches) > 1:
            markets = exact_matches

    if outcome:
        outcome_matches = [m for m in markets if m.get_token_id(outcome)]
        if not outcome_matches:
            return None, {
                "success": False,
                "error": f"Outcome '{outcome}' not found in any matching market",
                "candidates": [_format_candidate(m) for m in markets[:5]],
            }
        markets = outcome_matches

    if len(markets) != 1:
        return None, {
            "success": False,
            "error": "Ambiguous market selection. Use `resolve` first and rerun with --market-slug.",
            "candidates": [_format_candidate(m) for m in markets[:5]],
        }

    return markets[0], None


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_events(args):
    from pm_services import Market

    client = _get_client()
    events = await client.get_events(query=args.query, slug=args.slug, limit=args.limit, tag=args.tag)

    formatted = []
    for event in events:
        event_markets = []
        for raw_market in (event.get("markets") or [])[: args.market_limit]:
            try:
                event_markets.append(_format_market(Market.model_validate(raw_market)))
            except Exception:
                event_markets.append({
                    "slug": raw_market.get("slug") or raw_market.get("marketSlug"),
                    "question": raw_market.get("question") or raw_market.get("title") or "",
                    "yes_price": raw_market.get("yesPrice"),
                    "volume": raw_market.get("volume24hr") or raw_market.get("volume") or 0,
                    "liquidity": raw_market.get("liquidity") or 0,
                    "end_date": raw_market.get("endDate") or raw_market.get("resolutionDate"),
                    "category": raw_market.get("category"),
                    "neg_risk": raw_market.get("negRisk", False),
                    "outcomes": raw_market.get("outcomes") or [],
                    "tokens": [],
                })

        formatted.append({
            "id": event.get("id"),
            "slug": event.get("slug"),
            "title": event.get("title") or event.get("question") or event.get("slug") or "",
            "description": event.get("description"),
            "volume": event.get("volume24hr") or event.get("volume") or 0,
            "liquidity": event.get("liquidity") or 0,
            "end_date": event.get("endDate") or event.get("resolutionDate"),
            "category": event.get("category"),
            "markets": event_markets,
        })

    _out({"success": True, "events": formatted})


async def cmd_events_raw(args):
    client = _get_client()
    events = await client.raw_events(
        query=args.query,
        limit=args.limit,
        active=_parse_tristate_bool(args.active),
        closed=_parse_tristate_bool(args.closed),
        archived=_parse_tristate_bool(args.archived),
        tag=args.tag,
        order=args.order,
        ascending=_parse_tristate_bool(args.ascending),
    )
    _out({
        "success": True,
        "source": "gamma/events",
        "request": {
            "query": args.query,
            "limit": args.limit,
            "active": _parse_tristate_bool(args.active),
            "closed": _parse_tristate_bool(args.closed),
            "archived": _parse_tristate_bool(args.archived),
            "tag": args.tag,
            "order": args.order,
            "ascending": _parse_tristate_bool(args.ascending),
        },
        "events": events,
    })


async def cmd_resolve(args):
    client = _get_client()
    market, error = await _resolve_market(
        client,
        query=args.query,
        outcome=args.outcome,
        market_slug=args.market_slug,
    )
    if market:
        _out({"success": True, "resolved": True, "market": _format_candidate(market)})
        return

    payload = dict(error or {})
    payload["success"] = False
    payload["resolved"] = False
    _out(payload)


async def cmd_search(args):
    client = _get_client()
    if args.tag:
        markets = await client.get_markets(limit=args.limit, tag=args.tag)
    else:
        markets = await client.search_markets(args.query, limit=args.limit)
    _out({"success": True, "markets": [_format_market(m) for m in markets]})


async def cmd_markets_raw(args):
    client = _get_client()
    markets = await client.raw_markets(
        query=args.query,
        limit=args.limit,
        active=_parse_tristate_bool(args.active),
        closed=_parse_tristate_bool(args.closed),
        archived=_parse_tristate_bool(args.archived),
        tag=args.tag,
        sort_by=args.order,
        ascending=_parse_tristate_bool(args.ascending),
    )
    _out({
        "success": True,
        "source": "gamma/markets",
        "request": {
            "query": args.query,
            "limit": args.limit,
            "active": _parse_tristate_bool(args.active),
            "closed": _parse_tristate_bool(args.closed),
            "archived": _parse_tristate_bool(args.archived),
            "tag": args.tag,
            "order": args.order,
            "ascending": _parse_tristate_bool(args.ascending),
        },
        "markets": markets,
    })


async def cmd_public_search(args):
    client = _get_client()
    results = await client.public_search(args.query, limit=args.limit)
    _out({
        "success": True,
        "events": [_format_public_event(event, market_limit=args.market_limit) for event in results.get("events", [])],
        "pagination": results.get("pagination"),
        "inactive_match_count": results.get("inactive_match_count", 0),
    })


async def cmd_public_search_raw(args):
    client = _get_client()
    results = await client.raw_public_search(args.query, limit=args.limit)
    _out({
        "success": True,
        "source": "gamma/public-search",
        "request": {"query": args.query, "limit": args.limit},
        "results": results,
    })


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
        result["quality"] = _format_quality(m)
        results.append(result)

    _out({"success": True, "markets": results})


async def cmd_orderbook(args):
    client = _get_client()
    market, error = await _resolve_market(
        client,
        query=args.query,
        outcome=args.outcome,
        market_slug=args.market_slug,
    )
    if error:
        _out(error)
        return

    token_id = market.get_token_id(args.outcome)
    if not token_id:
        available = market.outcomes or ([t.outcome for t in market.tokens] if market.tokens else [])
        _out({"success": False, "error": f"Outcome '{args.outcome}' not found. Available: {available}"})
        return

    book = client.get_orderbook(token_id)
    midpoint = client.get_midpoint(token_id)
    spread = client.get_spread(token_id)
    payload = {
        "success": True,
        "market": market.question,
        "outcome": args.outcome,
        "token_id": token_id,
        "midpoint": midpoint,
        "spread": spread,
    }
    if args.raw:
        payload["orderbook"] = book
    else:
        payload["bids"] = (book.get("bids") or [])[:args.depth]
        payload["asks"] = (book.get("asks") or [])[:args.depth]
    _out(payload)


async def cmd_price_history(args):
    client = _get_client()
    token_id = args.token_id
    market = None
    if not token_id:
        market, error = await _resolve_market(
            client,
            query=args.query,
            outcome=args.outcome,
            market_slug=args.market_slug,
        )
        if error:
            _out(error)
            return

        token_id = market.get_token_id(args.outcome)
        if not token_id:
            available = market.outcomes or ([t.outcome for t in market.tokens] if market.tokens else [])
            _out({"success": False, "error": f"Outcome '{args.outcome}' not found. Available: {available}"})
            return

    history = await client.get_price_history(
        token_id,
        interval=None if args.start_ts is not None or args.end_ts is not None else args.interval,
        fidelity=args.fidelity,
        start_ts=args.start_ts,
        end_ts=args.end_ts,
    )
    payload = {
        "success": True,
        "token_id": token_id,
        "market": market.question if market else None,
        "outcome": args.outcome if market else None,
    }
    if args.raw:
        payload["response"] = history
    else:
        payload["history"] = history.get("history", [])
    _out(payload)


async def cmd_market_trades(args):
    client = _get_client()
    condition_id = args.condition_id
    market = None
    if not condition_id:
        market, error = await _resolve_market(
            client,
            query=args.query,
            outcome=args.outcome,
            market_slug=args.market_slug,
        )
        if error:
            _out(error)
            return
        condition_id = market.condition_id

    payload = await client.get_market_trades_events(condition_id, limit=args.limit)
    _out({
        "success": True,
        "condition_id": condition_id,
        "market": market.question if market else None,
        "trades": payload,
    })


def _validation_summary(validation):
    return {
        "checks_passed": sum(1 for c in validation.checks if c.passed),
        "checks_warned": len(validation.warnings),
    }


async def _execute_trade(args, side: str):
    """Shared buy/sell handler. Side is 'buy' or 'sell'."""
    from pm_services import validate_pre_trade

    is_buy = side == "buy"
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS.", "error_code": "TRADING_NOT_CONFIGURED"})
        return

    market, error = await _resolve_market(
        client,
        query=args.query,
        outcome=args.outcome,
        market_slug=args.market_slug,
    )
    if error:
        _out(error)
        return

    # Resolve shares for sell (support --amount-usd as alternative to --shares)
    shares = None
    if not is_buy:
        if hasattr(args, "amount_usd") and args.amount_usd is not None:
            if not args.price:
                # Need a price to convert amount_usd to shares — use midpoint
                token_id = market.get_token_id(args.outcome)
                mid = client.get_midpoint(token_id) if token_id else None
                if not mid:
                    _out({"success": False, "error": "Cannot determine current price to convert --amount-usd to shares. Provide --price or use --shares directly.", "error_code": "PRICE_REQUIRED"})
                    return
                shares = args.amount_usd / mid
            else:
                shares = args.amount_usd / args.price
        elif hasattr(args, "shares") and args.shares is not None:
            shares = args.shares
        else:
            _out({"success": False, "error": "Sell requires --shares or --amount-usd", "error_code": "INVALID_INPUT"})
            return

    # Limit order input checks
    if not args.market_order:
        if is_buy and not args.price:
            _out({"success": False, "error": "Limit orders require --price", "error_code": "INVALID_INPUT"})
            return
        if not is_buy and not args.price:
            if not (hasattr(args, "amount_usd") and args.amount_usd is not None):
                _out({"success": False, "error": "Limit sells require --price", "error_code": "INVALID_INPUT"})
                return
        if args.price and not (0.01 <= args.price <= 0.99):
            _out({"success": False, "error": "Price must be between 0.01 and 0.99", "error_code": "INVALID_INPUT"})
            return
        if args.time_in_force == "GTD" and not args.expire_seconds:
            _out({"success": False, "error": "GTD orders require --expire-seconds", "error_code": "INVALID_INPUT"})
            return

    # Pre-trade validation
    usdc_balance = None
    book_depth = None
    token_id = market.get_token_id(args.outcome)

    if is_buy:
        try:
            usdc_balance = client.get_usdc_balance()
        except Exception:
            pass
        amount_usd = args.amount_usd
    else:
        amount_usd = shares * (args.price or 0.50)

    if args.market_order and token_id:
        try:
            book_depth = client.get_book_depth_usd(token_id, side="asks" if is_buy else "bids")
        except Exception:
            pass

    validation = validate_pre_trade(
        market=market,
        outcome=args.outcome,
        amount_usd=amount_usd if amount_usd > 0 else 1.0,
        price=args.price,
        is_market_order=args.market_order,
        skip_liquidity_check=args.skip_liquidity_check,
        skip_spread_check=args.skip_spread_check,
        usdc_balance=usdc_balance if is_buy else None,
        book_depth_usd=book_depth,
    )

    if not validation.can_trade:
        result = {
            "success": False,
            "error": "Pre-trade validation failed",
            "error_code": "VALIDATION_FAILED",
            "validation": {
                "checks": [c.model_dump() for c in validation.checks],
                "warnings": validation.warnings,
            },
        }
        if is_buy:
            balance_failed = any(c.name == "balance" and not c.passed for c in validation.checks)
            if balance_failed:
                try:
                    wallet_bal = client.get_wallet_usdc_balance()
                    if wallet_bal > 0:
                        result["hint"] = f"Your wallet has {wallet_bal:.2f} USDC.e on-chain but trading balance is {usdc_balance or 0:.2f}. Run 'approve-trading' to make wallet funds available for trading."
                except Exception:
                    pass
        _out(result)
        return

    # Execute the order
    try:
        if args.market_order:
            if is_buy:
                order_id = client.market_buy(
                    token_id=token_id, amount_usd=args.amount_usd,
                    neg_risk=market.neg_risk, order_type=args.market_tif,
                )
                _out({
                    "success": True, "action": "market_buy", "market": market.question,
                    "outcome": args.outcome, "amount_usd": args.amount_usd, "order_id": order_id,
                    "time_in_force": args.market_tif,
                    "builder": client.get_builder_status(),
                    "validation": _validation_summary(validation),
                })
            else:
                order_id = client.market_sell(
                    token_id=token_id, shares=shares,
                    neg_risk=market.neg_risk, order_type=args.market_tif,
                )
                _out({
                    "success": True, "action": "market_sell", "market": market.question,
                    "outcome": args.outcome, "shares": round(shares, 2), "order_id": order_id,
                    "time_in_force": args.market_tif,
                    "builder": client.get_builder_status(),
                    "validation": _validation_summary(validation),
                })
        else:
            if is_buy:
                buy_shares = args.amount_usd / args.price
                order_id = client.buy(
                    token_id=token_id, price=args.price, size=buy_shares,
                    neg_risk=market.neg_risk, order_type=args.time_in_force,
                    expire_seconds=args.expire_seconds,
                )
                _out({
                    "success": True, "action": "limit_buy", "market": market.question,
                    "outcome": args.outcome, "price": args.price,
                    "shares": round(buy_shares, 2), "cost_usd": args.amount_usd, "order_id": order_id,
                    "time_in_force": args.time_in_force,
                    "builder": client.get_builder_status(),
                    "validation": _validation_summary(validation),
                })
            else:
                order_id = client.sell(
                    token_id=token_id, price=args.price, size=shares,
                    neg_risk=market.neg_risk, order_type=args.time_in_force,
                    expire_seconds=args.expire_seconds,
                )
                _out({
                    "success": True, "action": "limit_sell", "market": market.question,
                    "outcome": args.outcome, "price": args.price,
                    "shares": round(shares, 2), "proceeds_usd": round(shares * args.price, 2), "order_id": order_id,
                    "time_in_force": args.time_in_force,
                    "builder": client.get_builder_status(),
                    "validation": _validation_summary(validation),
                })
    except Exception as e:
        error_str = str(e)
        _out({
            "success": False,
            "error": error_str if error_str else f"Order failed: {type(e).__name__}",
            "error_code": "ORDER_FAILED",
            "market": market.question,
            "outcome": args.outcome,
            "exception_type": type(e).__name__,
        })


async def cmd_buy(args):
    await _execute_trade(args, side="buy")


async def cmd_sell(args):
    await _execute_trade(args, side="sell")


async def cmd_balance(args):
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS.", "error_code": "TRADING_NOT_CONFIGURED"})
        return
    trading_balance = client.get_usdc_balance()
    wallet_balance = client.get_wallet_usdc_balance()
    pol_balance = client.get_pol_balance()
    result = {
        "success": True,
        "wallet_balance": wallet_balance,
        "trading_balance": trading_balance,
        "pol_balance": round(pol_balance, 6),
    }
    hints = []
    if wallet_balance > 0 and trading_balance == 0:
        hints.append("Wallet has USDC.e but trading balance is 0. Run 'approve-trading' to allow the exchange contract to access your funds.")
    if pol_balance < 0.001:
        hints.append("Very low POL balance. On-chain operations (approve-trading, redeem, split, merge) require POL for gas. Send a small amount of POL to your wallet.")
    if hints:
        result["hints"] = hints
    _out(result)


async def cmd_positions(args):
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS.", "error_code": "TRADING_NOT_CONFIGURED"})
        return
    positions = await client.get_positions()
    if args.raw:
        _out({"success": True, "positions": positions})
        return

    formatted = []
    redeemable_count = 0
    for p in positions:
        size = float(p.get("size", 0))
        if abs(size) < 0.01:
            continue
        cur_price = float(p.get("curPrice", 0))
        resolved = p.get("resolved", False)
        # Use API's redeemable field if present; fall back to heuristic
        api_redeemable = p.get("redeemable")
        if api_redeemable is not None:
            redeemable = bool(api_redeemable)
        else:
            redeemable = bool(resolved and cur_price >= 0.99)
        if redeemable:
            redeemable_count += 1
        formatted.append({
            "title": p.get("title", ""),
            "outcome": p.get("outcome", ""),
            "size": size,
            "avg_price": float(p.get("avgPrice", 0)),
            "current_price": cur_price,
            "initial_value": float(p.get("initialValue", 0)),
            "current_value": float(p.get("currentValue", 0)),
            "pnl": float(p.get("cashPnl", 0)),
            "pnl_pct": float(p.get("percentPnl", 0)),
            "end_date": p.get("endDate", ""),
            "condition_id": p.get("conditionId", ""),
            "resolved": resolved,
            "redeemable": redeemable,
        })
    _out({
        "success": True,
        "positions": formatted,
        "summary": {
            "total_positions": len(formatted),
            "redeemable_positions": redeemable_count,
        },
    })


async def cmd_trades(args):
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS.", "error_code": "TRADING_NOT_CONFIGURED"})
        return
    trades = await client.get_trades(limit=args.limit)
    _out({"success": True, "trades": trades})


async def cmd_my_orders(args):
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS.", "error_code": "TRADING_NOT_CONFIGURED"})
        return
    orders = client.get_open_orders_raw() if args.raw else client.get_open_orders()
    _out({"success": True, "orders": orders})


async def cmd_cancel_order(args):
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS.", "error_code": "TRADING_NOT_CONFIGURED"})
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
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS.", "error_code": "TRADING_NOT_CONFIGURED"})
        return
    info = client.is_filled(args.order_id)
    info["success"] = True
    _out(info)


async def cmd_builder_status(args):
    client = _get_client()
    _out({"success": True, "builder": client.get_builder_status()})


async def cmd_builder_trades(args):
    client = _get_client()
    trades = client.get_builder_trades(
        market=args.market,
        asset_id=args.asset_id,
        maker_address=args.maker_address,
        before=args.before,
        after=args.after,
    )
    _out({"success": True, "builder": client.get_builder_status(), "trades": trades[: args.limit]})


async def cmd_fund_assets(args):
    client = _get_client()
    assets = await client.get_supported_bridge_assets()
    if args.chain_id:
        assets = [asset for asset in assets if asset.get("chainId") == args.chain_id]
    if args.symbol:
        assets = [asset for asset in assets if (asset.get("token") or {}).get("symbol", "").lower() == args.symbol.lower()]
    _out({"success": True, "supported_assets": assets[: args.limit]})


async def cmd_fund_quote(args):
    client = _get_client()
    recipient_address = args.recipient_address or os.environ.get("EVM_WALLET_ADDRESS", "")
    if not recipient_address:
        _out({"success": False, "error": "Provide --recipient-address or set EVM_WALLET_ADDRESS"})
        return

    quote = await client.get_bridge_quote(
        from_chain_id=args.from_chain_id,
        from_token_address=args.from_token_address,
        recipient_address=recipient_address,
        to_chain_id=args.to_chain_id,
        to_token_address=args.to_token_address,
        from_amount_base_unit=args.from_amount_base_unit,
    )
    _out({"success": True, "recipient_address": recipient_address, "quote": quote})


async def cmd_fund_address(args):
    client = _get_client()
    address = args.address or os.environ.get("EVM_WALLET_ADDRESS", "")
    if not address:
        _out({"success": False, "error": "Provide --address or set EVM_WALLET_ADDRESS"})
        return

    deposit_address = await client.get_bridge_deposit_address(address)
    _out({
        "success": True,
        "recipient_address": address,
        "deposit_address": deposit_address,
        "next_step": "Send funds to this deposit address. Then check arrival with: fund-status --deposit-address <addr>. After funds arrive on Polygon, run 'approve-trading' to make them available for trading.",
    })


async def cmd_fund_status(args):
    client = _get_client()
    transactions = await client.get_bridge_status(args.deposit_address)
    has_completed = any(
        t.get("status", "").lower() in ("completed", "complete", "success")
        for t in (transactions if isinstance(transactions, list) else [])
    )
    result = {"success": True, "deposit_address": args.deposit_address, "transactions": transactions}
    if has_completed:
        result["next_step"] = "Funds have arrived. Run 'balance' to check, then 'approve-trading' if trading balance is still 0."
    elif transactions:
        result["next_step"] = "Bridge transaction in progress. Check again in a few minutes."
    else:
        result["next_step"] = "No transactions found for this deposit address. Funds may not have been sent yet."
    _out(result)


async def cmd_withdraw_quote(args):
    """Get a bridge quote for withdrawing from Polygon."""
    client = _get_client()
    recipient_address = args.recipient_address or os.environ.get("EVM_WALLET_ADDRESS", "")
    if not recipient_address:
        _out({"success": False, "error": "Provide --recipient-address or set EVM_WALLET_ADDRESS"})
        return

    quote = await client.get_bridge_quote(
        from_chain_id="137",
        from_token_address="0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        recipient_address=recipient_address,
        to_chain_id=args.to_chain_id,
        to_token_address=args.to_token_address,
        from_amount_base_unit=args.from_amount_base_unit,
    )
    _out({"success": True, "recipient_address": recipient_address, "quote": quote})


async def cmd_withdraw_address(args):
    """Initiate a bridge withdrawal and get the withdrawal address."""
    client = _get_client()
    address = args.address or os.environ.get("EVM_WALLET_ADDRESS", "")
    if not address:
        _out({"success": False, "error": "Provide --address or set EVM_WALLET_ADDRESS"})
        return

    result = await client.initiate_bridge_withdrawal(address)
    _out({"success": True, "address": address, "withdrawal": result})


async def cmd_withdraw_status(args):
    """Check withdrawal transaction status (reuses bridge status endpoint)."""
    client = _get_client()
    transactions = await client.get_bridge_status(args.deposit_address)
    _out({"success": True, "deposit_address": args.deposit_address, "transactions": transactions})


async def cmd_geoblock(args):
    client = _get_client()
    result = await client.get_geoblock(ip=args.ip)
    result["success"] = True
    _out(result)


async def cmd_readiness(args):
    client = _get_client()
    geoblock = await client.get_geoblock(ip=args.ip)
    builder = client.get_builder_status()
    trading_balance = client.get_usdc_balance() if client.has_trading else None
    wallet_balance = client.get_wallet_usdc_balance() if client.has_trading else None
    pol_balance = client.get_pol_balance() if client.has_trading else None

    warnings = []

    # Signature type validation
    sig_type = int(os.environ.get("POLY_SIGNATURE_TYPE", "0"))
    if sig_type in (1, 2) and not os.environ.get("POLY_FUNDER_ADDRESS"):
        sig_label = {1: "Proxy/MagicLink", 2: "Gnosis Safe"}.get(sig_type, str(sig_type))
        warnings.append(f"POLY_SIGNATURE_TYPE is {sig_type} ({sig_label}) but POLY_FUNDER_ADDRESS is not set. This will cause order failures. Set it to your proxy/safe contract address.")

    # CLOB init failure
    if os.environ.get("EVM_PRIVATE_KEY") and os.environ.get("EVM_WALLET_ADDRESS") and not client.has_trading:
        init_err = client._clob_init_error
        msg = "EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS are set but CLOB client failed to initialize."
        if init_err:
            msg += f" Reason: {init_err}"
        warnings.append(msg)

    # POL gas warning
    if pol_balance is not None and pol_balance < 0.001:
        warnings.append("Very low POL balance. On-chain operations (approve-trading, redeem, split, merge) require POL for gas.")

    if geoblock.get("blocked"):
        next_action = "Trading blocked in this geography. Stop before placing orders."
    elif not client.has_trading:
        if warnings:
            next_action = warnings[0]
        else:
            next_action = "Configure EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS to enable trading."
    elif trading_balance is not None and trading_balance <= 0:
        if wallet_balance and wallet_balance > 0:
            next_action = "Wallet has USDC.e but trading balance is 0. Run 'approve-trading' to allow the exchange contract to access your funds."
        else:
            next_action = "Get a bridge quote or deposit address, fund the wallet, then re-run readiness."
    elif not builder.get("can_builder_auth"):
        next_action = "Trading is possible, but builder attribution is disabled. Configure builder credentials for leaderboard credit."
    else:
        next_action = "Ready for one-shot research and trading."

    result = {
        "success": True,
        "wallet_address": os.environ.get("EVM_WALLET_ADDRESS"),
        "funder_address": os.environ.get("POLY_FUNDER_ADDRESS", os.environ.get("EVM_WALLET_ADDRESS")),
        "signature_type": sig_type,
        "trading_configured": client.has_trading,
        "wallet_balance": wallet_balance,
        "trading_balance": trading_balance,
        "pol_balance": round(pol_balance, 6) if pol_balance is not None else None,
        "builder": builder,
        "geoblock": geoblock,
        "next_action": next_action,
    }
    if warnings:
        result["warnings"] = warnings
    _out(result)


async def cmd_approve_trading(args):
    client = _get_client()
    if not client.has_trading:
        _out({"success": False, "error": "Trading not configured. Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS.", "error_code": "TRADING_NOT_CONFIGURED"})
        return
    try:
        client.approve_trading()
        trading_balance = client.get_usdc_balance()
        wallet_balance = client.get_wallet_usdc_balance()
        _out({
            "success": True,
            "message": "Exchange contract approved to spend USDC.e.",
            "wallet_balance": wallet_balance,
            "trading_balance": trading_balance,
            "next_step": "You can now place trades. Run 'readiness' for a full status check or 'buy' to start trading.",
        })
    except Exception as e:
        err_str = str(e).lower()
        if "insufficient funds" in err_str or "gas" in err_str:
            _out({"success": False, "error": "Approve failed: insufficient POL for gas. Send a small amount of POL (Polygon's native token) to your wallet for transaction fees."})
        else:
            _out({"success": False, "error": f"Approve failed: {e}"})


# ---------------------------------------------------------------------------
# NEW commands
# ---------------------------------------------------------------------------

async def cmd_assess(args):
    """Single-market quality report with orderbook snapshot."""
    client = _get_client()
    market, error = await _resolve_market(
        client,
        query=args.query,
        outcome=args.outcome,
        market_slug=args.market_slug,
    )
    if error:
        _out(error)
        return

    quality = _format_quality(market)

    # Get orderbook snapshot for primary outcome
    outcome = args.outcome or "Yes"
    token_id = market.get_token_id(outcome)
    orderbook_snapshot = None
    if token_id:
        try:
            midpoint = client.get_midpoint(token_id)
            spread = client.get_spread(token_id)
            bid_depth = client.get_book_depth_usd(token_id, side="bids")
            ask_depth = client.get_book_depth_usd(token_id, side="asks")
            orderbook_snapshot = {
                "outcome": outcome,
                "token_id": token_id,
                "midpoint": midpoint,
                "spread": spread,
                "bid_depth_usd": round(bid_depth, 2),
                "ask_depth_usd": round(ask_depth, 2),
            }
        except Exception as e:
            orderbook_snapshot = {"error": str(e)}

    _out({
        "success": True,
        "market": _format_candidate(market),
        "quality": quality,
        "orderbook": orderbook_snapshot,
    })


async def cmd_validate_trade(args):
    """Dry-run pre-trade validation without placing an order."""
    from pm_services import validate_pre_trade

    client = _get_client()
    market, error = await _resolve_market(
        client,
        query=args.query,
        outcome=args.outcome,
        market_slug=args.market_slug,
    )
    if error:
        _out(error)
        return

    usdc_balance = None
    book_depth = None
    if client.has_trading:
        try:
            usdc_balance = client.get_usdc_balance()
        except Exception:
            pass

    if args.market_order:
        token_id = market.get_token_id(args.outcome)
        if token_id:
            side = "asks" if args.side == "buy" else "bids"
            try:
                book_depth = client.get_book_depth_usd(token_id, side=side)
            except Exception:
                pass

    validation = validate_pre_trade(
        market=market,
        outcome=args.outcome,
        amount_usd=args.amount_usd,
        price=args.price,
        is_market_order=args.market_order,
        skip_liquidity_check=args.skip_liquidity_check,
        skip_spread_check=args.skip_spread_check,
        usdc_balance=usdc_balance,
        book_depth_usd=book_depth,
    )

    _out({
        "success": True,
        "market": market.question,
        "market_slug": market.slug or market.market_slug,
        "outcome": args.outcome,
        "amount_usd": args.amount_usd,
        "can_trade": validation.can_trade,
        "checks": [c.model_dump() for c in validation.checks],
        "warnings": validation.warnings,
    })


async def cmd_top_markets(args):
    """Top N markets by quality score."""
    client = _get_client()
    markets = await client.get_top_markets(limit=args.limit, tag=args.tag)
    _out({
        "success": True,
        "markets": [_format_market(m) for m in markets],
    })


async def cmd_split(args):
    """Split USDC.e into YES + NO outcome tokens."""
    client = _get_client()
    condition_id = args.condition_id
    neg_risk = False

    if not condition_id:
        market, error = await _resolve_market(
            client,
            query=args.query,
            outcome=None,
            market_slug=args.market_slug,
        )
        if error:
            _out(error)
            return
        condition_id = market.condition_id
        neg_risk = getattr(market, "neg_risk", False)
        if not condition_id:
            _out({"success": False, "error": "Could not determine condition_id for this market"})
            return

    result = client.split_position(condition_id, args.amount_usdc, neg_risk=neg_risk)
    result["success"] = result.get("status") != "failed"
    result["condition_id"] = condition_id
    if not result["success"]:
        result["error"] = "Transaction reverted on-chain. Check that you have sufficient USDC.e and POL for gas."
    _out(result)


async def cmd_merge(args):
    """Merge YES + NO outcome tokens back into USDC.e."""
    client = _get_client()
    condition_id = args.condition_id
    neg_risk = False

    if not condition_id:
        market, error = await _resolve_market(
            client,
            query=args.query,
            outcome=None,
            market_slug=args.market_slug,
        )
        if error:
            _out(error)
            return
        condition_id = market.condition_id
        neg_risk = getattr(market, "neg_risk", False)
        if not condition_id:
            _out({"success": False, "error": "Could not determine condition_id for this market"})
            return

    result = client.merge_positions(condition_id, args.amount_usdc, neg_risk=neg_risk)
    result["success"] = result.get("status") != "failed"
    result["condition_id"] = condition_id
    if not result["success"]:
        result["error"] = "Transaction reverted on-chain. Check that you have sufficient outcome tokens and POL for gas."
    _out(result)


async def cmd_redeem(args):
    """Redeem resolved CTF positions back to USDC.e."""
    client = _get_client()
    condition_id = args.condition_id
    market = None

    if not condition_id:
        market, error = await _resolve_market(
            client,
            query=args.query,
            outcome=None,
            market_slug=args.market_slug,
        )
        if error:
            _out(error)
            return
        condition_id = market.condition_id
        if not condition_id:
            _out({"success": False, "error": "Could not determine condition_id for this market"})
            return

    # Warn if market is not yet resolved (resolution can lag hours/days after end date)
    resolution_warning = None
    if market and not getattr(market, "resolved", False):
        end_date = getattr(market, "end_date_iso", None) or getattr(market, "expiration_date", None)
        resolution_warning = "This market does not appear to be resolved yet. Resolution can take hours or days after the event concludes while Polymarket waits for oracle confirmation."
        if end_date:
            resolution_warning += f" End date: {end_date}."
        resolution_warning += " Proceeding anyway, but the transaction may revert (wasting gas)."

    result = client.redeem_positions(condition_id)
    result["success"] = result.get("status") != "failed"
    result["condition_id"] = condition_id
    if not result["success"]:
        result["error"] = "Transaction reverted on-chain. The market may not be resolved yet — resolution can take hours or days after the event ends. Check back later."
    if resolution_warning:
        result["warning"] = resolution_warning
    _out(result)


async def cmd_config(args):
    """Show environment/configuration status."""
    client = _get_client()
    sig_type = int(os.environ.get("POLY_SIGNATURE_TYPE", "0"))
    sig_type_label = {0: "EOA", 1: "Proxy", 2: "Gnosis Safe"}.get(sig_type, f"Unknown ({sig_type})")
    config = {
        "wallet_address": os.environ.get("EVM_WALLET_ADDRESS", ""),
        "funder_address": os.environ.get("POLY_FUNDER_ADDRESS", os.environ.get("EVM_WALLET_ADDRESS", "")),
        "signature_type": sig_type,
        "signature_type_label": sig_type_label,
        "trading_configured": client.has_trading,
        "builder": client.get_builder_status(),
        "has_private_key": bool(os.environ.get("EVM_PRIVATE_KEY")),
        "quality_thresholds": {
            "min_liquidity_usd": 5000,
            "max_spread_limit": 0.10,
            "book_depth_multiplier": 1.5,
        },
    }
    # Surface CLOB init failure reason
    if not client.has_trading and os.environ.get("EVM_PRIVATE_KEY") and os.environ.get("EVM_WALLET_ADDRESS"):
        config["clob_init_error"] = client._clob_init_error or "Unknown error during CLOB initialization"
    # Warn about proxy misconfiguration
    warnings = []
    if sig_type in (1, 2) and not os.environ.get("POLY_FUNDER_ADDRESS"):
        warnings.append(f"POLY_SIGNATURE_TYPE={sig_type} ({sig_type_label}) but POLY_FUNDER_ADDRESS is not set. Set it to your proxy/safe contract address.")
    if warnings:
        config["warnings"] = warnings
    _out({"success": True, "config": config})


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Polymarket CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # search
    p = sub.add_parser("search", help="Search markets (quality-ranked)")
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--tag", default=None, help="Filter by tag (crypto, politics, sports, etc.)")

    # markets-raw
    p = sub.add_parser("markets-raw", help="Raw Gamma market search/list response")
    p.add_argument("--query", default=None)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--active", default="true", choices=["true", "false", "any"])
    p.add_argument("--closed", default="false", choices=["true", "false", "any"])
    p.add_argument("--archived", default="false", choices=["true", "false", "any"])
    p.add_argument("--tag", default=None, help="Filter by tag (crypto, politics, sports, etc.)")
    p.add_argument("--order", default="volume24hr", help="Gamma sort field")
    p.add_argument("--ascending", default="false", choices=["true", "false", "any"])

    # public-search
    p = sub.add_parser("public-search", help="Search events via Polymarket public-search")
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--market-limit", type=int, default=3)

    # public-search-raw
    p = sub.add_parser("public-search-raw", help="Raw Polymarket public-search response")
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=10)

    # events
    p = sub.add_parser("events", help="Search Polymarket events")
    p.add_argument("--query", default=None)
    p.add_argument("--slug", default=None, help="Exact event slug lookup (bypasses fuzzy search)")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--tag", default=None, help="Filter by tag (crypto, politics, sports, etc.)")
    p.add_argument("--market-limit", type=int, default=3, help="Markets to include per event")

    # events-raw
    p = sub.add_parser("events-raw", help="Raw Gamma event search/list response")
    p.add_argument("--query", default=None)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--active", default="true", choices=["true", "false", "any"])
    p.add_argument("--closed", default="false", choices=["true", "false", "any"])
    p.add_argument("--archived", default="false", choices=["true", "false", "any"])
    p.add_argument("--tag", default=None, help="Filter by tag (crypto, politics, sports, etc.)")
    p.add_argument("--order", default="volume24hr", help="Gamma sort field")
    p.add_argument("--ascending", default="false", choices=["true", "false", "any"])

    # trending
    p = sub.add_parser("trending", help="Trending markets")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--sort", default="volume", choices=["volume", "liquidity", "ending"])

    # odds
    p = sub.add_parser("odds", help="Get odds for a specific event")
    p.add_argument("--query", required=True)

    # resolve
    p = sub.add_parser("resolve", help="Resolve a query to a unique market or a candidate list")
    p.add_argument("--query", default=None, help="Market search query")
    p.add_argument("--market-slug", default=None, help="Exact market slug")
    p.add_argument("--outcome", default=None, help="Optional outcome to narrow candidates")

    # orderbook
    p = sub.add_parser("orderbook", help="Get order book depth")
    p.add_argument("--query", default=None, help="Market search query")
    p.add_argument("--market-slug", default=None, help="Exact market slug from `resolve`")
    p.add_argument("--outcome", default="Yes", help="Outcome (Yes/No)")
    p.add_argument("--depth", type=int, default=10, help="Number of levels")
    p.add_argument("--raw", action="store_true", help="Return the full upstream orderbook payload")

    # price-history
    p = sub.add_parser("price-history", help="Get price history for a market outcome token")
    p.add_argument("--query", default=None, help="Market search query")
    p.add_argument("--market-slug", default=None, help="Exact market slug from `resolve`")
    p.add_argument("--outcome", default="Yes", help="Outcome used to resolve token id")
    p.add_argument("--token-id", default=None, help="Direct token id override")
    p.add_argument("--interval", default="1w", help="Range shorthand, e.g. 1d, 1w, 1m, max")
    p.add_argument("--fidelity", type=int, default=None, help="Sampling fidelity required by some ranges")
    p.add_argument("--start-ts", type=int, default=None, help="Explicit start timestamp (unix seconds)")
    p.add_argument("--end-ts", type=int, default=None, help="Explicit end timestamp (unix seconds)")
    p.add_argument("--raw", action="store_true", help="Return the full upstream price-history response")

    # market-trades
    p = sub.add_parser("market-trades", help="Get market trade events")
    p.add_argument("--condition-id", default=None, help="Direct condition id override")
    p.add_argument("--query", default=None, help="Market search query")
    p.add_argument("--market-slug", default=None, help="Exact market slug from `resolve`")
    p.add_argument("--outcome", default="Yes")
    p.add_argument("--limit", type=int, default=20)

    # buy
    p = sub.add_parser("buy", help="Buy outcome shares (with pre-trade validation)")
    p.add_argument("--query", default=None, help="Market search query")
    p.add_argument("--market-slug", default=None, help="Exact market slug from `resolve`")
    p.add_argument("--outcome", required=True, help="Outcome to buy (e.g. Yes, No)")
    p.add_argument("--price", type=float, default=None, help="Limit price 0.01-0.99 (omit for market order)")
    p.add_argument("--amount-usd", type=float, required=True, help="USD amount to spend")
    p.add_argument("--market-order", action="store_true", help="Use FOK market order instead of limit")
    p.add_argument("--market-tif", default="FOK", choices=["FOK", "FAK"], help="Time in force for market orders")
    p.add_argument("--time-in-force", default="GTC", choices=["GTC", "FAK", "GTD"], help="Time in force for limit orders")
    p.add_argument("--expire-seconds", type=int, default=None, help="Required for GTD orders")
    p.add_argument("--skip-liquidity-check", action="store_true", help="Bypass minimum liquidity check")
    p.add_argument("--skip-spread-check", action="store_true", help="Bypass maximum spread check")

    # sell
    p = sub.add_parser("sell", help="Sell outcome shares (with pre-trade validation)")
    p.add_argument("--query", default=None, help="Market search query")
    p.add_argument("--market-slug", default=None, help="Exact market slug from `resolve`")
    p.add_argument("--outcome", required=True, help="Outcome to sell")
    p.add_argument("--price", type=float, default=None, help="Limit price 0.01-0.99")
    p.add_argument("--shares", type=float, default=None, help="Number of shares to sell (or use --amount-usd)")
    p.add_argument("--amount-usd", type=float, default=None, help="USD amount to sell (alternative to --shares, requires --price or uses midpoint)")
    p.add_argument("--market-order", action="store_true", help="Sell immediately at available book prices")
    p.add_argument("--market-tif", default="FOK", choices=["FOK", "FAK"], help="Time in force for market sells")
    p.add_argument("--time-in-force", default="GTC", choices=["GTC", "FAK", "GTD"], help="Time in force for limit sells")
    p.add_argument("--expire-seconds", type=int, default=None, help="Required for GTD orders")
    p.add_argument("--skip-liquidity-check", action="store_true", help="Bypass minimum liquidity check")
    p.add_argument("--skip-spread-check", action="store_true", help="Bypass maximum spread check")

    # balance
    sub.add_parser("balance", help="Check USDC.e balance (wallet and trading)")

    # approve-trading
    sub.add_parser("approve-trading", help="Approve exchange contract to spend wallet USDC.e")

    # positions
    p = sub.add_parser("positions", help="View current positions and P&L")
    p.add_argument("--raw", action="store_true", help="Return the raw positions payload from Polymarket")

    # trades
    p = sub.add_parser("trades", help="View recent trade history")
    p.add_argument("--limit", type=int, default=20)

    # my-orders
    p = sub.add_parser("my-orders", help="List open orders")
    p.add_argument("--raw", action="store_true", help="Return the raw open-order payload from the CLOB client")

    # cancel-order
    p = sub.add_parser("cancel-order", help="Cancel orders")
    p.add_argument("--order-id", default=None, help="Specific order to cancel")
    p.add_argument("--all", action="store_true", help="Cancel all open orders")

    # check-order
    p = sub.add_parser("check-order", help="Check order fill status")
    p.add_argument("--order-id", required=True)

    # builder-status
    sub.add_parser("builder-status", help="Check builder attribution status")

    # builder-trades
    p = sub.add_parser("builder-trades", help="List trades attributed to the configured builder")
    p.add_argument("--market", default=None, help="Condition id filter used by builder trades API")
    p.add_argument("--asset-id", default=None, help="Token id filter")
    p.add_argument("--maker-address", default=None)
    p.add_argument("--before", type=int, default=None)
    p.add_argument("--after", type=int, default=None)
    p.add_argument("--limit", type=int, default=50)

    # fund-assets
    p = sub.add_parser("fund-assets", help="List bridge-supported assets for Polymarket funding")
    p.add_argument("--chain-id", default=None, help="Optional chain id filter")
    p.add_argument("--symbol", default=None, help="Optional token symbol filter")
    p.add_argument("--limit", type=int, default=50)

    # fund-quote
    p = sub.add_parser("fund-quote", help="Get a bridge quote into Polymarket-compatible USDC.e")
    p.add_argument("--from-chain-id", required=True)
    p.add_argument("--from-token-address", required=True)
    p.add_argument("--from-amount-base-unit", required=True, help="Raw token amount in base units")
    p.add_argument("--to-chain-id", default="137")
    p.add_argument("--to-token-address", default="0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
    p.add_argument("--recipient-address", default=None, help="Defaults to EVM_WALLET_ADDRESS")

    # fund-address
    p = sub.add_parser("fund-address", help="Create bridge deposit addresses for a wallet")
    p.add_argument("--address", default=None, help="Defaults to EVM_WALLET_ADDRESS")

    # fund-status
    p = sub.add_parser("fund-status", help="Check bridge transaction status for a deposit address")
    p.add_argument("--deposit-address", required=True)

    # withdraw-quote
    p = sub.add_parser("withdraw-quote", help="Get a bridge quote for withdrawing from Polygon")
    p.add_argument("--to-chain-id", required=True, help="Destination chain id (e.g. 1 for Ethereum)")
    p.add_argument("--to-token-address", required=True, help="Destination token contract address")
    p.add_argument("--from-amount-base-unit", required=True, help="USDC.e amount in base units (6 decimals)")
    p.add_argument("--recipient-address", default=None, help="Defaults to EVM_WALLET_ADDRESS")

    # withdraw-address
    p = sub.add_parser("withdraw-address", help="Initiate a bridge withdrawal from Polygon")
    p.add_argument("--address", default=None, help="Defaults to EVM_WALLET_ADDRESS")

    # withdraw-status
    p = sub.add_parser("withdraw-status", help="Check withdrawal transaction status")
    p.add_argument("--deposit-address", required=True, help="Address from withdraw-address")

    # geoblock
    p = sub.add_parser("geoblock", help="Check whether the current IP is geographically blocked")
    p.add_argument("--ip", default=None, help="Optional IP override if the endpoint supports it")

    # readiness
    p = sub.add_parser("readiness", help="One-shot readiness check: geography, balance, and builder attribution")
    p.add_argument("--ip", default=None, help="Optional IP override if the endpoint supports it")

    # --- NEW COMMANDS ---

    # assess
    p = sub.add_parser("assess", help="Single-market quality report with orderbook snapshot")
    p.add_argument("--query", default=None, help="Market search query")
    p.add_argument("--market-slug", default=None, help="Exact market slug")
    p.add_argument("--outcome", default=None, help="Focus outcome for orderbook (default: Yes)")

    # validate-trade
    p = sub.add_parser("validate-trade", help="Dry-run pre-trade validation (no order placed)")
    p.add_argument("--query", default=None, help="Market search query")
    p.add_argument("--market-slug", default=None, help="Exact market slug")
    p.add_argument("--outcome", required=True, help="Outcome to validate")
    p.add_argument("--amount-usd", type=float, required=True, help="USD amount")
    p.add_argument("--price", type=float, default=None, help="Limit price (omit for market order check)")
    p.add_argument("--side", default="buy", choices=["buy", "sell"], help="Trade side")
    p.add_argument("--market-order", action="store_true", help="Validate as market order")
    p.add_argument("--skip-liquidity-check", action="store_true", help="Bypass minimum liquidity check")
    p.add_argument("--skip-spread-check", action="store_true", help="Bypass maximum spread check")

    # top-markets
    p = sub.add_parser("top-markets", help="Top N markets by composite quality score")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--tag", default=None, help="Optional tag filter (crypto, politics, sports, etc.)")

    # redeem
    p = sub.add_parser("redeem", help="Redeem resolved CTF positions back to USDC.e")
    p.add_argument("--condition-id", default=None, help="Direct condition id")
    p.add_argument("--market-slug", default=None, help="Resolve condition id from market slug")
    p.add_argument("--query", default=None, help="Market search query")

    # split
    p = sub.add_parser("split", help="Split USDC.e into YES + NO outcome tokens")
    p.add_argument("--condition-id", default=None, help="Direct condition id")
    p.add_argument("--market-slug", default=None, help="Resolve condition id from market slug")
    p.add_argument("--query", default=None, help="Market search query")
    p.add_argument("--amount-usdc", type=float, required=True, help="USDC amount to split")

    # merge
    p = sub.add_parser("merge", help="Merge YES + NO outcome tokens back into USDC.e")
    p.add_argument("--condition-id", default=None, help="Direct condition id")
    p.add_argument("--market-slug", default=None, help="Resolve condition id from market slug")
    p.add_argument("--query", default=None, help="Market search query")
    p.add_argument("--amount-usdc", type=float, required=True, help="USDC amount to merge")

    # config
    sub.add_parser("config", help="Show environment and configuration status")

    args = parser.parse_args()

    handler = {
        "events": cmd_events,
        "events-raw": cmd_events_raw,
        "search": cmd_search,
        "markets-raw": cmd_markets_raw,
        "public-search": cmd_public_search,
        "public-search-raw": cmd_public_search_raw,
        "trending": cmd_trending,
        "odds": cmd_odds,
        "resolve": cmd_resolve,
        "orderbook": cmd_orderbook,
        "price-history": cmd_price_history,
        "market-trades": cmd_market_trades,
        "buy": cmd_buy,
        "sell": cmd_sell,
        "balance": cmd_balance,
        "approve-trading": cmd_approve_trading,
        "positions": cmd_positions,
        "trades": cmd_trades,
        "my-orders": cmd_my_orders,
        "cancel-order": cmd_cancel_order,
        "check-order": cmd_check_order,
        "builder-status": cmd_builder_status,
        "builder-trades": cmd_builder_trades,
        "fund-assets": cmd_fund_assets,
        "fund-quote": cmd_fund_quote,
        "fund-address": cmd_fund_address,
        "fund-status": cmd_fund_status,
        "withdraw-quote": cmd_withdraw_quote,
        "withdraw-address": cmd_withdraw_address,
        "withdraw-status": cmd_withdraw_status,
        "geoblock": cmd_geoblock,
        "readiness": cmd_readiness,
        # New commands
        "redeem": cmd_redeem,
        "split": cmd_split,
        "merge": cmd_merge,
        "assess": cmd_assess,
        "validate-trade": cmd_validate_trade,
        "top-markets": cmd_top_markets,
        "config": cmd_config,
    }[args.command]

    try:
        asyncio.run(handler(args))
    except Exception as e:
        error_str = str(e)
        error_code = "UNKNOWN_ERROR"
        hint = None
        err_lower = error_str.lower()
        if "insufficient funds" in err_lower or "gas" in err_lower:
            error_code = "INSUFFICIENT_GAS"
            hint = "Send a small amount of POL (Polygon's native token) to your wallet for transaction fees."
        elif "allowance" in err_lower:
            error_code = "ALLOWANCE_ERROR"
            hint = "Run 'approve-trading' to authorize the exchange contract."
        elif "429" in error_str or "rate" in err_lower:
            error_code = "RATE_LIMITED"
            hint = "Too many requests. Wait a moment and try again."
        elif "timeout" in err_lower or "timed out" in err_lower:
            error_code = "TIMEOUT"
            hint = "Request timed out. Check network connectivity and try again."
        elif "order rejected" in err_lower or "order failed" in err_lower:
            error_code = "ORDER_REJECTED"
        result = {"success": False, "error": error_str, "error_code": error_code}
        if hint:
            result["hint"] = hint
        _out(result)
        sys.exit(1)


if __name__ == "__main__":
    main()
