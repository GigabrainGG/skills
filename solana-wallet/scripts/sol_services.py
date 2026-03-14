"""Solana wallet service layer — balances, transfers, token info.

Self-contained module using solders and solana-py.
Supports read-only mode when no private key is provided.
"""

from __future__ import annotations

import logging
from typing import Any

from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TokenAccountOpts, TxOpts
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction
from spl.token.constants import TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID
from spl.token.instructions import (
    create_associated_token_account,
    get_associated_token_address,
    transfer_checked,
    TransferCheckedParams,
)

DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"
LAMPORTS_PER_SOL = 1_000_000_000

logger = logging.getLogger("sol_services")


class SolanaWalletServices:
    """Thin wrapper around solana-py with read-only support."""

    def __init__(
        self,
        wallet_address: str,
        private_key: str | None = None,
        rpc_url: str | None = None,
    ):
        self.wallet_address = wallet_address
        self.pubkey = Pubkey.from_string(wallet_address)
        self.rpc_url = rpc_url or DEFAULT_RPC_URL
        self.client = Client(self.rpc_url)
        self.keypair: Keypair | None = None
        if private_key:
            self.keypair = Keypair.from_base58_string(private_key)

    @property
    def has_signing(self) -> bool:
        return self.keypair is not None

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def show_config(self) -> dict[str, Any]:
        return {
            "success": True,
            "wallet_address": self.wallet_address,
            "rpc_url": self.rpc_url,
            "signing_enabled": self.has_signing,
        }

    # ------------------------------------------------------------------
    # Balances
    # ------------------------------------------------------------------

    def get_balances(self) -> dict[str, Any]:
        """Get SOL balance and all SPL token balances."""
        try:
            # SOL balance
            resp = self.client.get_balance(self.pubkey, commitment=Confirmed)
            sol_lamports = resp.value
            sol_balance = sol_lamports / LAMPORTS_PER_SOL

            # SPL token balances
            token_resp = self.client.get_token_accounts_by_owner_json_parsed(
                self.pubkey,
                TokenAccountOpts(program_id=TOKEN_PROGRAM_ID),
                commitment=Confirmed,
            )

            tokens = []
            for account in token_resp.value:
                parsed = account.account.data.parsed
                info = parsed["info"]
                token_amount = info["tokenAmount"]
                ui_amount = token_amount.get("uiAmount")
                if ui_amount is not None and ui_amount > 0:
                    tokens.append({
                        "mint": info["mint"],
                        "amount": ui_amount,
                        "decimals": token_amount["decimals"],
                        "token_account": str(account.pubkey),
                    })

            return {
                "success": True,
                "wallet": self.wallet_address,
                "sol_balance": sol_balance,
                "sol_lamports": sol_lamports,
                "spl_tokens": tokens,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to get balances: {e}"}

    def get_token_balance(self, mint_address: str) -> dict[str, Any]:
        """Get balance of a specific SPL token by mint address."""
        try:
            mint_pubkey = Pubkey.from_string(mint_address)
            ata = get_associated_token_address(self.pubkey, mint_pubkey)

            try:
                resp = self.client.get_token_account_balance(ata, commitment=Confirmed)
                token_amount = resp.value
                return {
                    "success": True,
                    "mint": mint_address,
                    "token_account": str(ata),
                    "amount": token_amount.ui_amount,
                    "decimals": token_amount.decimals,
                    "raw_amount": token_amount.amount,
                }
            except Exception:
                # Token account doesn't exist — zero balance
                return {
                    "success": True,
                    "mint": mint_address,
                    "token_account": str(ata),
                    "amount": 0,
                    "decimals": None,
                    "raw_amount": "0",
                }
        except Exception as e:
            return {"success": False, "error": f"Failed to get token balance: {e}"}

    # ------------------------------------------------------------------
    # Transfers
    # ------------------------------------------------------------------

    def _require_signing(self) -> Keypair:
        if not self.keypair:
            raise RuntimeError(
                "Signing not available. Set SOL_PRIVATE_KEY to enable transfers."
            )
        return self.keypair

    def transfer_sol(self, to_address: str, amount: float) -> dict[str, Any]:
        """Transfer SOL to another wallet."""
        try:
            kp = self._require_signing()
            to_pubkey = Pubkey.from_string(to_address)
            lamports = int(amount * LAMPORTS_PER_SOL)

            if lamports <= 0:
                return {"success": False, "error": "Amount must be positive"}

            # Check balance first
            resp = self.client.get_balance(self.pubkey, commitment=Confirmed)
            current_balance = resp.value
            if current_balance < lamports:
                return {
                    "success": False,
                    "error": f"Insufficient SOL balance. Have {current_balance / LAMPORTS_PER_SOL:.9f}, need {amount}",
                }

            # Build and send transaction
            recent_blockhash = self.client.get_latest_blockhash(commitment=Confirmed).value.blockhash
            ix = transfer(
                TransferParams(
                    from_pubkey=self.pubkey,
                    to_pubkey=to_pubkey,
                    lamports=lamports,
                )
            )
            tx = Transaction.new_signed_with_payer(
                [ix], self.pubkey, [kp], recent_blockhash
            )
            result = self.client.send_transaction(
                tx, opts=TxOpts(skip_confirmation=False, preflight_commitment=Confirmed),
            )
            sig = str(result.value)

            return {
                "success": True,
                "action": "transfer_sol",
                "from": self.wallet_address,
                "to": to_address,
                "amount_sol": amount,
                "lamports": lamports,
                "signature": sig,
            }
        except RuntimeError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"SOL transfer failed: {e}"}

    def transfer_spl(
        self, mint_address: str, to_address: str, amount: float
    ) -> dict[str, Any]:
        """Transfer SPL tokens to another wallet."""
        try:
            kp = self._require_signing()
            mint_pubkey = Pubkey.from_string(mint_address)
            to_pubkey = Pubkey.from_string(to_address)

            if amount <= 0:
                return {"success": False, "error": "Amount must be positive"}

            # Get source token account and decimals
            source_ata = get_associated_token_address(self.pubkey, mint_pubkey)

            try:
                source_info = self.client.get_token_account_balance(
                    source_ata, commitment=Confirmed
                )
                decimals = source_info.value.decimals
                current_balance = source_info.value.ui_amount or 0
            except Exception:
                return {
                    "success": False,
                    "error": f"No token account found for mint {mint_address}. Balance is 0.",
                }

            if current_balance < amount:
                return {
                    "success": False,
                    "error": f"Insufficient token balance. Have {current_balance}, need {amount}",
                }

            raw_amount = int(amount * (10 ** decimals))

            # Get or create destination ATA
            dest_ata = get_associated_token_address(to_pubkey, mint_pubkey)

            recent_blockhash = self.client.get_latest_blockhash(commitment=Confirmed).value.blockhash
            instructions = []

            # Check if destination ATA exists
            dest_account = self.client.get_account_info(dest_ata, commitment=Confirmed)
            if dest_account.value is None:
                # Create the associated token account for the recipient
                create_ata_ix = create_associated_token_account(
                    payer=self.pubkey,
                    owner=to_pubkey,
                    mint=mint_pubkey,
                )
                instructions.append(create_ata_ix)

            # Transfer instruction
            transfer_ix = transfer_checked(
                TransferCheckedParams(
                    program_id=TOKEN_PROGRAM_ID,
                    source=source_ata,
                    mint=mint_pubkey,
                    dest=dest_ata,
                    owner=self.pubkey,
                    amount=raw_amount,
                    decimals=decimals,
                )
            )
            instructions.append(transfer_ix)

            tx = Transaction.new_signed_with_payer(
                instructions, self.pubkey, [kp], recent_blockhash
            )
            result = self.client.send_transaction(
                tx, opts=TxOpts(skip_confirmation=False, preflight_commitment=Confirmed),
            )
            sig = str(result.value)

            return {
                "success": True,
                "action": "transfer_spl",
                "mint": mint_address,
                "from": self.wallet_address,
                "to": to_address,
                "amount": amount,
                "raw_amount": raw_amount,
                "decimals": decimals,
                "signature": sig,
            }
        except RuntimeError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"SPL transfer failed: {e}"}

    # ------------------------------------------------------------------
    # Token Info
    # ------------------------------------------------------------------

    def get_token_info(self, mint_address: str) -> dict[str, Any]:
        """Get token metadata for a mint address."""
        try:
            mint_pubkey = Pubkey.from_string(mint_address)

            # Get mint account info for supply and decimals
            resp = self.client.get_account_info_json_parsed(
                mint_pubkey, commitment=Confirmed
            )

            if resp.value is None:
                return {
                    "success": False,
                    "error": f"Mint account not found: {mint_address}",
                }

            parsed = resp.value.data.parsed
            info = parsed["info"]

            return {
                "success": True,
                "mint": mint_address,
                "decimals": info.get("decimals"),
                "supply": info.get("supply"),
                "mint_authority": info.get("mintAuthority"),
                "freeze_authority": info.get("freezeAuthority"),
                "is_initialized": info.get("isInitialized", False),
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to get token info: {e}"}
