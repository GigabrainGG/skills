"""Tests for polymarket skill pure functions and CLI smoke tests.

Run with: uv run pytest test_pm.py -v
"""
from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from pm_services import (
    Market,
    MarketQuality,
    PreTradeResult,
    _expand_query_terms,
    _normalize_text,
    compute_composite_score,
    compute_market_quality,
    score_relevance,
    validate_pre_trade,
)


# ---------------------------------------------------------------------------
# _normalize_text
# ---------------------------------------------------------------------------

class TestNormalizeText:
    def test_basic(self):
        assert _normalize_text("Hello World!") == "hello world"

    def test_strips_dollar_signs(self):
        assert _normalize_text("$100,000") == "100000"

    def test_removes_commas_in_numbers(self):
        assert _normalize_text("1,000,000") == "1000000"

    def test_none_returns_empty(self):
        assert _normalize_text(None) == ""

    def test_empty_returns_empty(self):
        assert _normalize_text("") == ""

    def test_special_chars_become_spaces(self):
        assert _normalize_text("foo-bar_baz") == "foo bar baz"

    def test_collapses_whitespace(self):
        assert _normalize_text("  too   many   spaces  ") == "too many spaces"


# ---------------------------------------------------------------------------
# _expand_query_terms
# ---------------------------------------------------------------------------

class TestExpandQueryTerms:
    def test_basic_terms(self):
        terms = _expand_query_terms("bitcoin price")
        assert "bitcoin" in terms
        assert "price" in terms

    def test_aliases_expanded(self):
        terms = _expand_query_terms("btc")
        assert "btc" in terms
        assert "bitcoin" in terms

    def test_stopwords_removed(self):
        terms = _expand_query_terms("will bitcoin hit 100k")
        assert "will" not in terms
        assert "hit" not in terms
        assert "bitcoin" in terms

    def test_k_suffix_expanded(self):
        terms = _expand_query_terms("100k")
        assert "100k" in terms
        assert "100000" in terms

    def test_m_suffix_expanded(self):
        terms = _expand_query_terms("1m")
        assert "1m" in terms
        assert "1000000" in terms

    def test_empty_query(self):
        assert _expand_query_terms("") == set()


# ---------------------------------------------------------------------------
# score_relevance
# ---------------------------------------------------------------------------

class TestScoreRelevance:
    def test_exact_match_high_score(self):
        score = score_relevance("bitcoin", "Will bitcoin hit 100k?")
        assert score > 50

    def test_no_match_zero(self):
        score = score_relevance("dogecoin", "Federal Reserve interest rates")
        assert score == 0.0

    def test_empty_query_zero(self):
        assert score_relevance("", "some text") == 0.0

    def test_empty_text_zero(self):
        assert score_relevance("bitcoin", "") == 0.0

    def test_slug_bonus(self):
        base = score_relevance("bitcoin", "Will BTC hit 100k?")
        with_slug = score_relevance("bitcoin", "Will BTC hit 100k?", slug="bitcoin-100k")
        assert with_slug >= base

    def test_exact_substring_bonus(self):
        # Exact query match should score higher than scattered terms
        exact = score_relevance("bitcoin price", "What is the bitcoin price today?")
        scattered = score_relevance("bitcoin price", "bitcoin and ethereum have a good price")
        assert exact >= scattered

    def test_score_capped_at_100(self):
        score = score_relevance("bitcoin btc crypto", "bitcoin btc crypto", slug="bitcoin-btc-crypto")
        assert score <= 100.0


# ---------------------------------------------------------------------------
# compute_market_quality
# ---------------------------------------------------------------------------

