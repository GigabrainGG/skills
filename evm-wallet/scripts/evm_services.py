"""EVM Wallet service layer — balances, transfers, approvals, gas.

Self-contained module using web3.py and eth-account.
Supports read-only mode when no private key is provided.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

logger = logging.getLogger("evm_services")


# ---------------------------------------------------------------------------
# Chain configurations
# ---------------------------------------------------------------------------

CHAINS: dict[str, dict[str, Any]] = {
    "ethereum": {
        "chain_id": 1,
        "rpc": "https://eth.llamarpc.com",
        "native_symbol": "ETH",
        "explorer": "https://etherscan.io",
        "poa": False,
    },
    "arbitrum": {
        "chain_id": 42161,
        "rpc": "https://arb1.arbitrum.io/rpc",
        "native_symbol": "ETH",
        "explorer": "https://arbiscan.io",
        "poa": True,
    },
    "base": {
        "chain_id": 8453,
        "rpc": "https://mainnet.base.org",
        "native_symbol": "ETH",
        "explorer": "https://basescan.org",
        "poa": True,
    },
    "polygon": {
        "chain_id": 137,
        "rpc": "https://polygon-rpc.com",
        "native_symbol": "POL",
        "explorer": "https://polygonscan.com",
        "poa": True,
    },
    "bsc": {
        "chain_id": 56,
        "rpc": "https://bsc-dataseed.binance.org",
        "native_symbol": "BNB",
        "explorer": "https://bscscan.com",
        "poa": True,
    },
    "optimism": {
        "chain_id": 10,
        "rpc": "https://mainnet.optimism.io",
        "native_symbol": "ETH",
        "explorer": "https://optimistic.etherscan.io",
        "poa": True,
    },
}


# ---------------------------------------------------------------------------
# Well-known token addresses per chain
# ---------------------------------------------------------------------------

WELL_KNOWN_TOKENS: dict[str, dict[str, dict[str, Any]]] = {
    "ethereum": {
        "USDC": {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
        "USDT": {"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
        "DAI": {"address": "0x6B175474E89094C44Da98b954EedeAC495271d0F", "decimals": 18},
        "WETH": {"address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "decimals": 18},
        "WBTC": {"address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "decimals": 8},
    },
    "arbitrum": {
        "USDC": {"address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "decimals": 6},
        "USDC.e": {"address": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8", "decimals": 6},
        "USDT": {"address": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", "decimals": 6},
        "DAI": {"address": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1", "decimals": 18},
        "WETH": {"address": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", "decimals": 18},
        "WBTC": {"address": "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f", "decimals": 8},
        "ARB": {"address": "0x912CE59144191C1204E64559FE8253a0e49E6548", "decimals": 18},
    },
    "base": {
        "USDC": {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "decimals": 6},
        "USDbC": {"address": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA", "decimals": 6},
        "DAI": {"address": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb", "decimals": 18},
        "WETH": {"address": "0x4200000000000000000000000000000000000006", "decimals": 18},
    },
    "polygon": {
        "USDC": {"address": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "decimals": 6},
        "USDC.e": {"address": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174", "decimals": 6},
        "USDT": {"address": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F", "decimals": 6},
        "DAI": {"address": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063", "decimals": 18},
        "WETH": {"address": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", "decimals": 18},
        "WBTC": {"address": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6", "decimals": 8},
        "WMATIC": {"address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270", "decimals": 18},
    },
    "bsc": {
        "USDC": {"address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", "decimals": 18},
        "USDT": {"address": "0x55d398326f99059fF775485246999027B3197955", "decimals": 18},
        "DAI": {"address": "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3", "decimals": 18},
        "WBNB": {"address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "decimals": 18},
        "WETH": {"address": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8", "decimals": 18},
        "BTCB": {"address": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", "decimals": 18},
    },
    "optimism": {
        "USDC": {"address": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85", "decimals": 6},
        "USDC.e": {"address": "0x7F5c764cBc14f9669B88837ca1490cCa17c31607", "decimals": 6},
        "USDT": {"address": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58", "decimals": 6},
        "DAI": {"address": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1", "decimals": 18},
        "WETH": {"address": "0x4200000000000000000000000000000000000006", "decimals": 18},
        "WBTC": {"address": "0x68f180fcCe6836688e9084f035309E29Bf0A2095", "decimals": 8},
        "OP": {"address": "0x4200000000000000000000000000000000000042", "decimals": 18},
    },
}


# ---------------------------------------------------------------------------
# Minimal ERC20 ABI
# ---------------------------------------------------------------------------

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
]


# ---------------------------------------------------------------------------
# EVM Wallet service layer
# ---------------------------------------------------------------------------

class EVMWalletServices:
    """EVM wallet operations — balances, transfers, approvals, gas.

    Supports read-only mode when no private key is provided.
    """

    def __init__(
        self,
        wallet_address: str,
        private_key: str | None = None,
    ):
        self.wallet_address = Web3.to_checksum_address(wallet_address)
        self.read_only = private_key is None
        self._private_key = private_key

        # Pre-build web3 instances for each chain
        self._w3_cache: dict[str, Web3] = {}

    # -- Internal helpers --

    def _get_w3(self, chain: str) -> Web3:
        """Get or create a Web3 instance for the given chain."""
        if chain not in CHAINS:
            raise ValueError(f"Unsupported chain: {chain}. Supported: {', '.join(CHAINS.keys())}")

        if chain not in self._w3_cache:
            cfg = CHAINS[chain]
            w3 = Web3(Web3.HTTPProvider(cfg["rpc"]))
            if cfg["poa"]:
                w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            self._w3_cache[chain] = w3
        return self._w3_cache[chain]

    def _require_write(self) -> None:
        """Raise if no private key is configured."""
        if self.read_only:
            raise PermissionError(
                "EVM_PRIVATE_KEY is required for write operations (transfers, approvals). "
                "Run 'config' to check your setup."
            )

    def _resolve_token(self, chain: str, token: str) -> dict[str, Any] | None:
        """Resolve a token symbol or address to its info dict.

        Returns dict with 'address' and 'decimals', or None if not found in well-known list.
        For raw addresses, queries on-chain for decimals.
        """
        chain_tokens = WELL_KNOWN_TOKENS.get(chain, {})

        # Check by symbol (case-insensitive)
        token_upper = token.upper()
        for sym, info in chain_tokens.items():
            if sym.upper() == token_upper:
                return {"address": info["address"], "decimals": info["decimals"], "symbol": sym}

        # Check by address
        if token.startswith("0x") and len(token) == 42:
            checksum = Web3.to_checksum_address(token)
            # Check if it matches a well-known token address
            for sym, info in chain_tokens.items():
                if Web3.to_checksum_address(info["address"]) == checksum:
                    return {"address": info["address"], "decimals": info["decimals"], "symbol": sym}
            # Not well-known — query on-chain
            try:
                w3 = self._get_w3(chain)
                contract = w3.eth.contract(address=checksum, abi=ERC20_ABI)
                decimals = contract.functions.decimals().call()
                try:
                    symbol = contract.functions.symbol().call()
                except Exception:
                    symbol = "UNKNOWN"
                return {"address": checksum, "decimals": decimals, "symbol": symbol}
            except Exception as e:
                logger.warning(f"Failed to query token {token} on {chain}: {e}")
                return None

        return None

    def _is_native_token(self, chain: str, token: str) -> bool:
        """Check if the token string refers to the chain's native token."""
        native = CHAINS[chain]["native_symbol"]
        token_upper = token.upper()
        # Match native symbol or common aliases
        if token_upper == native.upper():
            return True
        # ETH on Ethereum/Arbitrum/Base/Optimism, POL on Polygon, BNB on BSC
        return False

    def _build_and_send_tx(self, chain: str, tx: dict) -> dict:
        """Sign and send a transaction, return receipt info."""
        self._require_write()
        w3 = self._get_w3(chain)
        cfg = CHAINS[chain]

        tx["from"] = self.wallet_address
        tx["chainId"] = cfg["chain_id"]

        if "nonce" not in tx:
            tx["nonce"] = w3.eth.get_transaction_count(self.wallet_address)

        if "gas" not in tx:
            tx["gas"] = w3.eth.estimate_gas(tx)

        if "gasPrice" not in tx and "maxFeePerGas" not in tx:
            tx["gasPrice"] = w3.eth.gas_price

        from eth_account import Account
        signed = Account.sign_transaction(tx, self._private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        return {
            "tx_hash": receipt.transactionHash.hex(),
            "status": "confirmed" if receipt.status == 1 else "failed",
            "block_number": receipt.blockNumber,
            "gas_used": receipt.gasUsed,
            "explorer_url": f"{cfg['explorer']}/tx/0x{receipt.transactionHash.hex()}"
            if not receipt.transactionHash.hex().startswith("0x")
            else f"{cfg['explorer']}/tx/{receipt.transactionHash.hex()}",
        }

    # -- Public methods --

    def show_config(self) -> dict:
        """Show current configuration status."""
        return {
            "success": True,
            "wallet_address": self.wallet_address,
            "read_only": self.read_only,
            "has_private_key": not self.read_only,
            "supported_chains": list(CHAINS.keys()),
            "chains": {
                name: {
                    "chain_id": cfg["chain_id"],
                    "native_symbol": cfg["native_symbol"],
                    "explorer": cfg["explorer"],
                }
                for name, cfg in CHAINS.items()
            },
        }

    def get_balances(self, chain: str = "ethereum") -> dict:
        """Get native + well-known ERC20 token balances on a chain."""
        try:
            w3 = self._get_w3(chain)
            cfg = CHAINS[chain]

            # Native balance
            native_wei = w3.eth.get_balance(self.wallet_address)
            native_balance = str(Web3.from_wei(native_wei, "ether"))

            balances = [
                {
                    "token": cfg["native_symbol"],
                    "balance": native_balance,
                    "address": "native",
                }
            ]

            # ERC20 balances
            chain_tokens = WELL_KNOWN_TOKENS.get(chain, {})
            for symbol, info in chain_tokens.items():
                try:
                    contract = w3.eth.contract(
                        address=Web3.to_checksum_address(info["address"]),
                        abi=ERC20_ABI,
                    )
                    raw = contract.functions.balanceOf(self.wallet_address).call()
                    balance = str(Decimal(raw) / Decimal(10 ** info["decimals"]))
                    if Decimal(balance) > 0:
                        balances.append({
                            "token": symbol,
                            "balance": balance,
                            "address": info["address"],
                        })
                except Exception as e:
                    logger.warning(f"Failed to query {symbol} on {chain}: {e}")

            return {
                "success": True,
                "chain": chain,
                "wallet": self.wallet_address,
                "balances": balances,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_all_chain_balances(self) -> dict:
        """Get balances across all supported chains."""
        try:
            results = {}
            for chain in CHAINS:
                result = self.get_balances(chain)
                if result.get("success"):
                    # Only include chains where there's a non-zero balance
                    non_zero = [b for b in result["balances"] if Decimal(b["balance"]) > 0]
                    if non_zero:
                        results[chain] = non_zero

            return {
                "success": True,
                "wallet": self.wallet_address,
                "chains": results,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_token_balance(self, chain: str, token: str) -> dict:
        """Get balance of a specific token (native or ERC20)."""
        try:
            w3 = self._get_w3(chain)
            cfg = CHAINS[chain]

            if self._is_native_token(chain, token):
                native_wei = w3.eth.get_balance(self.wallet_address)
                balance = str(Web3.from_wei(native_wei, "ether"))
                return {
                    "success": True,
                    "chain": chain,
                    "token": cfg["native_symbol"],
                    "balance": balance,
                    "address": "native",
                }

            token_info = self._resolve_token(chain, token)
            if not token_info:
                return {
                    "success": False,
                    "error": f"Token '{token}' not found on {chain}. "
                    f"Use a contract address or one of: {', '.join(WELL_KNOWN_TOKENS.get(chain, {}).keys())}",
                }

            contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_info["address"]),
                abi=ERC20_ABI,
            )
            raw = contract.functions.balanceOf(self.wallet_address).call()
            balance = str(Decimal(raw) / Decimal(10 ** token_info["decimals"]))

            return {
                "success": True,
                "chain": chain,
                "token": token_info["symbol"],
                "balance": balance,
                "address": token_info["address"],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def transfer(self, chain: str, token: str, to: str, amount: float) -> dict:
        """Transfer native token or ERC20 to an address."""
        try:
            self._require_write()
            w3 = self._get_w3(chain)
            cfg = CHAINS[chain]
            to_address = Web3.to_checksum_address(to)

            if self._is_native_token(chain, token):
                # Native transfer
                value_wei = Web3.to_wei(Decimal(str(amount)), "ether")
                tx = {
                    "to": to_address,
                    "value": value_wei,
                }
                receipt = self._build_and_send_tx(chain, tx)
                return {
                    "success": True,
                    "chain": chain,
                    "token": cfg["native_symbol"],
                    "amount": str(amount),
                    "to": to,
                    **receipt,
                }

            # ERC20 transfer
            token_info = self._resolve_token(chain, token)
            if not token_info:
                return {
                    "success": False,
                    "error": f"Token '{token}' not found on {chain}. "
                    f"Use a contract address or one of: {', '.join(WELL_KNOWN_TOKENS.get(chain, {}).keys())}",
                }

            contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_info["address"]),
                abi=ERC20_ABI,
            )
            raw_amount = int(Decimal(str(amount)) * Decimal(10 ** token_info["decimals"]))
            tx = contract.functions.transfer(to_address, raw_amount).build_transaction({
                "from": self.wallet_address,
                "chainId": cfg["chain_id"],
                "nonce": w3.eth.get_transaction_count(self.wallet_address),
            })
            # Remove 'from' and 'chainId' since _build_and_send_tx will set them
            # Actually, pass the built tx directly to sign and send
            from eth_account import Account
            if "gas" not in tx:
                tx["gas"] = w3.eth.estimate_gas(tx)
            if "gasPrice" not in tx and "maxFeePerGas" not in tx:
                tx["gasPrice"] = w3.eth.gas_price

            signed = Account.sign_transaction(tx, self._private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            result = {
                "tx_hash": receipt.transactionHash.hex(),
                "status": "confirmed" if receipt.status == 1 else "failed",
                "block_number": receipt.blockNumber,
                "gas_used": receipt.gasUsed,
                "explorer_url": f"{cfg['explorer']}/tx/{receipt.transactionHash.hex()}"
                if receipt.transactionHash.hex().startswith("0x")
                else f"{cfg['explorer']}/tx/0x{receipt.transactionHash.hex()}",
            }

            return {
                "success": True,
                "chain": chain,
                "token": token_info["symbol"],
                "amount": str(amount),
                "to": to,
                **result,
            }
        except PermissionError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_allowance(self, chain: str, token: str, spender: str) -> dict:
        """Check current ERC20 allowance for a spender."""
        try:
            w3 = self._get_w3(chain)
            spender_address = Web3.to_checksum_address(spender)

            token_info = self._resolve_token(chain, token)
            if not token_info:
                return {
                    "success": False,
                    "error": f"Token '{token}' not found on {chain}.",
                }

            contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_info["address"]),
                abi=ERC20_ABI,
            )
            raw_allowance = contract.functions.allowance(
                self.wallet_address, spender_address
            ).call()
            allowance = str(Decimal(raw_allowance) / Decimal(10 ** token_info["decimals"]))

            return {
                "success": True,
                "chain": chain,
                "token": token_info["symbol"],
                "token_address": token_info["address"],
                "owner": self.wallet_address,
                "spender": spender,
                "allowance": allowance,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def approve(self, chain: str, token: str, spender: str, amount: float) -> dict:
        """Approve a spender to use ERC20 tokens."""
        try:
            self._require_write()
            w3 = self._get_w3(chain)
            cfg = CHAINS[chain]
            spender_address = Web3.to_checksum_address(spender)

            token_info = self._resolve_token(chain, token)
            if not token_info:
                return {
                    "success": False,
                    "error": f"Token '{token}' not found on {chain}.",
                }

            contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_info["address"]),
                abi=ERC20_ABI,
            )
            raw_amount = int(Decimal(str(amount)) * Decimal(10 ** token_info["decimals"]))
            tx = contract.functions.approve(spender_address, raw_amount).build_transaction({
                "from": self.wallet_address,
                "chainId": cfg["chain_id"],
                "nonce": w3.eth.get_transaction_count(self.wallet_address),
            })

            from eth_account import Account
            if "gas" not in tx:
                tx["gas"] = w3.eth.estimate_gas(tx)
            if "gasPrice" not in tx and "maxFeePerGas" not in tx:
                tx["gasPrice"] = w3.eth.gas_price

            signed = Account.sign_transaction(tx, self._private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            result = {
                "tx_hash": receipt.transactionHash.hex(),
                "status": "confirmed" if receipt.status == 1 else "failed",
                "block_number": receipt.blockNumber,
                "gas_used": receipt.gasUsed,
                "explorer_url": f"{cfg['explorer']}/tx/{receipt.transactionHash.hex()}"
                if receipt.transactionHash.hex().startswith("0x")
                else f"{cfg['explorer']}/tx/0x{receipt.transactionHash.hex()}",
            }

            return {
                "success": True,
                "chain": chain,
                "token": token_info["symbol"],
                "spender": spender,
                "amount": str(amount),
                **result,
            }
        except PermissionError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def revoke(self, chain: str, token: str, spender: str) -> dict:
        """Revoke ERC20 approval for a spender (set allowance to 0)."""
        return self.approve(chain, token, spender, amount=0)

    def get_gas_price(self, chain: str = "ethereum") -> dict:
        """Get current gas price on a chain."""
        try:
            w3 = self._get_w3(chain)
            gas_price_wei = w3.eth.gas_price
            gas_price_gwei = float(Web3.from_wei(gas_price_wei, "gwei"))

            # Estimate costs for common operations
            native_transfer_gas = 21000
            erc20_transfer_gas = 65000
            approval_gas = 46000

            native_symbol = CHAINS[chain]["native_symbol"]

            return {
                "success": True,
                "chain": chain,
                "gas_price_gwei": round(gas_price_gwei, 4),
                "gas_price_wei": gas_price_wei,
                "estimates": {
                    "native_transfer": {
                        "gas_units": native_transfer_gas,
                        f"cost_{native_symbol.lower()}": round(
                            float(Web3.from_wei(gas_price_wei * native_transfer_gas, "ether")), 8
                        ),
                    },
                    "erc20_transfer": {
                        "gas_units": erc20_transfer_gas,
                        f"cost_{native_symbol.lower()}": round(
                            float(Web3.from_wei(gas_price_wei * erc20_transfer_gas, "ether")), 8
                        ),
                    },
                    "erc20_approval": {
                        "gas_units": approval_gas,
                        f"cost_{native_symbol.lower()}": round(
                            float(Web3.from_wei(gas_price_wei * approval_gas, "ether")), 8
                        ),
                    },
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_token_info(self, chain: str, token: str) -> dict:
        """Look up token info by symbol or address."""
        try:
            cfg = CHAINS[chain]

            if self._is_native_token(chain, token):
                return {
                    "success": True,
                    "chain": chain,
                    "symbol": cfg["native_symbol"],
                    "name": cfg["native_symbol"],
                    "decimals": 18,
                    "address": "native",
                    "type": "native",
                }

            token_info = self._resolve_token(chain, token)
            if not token_info:
                return {
                    "success": False,
                    "error": f"Token '{token}' not found on {chain}. "
                    f"Available: {', '.join(WELL_KNOWN_TOKENS.get(chain, {}).keys())}",
                }

            # Try to get the full name on-chain
            w3 = self._get_w3(chain)
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_info["address"]),
                abi=ERC20_ABI,
            )
            try:
                name = contract.functions.name().call()
            except Exception:
                name = token_info["symbol"]

            return {
                "success": True,
                "chain": chain,
                "symbol": token_info["symbol"],
                "name": name,
                "decimals": token_info["decimals"],
                "address": token_info["address"],
                "type": "ERC20",
                "explorer_url": f"{cfg['explorer']}/token/{token_info['address']}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
