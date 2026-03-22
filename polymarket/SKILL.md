---
name: polymarket
description: Official Polymarket primitive skill for market discovery, quality assessment, pre-trade validation, orderbook/price data, funding/compliance, and live trading. Use when the user wants direct Polymarket capabilities or when another strategy skill needs canonical Polymarket data and execution.
license: MIT
metadata:
  author: gigabrain
  version: "2.0"
---

# Polymarket Official Skill

Canonical Polymarket primitive layer for SuperAgents.

Use this skill for:
- Market discovery with quality scoring
- Pre-trade safety validation
- Orderbook, price history, market trades, balances, positions, and orders
- Funding and bridge helpers
- Geoblock and readiness checks
- Live order execution

Do not use this skill itself as a strategy engine. Other skills should compose it for scanning, edge ranking, thesis generation, and portfolio policy.

Resolve `SKILL_DIR` as the directory containing this `SKILL.md`, then run scripts from absolute paths under that directory.

```bash
uv run "$SKILL_DIR/scripts/pm_client.py" <command> [args]
```

Use `--help` on any command when you need exact flags:

```bash
uv run "$SKILL_DIR/scripts/pm_client.py" assess --help
```

## Environment

- Read-only commands work without wallet keys.
- Trading requires `EVM_PRIVATE_KEY` and `EVM_WALLET_ADDRESS`.
- Builder attribution is optional.
- Trading-ready funding is USDC.e on Polygon.

Wallet type configuration (ask the user which type they use if unclear):
- `POLY_SIGNATURE_TYPE` — `0` (EOA, default), `1` (Proxy/MagicLink), or `2` (Gnosis Safe). See `references/wallet-guide.md` for details.
  - **EOA (0):** User created account with a browser wallet (MetaMask, Rabby, etc.) and deposited directly. Simplest setup.
  - **Proxy (1):** User signed up via email/MagicLink and Polymarket created a proxy wallet. Requires `POLY_FUNDER_ADDRESS` set to the proxy contract address.
  - **Gnosis Safe (2):** User connected a Gnosis Safe. Requires `POLY_FUNDER_ADDRESS` set to the Safe address.
- `POLY_FUNDER_ADDRESS` — The address that funds trades. Falls back to `EVM_WALLET_ADDRESS` if unset. Required for Proxy and Safe wallets where the funder differs from the signer.

Optional RPC:
- `POLYGON_RPC_URL` — Override the default Polygon RPC endpoint. Defaults to `https://polygon.drpc.org`. Set to your own Alchemy/Infura endpoint for higher rate limits.

Optional builder vars:
- `POLY_BUILDER_API_KEY`
- `POLY_BUILDER_SECRET`
- `POLY_BUILDER_PASSPHRASE`
- `POLY_BUILDER_SIGNER_URL`
- `POLY_BUILDER_SIGNER_TOKEN`

## BEFORE Every Trade

These rules are mandatory. Violating them risks trading dead, illiquid, or dangerous markets.

1. **ALWAYS** run `assess` or check the `quality` field from `search` before trading.
2. **NEVER** trade a market with `is_tradable: false`.
3. **NEVER** trade a market with liquidity below $5,000 without `--skip-liquidity-check` and explicit user approval.
4. **NEVER** trade a market with spread > 10% without `--skip-spread-check` and explicit user approval.
5. **ALWAYS** check `balance` before buying.
6. For orders > $100: use limit orders (not market orders).
7. For orders > $500: check orderbook depth first via `orderbook` or `assess`.
8. **ALWAYS** use exact `--market-slug`, never free-text `--query` for trading commands (`buy`, `sell`).
9. After every trade, verify with `positions` or `check-order`.

## Preserve These IDs

Downstream strategy skills should preserve:
- `event_id`
- `event_slug`
- `market_slug`
- `condition_id`
- `token_id`

Important upstream fields to keep when present:
- `active`, `closed`, `archived`
- `acceptingOrders`, `ready`
- `negRisk`
- `liquidity`, `volume`
- `spread`, `bestBid`, `bestAsk`
- `openInterest`, `commentCount`
- `resolutionSource`

## Command Families

### Quality Assessment (NEW)

Use these before any trade decision.

- `assess` -- Single-market quality report with orderbook snapshot
- `validate-trade` -- Dry-run pre-trade validation without placing an order
- `top-markets` -- Top N markets by composite quality score
- `config` -- Show environment and configuration status

