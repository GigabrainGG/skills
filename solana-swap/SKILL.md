---
name: solana-swap
description: >-
  Swap SPL tokens on Solana via Jupiter aggregator. Get quotes, execute swaps with
  slippage protection, look up token prices, place limit orders, and set up DCA.
  Jupiter routes through Raydium, Orca, Meteora, and other Solana DEXs for best
  pricing. Use when the user asks about swapping Solana tokens, Jupiter trading,
  buying/selling SPL tokens, token prices on Solana, or DCA strategies.
license: MIT
allowed-tools: Bash(uv *)
metadata:
  author: gigabrain
  version: "1.0"
---

# Solana Token Swaps (Jupiter)

Swap SPL tokens via Jupiter — routes through all major Solana DEXs.

```
uv run ${CLAUDE_SKILL_DIR}/scripts/sol_swap.py <command> [args]
```

All commands return JSON to stdout with a `success` field.

## Environment

| Variable | Required | Description |
|---|---|---|
| `SOL_WALLET_ADDRESS` | Yes | Your Solana wallet public key |
| `SOL_PRIVATE_KEY` | For swaps | Base58 private key — enables swap execution |
| `SOLANA_RPC_URL` | No | Custom RPC (default: public mainnet) |
| `JUPITER_API_KEY` | No | Jupiter API key for higher rate limits |

## Commands

### Get Quote
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/sol_swap.py quote --from SOL --to USDC --amount 1.0
uv run ${CLAUDE_SKILL_DIR}/scripts/sol_swap.py quote --from SOL --to USDC --amount 1.0 --slippage 1.0
```

### Execute Swap
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/sol_swap.py swap --from SOL --to USDC --amount 1.0 --slippage 0.5
```

### Token Price
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/sol_swap.py price --token SOL
uv run ${CLAUDE_SKILL_DIR}/scripts/sol_swap.py price --token <mint_address>
```

## Well-Known Tokens

| Symbol | Mint Address |
|---|---|
| SOL | So11111111111111111111111111111111111111112 |
| USDC | EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v |
| USDT | Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB |

## Safety Rules

1. **ALWAYS** get a quote before executing a swap
2. **ALWAYS** verify balances before and after swaps
3. Default slippage is 0.5% — increase for low-liquidity tokens
4. **NEVER** retry failed swaps without user confirmation
