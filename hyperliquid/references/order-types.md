# HyperLiquid Order Types Reference

## Market Orders
- Execute immediately at best available price
- Default slippage tolerance: 5% (configurable via `--slippage`)
- Price is calculated as: mid_price * (1 + slippage) for buys, mid_price * (1 - slippage) for sells
- Size can be specified in tokens (`--sz`) or USD notional (`--usd`)
- Uses IOC (Immediate-or-Cancel) time-in-force — unfilled portion is cancelled

## Limit Orders
- Rest on the orderbook at the specified price
- Fill when market reaches the limit price
- Price is rounded to 5 significant figures (HyperLiquid requirement)
- Size is rounded to the asset's szDecimals
- Uses GTC (Good-Till-Cancelled) time-in-force by default

## Post-Only / ALO (Add-Liquidity-Only)
- Limit order that is rejected if it would cross the spread (i.e., execute immediately)
- Guarantees maker fees, never taker fees
- Useful for market making strategies

## Bracket Orders
- Entry limit order + take-profit + stop-loss as a grouped order
- All legs are placed atomically using `normalTpsl` grouping
- If entry cancels, TP/SL cancel too
- TP is a limit trigger order (fills at TP price)
- SL is a market trigger order (fills at market on trigger)
- Both TP and SL are reduce-only

## Position TP/SL
- Set TP/SL on an existing open position using `positionTpsl` grouping
- Uses `tpsl` command instead of `order`
- TP triggers as limit order, SL triggers as market order
- Applies to full position size by default (override with `--position-size`)

## Trigger Orders
- **Take-Profit (TP)**: Triggers when mark price reaches triggerPx, executes as limit order at triggerPx
- **Stop-Loss (SL)**: Triggers when mark price reaches triggerPx, executes as market order

## TWAP Orders
- Time-Weighted Average Price execution over a specified number of minutes
- Splits large orders into smaller slices executed over time
- `--minutes`: Total execution window
- `--no-randomize`: Disable randomized slice timing (default: randomized)
- Cancel with `--cancel <twap_id>`

## Time-in-Force
- **GTC** (Good-Till-Cancelled): Stays on book until filled or cancelled
- **IOC** (Immediate-or-Cancel): Fills immediately or cancels unfilled portion
- **ALO** (Add-Liquidity-Only): Post-only, rejected if would cross spread

## Size Rules
- Each asset has a `szDecimals` value (e.g., BTC = 5, ETH = 4, SOL = 2)
- Minimum order notional: ~$10
- Size is automatically rounded to the correct decimals
- Use `calc-size` to compute size from USD or % of margin

## Price Rules
- All prices are rounded to 5 significant figures
- Prices too far from oracle may be rejected (typically >10% deviation)
