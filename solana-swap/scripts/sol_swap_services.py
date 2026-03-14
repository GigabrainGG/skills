"""Solana swap service layer — Jupiter aggregator integration.

Self-contained module using httpx for API calls and solders for signing.
Supports read-only mode (quotes/prices) when no private key is provided.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx
from solders.keypair import Keypair  # type: ignore
from solders.transaction import VersionedTransaction  # type: ignore

JUPITER_FREE_API = "https://lite-api.jup.ag"
JUPITER_PAID_API = "https://api.jup.ag"
JUPITER_PRICE_API = "https://lite-api.jup.ag/price/v2"

DEFAULT_SLIPPAGE_BPS = 50  # 0.5%
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"

# Well-known SPL token mint addresses
KNOWN_MINTS: dict[str, str] = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "PYTH": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
}

logger = logging.getLogger("sol_swap_services")


class SolanaSwapServices:
    """Jupiter-based swap service for Solana SPL tokens."""

    def __init__(
        self,
        wallet_address: str,
        private_key: str | None = None,
        rpc_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.wallet_address = wallet_address
        self._private_key = private_key
        self.rpc_url = rpc_url or DEFAULT_RPC_URL
        self.api_key = api_key

        # Use paid API if key is provided, otherwise free tier
        if self.api_key:
            self.jupiter_api = JUPITER_PAID_API
        else:
            self.jupiter_api = JUPITER_FREE_API

    # ------------------------------------------------------------------
    # Config / status
    # ------------------------------------------------------------------

    def show_config(self) -> dict[str, Any]:
        return {
            "success": True,
            "wallet_address": self.wallet_address or "(not set)",
            "has_private_key": bool(self._private_key),
            "rpc_url": self.rpc_url,
            "jupiter_api": self.jupiter_api,
            "has_api_key": bool(self.api_key),
        }

    # ------------------------------------------------------------------
    # Token resolution
    # ------------------------------------------------------------------

    def _resolve_mint(self, token: str) -> str:
        """Resolve a token symbol or mint address to a mint address."""
        upper = token.strip().upper()
        if upper.startswith("$"):
            upper = upper[1:]
        if upper in KNOWN_MINTS:
            return KNOWN_MINTS[upper]
        # If it looks like a mint address (long base58), use as-is
        if len(token.strip()) >= 32:
            return token.strip()
        # Try case-insensitive match
        for symbol, mint in KNOWN_MINTS.items():
            if symbol == upper:
                return mint
        # Return as-is, Jupiter will validate
        return token.strip()

    def _get_decimals(self, mint: str) -> int:
        """Get token decimals for known tokens."""
        # SOL and wrapped SOL use 9 decimals
        if mint == KNOWN_MINTS.get("SOL"):
            return 9
        # USDC and USDT use 6 decimals
        if mint in (KNOWN_MINTS.get("USDC"), KNOWN_MINTS.get("USDT")):
            return 6
        # BONK uses 5 decimals
        if mint == KNOWN_MINTS.get("BONK"):
            return 5
        # JUP uses 6 decimals
        if mint == KNOWN_MINTS.get("JUP"):
            return 6
        # WIF uses 6 decimals
        if mint == KNOWN_MINTS.get("WIF"):
            return 6
        # PYTH uses 6 decimals
        if mint == KNOWN_MINTS.get("PYTH"):
            return 6
        # RAY uses 6 decimals
        if mint == KNOWN_MINTS.get("RAY"):
            return 6
        # Default to 6 for unknown tokens — caller should verify
        return 6

    def _get_headers(self) -> dict[str, str]:
        """Build HTTP headers including API key if available."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    # ------------------------------------------------------------------
    # Quote
    # ------------------------------------------------------------------

    async def get_quote(
        self,
        from_token: str,
        to_token: str,
        amount: float,
        slippage: float = 0.5,
    ) -> dict[str, Any]:
        """Get a swap quote from Jupiter.

        Args:
            from_token: Source token symbol or mint address.
            to_token: Destination token symbol or mint address.
            amount: Amount of source token to swap (human-readable).
            slippage: Slippage tolerance in percent (default 0.5%).

        Returns:
            Quote details including estimated output, price impact, and route.
        """
        input_mint = self._resolve_mint(from_token)
        output_mint = self._resolve_mint(to_token)
        decimals = self._get_decimals(input_mint)
        amount_raw = int(amount * (10 ** decimals))
        slippage_bps = int(slippage * 100)

        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount_raw),
            "slippageBps": str(slippage_bps),
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{self.jupiter_api}/swap/v1/quote",
                    params=params,
                    headers=self._get_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"Jupiter API error: {e.response.status_code} — {e.response.text}",
            }
        except httpx.RequestError as e:
            return {"success": False, "error": f"Request failed: {e}"}

        # Parse output amount
        out_decimals = self._get_decimals(output_mint)
        out_amount_raw = int(data.get("outAmount", 0))
        out_amount = out_amount_raw / (10 ** out_decimals)

        in_amount_raw = int(data.get("inAmount", 0))
        in_amount = in_amount_raw / (10 ** decimals)

        # Build route summary
        route_plan = data.get("routePlan", [])
        routes = []
        for step in route_plan:
            swap_info = step.get("swapInfo", {})
            routes.append({
                "amm": swap_info.get("label", "unknown"),
                "input_mint": swap_info.get("inputMint", ""),
                "output_mint": swap_info.get("outputMint", ""),
                "percent": step.get("percent", 100),
            })

        return {
            "success": True,
            "input_token": from_token.upper(),
            "input_mint": input_mint,
            "input_amount": in_amount,
            "output_token": to_token.upper(),
            "output_mint": output_mint,
            "output_amount": out_amount,
            "price_impact_pct": data.get("priceImpactPct", "0"),
            "slippage_bps": slippage_bps,
            "route_plan": routes,
            "raw_quote": data,
        }

    # ------------------------------------------------------------------
    # Swap
    # ------------------------------------------------------------------

    async def execute_swap(
        self,
        from_token: str,
        to_token: str,
        amount: float,
        slippage: float = 0.5,
    ) -> dict[str, Any]:
        """Execute a swap via Jupiter.

        Gets a quote, builds the transaction, signs it locally, and submits
        to the Solana RPC.

        Args:
            from_token: Source token symbol or mint address.
            to_token: Destination token symbol or mint address.
            amount: Amount of source token to swap (human-readable).
            slippage: Slippage tolerance in percent (default 0.5%).

        Returns:
            Transaction signature on success.
        """
        if not self._private_key:
            return {
                "success": False,
                "error": "SOL_PRIVATE_KEY is required for swap execution",
            }

        if not self.wallet_address:
            return {
                "success": False,
                "error": "SOL_WALLET_ADDRESS is required for swap execution",
            }

        # Step 1: Get quote
        quote_result = await self.get_quote(from_token, to_token, amount, slippage)
        if not quote_result.get("success"):
            return quote_result

        raw_quote = quote_result["raw_quote"]

        # Step 2: Get swap transaction from Jupiter
        swap_body = {
            "userPublicKey": self.wallet_address,
            "quoteResponse": raw_quote,
            "dynamicComputeUnitLimit": True,
            "dynamicSlippage": True,
            "prioritizationFeeLamports": {
                "priorityLevelWithMaxLamports": {
                    "maxLamports": 1000000,
                    "priorityLevel": "medium",
                }
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.jupiter_api}/swap/v1/swap",
                    json=swap_body,
                    headers=self._get_headers(),
                )
                resp.raise_for_status()
                swap_data = resp.json()
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"Jupiter swap API error: {e.response.status_code} — {e.response.text}",
            }
        except httpx.RequestError as e:
            return {"success": False, "error": f"Swap request failed: {e}"}

        swap_tx_b64 = swap_data.get("swapTransaction")
        if not swap_tx_b64:
            return {"success": False, "error": "No swapTransaction in Jupiter response"}

        # Step 3: Sign and send the transaction
        try:
            keypair = Keypair.from_base58_string(self._private_key)
            tx_bytes = base64.b64decode(swap_tx_b64)
            versioned_tx = VersionedTransaction.from_bytes(tx_bytes)

            # Sign the transaction
            signed_tx = VersionedTransaction(versioned_tx.message, [keypair])
            signed_tx_bytes = bytes(signed_tx)
            signed_tx_b64 = base64.b64encode(signed_tx_bytes).decode("utf-8")
        except Exception as e:
            return {"success": False, "error": f"Transaction signing failed: {e}"}

        # Step 4: Send via RPC
        try:
            rpc_body = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendTransaction",
                "params": [
                    signed_tx_b64,
                    {
                        "encoding": "base64",
                        "skipPreflight": False,
                        "maxRetries": 2,
                    },
                ],
            }
            async with httpx.AsyncClient(timeout=60) as client:
                rpc_resp = await client.post(
                    self.rpc_url,
                    json=rpc_body,
                    headers={"Content-Type": "application/json"},
                )
                rpc_resp.raise_for_status()
                rpc_data = rpc_resp.json()
        except httpx.RequestError as e:
            return {"success": False, "error": f"RPC request failed: {e}"}

        if "error" in rpc_data:
            rpc_error = rpc_data["error"]
            error_msg = rpc_error.get("message", str(rpc_error)) if isinstance(rpc_error, dict) else str(rpc_error)
            return {"success": False, "error": f"RPC error: {error_msg}"}

        tx_signature = rpc_data.get("result", "")
        return {
            "success": True,
            "transaction_signature": tx_signature,
            "explorer_url": f"https://solscan.io/tx/{tx_signature}",
            "input_token": from_token.upper(),
            "input_amount": quote_result["input_amount"],
            "output_token": to_token.upper(),
            "estimated_output": quote_result["output_amount"],
            "price_impact_pct": quote_result["price_impact_pct"],
        }

    # ------------------------------------------------------------------
    # Price
    # ------------------------------------------------------------------

    async def get_price(self, token: str) -> dict[str, Any]:
        """Get current token price by quoting a swap to USDC via Jupiter.

        Args:
            token: Token symbol or mint address.

        Returns:
            Token price in USD.
        """
        mint = self._resolve_mint(token)
        usdc_mint = KNOWN_MINTS["USDC"]

        # If asking for USDC price, it's always $1
        if mint == usdc_mint:
            return {
                "success": True,
                "token": "USDC",
                "mint": usdc_mint,
                "price_usd": 1.0,
            }

        # Get a quote for 1 unit of the token -> USDC to derive price
        decimals = self._get_decimals(mint)
        amount = 10 ** decimals  # 1 full token

        api_base = self.jupiter_api
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{api_base}/swap/v1/quote",
                    params={
                        "inputMint": mint,
                        "outputMint": usdc_mint,
                        "amount": amount,
                        "slippageBps": 50,
                    },
                    headers=self._get_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"Price lookup error: {e.response.status_code} — {e.response.text}",
            }
        except httpx.RequestError as e:
            return {"success": False, "error": f"Price request failed: {e}"}

        out_amount = int(data.get("outAmount", 0))
        # USDC has 6 decimals
        price_usd = out_amount / (10 ** 6)

        return {
            "success": True,
            "token": token.upper() if token.upper() in KNOWN_MINTS else token,
            "mint": mint,
            "price_usd": price_usd,
        }
