---
name: polymarket
description: Official Polymarket skill for raw market, event, funding, compliance, and trading primitives. Use when the user wants direct Polymarket capabilities or when another strategy skill needs canonical Polymarket data and execution tools.
license: MIT
metadata:
  author: gigabrain
  version: "4.0"
---

# Polymarket Official Skill

This is the canonical Polymarket primitive skill for SuperAgents.

Use it for:
- raw Polymarket discovery and market metadata
- exact identifiers and status fields
- order book, price history, trade history, balances, positions, and orders
- funding and bridge helpers
- geoblock/readiness checks
- live order execution

Do not treat this skill itself as a strategy engine. Strategy-specific skills should compose this skill and make their own decisions on filtering, ranking, edge, and risk.

Resolve `SKILL_DIR` as the directory containing this `SKILL.md`, then run scripts from absolute paths under that directory. Do not rely on the current working directory or any injected `CLAUDE_*` skill path variable.

```bash
uv run "$SKILL_DIR/scripts/pm_client.py" <command> [args]
```

All commands return JSON to stdout.

## Setup
No manual setup needed. Scripts declare their own dependencies and run in isolated environments via `uv run`.

## Environment

- Read-only discovery and market-data commands work without wallet keys.
- Trading commands require a Polygon EOA wallet.
- Builder attribution is optional and only matters for leaderboard credit.

| Variable | Description |
|----------|-------------|
| `EVM_PRIVATE_KEY` | Polygon EOA private key for signing CLOB orders |
| `EVM_WALLET_ADDRESS` | Corresponding wallet address |
| `POLY_BUILDER_API_KEY` | Optional builder API key for order attribution |
| `POLY_BUILDER_SECRET` | Optional builder API secret |
| `POLY_BUILDER_PASSPHRASE` | Optional builder API passphrase |
| `POLY_BUILDER_SIGNER_URL` | Optional remote signer endpoint for builder attribution |
| `POLY_BUILDER_SIGNER_TOKEN` | Optional bearer token for the remote signer |

This skill is EOA-based. It does not require a Safe wallet.

## Raw-First Contract

If another skill needs canonical Polymarket data, prefer the raw commands and raw modes first.

The raw surfaces are intended to preserve upstream fields with minimal opinionation:
- `markets-raw`
- `events-raw`
- `public-search-raw`
- `orderbook --raw`
- `price-history --raw`
- `positions --raw`
- `my-orders --raw`
- `trades`
- `market-trades`
- `fund-assets`
- `fund-quote`
- `fund-address`
- `fund-status`
- `geoblock`

The convenience helpers are still available, but they may rank, summarize, or filter:
- `search`
- `events`
- `public-search`
- `trending`
- `odds`
- `resolve`
- `readiness`

## Stable Identifiers

Strategy skills should preserve and pass through these identifiers whenever possible:
- `event_id`
- `event_slug`
- `market_slug`
- `condition_id`
- `token_id`

Also preserve core status and microstructure fields where present:
- `active`
- `closed`
- `archived`
- `acceptingOrders`
- `ready`
- `negRisk`
- `bestBid`
- `bestAsk`
- `spread`
- `liquidity`
- `volume`
- `openInterest`
- `commentCount`
- `endDate`
- `resolutionSource`

## Raw Discovery Commands

Use these when another skill needs direct Polymarket/Gamma payloads.

```bash
# Raw market listing/search from Gamma
uv run "$SKILL_DIR/scripts/pm_client.py" markets-raw --query "bitcoin" --limit 10
uv run "$SKILL_DIR/scripts/pm_client.py" markets-raw --tag crypto --order volume24hr

# Raw event listing/search from Gamma
uv run "$SKILL_DIR/scripts/pm_client.py" events-raw --query "bitcoin" --limit 10
uv run "$SKILL_DIR/scripts/pm_client.py" events-raw --tag crypto --active true --closed false

# Raw public-search response from Polymarket
uv run "$SKILL_DIR/scripts/pm_client.py" public-search-raw --query "bitcoin 100k" --limit 10
```

These are the preferred inputs for downstream strategy skills.

## Convenience Discovery Commands

Use these when the user wants a faster direct answer rather than raw payloads.

```bash
# Search markets with local normalization/ranking
uv run "$SKILL_DIR/scripts/pm_client.py" search --query "bitcoin 100k" --limit 5

# Search events with trimmed nested markets
uv run "$SKILL_DIR/scripts/pm_client.py" events --query "bitcoin 100k" --limit 5

# Public-search with live/open event shaping
uv run "$SKILL_DIR/scripts/pm_client.py" public-search --query "bitcoin 100k" --limit 5 --market-limit 3

# Trending helper views
uv run "$SKILL_DIR/scripts/pm_client.py" trending --limit 10
uv run "$SKILL_DIR/scripts/pm_client.py" trending --sort liquidity
uv run "$SKILL_DIR/scripts/pm_client.py" trending --sort ending

# Quick odds summary and exact-market resolution
uv run "$SKILL_DIR/scripts/pm_client.py" odds --query "Will BTC hit 100k"
uv run "$SKILL_DIR/scripts/pm_client.py" resolve --query "Will BTC hit 100k" --outcome Yes
```

## Market Data And Microstructure

Use exact `--market-slug` values after disambiguation whenever possible.

