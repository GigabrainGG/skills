#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "pydantic", "py-clob-client", "eth-account", "web3"]
# ///
"""Polymarket deep research - quality-aware market research, thesis generation, and comparison.

Run with:
  uv run pm_deep_research.py research --query "..."
  uv run pm_deep_research.py thesis --query "..." --outcome Yes
  uv run pm_deep_research.py compare --query "..."
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_ROOT = SCRIPT_DIR.parent.parent
POLYMARKET_SCRIPTS_DIR = SKILLS_ROOT / "polymarket" / "scripts"
sys.path.insert(0, str(POLYMARKET_SCRIPTS_DIR))

from pm_services import (  # noqa: E402
    PMClient,
    Market,
    MarketQuality,
    compute_market_quality,
    score_relevance,
    _get_market_liquidity,
    _get_market_volume,
    _get_market_spread,
    _market_search_text,
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


def _format_quality(market: Market) -> dict:
    q = market.quality
    return {
        "tradability_score": q.tradability_score,
        "liquidity_usd": q.liquidity_usd,
        "volume_24h_usd": q.volume_24h_usd,
        "spread_pct": q.spread_pct,
        "is_tradable": q.is_tradable,
        "warnings": q.warnings,
    }


def _format_market(m: Market, focus_outcome: str | None = None, orderbook: dict | None = None) -> dict:
    payload = {
        "slug": m.slug or m.market_slug,
        "market_slug": m.market_slug,
        "question": m.question,
        "description": m.description,
        "category": m.category,
        "yes_price": m.yes_price,
        "volume": m.volume_24hr or m.volume_num or m.volume or 0,
        "liquidity": m.liquidity_num or m.liquidity or 0,
        "end_date": m.end_date.isoformat() if m.end_date else None,
        "neg_risk": m.neg_risk,
        "outcomes": m.outcomes or [t.outcome for t in (m.tokens or [])],
        "tokens": [
            {"outcome": t.outcome, "price": t.price, "token_id": t.token_id}
            for t in (m.tokens or [])
        ],
        "quality": _format_quality(m),
    }
    if focus_outcome:
        payload["focus_outcome"] = focus_outcome
        payload["focus_token_id"] = m.get_token_id(focus_outcome)
    if orderbook is not None:
        payload["orderbook"] = orderbook
    return payload


def _format_event(event: dict, market_limit: int) -> dict:
    markets = []
    for raw_market in (event.get("markets") or [])[:market_limit]:
        try:
            markets.append(_format_market(Market.model_validate(raw_market)))
        except Exception:
            markets.append({
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

    return {
        "id": event.get("id"),
        "slug": event.get("slug"),
        "title": event.get("title") or event.get("question") or event.get("slug") or "",
        "description": event.get("description"),
        "volume": event.get("volume24hr") or event.get("volume") or 0,
        "liquidity": event.get("liquidity") or 0,
        "end_date": event.get("endDate") or event.get("resolutionDate"),
        "category": event.get("category"),
        "markets": markets,
    }


def _format_public_event(event: dict, market_limit: int) -> dict:
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
        "markets": [
            {
                "slug": market.get("slug") or market.get("marketSlug"),
                "question": market.get("question") or market.get("title") or "",
                "condition_id": market.get("conditionId"),
                "active": market.get("active"),
                "closed": market.get("closed"),
                "archived": market.get("archived"),
                "accepting_orders": market.get("acceptingOrders"),
                "ready": market.get("ready"),
                "best_bid": market.get("bestBid"),
                "best_ask": market.get("bestAsk"),
                "spread": market.get("spread"),
                "last_trade_price": market.get("lastTradePrice"),
                "volume": market.get("volume24hr") or market.get("volume") or 0,
                "liquidity": market.get("liquidityClob") or market.get("liquidity") or 0,
                "outcomes": _parse_jsonish(market.get("outcomes")),
                "token_ids": _parse_jsonish(market.get("clobTokenIds")),
            }
            for market in (event.get("markets") or [])[:market_limit]
        ],
    }


async def _run_external_research(query: str, outcome: str | None, markets: list[dict]) -> dict | None:
    api_url = os.environ.get("GIGABRAIN_API_URL", "").rstrip("/")
    api_key = os.environ.get("GIGABRAIN_API_KEY", "")
    if not api_url:
        return None

    prompt = (
        "You are preparing a pre-trade Polymarket research brief.\n"
        f"User query: {query}\n"
        + (f"Focus outcome: {outcome}\n" if outcome else "")
        + "Candidate Polymarket markets:\n"
        + json.dumps(markets[:3], default=str)
        + "\nReturn a concise analysis with:\n"
          "1. evidence for the current market price\n"
          "2. evidence against it\n"
          "3. upcoming catalysts and dates\n"
          "4. resolution/wording traps or hidden risks\n"
          "5. what to monitor next\n"
          "Use dated evidence and mention sources where possible."
    )

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=120, headers=headers) as client:
        resp = await client.post(f"{api_url}/v1/chat", json={"message": prompt})
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content") or data.get("message") or str(data)
        return {"summary": content}


async def _run_thesis_research(query: str, outcome: str, market: dict) -> dict | None:
    """Generate a structured thesis via external research."""
    api_url = os.environ.get("GIGABRAIN_API_URL", "").rstrip("/")
    api_key = os.environ.get("GIGABRAIN_API_KEY", "")
    if not api_url:
        return None

    prompt = (
        "You are generating a structured Polymarket trade thesis.\n"
        f"Market: {market.get('question', '')}\n"
        f"Slug: {market.get('slug', '')}\n"
        f"Current Yes price: {market.get('yes_price', 'unknown')}\n"
        f"Focus outcome: {outcome}\n"
        f"Liquidity: ${market.get('liquidity', 0):,.0f}\n"
        f"Volume 24h: ${market.get('volume', 0):,.0f}\n"
        f"End date: {market.get('end_date', 'unknown')}\n"
        "\nProvide a structured thesis with:\n"
        "1. CONVICTION SCORE (0-100): How confident is this trade?\n"
        "2. RECOMMENDED SIZING: What % of available capital? (conservative/moderate/aggressive)\n"
        "3. TARGET PRICE: What price represents fair value?\n"
        "4. STOP PRICE: At what price should you exit?\n"
        "5. KEY CATALYSTS: Upcoming events with dates that could move this market\n"
        "6. BULL CASE: Evidence supporting the outcome\n"
        "7. BEAR CASE: Evidence against the outcome\n"
        "8. MONITORING TRIGGERS: What signals to watch for position changes\n"
        "9. RESOLUTION RISKS: Wording traps or ambiguities in market resolution\n"
        "\nUse dated evidence and mention sources where possible."
    )

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=120, headers=headers) as client:
        resp = await client.post(f"{api_url}/v1/chat", json={"message": prompt})
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content") or data.get("message") or str(data)
        return {"thesis": content}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

async def cmd_research(args):
    """Quality-aware research across events, markets, and external sources."""
    client = PMClient()
    try:
        public_search = await client.public_search(args.query, limit=args.limit)
        events = await client.get_events(query=args.query, limit=args.limit, tag=args.tag)
        markets = await client.search_markets(args.query, limit=args.limit)

        market_payloads = []
        for market in markets:
            orderbook = None
            if args.outcome:
                token_id = market.get_token_id(args.outcome)
                if token_id:
                    orderbook = {
                        "midpoint": client.get_midpoint(token_id),
                        "spread": client.get_spread(token_id),
                    }
            market_payloads.append(_format_market(market, focus_outcome=args.outcome, orderbook=orderbook))

        external_research = None
        if not args.skip_intel:
            try:
                external_research = await _run_external_research(
                    args.query,
                    args.outcome,
                    market_payloads,
                )
            except Exception as e:
                external_research = {"error": str(e)}

        focus_market_history = None
        if markets:
            focus_market = markets[0]
            available_outcomes = focus_market.outcomes or [t.outcome for t in (focus_market.tokens or [])]
            focus_outcome = args.outcome or (available_outcomes[0] if available_outcomes else None)
            token_id = focus_market.get_token_id(focus_outcome) if focus_outcome else None
            if token_id:
                try:
                    history = await client.get_price_history(token_id, interval="1w", fidelity=5)
                    focus_market_history = {
                        "market_slug": focus_market.slug or focus_market.market_slug,
                        "question": focus_market.question,
                        "outcome": focus_outcome,
                        "token_id": token_id,
                        "history": history.get("history", [])[:200],
                    }
                except Exception as e:
                    focus_market_history = {"error": str(e)}

        # Tradability verdict
        tradable_markets = [m for m in market_payloads if m.get("quality", {}).get("is_tradable")]
        untradable_markets = [m for m in market_payloads if not m.get("quality", {}).get("is_tradable")]

        if not market_payloads:
            next_step = "No confident Polymarket match found. Refine the query or inspect candidate events manually."
        elif not tradable_markets:
            next_step = (
                "Found markets but none are tradable (low liquidity or inactive). "
                "Consider monitoring these markets or broadening the search."
            )
        elif len(tradable_markets) == 1:
            next_step = (
                f"Resolved to one tradable market. Use the polymarket skill with "
                f"--market-slug {tradable_markets[0]['slug']} for orderbook or execution."
            )
        else:
            best = max(tradable_markets, key=lambda m: m.get("quality", {}).get("tradability_score", 0))
            next_step = (
                f"Multiple tradable markets found. Best quality: {best['slug']} "
                f"(score: {best.get('quality', {}).get('tradability_score', 0)}). "
                "Pick one exact market_slug and switch to the polymarket skill."
            )

        _out({
            "success": True,
            "query": args.query,
            "public_search_events": [
                _format_public_event(event, args.market_limit)
                for event in public_search.get("events", [])
            ],
            "public_search_inactive_match_count": public_search.get("inactive_match_count", 0),
            "events": [_format_event(event, args.market_limit) for event in events],
            "candidate_markets": market_payloads,
            "tradable_count": len(tradable_markets),
            "untradable_count": len(untradable_markets),
            "focus_market_history": focus_market_history,
            "external_research": external_research,
            "next_step": next_step,
        })
    finally:
        await client.close()


async def cmd_thesis(args):
    """Generate a structured trade thesis for a specific market and outcome."""
    client = PMClient()
    try:
        markets = await client.search_markets(args.query, limit=5)
        if not markets:
            _out({"success": False, "error": f"No markets found for '{args.query}'"})
            return

        # Find best tradable market
        target = None
        if args.market_slug:
            for m in markets:
                slug = (m.slug or m.market_slug or "").lower().replace("-", " ")
                if slug == args.market_slug.lower().replace("-", " "):
                    target = m
                    break
            if not target:
                _out({
                    "success": False,
                    "error": f"No market matched slug '{args.market_slug}'",
                    "candidates": [_format_market(m) for m in markets[:5]],
                })
                return
        else:
            target = markets[0]

        market_payload = _format_market(target, focus_outcome=args.outcome)
        quality = target.quality

        # Get orderbook snapshot
        token_id = target.get_token_id(args.outcome)
        orderbook_snapshot = None
        if token_id:
            try:
                midpoint = client.get_midpoint(token_id)
                spread = client.get_spread(token_id)
                bid_depth = client.get_book_depth_usd(token_id, side="bids")
                ask_depth = client.get_book_depth_usd(token_id, side="asks")
                orderbook_snapshot = {
                    "outcome": args.outcome,
                    "midpoint": midpoint,
                    "spread": spread,
                    "bid_depth_usd": round(bid_depth, 2),
                    "ask_depth_usd": round(ask_depth, 2),
                }
            except Exception:
                pass

        # Price history
        price_history = None
        if token_id:
            try:
                history = await client.get_price_history(token_id, interval="1w", fidelity=5)
                price_history = history.get("history", [])[:100]
            except Exception:
                pass

        # External thesis
        external_thesis = None
        if not args.skip_intel:
            try:
                external_thesis = await _run_thesis_research(
                    args.query, args.outcome, market_payload
                )
            except Exception as e:
                external_thesis = {"error": str(e)}

        _out({
            "success": True,
            "query": args.query,
            "market": market_payload,
            "quality": _format_quality(target),
            "tradability_verdict": "TRADABLE" if quality.is_tradable else "NOT TRADABLE",
            "orderbook": orderbook_snapshot,
            "price_history": price_history,
            "external_thesis": external_thesis,
            "next_step": (
                f"Use polymarket skill: validate-trade --market-slug {target.slug or target.market_slug} "
                f"--outcome {args.outcome} --amount-usd <amount> --price <price>"
                if quality.is_tradable
                else "Market not tradable. Check quality warnings."
            ),
        })
    finally:
        await client.close()


async def cmd_compare(args):
    """Side-by-side comparison of candidate markets for the same query."""
    client = PMClient()
    try:
        markets = await client.search_markets(args.query, limit=args.limit)
        if not markets:
            _out({"success": False, "error": f"No markets found for '{args.query}'"})
            return

        comparisons = []
        for market in markets:
            quality = market.quality
            entry = {
                "slug": market.slug or market.market_slug,
                "question": market.question,
                "yes_price": market.yes_price,
                "volume": market.volume_24hr or market.volume_num or market.volume or 0,
                "liquidity": market.liquidity_num or market.liquidity or 0,
                "end_date": market.end_date.isoformat() if market.end_date else None,
                "quality": _format_quality(market),
                "tradability_verdict": "TRADABLE" if quality.is_tradable else "NOT TRADABLE",
            }

            # Optional orderbook snapshot for focus outcome
            outcome = args.outcome or "Yes"
            token_id = market.get_token_id(outcome)
            if token_id:
                try:
                    entry["orderbook"] = {
                        "outcome": outcome,
                        "midpoint": client.get_midpoint(token_id),
                        "bid_depth_usd": round(client.get_book_depth_usd(token_id, "bids"), 2),
                        "ask_depth_usd": round(client.get_book_depth_usd(token_id, "asks"), 2),
                    }
                except Exception:
                    pass

            comparisons.append(entry)

        # Identify best market
        tradable = [c for c in comparisons if c["tradability_verdict"] == "TRADABLE"]
        best = None
        if tradable:
            best = max(tradable, key=lambda c: c["quality"]["tradability_score"])

        _out({
            "success": True,
            "query": args.query,
            "market_count": len(comparisons),
            "tradable_count": len(tradable),
            "comparisons": comparisons,
            "best_market": best["slug"] if best else None,
            "best_quality_score": best["quality"]["tradability_score"] if best else None,
            "next_step": (
                f"Best market: {best['slug']} (quality: {best['quality']['tradability_score']}). "
                f"Use polymarket skill assess --market-slug {best['slug']} for full report."
                if best
                else "No tradable markets found. Consider broadening the search."
            ),
        })
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Polymarket deep research CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # research
    p = sub.add_parser("research", help="Quality-aware research across events, markets, and external sources")
    p.add_argument("--query", required=True)
    p.add_argument("--outcome", default=None, help="Optional focus outcome (Yes/No/etc.)")
    p.add_argument("--tag", default=None, help="Optional category tag")
    p.add_argument("--limit", type=int, default=5, help="Max candidate events/markets")
    p.add_argument("--market-limit", type=int, default=3, help="Markets per event in the response")
    p.add_argument("--skip-intel", action="store_true", help="Skip external GigaBrain research")

    # thesis
    p = sub.add_parser("thesis", help="Generate structured trade thesis for a specific market")
    p.add_argument("--query", required=True)
    p.add_argument("--outcome", required=True, help="Focus outcome (Yes/No/etc.)")
    p.add_argument("--market-slug", default=None, help="Exact market slug (optional, uses best match if omitted)")
    p.add_argument("--skip-intel", action="store_true", help="Skip external GigaBrain research")

    # compare
    p = sub.add_parser("compare", help="Side-by-side comparison of candidate markets")
    p.add_argument("--query", required=True)
    p.add_argument("--outcome", default=None, help="Focus outcome for orderbook comparison")
    p.add_argument("--limit", type=int, default=5, help="Max markets to compare")

    args = parser.parse_args()

    handler = {
        "research": cmd_research,
        "thesis": cmd_thesis,
        "compare": cmd_compare,
    }[args.command]

    try:
        asyncio.run(handler(args))
    except Exception as e:
        _out({"success": False, "error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
