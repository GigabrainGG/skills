---
name: evm-wallet
description: >-
  Manage EVM wallets across Ethereum, Arbitrum, Base, Polygon, BSC, and Optimism.
  Check native and ERC20 token balances, transfer tokens, view transaction history,
  manage token approvals, and estimate gas costs. Use when the user asks about
  wallet balances, token transfers, approvals, gas fees, or EVM portfolio overview.
license: MIT
allowed-tools: Bash(uv *)
metadata:
  author: gigabrain
  version: "1.0"
---

# EVM Wallet Management

Manage wallets across EVM chains — balances, transfers, approvals, gas.

Resolve `SKILL_DIR` as the directory containing this `SKILL.md`, then run scripts from absolute paths under that directory. Do not rely on the current working directory or any injected `CLAUDE_*` skill path variable.

```
uv run "$SKILL_DIR/scripts/evm_wallet.py" <command> [args]
```

All commands return JSON to stdout with a `success` field.

## Environment

| Variable | Required | Description |
|---|---|---|
| `EVM_WALLET_ADDRESS` | Yes | Your EVM wallet address |
| `EVM_PRIVATE_KEY` | For transfers | Signing key — enables transfers and approvals |

Without `EVM_PRIVATE_KEY`, all read commands work but write commands return an error.

## Supported Chains

`ethereum`, `arbitrum`, `base`, `polygon`, `bsc`, `optimism`

Default chain is `ethereum` if `--chain` is omitted.

## Commands

### Configuration
```bash
# Show config status and supported chains
uv run "$SKILL_DIR/scripts/evm_wallet.py" config
```

### Balances
```bash
# Native + top ERC20 token balances on a chain
uv run "$SKILL_DIR/scripts/evm_wallet.py" balances --chain base

# Balances across all supported chains
uv run "$SKILL_DIR/scripts/evm_wallet.py" balances --all-chains

# Balance of a specific token
uv run "$SKILL_DIR/scripts/evm_wallet.py" balance-of --chain base --token USDC
uv run "$SKILL_DIR/scripts/evm_wallet.py" balance-of --chain base --token 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
```

### Transfers
```bash
# Transfer native token (ETH, MATIC, etc.)
uv run "$SKILL_DIR/scripts/evm_wallet.py" transfer --chain base --token ETH --to 0x... --amount 0.1

# Transfer ERC20 token
uv run "$SKILL_DIR/scripts/evm_wallet.py" transfer --chain base --token USDC --to 0x... --amount 100
```

### Token Approvals
```bash
# Check current approval
uv run "$SKILL_DIR/scripts/evm_wallet.py" allowance --chain base --token USDC --spender 0x...

# Approve token spending
uv run "$SKILL_DIR/scripts/evm_wallet.py" approve --chain base --token USDC --spender 0x... --amount 1000

# Revoke approval
uv run "$SKILL_DIR/scripts/evm_wallet.py" revoke --chain base --token USDC --spender 0x...
```

### Gas
```bash
# Current gas price on chain
uv run "$SKILL_DIR/scripts/evm_wallet.py" gas --chain ethereum
```

### Token Info
```bash
# Look up token by symbol or address
uv run "$SKILL_DIR/scripts/evm_wallet.py" token-info --chain base --token USDC
```

## Safety Rules

1. **ALWAYS** check balance before transfers
2. After **EVERY** transfer, verify with `balances`
3. **NEVER** retry failed transfers without user confirmation
4. Explain what approvals do before requesting them
5. Double-check recipient address with user before transfers