```bash
# Structured orderbook summary
uv run "$SKILL_DIR/scripts/pm_client.py" orderbook \
  --market-slug "<exact-market-slug>" \
  --outcome Yes \
  --depth 10

# Raw orderbook payload
uv run "$SKILL_DIR/scripts/pm_client.py" orderbook \
  --market-slug "<exact-market-slug>" \
  --outcome Yes \
  --raw

# Structured price history
uv run "$SKILL_DIR/scripts/pm_client.py" price-history \
  --market-slug "<exact-market-slug>" \
  --outcome Yes \
  --interval 1w \
  --fidelity 5

# Raw price-history response
uv run "$SKILL_DIR/scripts/pm_client.py" price-history \
  --market-slug "<exact-market-slug>" \
  --outcome Yes \
  --interval 1w \
  --raw

# Market trade events
uv run "$SKILL_DIR/scripts/pm_client.py" market-trades \
  --market-slug "<exact-market-slug>" \
  --outcome Yes \
  --limit 20
```

## Funding And Compliance

When the user says "deposit to Polymarket", "fund Polymarket", or "top up the bot", use this section first.

Trading requires USDC.e on Polygon in `EVM_WALLET_ADDRESS`.

```bash
# Check readiness before a live trade
uv run "$SKILL_DIR/scripts/pm_client.py" readiness

# Check current geoblock status
uv run "$SKILL_DIR/scripts/pm_client.py" geoblock

# View trading-ready balance
uv run "$SKILL_DIR/scripts/pm_client.py" balance

# Discover bridgeable assets
uv run "$SKILL_DIR/scripts/pm_client.py" fund-assets --symbol USDC

# Create a bridge quote into Polygon USDC.e
uv run "$SKILL_DIR/scripts/pm_client.py" fund-quote \
  --from-chain-id 8453 \
  --from-token-address 0x833589fCD6EDb6E08f4c7C32D4f71b54bdA02913 \
  --from-amount-base-unit 1000000

# Create or fetch a bridge deposit address
uv run "$SKILL_DIR/scripts/pm_client.py" fund-address

# Track bridge settlement
uv run "$SKILL_DIR/scripts/pm_client.py" fund-status --deposit-address <address>
```

## Trading Commands

Trading requires `EVM_PRIVATE_KEY` and `EVM_WALLET_ADDRESS`.

Always prefer exact `--market-slug` after `resolve` if the market is not already known.

```bash
# Limit buy
uv run "$SKILL_DIR/scripts/pm_client.py" buy \
  --market-slug "<exact-market-slug>" \
  --outcome Yes \
  --price 0.65 \
  --amount-usd 50

# Market buy
uv run "$SKILL_DIR/scripts/pm_client.py" buy \
  --market-slug "<exact-market-slug>" \
  --outcome Yes \
  --amount-usd 50 \
  --market-order \
  --market-tif FAK

# GTD buy
uv run "$SKILL_DIR/scripts/pm_client.py" buy \
  --market-slug "<exact-market-slug>" \
  --outcome Yes \
  --price 0.65 \
  --amount-usd 50 \
  --time-in-force GTD \
  --expire-seconds 600

# Limit sell
uv run "$SKILL_DIR/scripts/pm_client.py" sell \
  --market-slug "<exact-market-slug>" \
  --outcome Yes \
  --price 0.70 \
  --shares 100

# Market sell
uv run "$SKILL_DIR/scripts/pm_client.py" sell \
  --market-slug "<exact-market-slug>" \
  --outcome Yes \
  --shares 100 \
  --market-order \
  --market-tif FOK
```

## Portfolio And Orders

```bash
# Current positions summary
uv run "$SKILL_DIR/scripts/pm_client.py" positions

# Raw positions payload
uv run "$SKILL_DIR/scripts/pm_client.py" positions --raw

# Recent trade history
uv run "$SKILL_DIR/scripts/pm_client.py" trades --limit 20

# Open orders summary
uv run "$SKILL_DIR/scripts/pm_client.py" my-orders

# Raw open-order payload
uv run "$SKILL_DIR/scripts/pm_client.py" my-orders --raw

# Cancel a single order
uv run "$SKILL_DIR/scripts/pm_client.py" cancel-order --order-id abc123

# Cancel all open orders
uv run "$SKILL_DIR/scripts/pm_client.py" cancel-order --all

# Check fill status
uv run "$SKILL_DIR/scripts/pm_client.py" check-order --order-id abc123
```

## Builder Attribution

Builder attribution is optional. If builder credentials are missing, trading still works but volume will not count toward leaderboard attribution.

```bash
# Check whether builder auth is active
uv run "$SKILL_DIR/scripts/pm_client.py" builder-status

# Verify attributed fills
uv run "$SKILL_DIR/scripts/pm_client.py" builder-trades --limit 20
```

## Usage Rules

1. Prefer raw commands when another skill needs canonical Polymarket fields.
2. Prefer exact `market_slug` values for `orderbook`, `price-history`, `market-trades`, `buy`, and `sell`.
3. Do not place trades from a fuzzy query if `resolve` returns multiple candidate markets.
4. Treat funding as a separate workflow from trading.
5. Run `readiness` before live execution when geography, funding, or builder attribution matters.
6. If `geoblock` or `readiness` indicates a geographic block, do not proceed to trading.
7. If a user wants thesis generation, edge ranking, or market selection logic, compose this skill from a separate strategy skill rather than encoding that logic here.
