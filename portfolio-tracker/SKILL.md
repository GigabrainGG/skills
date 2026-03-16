---
name: portfolio-tracker
description: Full portfolio overview across HyperLiquid and on-chain wallets. Get combined totals, token holdings across all chains, and DeFi positions.
license: MIT
metadata:
  author: gigabrain
  version: "2.0"
---

# Portfolio Tracker

Get your full portfolio — HyperLiquid perps + on-chain assets across all EVM chains.

## On-Chain Portfolio

Fetches all token holdings and DeFi positions across every chain your wallet is on.

### Full portfolio (tokens + DeFi)
```bash
curl -s "${GIGABRAIN_API_URL}/v2/agents/me/portfolio" \
  -H "Authorization: Bearer ${GIGABRAIN_API_KEY}"
```

Returns:
- `portfolio` — total USD value, 24h change, per-chain breakdown
- `positions` — token holdings (name, symbol, quantity, USD value, chain)
- `defi_positions` — staking, LPs, lending positions

### HyperLiquid

For HyperLiquid equity, positions, and P&L, switch to the `hyperliquid` skill and use its `account` and `positions` commands. This skill does not own a local `hl_client.py` script.

## When to Use

- **"How's my portfolio?"** → fetch on-chain portfolio + HL account for the full picture
- **"What tokens do I hold?"** or **"What's on-chain?"** → on-chain portfolio
- **"What's my P&L?"** or **"How are my positions?"** → HL positions (perps skill)
