#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""GigaBrain Intel CLI — queries the Brain API for search, news, and analysis.

All output is JSON to stdout.

Run with: uv run intel_client.py <command> [args]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import httpx


async def _query(api_url: str, api_key: str, question: str) -> dict:
    """Send a query to the Brain API."""
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=600, headers=headers) as client:
        resp = await client.post(
            f"{api_url}/v1/chat",
            json={"message": question},
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content") or data.get("message") or str(data)
        return {"success": True, "content": content}


def _get_config():
    api_url = os.environ.get("GIGABRAIN_API_URL", "")
    api_key = os.environ.get("GIGABRAIN_API_KEY", "")
    if not api_url:
        print(json.dumps({"success": False, "error": "GIGABRAIN_API_URL not set."}))
        sys.exit(1)
    return api_url.rstrip("/"), api_key


async def cmd_web_search(args):
    api_url, api_key = _get_config()
    result = await _query(api_url, api_key, f"Web search: {args.query}")
    print(json.dumps(result, default=str))


async def cmd_news_search(args):
    api_url, api_key = _get_config()
    result = await _query(
        api_url, api_key,
        f"Search latest news about: {args.query}. "
        f"Summarize key headlines with dates and sources."
    )
    print(json.dumps(result, default=str))


async def cmd_ask(args):
    api_url, api_key = _get_config()
    result = await _query(api_url, api_key, args.question)
    print(json.dumps(result, default=str))


async def cmd_market_analysis(args):
    api_url, api_key = _get_config()
    result = await _query(
        api_url, api_key,
        f"Give me a concise market analysis for {args.coin}. "
        f"Include: current price drivers, sentiment, key recent developments, "
        f"and risk factors. Be specific with data points."
    )
    print(json.dumps(result, default=str))


def main():
    parser = argparse.ArgumentParser(description="GigaBrain Intel CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("web-search", help="Web search")
    p.add_argument("--query", required=True)

    p = sub.add_parser("news-search", help="News search")
    p.add_argument("--query", required=True)

    p = sub.add_parser("ask", help="Ask GigaBrain anything")
    p.add_argument("--question", required=True)

    p = sub.add_parser("market-analysis", help="Market analysis for a coin")
    p.add_argument("--coin", required=True)

    args = parser.parse_args()

    handler = {
        "web-search": cmd_web_search,
        "news-search": cmd_news_search,
        "ask": cmd_ask,
        "market-analysis": cmd_market_analysis,
    }[args.command]

    try:
        asyncio.run(handler(args))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}, default=str))
        sys.exit(1)


if __name__ == "__main__":
    main()
