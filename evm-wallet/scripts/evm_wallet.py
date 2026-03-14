#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["web3", "eth-account"]
# ///
"""EVM Wallet CLI — balances, transfers, approvals, gas across EVM chains.

All output is JSON to stdout. Supports read-only mode (no private key).

Run with: uv run evm_wallet.py <command> [args]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Add scripts directory to path for co-located imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _get_services(require_address: bool = False):
    """Create EVMWalletServices from environment variables."""
    from evm_services import EVMWalletServices

    wallet_address = os.environ.get("EVM_WALLET_ADDRESS", "")
    private_key = os.environ.get("EVM_PRIVATE_KEY") or None  # None = read-only

    if require_address and not wallet_address:
        _out({"success": False, "error": "EVM_WALLET_ADDRESS must be set. Run 'config' to check."})
        sys.exit(1)

    return EVMWalletServices(
        wallet_address=wallet_address,
        private_key=private_key,
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
    if args.all_chains:
        _out(svc.get_all_chain_balances())
    else:
        _out(svc.get_balances(chain=args.chain))


def cmd_balance_of(args):
    svc = _get_services(require_address=True)
    _out(svc.get_token_balance(chain=args.chain, token=args.token))


def cmd_transfer(args):
    svc = _get_services(require_address=True)
    if args.amount <= 0:
        _out({"success": False, "error": "Amount must be positive"})
        return
    if not args.to:
        _out({"success": False, "error": "--to address is required"})
        return
    _out(svc.transfer(chain=args.chain, token=args.token, to=args.to, amount=args.amount))


def cmd_allowance(args):
    svc = _get_services(require_address=True)
    _out(svc.get_allowance(chain=args.chain, token=args.token, spender=args.spender))


def cmd_approve(args):
    svc = _get_services(require_address=True)
    if args.amount < 0:
        _out({"success": False, "error": "Amount must not be negative"})
        return
    _out(svc.approve(chain=args.chain, token=args.token, spender=args.spender, amount=args.amount))


def cmd_revoke(args):
    svc = _get_services(require_address=True)
    _out(svc.revoke(chain=args.chain, token=args.token, spender=args.spender))


def cmd_gas(args):
    svc = _get_services()
    _out(svc.get_gas_price(chain=args.chain))


def cmd_token_info(args):
    svc = _get_services()
    _out(svc.get_token_info(chain=args.chain, token=args.token))


# ---------------------------------------------------------------------------
# Argparse setup
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="EVM Wallet CLI — balances, transfers, approvals, gas")
    sub = parser.add_subparsers(dest="command", required=True)

    # config
    sub.add_parser("config", help="Show configuration status and supported chains")

    # balances
    p = sub.add_parser("balances", help="Native + ERC20 token balances")
    p.add_argument("--chain", default="ethereum", help="Chain name (default: ethereum)")
    p.add_argument("--all-chains", action="store_true", help="Query all supported chains")

    # balance-of
    p = sub.add_parser("balance-of", help="Balance of a specific token")
    p.add_argument("--chain", default="ethereum", help="Chain name (default: ethereum)")
    p.add_argument("--token", required=True, help="Token symbol or contract address")

    # transfer
    p = sub.add_parser("transfer", help="Transfer native or ERC20 token")
    p.add_argument("--chain", default="ethereum", help="Chain name (default: ethereum)")
    p.add_argument("--token", required=True, help="Token symbol or 'ETH' for native")
    p.add_argument("--to", required=True, help="Recipient address")
    p.add_argument("--amount", type=float, required=True, help="Amount to transfer")

    # allowance
    p = sub.add_parser("allowance", help="Check ERC20 allowance for a spender")
    p.add_argument("--chain", default="ethereum", help="Chain name (default: ethereum)")
    p.add_argument("--token", required=True, help="Token symbol or contract address")
    p.add_argument("--spender", required=True, help="Spender address")

    # approve
    p = sub.add_parser("approve", help="Approve ERC20 token spending")
    p.add_argument("--chain", default="ethereum", help="Chain name (default: ethereum)")
    p.add_argument("--token", required=True, help="Token symbol or contract address")
    p.add_argument("--spender", required=True, help="Spender address")
    p.add_argument("--amount", type=float, required=True, help="Amount to approve")

    # revoke
    p = sub.add_parser("revoke", help="Revoke ERC20 approval (set to 0)")
    p.add_argument("--chain", default="ethereum", help="Chain name (default: ethereum)")
    p.add_argument("--token", required=True, help="Token symbol or contract address")
    p.add_argument("--spender", required=True, help="Spender address")

    # gas
    p = sub.add_parser("gas", help="Current gas price and cost estimates")
    p.add_argument("--chain", default="ethereum", help="Chain name (default: ethereum)")

    # token-info
    p = sub.add_parser("token-info", help="Look up token info by symbol or address")
    p.add_argument("--chain", default="ethereum", help="Chain name (default: ethereum)")
    p.add_argument("--token", required=True, help="Token symbol or contract address")

    args = parser.parse_args()

    # Dispatch
    handler = {
        "config": cmd_config,
        "balances": cmd_balances,
        "balance-of": cmd_balance_of,
        "transfer": cmd_transfer,
        "allowance": cmd_allowance,
        "approve": cmd_approve,
        "revoke": cmd_revoke,
        "gas": cmd_gas,
        "token-info": cmd_token_info,
    }[args.command]

    try:
        handler(args)
    except Exception as e:
        _out({"success": False, "error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