Examples:

```bash
# Assess a specific market
uv run "$SKILL_DIR/scripts/pm_client.py" assess --market-slug "will-bitcoin-hit-100k-in-2026"

# Dry-run validation before buying
uv run "$SKILL_DIR/scripts/pm_client.py" validate-trade --market-slug "will-bitcoin-hit-100k-in-2026" --outcome Yes --amount-usd 50 --price 0.65

# Top tradable markets
uv run "$SKILL_DIR/scripts/pm_client.py" top-markets --limit 5

# Top crypto markets
uv run "$SKILL_DIR/scripts/pm_client.py" top-markets --limit 5 --tag crypto
```

### Raw Discovery

Preferred for downstream strategy skills.

- `markets-raw`
- `events-raw`
- `public-search-raw`

Example:

```bash
uv run "$SKILL_DIR/scripts/pm_client.py" markets-raw --query "bitcoin" --limit 10
```

### Convenience Discovery

Useful for direct user-facing exploration. Results include quality scores.

- `search` -- Quality-ranked market search
- `events`
- `public-search`
- `trending`
- `odds`
- `resolve`

Example:

```bash
uv run "$SKILL_DIR/scripts/pm_client.py" search --query "bitcoin" --limit 10
uv run "$SKILL_DIR/scripts/pm_client.py" resolve --query "Will BTC hit 100k" --outcome Yes
```

### Market Data

- `orderbook` and `orderbook --raw`
- `price-history` and `price-history --raw`
- `market-trades`

Example:

```bash
uv run "$SKILL_DIR/scripts/pm_client.py" orderbook --market-slug "<exact-market-slug>" --outcome Yes --raw
```

### Funding And Compliance

When the user says deposit, fund, or top up Polymarket, do this before trading.

- `readiness`
- `geoblock`
- `balance` -- Shows both on-chain wallet balance and CLOB trading balance
- `approve-trading` -- Approve the exchange contract to spend wallet USDC.e (required before wallet funds appear as trading balance)
- `fund-assets`
- `fund-quote`
- `fund-address`
- `fund-status`

**Wallet vs Trading Balance:** USDC.e sent directly to the Polygon wallet address is not immediately available for trading. The `balance` command shows both `wallet_balance` (on-chain) and `trading_balance` (CLOB-ready). If wallet has funds but trading shows 0, run `approve-trading` to authorize the exchange contract.

Example:

```bash
uv run "$SKILL_DIR/scripts/pm_client.py" readiness
uv run "$SKILL_DIR/scripts/pm_client.py" balance
uv run "$SKILL_DIR/scripts/pm_client.py" approve-trading
uv run "$SKILL_DIR/scripts/pm_client.py" fund-address
```

### Withdrawal

When the user wants to withdraw funds from Polymarket back to another chain.

- `withdraw-quote` -- Get a bridge quote for withdrawing USDC.e from Polygon
- `withdraw-address` -- Initiate a withdrawal and get the withdrawal address
- `withdraw-status` -- Check withdrawal transaction status

Example:

```bash
# Get a withdrawal quote to Ethereum mainnet USDC
uv run "$SKILL_DIR/scripts/pm_client.py" withdraw-quote --to-chain-id 1 --to-token-address 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 --from-amount-base-unit 1000000

# Initiate withdrawal
uv run "$SKILL_DIR/scripts/pm_client.py" withdraw-address

# Check status
uv run "$SKILL_DIR/scripts/pm_client.py" withdraw-status --deposit-address <address-from-withdraw-address>
```

### Token Operations

CTF token lifecycle operations. Requires `EVM_PRIVATE_KEY` and a small amount of POL for gas (~$0.01 per tx).

- `redeem` -- Redeem resolved positions back to USDC.e
- `split` -- Split USDC.e into YES + NO outcome tokens
- `merge` -- Merge YES + NO outcome tokens back into USDC.e

Token lifecycle: USDC.e → `split` → YES + NO tokens → trade on CLOB → `merge` back or wait for resolution → `redeem`

Example:

```bash
# Redeem a resolved market
uv run "$SKILL_DIR/scripts/pm_client.py" redeem --market-slug "will-bitcoin-hit-100k-in-2026"

# Split $1 into YES + NO tokens
uv run "$SKILL_DIR/scripts/pm_client.py" split --market-slug "will-bitcoin-hit-100k-in-2026" --amount-usdc 1

# Merge tokens back into USDC.e
uv run "$SKILL_DIR/scripts/pm_client.py" merge --market-slug "will-bitcoin-hit-100k-in-2026" --amount-usdc 1
```

### Trading And Orders

All buy/sell commands include pre-trade validation. Orders are blocked if validation fails unless checks are explicitly bypassed.

- `buy` -- `--amount-usd` (required), `--price` (for limit), `--market-order` (for FOK)
- `sell` -- `--shares` or `--amount-usd` (one required), `--price` (for limit), `--market-order` (for FOK)
- `positions` and `positions --raw`
- `trades`
- `my-orders` and `my-orders --raw`
- `cancel-order`
- `check-order`

Bypass flags: `--skip-liquidity-check`, `--skip-spread-check`

Example:

```bash
# Limit buy (recommended for > $100)
uv run "$SKILL_DIR/scripts/pm_client.py" buy --market-slug "<exact-market-slug>" --outcome Yes --price 0.65 --amount-usd 50

# Market buy (only for small orders on liquid markets)
uv run "$SKILL_DIR/scripts/pm_client.py" buy --market-slug "<exact-market-slug>" --outcome Yes --amount-usd 10 --market-order

# Sell by share count
uv run "$SKILL_DIR/scripts/pm_client.py" sell --market-slug "<slug>" --outcome Yes --price 0.65 --shares 100

# Sell by dollar amount (computes shares from price)
uv run "$SKILL_DIR/scripts/pm_client.py" sell --market-slug "<slug>" --outcome Yes --price 0.65 --amount-usd 50

# Force trade on low-liquidity market (requires explicit user approval)
uv run "$SKILL_DIR/scripts/pm_client.py" buy --market-slug "<slug>" --outcome Yes --price 0.65 --amount-usd 50 --skip-liquidity-check
```

### Builder Attribution

Optional only. Missing builder creds should not block normal research or trading.

- `builder-status`
- `builder-trades`

## Quality Scoring

Every market gets a quality assessment with:
- `tradability_score` (0-100): Composite of liquidity, volume, spread, and status
- `liquidity_usd`: Market liquidity in USD
- `volume_24h_usd`: 24-hour trading volume
- `spread_pct`: Bid-ask spread as percentage
- `is_tradable`: Boolean - meets minimum safety thresholds
- `warnings`: List of quality concerns

Search results are ranked by composite score: `sqrt(relevance * quality)`. This means both relevance to the query AND market quality matter equally. A $0-liquidity market scores 0 regardless of query match.

See `references/market-quality.md` for detailed scoring methodology.

## Pre-Trade Validation

Every `buy` and `sell` runs through a validation cascade:

1. **Input validation** -- outcome non-empty, amount > 0, price in range
2. **Market status** -- active, not closed, not archived, accepting orders, not expired (CANNOT be bypassed)
3. **Outcome resolution** -- outcome exists in market tokens
4. **Liquidity check** -- liquidity >= $5,000 (bypassable: `--skip-liquidity-check`)
5. **Spread check** -- spread <= 10% for limit orders (bypassable: `--skip-spread-check`)
6. **Book depth check** -- available USD >= 1.5x order size for market orders
7. **Balance check** -- USDC balance >= order amount

Status checks (step 2) can NEVER be bypassed. Liquidity and spread checks can be bypassed with explicit flags.

## Recommended Workflow

1. `search` or `top-markets` to find candidates
2. `assess --market-slug <slug>` for quality report
3. `validate-trade` to dry-run the trade
4. `readiness` to check wallet and geo status
5. `buy` or `sell` with exact `--market-slug`
6. `check-order` or `positions` to verify
7. After resolution: `positions` to find redeemable positions, then `redeem` to collect winnings

## Things To Know

