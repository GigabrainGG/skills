# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""EVM chain registry CLI — look up chain IDs, RPCs, and metadata.

Data sourced from chainlist.org, curated for supported mainnet chains.
"""

from __future__ import annotations

import argparse
import json
import sys

# Curated mainnet chains — sourced from chainlist.org/rpcs.json
# RPCs selected for: no tracking, high reliability, public access
CHAINS: dict[str, dict] = {
    "ethereum": {
        "chain_id": 1,
        "rpc": "https://eth.llamarpc.com",
        "native_symbol": "ETH",
        "native_decimals": 18,
        "explorer": "https://etherscan.io",
    },
    "arbitrum": {
        "chain_id": 42161,
        "rpc": "https://arb1.arbitrum.io/rpc",
        "native_symbol": "ETH",
        "native_decimals": 18,
        "explorer": "https://arbiscan.io",
    },
    "base": {
        "chain_id": 8453,
        "rpc": "https://mainnet.base.org",
        "native_symbol": "ETH",
        "native_decimals": 18,
        "explorer": "https://basescan.org",
    },
    "optimism": {
        "chain_id": 10,
        "rpc": "https://mainnet.optimism.io",
        "native_symbol": "ETH",
        "native_decimals": 18,
        "explorer": "https://optimistic.etherscan.io",
    },
    "polygon": {
        "chain_id": 137,
        "rpc": "https://polygon-rpc.com",
        "native_symbol": "POL",
        "native_decimals": 18,
        "explorer": "https://polygonscan.com",
    },
    "bsc": {
        "chain_id": 56,
        "rpc": "https://bsc-dataseed.binance.org",
        "native_symbol": "BNB",
        "native_decimals": 18,
        "explorer": "https://bscscan.com",
    },
    "avalanche": {
        "chain_id": 43114,
        "rpc": "https://api.avax.network/ext/bc/C/rpc",
        "native_symbol": "AVAX",
        "native_decimals": 18,
        "explorer": "https://snowtrace.io",
    },
    "gnosis": {
        "chain_id": 100,
        "rpc": "https://rpc.gnosischain.com",
        "native_symbol": "xDAI",
        "native_decimals": 18,
        "explorer": "https://gnosisscan.io",
    },
    "fantom": {
        "chain_id": 250,
        "rpc": "https://rpc.ftm.tools",
        "native_symbol": "FTM",
        "native_decimals": 18,
        "explorer": "https://ftmscan.com",
    },
    "linea": {
        "chain_id": 59144,
        "rpc": "https://rpc.linea.build",
        "native_symbol": "ETH",
        "native_decimals": 18,
        "explorer": "https://lineascan.build",
    },
    "scroll": {
        "chain_id": 534352,
        "rpc": "https://rpc.scroll.io",
        "native_symbol": "ETH",
        "native_decimals": 18,
        "explorer": "https://scrollscan.com",
    },
    "zksync": {
        "chain_id": 324,
        "rpc": "https://mainnet.era.zksync.io",
        "native_symbol": "ETH",
        "native_decimals": 18,
        "explorer": "https://explorer.zksync.io",
    },
    "mantle": {
        "chain_id": 5000,
        "rpc": "https://rpc.mantle.xyz",
        "native_symbol": "MNT",
        "native_decimals": 18,
        "explorer": "https://explorer.mantle.xyz",
    },
    "blast": {
        "chain_id": 81457,
        "rpc": "https://rpc.blast.io",
        "native_symbol": "ETH",
        "native_decimals": 18,
        "explorer": "https://blastscan.io",
    },
    "mode": {
        "chain_id": 34443,
        "rpc": "https://mainnet.mode.network",
        "native_symbol": "ETH",
        "native_decimals": 18,
        "explorer": "https://explorer.mode.network",
    },
}

# Reverse lookup: chain_id → chain name
_ID_TO_NAME: dict[int, str] = {v["chain_id"]: k for k, v in CHAINS.items()}

# Aliases for common alternative names
_ALIASES: dict[str, str] = {
    "eth": "ethereum",
    "mainnet": "ethereum",
    "arb": "arbitrum",
    "op": "optimism",
    "matic": "polygon",
    "poly": "polygon",
    "avax": "avalanche",
    "bnb": "bsc",
    "binance": "bsc",
}


def _resolve(name_or_id: str) -> dict | None:
    """Resolve a chain by name, alias, or numeric chain ID."""
    key = name_or_id.strip().lower()

    # Try direct name
    if key in CHAINS:
        return {"chain": key, **CHAINS[key]}

    # Try alias
    if key in _ALIASES:
        canonical = _ALIASES[key]
        return {"chain": canonical, **CHAINS[canonical]}

    # Try numeric chain ID
    try:
        cid = int(key)
        if cid in _ID_TO_NAME:
            canonical = _ID_TO_NAME[cid]
            return {"chain": canonical, **CHAINS[canonical]}
    except ValueError:
        pass

    return None


def cmd_lookup(args: argparse.Namespace) -> None:
    query = args.chain or args.chain_id
    if not query:
        print(json.dumps({"success": False, "error": "Provide --chain or --chain-id"}))
        sys.exit(1)

    result = _resolve(query)
    if result is None:
        print(json.dumps({
            "success": False,
            "error": f"Unknown chain: {query}",
            "supported": list(CHAINS.keys()),
        }))
        sys.exit(1)

    print(json.dumps({"success": True, **result}))


def cmd_list(args: argparse.Namespace) -> None:
    chains = [
        {"chain": name, "chain_id": info["chain_id"], "native_symbol": info["native_symbol"]}
        for name, info in CHAINS.items()
    ]
    print(json.dumps({"success": True, "chains": chains}))


def cmd_rpc(args: argparse.Namespace) -> None:
    result = _resolve(args.chain)
    if result is None:
        print(json.dumps({"success": False, "error": f"Unknown chain: {args.chain}"}))
        sys.exit(1)
    print(json.dumps({"success": True, "chain": result["chain"], "rpc": result["rpc"]}))


def main() -> None:
    parser = argparse.ArgumentParser(description="EVM chain registry")
    sub = parser.add_subparsers(dest="command", required=True)

    p_lookup = sub.add_parser("lookup", help="Look up a chain by name or ID")
    p_lookup.add_argument("--chain", help="Chain name (e.g. base, ethereum, arb)")
    p_lookup.add_argument("--chain-id", help="Numeric chain ID (e.g. 8453)")
    p_lookup.set_defaults(func=cmd_lookup)

    p_list = sub.add_parser("list", help="List all supported chains")
    p_list.set_defaults(func=cmd_list)

    p_rpc = sub.add_parser("rpc", help="Get RPC URL for a chain")
    p_rpc.add_argument("--chain", required=True, help="Chain name or ID")
    p_rpc.set_defaults(func=cmd_rpc)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
