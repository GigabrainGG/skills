#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "solders"]
# ///
"""Solana swap CLI — Jupiter aggregator integration.

All output is JSON to stdout. Supports read-only mode (no private key) for
quotes and prices.

Run with: uv run sol_swap.py <command> [args]
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
    """Create SolanaSwapServices from environment variables."""
    from sol_swap_services import SolanaSwapServices

    wallet_address = os.environ.get("SOL_WALLET_ADDRESS", "")
    private_key = os.environ.get("SOL_PRIVATE_KEY") or None
    rpc_url = os.environ.get("SOLANA_RPC_URL") or None
    api_key = os.environ.get("JUPITER_API_KEY") or None

    if require_address and not wallet_address:
        _out({"success": False, "error": "SOL_WALLET_ADDRESS must be set."})
        sys.exit(1)

    return SolanaSwapServices(
        wallet_address=wallet_address,
        private_key=private_key,
        rpc_url=rpc_url,
        api_key=api_key,
    )


def _out(data):
    print(json.dumps(data, default=str))


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_quote(args):
    svc = _get_services()
    _out(await svc.get_quote(
        from_token=args.from_token,
        to_token=args.to_token,
        amount=args.amount,
        slippage=args.slippage,
    ))


async def cmd_swap(args):
    svc = _get_services(require_address=True)
    _out(await svc.execute_swap(
        from_token=args.from_token,
        to_token=args.to_token,
        amount=args.amount,
        slippage=args.slippage,
    ))


async def cmd_price(args):
    svc = _get_services()
    _out(await svc.get_price(token=args.token))


# ---------------------------------------------------------------------------
# Argparse setup
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Solana swap CLI — Jupiter aggregator")
    sub = parser.add_subparsers(dest="command", required=True)

    # quote
    p = sub.add_parser("quote", help="Get swap quote")
    p.add_argument("--from", dest="from_token", required=True, help="Source token symbol or mint")
    p.add_argument("--to", dest="to_token", required=True, help="Destination token symbol or mint")
    p.add_argument("--amount", type=float, required=True, help="Amount of source token")
    p.add_argument("--slippage", type=float, default=0.5, help="Slippage tolerance in %% (default: 0.5)")

    # swap
    p = sub.add_parser("swap", help="Execute swap")
    p.add_argument("--from", dest="from_token", required=True, help="Source token symbol or mint")
    p.add_argument("--to", dest="to_token", required=True, help="Destination token symbol or mint")
    p.add_argument("--amount", type=float, required=True, help="Amount of source token")
    p.add_argument("--slippage", type=float, default=0.5, help="Slippage tolerance in %% (default: 0.5)")

    # price
    p = sub.add_parser("price", help="Get token price")
    p.add_argument("--token", required=True, help="Token symbol or mint address")

    args = parser.parse_args()

    handler = {
        "quote": cmd_quote,
        "swap": cmd_swap,
        "price": cmd_price,
    }[args.command]

    try:
        asyncio.run(handler(args))
    except Exception as e:
        _out({"success": False, "error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
