#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["solana", "solders"]
# ///
"""Solana Wallet CLI — balances, transfers, token info.

All output is JSON to stdout. Supports read-only mode (no private key).

Run with: uv run sol_wallet.py <command> [args]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Add scripts directory to path for co-located imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _get_services(require_address: bool = False):
    """Create SolanaWalletServices from environment variables."""
    from sol_services import SolanaWalletServices

    wallet_address = os.environ.get("SOL_WALLET_ADDRESS", "")
    private_key = os.environ.get("SOL_PRIVATE_KEY") or None
    rpc_url = os.environ.get("SOLANA_RPC_URL") or None

    if require_address and not wallet_address:
        _out({"success": False, "error": "SOL_WALLET_ADDRESS must be set. Run 'config' to check."})
        sys.exit(1)

    return SolanaWalletServices(
        wallet_address=wallet_address,
        private_key=private_key,
        rpc_url=rpc_url,
    )


def _out(data):
    print(json.dumps(data, default=str))


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_config(args):
    svc = _get_services()
    _out(svc.show_config())


def cmd_balances(args):
    svc = _get_services(require_address=True)
    _out(svc.get_balances())


def cmd_balance_of(args):
    svc = _get_services(require_address=True)
    _out(svc.get_token_balance(args.mint))


def cmd_transfer(args):
    svc = _get_services(require_address=True)
    if args.amount <= 0:
        _out({"success": False, "error": "Amount must be positive"})
        return
    _out(svc.transfer_sol(to_address=args.to, amount=args.amount))


def cmd_transfer_spl(args):
    svc = _get_services(require_address=True)
    if args.amount <= 0:
        _out({"success": False, "error": "Amount must be positive"})
        return
    _out(svc.transfer_spl(mint_address=args.mint, to_address=args.to, amount=args.amount))


def cmd_token_info(args):
    svc = _get_services(require_address=False)
    _out(svc.get_token_info(args.mint))


# ---------------------------------------------------------------------------
# Argparse setup
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Solana Wallet CLI — balances, transfers, token info")
    sub = parser.add_subparsers(dest="command", required=True)

    # config
    sub.add_parser("config", help="Show configuration status")

    # balances
    sub.add_parser("balances", help="SOL + all SPL token balances")

    # balance-of
    p = sub.add_parser("balance-of", help="Balance of a specific SPL token")
    p.add_argument("--mint", required=True, help="Token mint address")

    # transfer
    p = sub.add_parser("transfer", help="Transfer SOL")
    p.add_argument("--to", required=True, help="Destination wallet address")
    p.add_argument("--amount", type=float, required=True, help="Amount of SOL to send")

    # transfer-spl
    p = sub.add_parser("transfer-spl", help="Transfer SPL token")
    p.add_argument("--mint", required=True, help="Token mint address")
    p.add_argument("--to", required=True, help="Destination wallet address")
    p.add_argument("--amount", type=float, required=True, help="Amount of tokens to send")

    # token-info
    p = sub.add_parser("token-info", help="Get token metadata by mint address")
    p.add_argument("--mint", required=True, help="Token mint address")

    args = parser.parse_args()

    handler = {
        "config": cmd_config,
        "balances": cmd_balances,
        "balance-of": cmd_balance_of,
        "transfer": cmd_transfer,
        "transfer-spl": cmd_transfer_spl,
        "token-info": cmd_token_info,
    }[args.command]

    try:
        handler(args)
    except Exception as e:
        _out({"success": False, "error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
