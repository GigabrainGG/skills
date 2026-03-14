---
name: solana-wallet
description: >-
  Manage Solana wallets. Check SOL and SPL token balances, transfer SOL and SPL tokens,
  view transaction history, and look up token metadata. Use when the user asks about
  Solana balances, SOL transfers, SPL token operations, or Solana wallet management.
license: MIT
allowed-tools: Bash(uv *)
metadata:
  author: gigabrain
  version: "1.0"
---

# Solana Wallet Management

Manage Solana wallets — balances, transfers, token info.

```
uv run ${CLAUDE_SKILL_DIR}/scripts/sol_wallet.py <command> [args]
```

All commands return JSON to stdout with a `success` field.

## Environment

| Variable | Required | Description |
|---|---|---|
| `SOL_WALLET_ADDRESS` | Yes | Your Solana wallet public key |
| `SOL_PRIVATE_KEY` | For transfers | Base58 private key — enables transfers |
| `SOLANA_RPC_URL` | No | Custom RPC endpoint (default: public mainnet) |

Without `SOL_PRIVATE_KEY`, all read commands work but transfers return an error.

## Commands

### Configuration
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/sol_wallet.py config
```

### Balances
```bash
# SOL + all SPL token balances
uv run ${CLAUDE_SKILL_DIR}/scripts/sol_wallet.py balances

# Balance of specific token by mint address
uv run ${CLAUDE_SKILL_DIR}/scripts/sol_wallet.py balance-of --mint <mint_address>
```

### Transfers
```bash
# Transfer SOL
uv run ${CLAUDE_SKILL_DIR}/scripts/sol_wallet.py transfer --to <pubkey> --amount 1.5

# Transfer SPL token
uv run ${CLAUDE_SKILL_DIR}/scripts/sol_wallet.py transfer-spl --mint <mint_address> --to <pubkey> --amount 100
```

### Token Info
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/sol_wallet.py token-info --mint <mint_address>
```

## Safety Rules

1. **ALWAYS** check balance before transfers
2. After **EVERY** transfer, verify with `balances`
3. **NEVER** retry failed transfers without user confirmation
4. Double-check recipient address with user before transfers
