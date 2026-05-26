---
name: hyperliquid
description: >-
  Trade perpetual futures and spot tokens on HyperLiquid L1. Place market, limit,
  bracket, and TWAP orders. Manage positions with TP/SL, check balances, orderbooks,
  candles, funding rates, and portfolio performance. Transfer USDC between wallets.
  Use when the user asks about HyperLiquid, perp trading, spot trading, position
  management, HL portfolio, or USDC transfers on HyperLiquid.
license: MIT
allowed-tools: Bash(uv *)
metadata:
  author: gigabrain
  version: "2.0"
---

# HyperLiquid Trading

Trade perpetual futures, spot tokens, and transfer USDC on HyperLiquid L1.

Resolve `SKILL_DIR` as the directory containing this `SKILL.md`, then run scripts from absolute paths under that directory. Do not rely on the current working directory or any injected `CLAUDE_*` skill path variable.

```
uv run "$SKILL_DIR/scripts/hl_client.py" <command> [args]
```

All commands return JSON to stdout with a `success` field.

## Environment

| Variable | Required | Description |
|---|---|---|
| `HYPERLIQUID_ACCOUNT_ADDRESS` | For account data | Selected HyperLiquid-capable account address |
| `HYPERLIQUID_PRIVATE_KEY` | For trading | Approved HyperLiquid API/agent wallet key — enables order placement and transfers |
| `HYPERLIQUID_ACCOUNT_SOURCE` | No | `agent_wallet` or `user_integration` |
| `HYPERLIQUID_INTEGRATION_ID` | No | Integration id when using a connected HyperLiquid account |
| `EVM_WALLET_ADDRESS` | Fallback | Dedicated EVM wallet address, used when no `HYPERLIQUID_ACCOUNT_ADDRESS` is set |
| `EVM_PRIVATE_KEY` | Fallback | Dedicated EVM signing key, used when no `HYPERLIQUID_PRIVATE_KEY` is set |
| `HL_BUILDER_ADDRESS` | No | Builder fee recipient (default: GigaBrain) |
| `HL_BUILDER_FEE_BPS` | No | Builder fee in basis points (default: 5) |
| `HL_TESTNET` | No | Set `true` for testnet |

The platform injects `HYPERLIQUID_*` from the agent's selected connected account.
For a dedicated agent EVM wallet, `HYPERLIQUID_ACCOUNT_ADDRESS` is the master
account address and `HYPERLIQUID_PRIVATE_KEY` is the approved HyperLiquid
API/agent wallet key. Do not substitute the master EVM private key when an
approved API/agent key is missing; the skill should remain read-only until the
wallet is activated. If the selected account is Solana, HyperLiquid account data
is intentionally unset and trading commands return a clear configuration error.

Without `HYPERLIQUID_PRIVATE_KEY` or fallback `EVM_PRIVATE_KEY`, all read commands
work but trading commands return an error.

## Coin Names

- **Perps**: Plain tickers — `BTC`, `ETH`, `SOL`. Never `BTC-PERP` or `BTCUSDT`.
- **Spot**: Use `TOKEN/USDC` format — `HYPE/USDC`, `PURR/USDC`.
- The script normalizes common formats automatically, but clean input is preferred.

## Commands

### Configuration
```bash
# Show config status (works without any keys)
uv run "$SKILL_DIR/scripts/hl_client.py" config
```

### Account & Positions
```bash
# Full account overview (equity, margin, positions)
uv run "$SKILL_DIR/scripts/hl_client.py" account

# Open positions (all or one coin)
uv run "$SKILL_DIR/scripts/hl_client.py" positions
uv run "$SKILL_DIR/scripts/hl_client.py" positions --coin ETH

# Pending orders (with trigger conditions)
uv run "$SKILL_DIR/scripts/hl_client.py" orders

# Spot wallet balances
uv run "$SKILL_DIR/scripts/hl_client.py" balance

# Fee schedule and volume tier
uv run "$SKILL_DIR/scripts/hl_client.py" fees

# Portfolio PnL (day/week/month/all-time)
uv run "$SKILL_DIR/scripts/hl_client.py" portfolio
```

### Market Data
```bash
# Full market info (funding, OI, volume, oracle, mark price)
uv run "$SKILL_DIR/scripts/hl_client.py" market-info --coin BTC

# Orderbook
uv run "$SKILL_DIR/scripts/hl_client.py" orderbook --coin BTC --depth 20

# All markets with prices, funding, OI
uv run "$SKILL_DIR/scripts/hl_client.py" all-markets

# OHLCV candles
uv run "$SKILL_DIR/scripts/hl_client.py" candles --coin BTC --interval 1h --days 1

# Funding rates
uv run "$SKILL_DIR/scripts/hl_client.py" funding --coin BTC --days 7
uv run "$SKILL_DIR/scripts/hl_client.py" funding --coins BTC,ETH,SOL
uv run "$SKILL_DIR/scripts/hl_client.py" funding

# Trade history
uv run "$SKILL_DIR/scripts/hl_client.py" trades --source user --days 7
uv run "$SKILL_DIR/scripts/hl_client.py" trades --source market --coin ETH --limit 50

# Order history
uv run "$SKILL_DIR/scripts/hl_client.py" historical-orders
```

