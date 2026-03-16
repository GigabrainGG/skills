#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "pydantic", "py-clob-client", "eth-account", "web3"]
# ///
"""Polymarket deep research - read-only market + external evidence synthesis.

Run with:
  uv run pm_deep_research.py research --query "..."
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

from pm_services import PMClient, Market  # noqa: E402


def _out(data):
    print(json.dumps(data, default=str))


def _parse_jsonish(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


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


async def cmd_research(args):
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

        if not market_payloads:
            next_step = "No confident Polymarket match found. Refine the query or inspect candidate events manually."
        elif len(market_payloads) == 1:
            next_step = (
                "Resolved to a single market. Use the polymarket skill with "
                f"--market-slug {market_payloads[0]['slug']} for orderbook or execution."
            )
        else:
            next_step = "If multiple candidate markets remain, pick one exact market_slug and switch to the polymarket skill."

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
            "focus_market_history": focus_market_history,
            "external_research": external_research,
            "next_step": next_step,
        })
    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(description="Polymarket deep research CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("research", help="Research a Polymarket market thesis")
    p.add_argument("--query", required=True)
    p.add_argument("--outcome", default=None, help="Optional focus outcome (Yes/No/etc.)")
    p.add_argument("--tag", default=None, help="Optional category tag")
    p.add_argument("--limit", type=int, default=5, help="Max candidate events/markets")
    p.add_argument("--market-limit", type=int, default=3, help="Markets per event in the response")
    p.add_argument("--skip-intel", action="store_true", help="Skip external GigaBrain research")

    args = parser.parse_args()

    try:
        asyncio.run(cmd_research(args))
    except Exception as e:
        _out({"success": False, "error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
