#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""GigaBrain Intel CLI — Brain API client for market intelligence and research.

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


async def _query_stream(api_url: str, api_key: str, question: str,
                         model: str = "", model_provider: str = "") -> dict:
    """Send a streaming query to the Brain API and collect the full response."""
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload: dict = {"message": question, "stream": True}
    if model:
        payload["model"] = model
    if model_provider:
        payload["model_provider"] = model_provider

    content_parts: list[str] = []

    async with httpx.AsyncClient(timeout=600, headers=headers) as client:
        async with client.stream(
            "POST",
            f"{api_url}/v1/chat",
            json=payload,
        ) as resp:
            resp.raise_for_status()
            # Use aiter_lines() to handle \r\n, \r, and \n line endings
            # from any upstream proxy. SSE events are delimited by blank lines.
            event_lines: list[str] = []
            async for line in resp.aiter_lines():
                if line:
                    event_lines.append(line)
                    continue
                # Blank line = end of SSE event
                for event_line in event_lines:
                    if not event_line.startswith("data: "):
                        continue
                    try:
                        evt = json.loads(event_line[6:])
                    except json.JSONDecodeError:
                        continue
                    event_type = evt.get("event", "")
                    if event_type == "RunResponseContent":
                        content_parts.append(evt.get("content", ""))
                    elif event_type == "error":
                        return {
                            "success": False,
                            "error": evt.get("message", "Unknown stream error"),
                        }
                event_lines = []

    content = "".join(content_parts)
    if not content:
        return {"success": False, "error": "Empty response from Brain API (streaming)"}
    return {"success": True, "content": content}


async def _query(api_url: str, api_key: str, question: str,
                  model: str = "", model_provider: str = "",
                  force_stream: bool = False) -> dict:
    """Send a query to the Brain API.

    When force_stream is True (required for litellm provider), uses SSE
    streaming and collects the full response.
    """
    if force_stream:
        return await _query_stream(api_url, api_key, question, model, model_provider)

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload: dict = {"message": question}
    if model:
        payload["model"] = model
    if model_provider:
        payload["model_provider"] = model_provider

    async with httpx.AsyncClient(timeout=600, headers=headers) as client:
        resp = await client.post(
            f"{api_url}/v1/chat",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content") or data.get("message") or str(data)
        return {"success": True, "content": content}


# Providers that require stream=true (consumer subscription proxies)
_STREAM_REQUIRED_PROVIDERS = {"litellm"}


def _get_config():
    api_url = os.environ.get("GIGABRAIN_API_URL", "")
    api_key = os.environ.get("GIGABRAIN_API_KEY", "")
    model = os.environ.get("GIGABRAIN_MODEL", "")
    model_provider = os.environ.get("GIGABRAIN_MODEL_PROVIDER", "")
    if not api_url:
        print(json.dumps({"success": False, "error": "GIGABRAIN_API_URL not set."}))
        sys.exit(1)
    force_stream = model_provider in _STREAM_REQUIRED_PROVIDERS
    return api_url.rstrip("/"), api_key, model, model_provider, force_stream


async def cmd_web_search(args):
    api_url, api_key, model, model_provider, force_stream = _get_config()
    result = await _query(api_url, api_key, f"Web search: {args.query}",
                          model, model_provider, force_stream)
    print(json.dumps(result, default=str))


async def cmd_news_search(args):
    api_url, api_key, model, model_provider, force_stream = _get_config()
    result = await _query(
        api_url, api_key,
        f"Search latest news about: {args.query}. "
        f"Summarize key headlines with dates and sources.",
        model, model_provider, force_stream,
    )
    print(json.dumps(result, default=str))


async def cmd_ask(args):
    api_url, api_key, model, model_provider, force_stream = _get_config()
    result = await _query(api_url, api_key, args.question,
                          model, model_provider, force_stream)
    print(json.dumps(result, default=str))


async def cmd_market_analysis(args):
    api_url, api_key, model, model_provider, force_stream = _get_config()
    result = await _query(
        api_url, api_key,
        f"Give me a concise but high-signal market analysis for {args.coin}. "
        f"Include: current price drivers, market structure, sentiment/positioning, "
        f"key recent developments, important levels or technical context, catalysts, "
        f"and risk factors. Be specific with data points.",
        model, model_provider, force_stream,
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

    p = sub.add_parser("market-analysis", help="High-signal market intelligence summary for a coin")
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