- **Resolution is not instant.** A market's end date passing does not mean it is resolved. Resolution can take hours or days after the event concludes — Polymarket waits for oracle confirmation. If a user asks "why can't I redeem?" after a market ended, explain the delay and suggest checking back later. Do not treat unresolved markets as broken. The `redeem` command will warn if a market appears unresolved and explain if the transaction reverts.
- **Wallet balance vs trading balance.** USDC.e sitting in the Polygon wallet is not automatically available for CLOB trading. The exchange contract must be approved first. If `balance` shows `wallet_balance > 0` but `trading_balance = 0`, tell the user to run `approve-trading`. This is the most common reason new users see a zero balance after funding. The `buy` command also hints about this if a purchase fails due to insufficient trading balance.
- **Wallet type matters.** If the user's `POLY_SIGNATURE_TYPE` is wrong, orders will silently fail or produce cryptic errors. When a user reports unexpected trading failures, run `config` to check — it will warn about misconfigurations like missing `POLY_FUNDER_ADDRESS` for proxy wallets. `readiness` also validates this. See `references/wallet-guide.md`.
- **Proxy/MagicLink limitations.** On-chain operations (`redeem`, `split`, `merge`) execute from the signer EOA but funds/positions live in the proxy contract. These operations may not work correctly for Proxy (type 1) and Gnosis Safe (type 2) wallets. CLOB trading (buy/sell) works correctly for all wallet types. If a proxy user needs to redeem, they should use the Polymarket web UI.
- **Gas fees (POL).** On-chain operations (`redeem`, `split`, `merge`, `approve-trading`) require a small amount of POL (Polygon's native token) for gas — typically < $0.01 per tx. The `balance` and `readiness` commands show the `pol_balance` and warn if it's too low. If gas-related errors appear, the user needs to send a tiny amount of POL to their signer wallet address.
- **CLOB initialization failures.** If `EVM_PRIVATE_KEY` and `EVM_WALLET_ADDRESS` are set but trading commands say "not configured," the CLOB client failed to initialize. Run `config` to see the specific error. Common causes: malformed private key, nonce issues during API credential derivation, or network problems.
- **Follow next_step hints.** Many commands (`fund-address`, `fund-status`, `approve-trading`, `readiness`) return a `next_step` field telling you what to do next. Always surface these to the user.

## Funding Workflow

The complete sequence to go from zero to trading-ready:

1. `readiness` — Check geography, wallet config, and current balances
2. `fund-assets` — Find supported tokens/chains for bridging
3. `fund-quote` — Get a bridge quote with amounts
4. `fund-address` — Get a deposit address (output includes next_step instructions)
5. User sends funds externally to the deposit address
6. `fund-status --deposit-address <addr>` — Wait for bridge completion
7. `balance` — Verify wallet_balance shows the funds
8. `approve-trading` — Authorize the exchange contract (one-time per wallet)
9. `balance` — Verify trading_balance is now available
10. `readiness` — Final check before trading

Each command returns `next_step` guidance so the agent can walk the user through seamlessly.

## Rules

1. Prefer raw commands when another skill needs canonical Polymarket fields.
2. Prefer exact `market_slug` values for `orderbook`, `price-history`, `market-trades`, `buy`, and `sell`.
3. If `resolve` returns multiple candidates, do not trade until one exact market is selected.
4. Treat funding as a separate workflow from trading.
5. If `readiness` or `geoblock` indicates a geographic block, do not trade.
6. If the user wants thesis generation or catalyst analysis, use `polymarket-deep-research` first.
7. Always check `quality.is_tradable` before executing trades.
8. Never bypass liquidity or spread checks without explicit user approval.
9. When `config` or `readiness` shows warnings, surface them to the user before proceeding.
10. For Proxy/MagicLink (type 1) or Gnosis Safe (type 2) wallets, warn that on-chain operations (redeem/split/merge) may not work — recommend the Polymarket web UI for those.

## Error Codes

Error responses include a machine-readable `error_code` field for programmatic handling:

- `TRADING_NOT_CONFIGURED` — Missing EVM_PRIVATE_KEY or EVM_WALLET_ADDRESS
- `INVALID_INPUT` — Bad arguments (price out of range, missing required fields)
- `VALIDATION_FAILED` — Pre-trade validation cascade blocked the order
- `PRICE_REQUIRED` — Cannot compute shares without a price
- `ORDER_REJECTED` — Exchange rejected the order
- `INSUFFICIENT_GAS` — Not enough POL for gas fees
- `ALLOWANCE_ERROR` — Exchange contract not approved to spend USDC.e
- `RATE_LIMITED` — Too many API requests
- `TIMEOUT` — Request timed out
- `UNKNOWN_ERROR` — Unclassified error

See `references/error-codes.md` for detailed resolution steps.
