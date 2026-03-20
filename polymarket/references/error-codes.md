# Error Codes and Resolutions

## Pre-Trade Validation Errors

### `Liquidity $X below $5,000 minimum`
The market has insufficient liquidity for safe trading.

**Resolution**:
- Use `assess` to check the market's full quality report
- If you understand the risk, add `--skip-liquidity-check` flag
- Consider finding a more liquid market via `top-markets`

### `Spread X% exceeds 10% limit`
The bid-ask spread is too wide for a fair trade.

**Resolution**:
- Use `orderbook` to inspect actual bid/ask levels
- If you accept the wide spread, add `--skip-spread-check` flag
- Use a limit order at a specific price instead of a market order

### `Market is not active` / `Market is closed` / `Market is archived`
Cannot trade resolved, closed, or inactive markets. This check cannot be bypassed.

**Resolution**: Find a different market. Use `search` or `top-markets`.

### `Market not accepting orders`
Market temporarily not accepting new orders (e.g., during resolution).

**Resolution**: Wait or find a different market.

### `Market has expired`
Market end date has passed.

**Resolution**: Find a different market.

### `Outcome 'X' not found`
The specified outcome doesn't exist in this market.

**Resolution**: Check `assess` or `resolve` output for available outcomes.

### `Book depth $X < required $Y`
For market orders, the orderbook doesn't have enough depth.

**Resolution**:
- Use a limit order instead
- Reduce order size
- Check `orderbook` for actual levels

### `Insufficient balance: $X < $Y needed`
Not enough USDC.e for the trade.

**Resolution**:
- Check `balance`
- Use `fund-address` or `fund-quote` to deposit more USDC

## Trading Errors

### `Order failed: allowance`
CLOB token allowance needs refresh. The system auto-retries this once.

**Resolution**: Usually auto-resolved. If persistent, check wallet approval status.

### `Trading not configured`
Missing `EVM_PRIVATE_KEY` and/or `EVM_WALLET_ADDRESS`.

**Resolution**: Set both environment variables.

### `Price X out of range (0.01-0.99)`
Polymarket prices must be between 0.01 and 0.99.

**Resolution**: Adjust price to valid range.

### `Size must be > 0 after rounding`
Order too small after rounding to tick size.

**Resolution**: Increase order amount.

### `GTD orders require expire_seconds`
GTD time-in-force needs an expiration.

**Resolution**: Add `--expire-seconds <seconds>`.

## Market Resolution Errors

### `Ambiguous market selection`
Query matched multiple markets and couldn't resolve to one.

**Resolution**:
- Use `resolve` to see candidates
- Rerun with exact `--market-slug`

### `No markets found for 'X'`
No markets matched the query.

**Resolution**:
- Try broader search terms
- Use `public-search` for event-level search
- Check `top-markets` for available markets

## Network/API Errors

### HTTP 429 (Rate Limited)
Too many API requests.

**Resolution**: Wait and retry. Reduce request frequency.

### HTTP 500 (Server Error)
Polymarket API error.

**Resolution**: Wait and retry. Check Polymarket status.

### `Builder auth not configured`
Builder attribution requested but not set up.

**Resolution**: Set `POLY_BUILDER_API_KEY`, `POLY_BUILDER_SECRET`, `POLY_BUILDER_PASSPHRASE`. Or ignore if builder attribution is not needed.

## Geographic Errors

### Geoblock: `blocked: true`
Trading not available in your geography.

**Resolution**: Cannot trade from this location. Read-only operations still work.