### Position Sizing
```bash
# Calculate size from % of margin
uv run "$SKILL_DIR/scripts/hl_client.py" calc-size --coin ETH --percent 10

# Calculate size from USD
uv run "$SKILL_DIR/scripts/hl_client.py" calc-size --coin ETH --usd 500
```

### Perp Trading
```bash
# Market order (by USD notional)
uv run "$SKILL_DIR/scripts/hl_client.py" order --coin ETH --side buy --usd 100

# Market order (by token size)
uv run "$SKILL_DIR/scripts/hl_client.py" order --coin ETH --side buy --sz 0.5

# Limit order
uv run "$SKILL_DIR/scripts/hl_client.py" order --coin ETH --side buy --sz 0.5 --limit-px 3000

# Bracket order (entry + TP + SL)
uv run "$SKILL_DIR/scripts/hl_client.py" order --coin ETH --side buy --sz 0.5 --limit-px 3000 --tp-px 3500 --sl-px 2800

# Close position (full or partial)
uv run "$SKILL_DIR/scripts/hl_client.py" close --coin ETH
uv run "$SKILL_DIR/scripts/hl_client.py" close --coin ETH --sz 0.25

# Modify order
uv run "$SKILL_DIR/scripts/hl_client.py" modify --coin ETH --oid 12345 --new-sz 1.0 --new-limit-px 3100

# Cancel orders
uv run "$SKILL_DIR/scripts/hl_client.py" cancel                       # cancel all
uv run "$SKILL_DIR/scripts/hl_client.py" cancel --coin ETH             # cancel all for coin
uv run "$SKILL_DIR/scripts/hl_client.py" cancel --coin ETH --oid 123   # cancel specific

# Set TP/SL on existing position
uv run "$SKILL_DIR/scripts/hl_client.py" tpsl --coin ETH --tp-px 3500 --sl-px 2800

# Update leverage
uv run "$SKILL_DIR/scripts/hl_client.py" leverage --coin ETH --leverage 10 --cross

# TWAP order
uv run "$SKILL_DIR/scripts/hl_client.py" twap --coin ETH --side buy --sz 1.0 --minutes 30
uv run "$SKILL_DIR/scripts/hl_client.py" twap --coin ETH --cancel 12345

# Dead man's switch (cancel all at timestamp)
uv run "$SKILL_DIR/scripts/hl_client.py" schedule-cancel --timestamp 1700000000000
uv run "$SKILL_DIR/scripts/hl_client.py" schedule-cancel --clear
```

### Spot Trading
```bash
# Buy spot token
uv run "$SKILL_DIR/scripts/hl_client.py" spot-order --coin HYPE/USDC --side buy --usd 100

# Sell spot token
uv run "$SKILL_DIR/scripts/hl_client.py" spot-order --coin HYPE/USDC --side sell --sz 10
```

### Transfers
```bash
# Move USDC between spot and perp wallets
uv run "$SKILL_DIR/scripts/hl_client.py" transfer --amount 100 --direction to-perp
uv run "$SKILL_DIR/scripts/hl_client.py" transfer --amount 100 --direction to-spot

# Send USDC to another HL address
uv run "$SKILL_DIR/scripts/hl_client.py" send --amount 50 --to 0x1234...

# Withdraw to EVM via bridge
uv run "$SKILL_DIR/scripts/hl_client.py" withdraw --amount 100 --to 0x1234...
```

## Order Types

- **Market**: Omit `--limit-px` — executes immediately with 5% default slippage (IOC)
- **Limit**: Set `--limit-px` — rests on book (GTC)
- **Bracket**: Limit entry + `--tp-px` and/or `--sl-px` — atomic grouped order
- **TWAP**: Time-weighted execution over `--minutes` with optional randomization

See `references/order-types.md` for full details on all order types, trigger behavior, and size rules.

## Safety Rules

1. **ALWAYS** check balance with `account` before trading
2. After **EVERY** trade, verify with `positions` or `orders`
3. **NEVER** retry failed orders without user confirmation
4. Use `calc-size` to determine appropriate position sizes
5. For large orders, consider using TWAP to reduce slippage

## Error Handling

All commands return `{"success": false, "error": "..."}` on failure. See `references/error-codes.md` for common exchange errors and how to handle them.