class TestComputeMarketQuality:
    def test_healthy_market(self):
        q = compute_market_quality(
            liquidity_usd=50_000, volume_24h=10_000, spread=0.02,
            active=True, closed=False, accepting_orders=True, ready=True,
        )
        assert q.is_tradable
        assert q.tradability_score > 50
        assert len(q.warnings) == 0

    def test_zero_liquidity(self):
        q = compute_market_quality(
            liquidity_usd=0, volume_24h=0, spread=0.05,
            active=True, closed=False, accepting_orders=True, ready=True,
        )
        assert not q.is_tradable
        assert any("liquidity" in w.lower() for w in q.warnings)

    def test_closed_market(self):
        q = compute_market_quality(
            liquidity_usd=100_000, volume_24h=50_000, spread=0.01,
            active=True, closed=True, accepting_orders=True, ready=True,
        )
        assert not q.is_tradable
        assert any("closed" in w.lower() for w in q.warnings)

    def test_wide_spread_warning(self):
        q = compute_market_quality(
            liquidity_usd=50_000, volume_24h=10_000, spread=0.15,
            active=True, closed=False, accepting_orders=True, ready=True,
        )
        assert q.is_tradable  # spread doesn't block tradability by itself
        assert any("spread" in w.lower() for w in q.warnings)

    def test_none_spread(self):
        q = compute_market_quality(
            liquidity_usd=50_000, volume_24h=10_000, spread=None,
            active=True, closed=False, accepting_orders=True, ready=True,
        )
        assert q.is_tradable
        assert q.spread_pct is None


# ---------------------------------------------------------------------------
# compute_composite_score
# ---------------------------------------------------------------------------

class TestCompositeScore:
    def test_both_positive(self):
        score = compute_composite_score(80, 60)
        assert score > 0
        assert score == pytest.approx((80 * 60) ** 0.5, rel=1e-6)

    def test_zero_relevance(self):
        assert compute_composite_score(0, 80) == 0.0

    def test_zero_quality(self):
        assert compute_composite_score(80, 0) == 0.0

    def test_negative_input(self):
        assert compute_composite_score(-10, 80) == 0.0


# ---------------------------------------------------------------------------
# validate_pre_trade
# ---------------------------------------------------------------------------

def _make_market(**overrides) -> Market:
    """Create a minimal Market object for testing."""
    defaults = {
        "id": "test-market-id",
        "condition_id": "0x" + "ab" * 32,
        "question_id": "0x" + "cd" * 32,
        "question": "Will BTC hit 100k?",
        "tokens": [
            {"token_id": "tok_yes", "outcome": "Yes", "price": 0.65},
            {"token_id": "tok_no", "outcome": "No", "price": 0.35},
        ],
        "outcomes": ["Yes", "No"],
        "active": True,
        "closed": False,
        "archived": False,
        "acceptingOrders": True,
        "ready": True,
        "negRisk": False,
        "liquidity": 50000,
        "volume": 10000,
        "volume24hr": 5000,
        "spread": 0.02,
        "bestBid": 0.64,
        "bestAsk": 0.66,
    }
    defaults.update(overrides)
    return Market(**defaults)


