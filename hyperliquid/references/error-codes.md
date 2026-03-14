# HyperLiquid Error Codes Reference

## Common Exchange Errors

| Error | Meaning | Resolution |
|---|---|---|
| `Insufficient margin` | Not enough available margin for the order | Reduce position size or deposit more USDC |
| `Reduce-only order would increase position` | Reduce-only flag set but order would open/increase position | Check position direction and order side |
| `Post-only order would cross` | ALO/post-only order would execute immediately | Adjust limit price further from market |
| `Price too far from oracle` | Limit price deviates >10% from oracle price | Use a price closer to current market |
| `Size below minimum` | Order notional below ~$10 minimum | Increase order size |
| `Order not found` | Trying to cancel/modify non-existent order | Verify order ID with `orders` command |
| `Rate limited` | Too many requests in short period | Wait a few seconds before retrying |
| `Open interest cap reached` | Asset has hit max OI limit | Try a smaller size or different asset |
| `User or IP is banned` | Account flagged by exchange | Contact HyperLiquid support |
| `Not enough base token` | Spot sell without sufficient balance | Check spot balances with `balance` |
| `Leverage exceeds max` | Requested leverage above asset's maximum | Check `maxLeverage` in `market-info` |

## Error Response Format

All errors from the CLI follow this format:
```json
{"success": false, "error": "descriptive error message"}
```

Exchange-level errors are prefixed with `Exchange rejected <action>:` followed by the exchange's error message.

## Tips

- Always check `account` before trading to verify available margin
- Use `config` to verify your keys are set correctly
- If trading commands fail with "Trading requires EVM_PRIVATE_KEY", the agent is in read-only mode
- For "Order not found" on modify/cancel, refresh orders with the `orders` command first
