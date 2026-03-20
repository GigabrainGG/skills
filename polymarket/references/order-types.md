# Order Types

## Limit Orders

### GTC (Good Till Cancelled)
Default order type. Remains on the book until fully filled or manually cancelled.

```bash
uv run pm_client.py buy --market-slug "<slug>" --outcome Yes --price 0.65 --amount-usd 50
```

Best for: Most trades. Gives price control. Recommended for orders > $100.

### GTD (Good Till Date)
Like GTC but auto-expires after specified seconds.

```bash
uv run pm_client.py buy --market-slug "<slug>" --outcome Yes --price 0.65 --amount-usd 50 --time-in-force GTD --expire-seconds 3600
```

Best for: Time-sensitive strategies where you want automatic cleanup.

### FAK (Fill And Kill)
Fills whatever is available at your price, then cancels the remainder. Partial fills are possible.

```bash
uv run pm_client.py buy --market-slug "<slug>" --outcome Yes --price 0.65 --amount-usd 50 --time-in-force FAK
```

Best for: When you want immediate execution but with price protection.

## Market Orders

### FOK (Fill Or Kill)
Fills the entire order at the best available prices or rejects completely. No partial fills.

```bash
uv run pm_client.py buy --market-slug "<slug>" --outcome Yes --amount-usd 10 --market-order
```

Best for: Small orders on liquid markets where you want guaranteed full execution.

### FAK (Fill And Kill) -- Market
Fills what's available at market prices, cancels rest.

```bash
uv run pm_client.py buy --market-slug "<slug>" --outcome Yes --amount-usd 10 --market-order --market-tif FAK
```

Best for: When partial fill is acceptable and you want immediate execution.

## Choosing an Order Type

| Scenario | Order Type |
|----------|-----------|
| Standard trade, price matters | GTC (limit) |
| Need execution now, small size | FOK (market) |
| Time-limited opportunity | GTD (limit) |
| Want best available, accept partial | FAK |
| Order > $100 | GTC (limit) -- always |
| Order > $500 | GTC (limit) + check orderbook depth first |

## Price Constraints

- All prices must be between 0.01 and 0.99
- Prices are rounded to the nearest tick size (usually 0.01)
- The size (shares) is computed as `amount_usd / price` for buys

## Common Gotchas

- **FOK on thin books**: If the orderbook can't fill your full order, FOK rejects entirely. Use FAK if you accept partial fills.
- **GTC forgotten orders**: Always check `my-orders` periodically. Stale GTC orders can fill at unfavorable prices if market moves.
- **GTD expiration**: Specified in seconds from now. 3600 = 1 hour, 86400 = 1 day.
