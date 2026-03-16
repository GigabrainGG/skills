---
name: chain-registry
description: |
  Look up EVM chain IDs, RPC URLs, native tokens, and block explorers.

  USE THIS SKILL TO:
  - Resolve a chain name to its chain ID (e.g., "what's the chain ID for Base?")
  - Get the RPC URL for a chain (e.g., "RPC for Arbitrum")
  - Look up a chain by its numeric ID (e.g., "what chain is 42161?")
  - List all supported EVM chains
  - Get block explorer URLs for any supported chain
metadata:
  author: gigabrain
  version: "1.0"
---

# Chain Registry

Look up EVM chain metadata without reading large files. Supports 15+ mainnet chains with curated public RPCs (sourced from chainlist.org).

Resolve `SKILL_DIR` as the directory containing this `SKILL.md`, then run scripts from absolute paths under that directory. Do not rely on the current working directory.

## Commands

### Look up a chain by name
```bash
uv run "$SKILL_DIR/scripts/chain_registry.py" lookup --chain base
```

### Look up a chain by ID
```bash
uv run "$SKILL_DIR/scripts/chain_registry.py" lookup --chain-id 42161
```

### Get just the RPC URL
```bash
uv run "$SKILL_DIR/scripts/chain_registry.py" rpc --chain ethereum
```

### List all supported chains
```bash
uv run "$SKILL_DIR/scripts/chain_registry.py" list
```

## Supported Chains

ethereum, arbitrum, base, optimism, polygon, bsc, avalanche, gnosis, fantom, linea, scroll, zksync, mantle, blast, mode

## Aliases

Common aliases are supported: `eth`/`mainnet` → ethereum, `arb` → arbitrum, `op` → optimism, `matic`/`poly` → polygon, `avax` → avalanche, `bnb`/`binance` → bsc

## Output Format

All commands output JSON to stdout:
```json
{"success": true, "chain": "base", "chain_id": 8453, "rpc": "https://mainnet.base.org", "native_symbol": "ETH", "native_decimals": 18, "explorer": "https://basescan.org"}
```

## Path Resolution

`SKILL_DIR` means the directory containing this `SKILL.md`.
