import importlib.util
import os
import sys
import types
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent / "hl_client.py"


class FakeHLServices:
    def __init__(
        self,
        *,
        account_address,
        private_key,
        testnet,
        builder_address,
        builder_fee_bps,
    ):
        self.account_address = account_address
        self.private_key = private_key
        self.testnet = testnet
        self.builder_address = builder_address
        self.builder_fee_bps = builder_fee_bps


def load_hl_client(monkeypatch):
    fake_module = types.ModuleType("hl_services")
    fake_module.HLServices = FakeHLServices
    monkeypatch.setitem(sys.modules, "hl_services", fake_module)

    spec = importlib.util.spec_from_file_location("hl_client_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_get_services_prefers_hyperliquid_env_over_generic_evm(monkeypatch):
    monkeypatch.setenv("HYPERLIQUID_ACCOUNT_ADDRESS", "0xhyperliquid")
    monkeypatch.setenv("HYPERLIQUID_PRIVATE_KEY", "0xhl-private")
    monkeypatch.setenv("EVM_WALLET_ADDRESS", "0xevm")
    monkeypatch.setenv("EVM_PRIVATE_KEY", "0xevm-private")

    hl_client = load_hl_client(monkeypatch)
    services = hl_client._get_services(require_address=True)

    assert services.account_address == "0xhyperliquid"
    assert services.private_key == "0xhl-private"


def test_get_services_falls_back_to_evm_env(monkeypatch):
    monkeypatch.delenv("HYPERLIQUID_ACCOUNT_ADDRESS", raising=False)
    monkeypatch.delenv("HYPERLIQUID_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("EVM_WALLET_ADDRESS", "0xevm")
    monkeypatch.setenv("EVM_PRIVATE_KEY", "0xevm-private")

    hl_client = load_hl_client(monkeypatch)
    services = hl_client._get_services(require_address=True)

    assert services.account_address == "0xevm"
    assert services.private_key == "0xevm-private"


def test_get_services_does_not_fallback_to_evm_private_key_for_selected_hl_account(monkeypatch):
    monkeypatch.setenv("HYPERLIQUID_ACCOUNT_ADDRESS", "0xhyperliquid")
    monkeypatch.delenv("HYPERLIQUID_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("EVM_PRIVATE_KEY", "0xevm-private")

    hl_client = load_hl_client(monkeypatch)
    services = hl_client._get_services(require_address=True)

    assert services.account_address == "0xhyperliquid"
    assert services.private_key is None