class TestValidatePreTrade:
    def test_valid_limit_buy(self):
        market = _make_market()
        result = validate_pre_trade(
            market=market, outcome="Yes", amount_usd=50, price=0.65,
            usdc_balance=100,
        )
        assert result.can_trade
        assert all(c.passed for c in result.checks)

    def test_empty_outcome_fails(self):
        market = _make_market()
        result = validate_pre_trade(market=market, outcome="", amount_usd=50, price=0.65)
        assert not result.can_trade
        assert result.checks[0].name == "input"
        assert not result.checks[0].passed

    def test_zero_amount_fails(self):
        market = _make_market()
        result = validate_pre_trade(market=market, outcome="Yes", amount_usd=0, price=0.65)
        assert not result.can_trade

    def test_invalid_price_fails(self):
        market = _make_market()
        result = validate_pre_trade(market=market, outcome="Yes", amount_usd=50, price=1.5)
        assert not result.can_trade

    def test_closed_market_fails(self):
        market = _make_market(closed=True)
        result = validate_pre_trade(market=market, outcome="Yes", amount_usd=50, price=0.65)
        assert not result.can_trade
        assert any(c.name == "market_status" and not c.passed for c in result.checks)

    def test_inactive_market_fails(self):
        market = _make_market(active=False)
        result = validate_pre_trade(market=market, outcome="Yes", amount_usd=50, price=0.65)
        assert not result.can_trade

    def test_archived_market_fails(self):
        market = _make_market(archived=True)
        result = validate_pre_trade(market=market, outcome="Yes", amount_usd=50, price=0.65)
        assert not result.can_trade

    def test_wrong_outcome_fails(self):
        market = _make_market()
        result = validate_pre_trade(market=market, outcome="Maybe", amount_usd=50, price=0.65)
        assert not result.can_trade
        assert any(c.name == "outcome" and not c.passed for c in result.checks)

    def test_low_liquidity_fails(self):
        market = _make_market(liquidity=100)
        result = validate_pre_trade(market=market, outcome="Yes", amount_usd=50, price=0.65)
        assert not result.can_trade
        assert any(c.name == "liquidity" and not c.passed for c in result.checks)

    def test_low_liquidity_bypass(self):
        market = _make_market(liquidity=100)
        result = validate_pre_trade(
            market=market, outcome="Yes", amount_usd=50, price=0.65,
            skip_liquidity_check=True,
        )
        assert result.can_trade
        assert len(result.warnings) > 0

    def test_wide_spread_fails(self):
        market = _make_market(spread=0.20)
        result = validate_pre_trade(market=market, outcome="Yes", amount_usd=50, price=0.65)
        assert not result.can_trade
        assert any(c.name == "spread" and not c.passed for c in result.checks)

    def test_wide_spread_bypass(self):
        market = _make_market(spread=0.20)
        result = validate_pre_trade(
            market=market, outcome="Yes", amount_usd=50, price=0.65,
            skip_spread_check=True,
        )
        assert result.can_trade

    def test_insufficient_balance_fails(self):
        market = _make_market()
        result = validate_pre_trade(
            market=market, outcome="Yes", amount_usd=100, price=0.65,
            usdc_balance=50,
        )
        assert not result.can_trade
        assert any(c.name == "balance" and not c.passed for c in result.checks)

    def test_balance_not_checked_when_none(self):
        market = _make_market()
        result = validate_pre_trade(
            market=market, outcome="Yes", amount_usd=50, price=0.65,
            usdc_balance=None,
        )
        assert result.can_trade
        assert any("balance not checked" in w.lower() for w in result.warnings)

    def test_market_order_book_depth_check(self):
        market = _make_market()
        result = validate_pre_trade(
            market=market, outcome="Yes", amount_usd=100, price=None,
            is_market_order=True, book_depth_usd=50,
        )
        assert not result.can_trade
        assert any(c.name == "book_depth" and not c.passed for c in result.checks)

    def test_market_order_sufficient_depth(self):
        market = _make_market()
        result = validate_pre_trade(
            market=market, outcome="Yes", amount_usd=50, price=None,
            is_market_order=True, book_depth_usd=200,
        )
        assert result.can_trade


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------

class TestCLISmoke:
    """Verify argparse definitions don't break. These tests run --help on each
    command which parses args but does not execute any logic."""

    COMMANDS = [
        "events", "events-raw", "search", "markets-raw", "public-search",
        "public-search-raw", "trending", "odds", "resolve", "orderbook",
        "price-history", "market-trades", "buy", "sell", "balance",
        "approve-trading", "positions", "trades", "my-orders", "cancel-order",
        "check-order", "builder-status", "builder-trades", "fund-assets",
        "fund-quote", "fund-address", "fund-status", "withdraw-quote",
        "withdraw-address", "withdraw-status", "geoblock", "readiness",
        "assess", "validate-trade", "top-markets", "redeem", "split",
        "merge", "config",
    ]

    @pytest.mark.parametrize("command", COMMANDS)
    def test_help_exits_cleanly(self, command):
        result = subprocess.run(
            [sys.executable, "pm_client.py", command, "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"{command} --help failed: {result.stderr}"
        assert "usage:" in result.stdout.lower()
