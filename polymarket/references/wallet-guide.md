# Polymarket Wallet Types

Polymarket supports three wallet types, configured via `POLY_SIGNATURE_TYPE`.

## Type 0: EOA (Default)

Standard Externally Owned Account. The private key directly controls the trading wallet.

```
POLY_SIGNATURE_TYPE=0
EVM_PRIVATE_KEY=<your-private-key>
EVM_WALLET_ADDRESS=<derived-from-private-key>
```

- Simplest setup. The signer IS the trader.
- `POLY_FUNDER_ADDRESS` is not needed (defaults to `EVM_WALLET_ADDRESS`).

## Type 1: Proxy (MagicLink)

Used when Polymarket creates a proxy wallet on your behalf (e.g., via MagicLink email login). Your EOA key signs, but trades execute through a proxy contract.

```
POLY_SIGNATURE_TYPE=1
EVM_PRIVATE_KEY=<your-signer-key>
POLY_FUNDER_ADDRESS=<your-proxy-wallet-address>
EVM_WALLET_ADDRESS=<your-signer-address>
```

- `POLY_FUNDER_ADDRESS` is the proxy wallet that holds funds and executes trades.
- `EVM_WALLET_ADDRESS` / `EVM_PRIVATE_KEY` is the signer that authorizes transactions.

## Type 2: Gnosis Safe

Multi-sig or smart contract wallet via Gnosis Safe.

```
POLY_SIGNATURE_TYPE=2
EVM_PRIVATE_KEY=<safe-owner-key>
POLY_FUNDER_ADDRESS=<safe-address>
EVM_WALLET_ADDRESS=<safe-owner-address>
```

- `POLY_FUNDER_ADDRESS` is the Safe contract address.
- The private key belongs to one of the Safe owners/signers.

## How to Determine Your Wallet Type

1. If you created your Polymarket account with a browser wallet (MetaMask, Rabby, etc.) and directly deposited: **Type 0 (EOA)**.
2. If you signed up via email/MagicLink and Polymarket created a wallet for you: **Type 1 (Proxy)**.
3. If you connected a Gnosis Safe: **Type 2 (Safe)**.

Check your wallet type in the Polymarket UI under Settings > Wallet, or by inspecting whether your trading address is a contract on Polygonscan.

## Funder Address

The funder address is the wallet that holds USDC.e and executes trades on the CLOB. For EOA wallets, this is the same as the signer address. For Proxy and Safe wallets, it differs:

- **EOA**: funder = signer address (automatic)
- **Proxy**: funder = proxy contract address (set `POLY_FUNDER_ADDRESS`)
- **Safe**: funder = Safe contract address (set `POLY_FUNDER_ADDRESS`)
