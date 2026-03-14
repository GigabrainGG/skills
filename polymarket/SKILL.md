---
name: polymarket
description: Trade prediction markets on Polymarket. Search events, check odds, view order book depth, buy/sell outcome shares, track positions and P&L. Use when the user asks about prediction markets, event probabilities, or Polymarket trading.
license: MIT
metadata:
  author: gigabrain
  version: "2.0"
---

# Polymarket Prediction Markets

Trade and research prediction markets on Polymarket (Polygon chain, USDC.e collateral).

```
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py <command> [args]
```

All commands return JSON to stdout.

## Setup
No manual setup needed. Scripts declare their own dependencies and run in isolated environments via `uv run`.

## Environment
- **Read-only** (search, odds, trending, orderbook): Works without any keys
- **Trading** (buy, sell, positions, balance): Requires `EVM_PRIVATE_KEY` and `EVM_WALLET_ADDRESS`

| Variable | Description |
|----------|-------------|
| `EVM_PRIVATE_KEY` | Polygon EOA private key for signing CLOB orders |
| `EVM_WALLET_ADDRESS` | Corresponding wallet address (must hold USDC.e on Polygon) |

## Commands

### Market Discovery

```bash
# Search markets by keyword
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py search --query "bitcoin 100k" --limit 5

# Trending markets (by 24h volume)
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py trending --limit 10

# Trending by liquidity or ending soon
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py trending --sort liquidity
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py trending --sort ending

# Filter by category tag
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py search --query "crypto" --tag crypto
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py search --query "election" --tag politics

# Get odds for a specific event (returns top 3 matches)
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py odds --query "Will BTC hit 100k"
```

### Order Book

```bash
# View order book depth for a market outcome
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py orderbook --query "Will BTC hit 100k" --outcome Yes --depth 10
```

Returns midpoint price, bid-ask spread, and top N bids/asks.

### Trading

```bash
# Limit buy - specify price (probability) and USD amount
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py buy \
  --query "Will BTC hit 100k" \
  --outcome Yes \
  --price 0.65 \
  --amount-usd 50

# Market buy (FOK) - fills immediately at best available price
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py buy \
  --query "Will BTC hit 100k" \
  --outcome Yes \
  --amount-usd 50 \
  --market-order

# Limit sell - specify price and number of shares
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py sell \
  --query "Will BTC hit 100k" \
  --outcome Yes \
  --price 0.70 \
  --shares 100
```

### Portfolio

```bash
# USDC.e balance (trading-ready funds on CLOB)
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py balance

# Current positions with P&L
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py positions

# Recent trade history
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py trades --limit 20
```

### Order Management

```bash
# View open orders
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py my-orders

# Cancel a specific order
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py cancel-order --order-id abc123

# Cancel all open orders
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py cancel-order --all

# Check order fill status
uv run ${CLAUDE_SKILL_DIR}/scripts/pm_client.py check-order --order-id abc123
```

## How Prices Work
- Prices are probabilities from 0.01 to 0.99
- A price of 0.65 means 65% implied probability
- Buying "Yes" at 0.65 costs $0.65 per share, pays $1.00 if resolved Yes
- Shares received = amount_usd / price
- Prices must conform to tick size (auto-rounded by the CLI)
- Polymarket uses USDC.e (bridged USDC) on Polygon, not native USDC

## Trading Tips
- Use `odds` to check current probabilities before trading
- Use `orderbook` to see liquidity depth and spread before large orders
- Use `balance` to verify available USDC.e before placing orders
- Use `positions` to track P&L on open positions
- Market orders (`--market-order`) fill immediately but may get worse prices on thin books
- Limit orders rest on the book until filled or cancelled (GTC)
- After placing a limit order, use `check-order` to track fill status
- Multi-outcome markets (3+ outcomes) use neg-risk exchange, handled automatically
