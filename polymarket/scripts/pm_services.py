"""Polymarket service layer - market data, quality scoring, and trading.

Self-contained module using:
- Gamma API (httpx) for market discovery
- CLOB API (py-clob-client) for trading & orderbook
- Data API (httpx) for positions/trades

No daemon-specific dependencies.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, PrivateAttr, field_validator

logger = logging.getLogger("pm_services")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STOPWORDS = {
    "a", "an", "and", "are", "be", "before", "by", "for", "from", "hit", "in",
    "is", "of", "on", "or", "reach", "the", "to", "what", "when", "will", "with",
}

QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "btc": ("bitcoin",),
    "bitcoin": ("btc",),
    "eth": ("ethereum",),
    "ethereum": ("eth",),
    "sol": ("solana",),
    "solana": ("sol",),
    "doge": ("dogecoin",),
    "dogecoin": ("doge",),
    "xrp": ("ripple",),
    "ripple": ("xrp",),
    "ada": ("cardano",),
    "cardano": ("ada",),
    "fed": ("federal reserve", "fomc"),
}

TAG_KEYWORDS: dict[str, set[str]] = {
    "crypto": {
        "bitcoin", "btc", "crypto", "cryptocurrency", "doge", "dogecoin",
        "ethereum", "eth", "sol", "solana", "xrp", "ripple", "cardano", "ada",
    },
    "politics": {
        "biden", "congress", "democrat", "democratic", "election", "elections",
        "governor", "macron", "mayor", "minister", "netanyahu", "politics",
        "president", "prime minister", "republican", "senate", "trump",
    },
    "sports": {
        "arsenal", "baseball", "basketball", "celtics", "champions league", "chiefs",
        "f1", "football", "formula 1", "knicks", "lakers", "mlb", "nba", "nfl",
        "nhl", "soccer", "super bowl", "ufc", "warriors", "world cup",
    },
    "economy": {
        "cpi", "economy", "fed", "federal reserve", "fomc", "gdp", "inflation",
        "interest rates", "jobs report", "payrolls", "rates", "recession",
    },
}

# Quality thresholds
MIN_LIQUIDITY_USD = 5_000
MAX_SPREAD_LIMIT = 0.10
BOOK_DEPTH_MULTIPLIER = 1.5


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    compact = re.sub(r"(?<=\d),(?=\d)", "", value.lower()).replace("$", "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", compact)).strip()


def _expand_query_terms(query: str) -> set[str]:
    normalized = _normalize_text(query)
    terms: set[str] = set()

    for token in normalized.split():
        if token in STOPWORDS:
            continue
        terms.add(token)
        if token.endswith("k") and token[:-1].isdigit():
            terms.add(str(int(token[:-1]) * 1000))
        if token.endswith("m") and token[:-1].isdigit():
            terms.add(str(int(token[:-1]) * 1_000_000))
        for alias in QUERY_ALIASES.get(token, ()):
            terms.add(_normalize_text(alias))

    return {term for term in terms if term}


def _infer_tags(query: str) -> list[str]:
    normalized = _normalize_text(query)
    terms = _expand_query_terms(query)
    inferred: list[str] = []

    for tag, keywords in TAG_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords if " " in keyword):
            inferred.append(tag)
            continue
        if any(keyword in terms for keyword in keywords if " " not in keyword):
            inferred.append(tag)

    return inferred


def _canonical_public_search_term(term: str) -> str:
    if term.endswith("k") and term[:-1].isdigit():
        return str(int(term[:-1]) * 1000)
    if term.endswith("m") and term[:-1].isdigit():
        return str(int(term[:-1]) * 1_000_000)
    aliases = QUERY_ALIASES.get(term, ())
    if aliases:
        candidates = (term, *aliases)
        return max((_normalize_text(candidate) for candidate in candidates), key=len)
    return term


def _build_public_search_queries(query: str) -> list[str]:
    normalized = _normalize_text(query)
    if not normalized:
        return []

    queries: list[str] = [query]
    tokens = [token for token in normalized.split() if token not in STOPWORDS]
    canonical_tokens = [_canonical_public_search_term(token) for token in tokens]

    if canonical_tokens:
        queries.append(" ".join(canonical_tokens))

    text_terms = [token for token in canonical_tokens if not any(ch.isdigit() for ch in token)]
    numeric_terms = [token for token in canonical_tokens if any(ch.isdigit() for ch in token)]

    if text_terms and numeric_terms:
        queries.append(f"{text_terms[0]} {numeric_terms[0]}")
        if len(numeric_terms) > 1:
            queries.append(f"{text_terms[0]} {numeric_terms[-1]}")
    if text_terms:
        queries.append(text_terms[0])

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in queries:
        normalized_candidate = _normalize_text(candidate)
        if not normalized_candidate or normalized_candidate in seen:
            continue
        seen.add(normalized_candidate)
        deduped.append(candidate)
    return deduped


def _extract_tag_text(tags: list[Any] | None) -> list[str]:
    if not tags:
        return []
    values: list[str] = []
    for tag in tags:
        if isinstance(tag, dict):
            values.extend([tag.get("label") or "", tag.get("slug") or ""])
        else:
            values.append(str(tag))
    return [value for value in values if value]


# ---------------------------------------------------------------------------
# Relevance scoring (replaces _score_query_text)
# ---------------------------------------------------------------------------

def score_relevance(query: str, text: str, slug: str | None = None) -> float:
    """Score relevance of text to query on 0-100 scale.

    Components:
    - Term coverage (60%): fraction of query terms found in text
    - Exact substring (25%): full query appears as substring
    - Slug match (15%): query terms appear in slug
    """
    normalized_query = _normalize_text(query)
    normalized_text = _normalize_text(text)
    if not normalized_query or not normalized_text:
        return 0.0

    terms = _expand_query_terms(query)
    if not terms:
        return 0.0

    text_tokens = set(normalized_text.split())

    # Term coverage (0-60)
    matched = 0
    for term in terms:
        if " " in term:
            if term in normalized_text:
                matched += 1
        elif term in text_tokens:
            matched += 1

    if matched == 0:
        return 0.0

    term_coverage = (matched / len(terms)) * 60.0

    # Exact substring match (0-25)
    exact_bonus = 25.0 if normalized_query in normalized_text else 0.0

    # Slug match (0-15)
    slug_bonus = 0.0
    if slug:
        normalized_slug = _normalize_text(slug)
        slug_tokens = set(normalized_slug.split())
        slug_matched = sum(1 for t in terms if t in slug_tokens or t in normalized_slug)
        if slug_matched > 0:
            slug_bonus = min(15.0, (slug_matched / len(terms)) * 15.0)

    return min(100.0, term_coverage + exact_bonus + slug_bonus)


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------

def _liquidity_score(liquidity_usd: float) -> float:
    """Score liquidity on 0-30 scale. Log-scaled.
    $0→0, $10K→15, $50K≈20, $1M+→30
    """
    if liquidity_usd <= 0:
        return 0.0
    return min(30.0, 30.0 * math.log10(1 + liquidity_usd / 100) / math.log10(10001))


def _volume_score(volume_24h: float) -> float:
    """Score 24h volume on 0-25 scale. Log-scaled."""
    if volume_24h <= 0:
        return 0.0
    return min(25.0, 25.0 * math.log10(1 + volume_24h / 100) / math.log10(10001))


def _spread_score(spread: float | None) -> float:
    """Score spread on 0-25 scale. Lower spread = higher score."""
    if spread is None:
        return 12.0  # Unknown spread gets middle score
    spread = abs(spread)
    if spread <= 0.01:
        return 25.0
    if spread <= 0.03:
        return 20.0
    if spread <= 0.05:
        return 15.0
    if spread <= 0.10:
        return 8.0
    return 0.0


def _status_score(active: bool, closed: bool, accepting_orders: bool, ready: bool) -> float:
    """Score market status on 0-20 scale."""
    score = 0.0
    if active and not closed:
        score += 10.0
    if accepting_orders:
        score += 5.0
    if ready:
        score += 5.0
    return score


def compute_market_quality(
    liquidity_usd: float,
    volume_24h: float,
    spread: float | None,
    active: bool = True,
    closed: bool = False,
    accepting_orders: bool = True,
    ready: bool = True,
) -> "MarketQuality":
    """Compute quality score for a market."""
    liq = _liquidity_score(liquidity_usd)
    vol = _volume_score(volume_24h)
    spr = _spread_score(spread)
    sta = _status_score(active, closed, accepting_orders, ready)

    quality_raw = liq + vol + spr + sta

    warnings: list[str] = []

    if liquidity_usd < MIN_LIQUIDITY_USD:
        warnings.append(f"Low liquidity: ${liquidity_usd:,.0f} (min ${MIN_LIQUIDITY_USD:,})")
    if volume_24h <= 0:
        warnings.append("No 24h volume")
    if spread is not None and spread > MAX_SPREAD_LIMIT:
        warnings.append(f"Wide spread: {spread:.2%} (max {MAX_SPREAD_LIMIT:.0%})")
    if not active or closed:
        warnings.append("Market not active or closed")
    if not accepting_orders:
        warnings.append("Market not accepting orders")
    if not ready:
        warnings.append("Market not ready")

    is_tradable = (
        active
        and not closed
        and accepting_orders
        and liquidity_usd >= MIN_LIQUIDITY_USD
    )

    return MarketQuality(
        tradability_score=round(quality_raw, 1),
        liquidity_usd=round(liquidity_usd, 2),
        volume_24h_usd=round(volume_24h, 2),
        spread_pct=round(spread, 4) if spread is not None else None,
        is_tradable=is_tradable,
        warnings=warnings,
    )


def compute_composite_score(relevance: float, quality_score: float) -> float:
    """Geometric mean of relevance and quality. Both axes must be nonzero."""
    if relevance <= 0 or quality_score <= 0:
        return 0.0
    return math.sqrt(relevance * quality_score)


# ---------------------------------------------------------------------------
# Market search text helpers
# ---------------------------------------------------------------------------

def _market_search_text(market: "Market") -> str:
    parts = [
        market.question,
        market.slug or "",
        market.market_slug or "",
        market.group_slug or "",
        market.description or "",
        market.category or "",
        *_extract_tag_text(market.tags),
    ]
    return " ".join(part for part in parts if part)


def _event_search_text(event: dict) -> str:
    parts = [
        event.get("title") or "",
        event.get("question") or "",
        event.get("slug") or "",
        event.get("description") or "",
        event.get("category") or "",
        *_extract_tag_text(event.get("tags")),
    ]
    for market in event.get("markets") or []:
        parts.extend([
            market.get("question") or "",
            market.get("title") or "",
            market.get("slug") or "",
            market.get("marketSlug") or "",
        ])
    return " ".join(part for part in parts if part)


def _raw_market_search_text(market: dict) -> str:
    parts = [
        market.get("question") or "",
        market.get("title") or "",
        market.get("slug") or "",
        market.get("marketSlug") or "",
        market.get("description") or "",
    ]
    return " ".join(part for part in parts if part)


# ---------------------------------------------------------------------------
# Market ranking (quality-aware)
# ---------------------------------------------------------------------------

def _get_market_liquidity(market: "Market") -> float:
    return float(market.liquidity_num or market.liquidity or 0)


def _get_market_volume(market: "Market") -> float:
    return float(market.volume_24hr or market.volume_num or market.volume or 0)


def _get_market_spread(market: "Market") -> float | None:
    if market.spread is not None:
        try:
            return float(market.spread)
        except (ValueError, TypeError):
            return None
    if market.best_bid is not None and market.best_ask is not None:
        try:
            return float(market.best_ask) - float(market.best_bid)
        except (ValueError, TypeError):
            return None
    return None


def rank_markets(query: str, markets: list["Market"], limit: int) -> list["Market"]:
    """Rank markets by composite score (geometric mean of relevance and quality)."""
    scored: list[tuple[float, "Market", "MarketQuality"]] = []
    for market in markets:
        text = _market_search_text(market)
        slug = market.slug or market.market_slug
        relevance = score_relevance(query, text, slug)
        if relevance <= 0:
            continue

        quality = compute_market_quality(
            liquidity_usd=_get_market_liquidity(market),
            volume_24h=_get_market_volume(market),
            spread=_get_market_spread(market),
            active=market.active,
            closed=market.closed,
            accepting_orders=market.accepting_orders,
            ready=market.ready,
        )
        composite = compute_composite_score(relevance, quality.tradability_score)
        market._quality = quality  # Attach quality info
        scored.append((composite, market, quality))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [market for _, market, _ in scored[:limit]]


# ---------------------------------------------------------------------------
# Event ranking helpers
# ---------------------------------------------------------------------------

def _is_live_public_market(market: dict) -> bool:
    return (
        bool(market.get("active"))
        and not bool(market.get("closed"))
        and not bool(market.get("archived"))
        and bool(market.get("acceptingOrders"))
    )


def _prepare_public_event(query: str, event: dict) -> dict | None:
    scored_markets: list[tuple[int, float, float, float, dict]] = []

    for market in event.get("markets") or []:
        text = _raw_market_search_text(market)
        rel = score_relevance(query, text, market.get("slug") or market.get("marketSlug"))
        volume = float(market.get("volume24hr") or market.get("volume") or 0)
        liquidity = float(market.get("liquidityClob") or market.get("liquidity") or 0)
        scored_markets.append(
            (
                1 if _is_live_public_market(market) else 0,
                rel,
                volume,
                liquidity,
                market,
            )
        )

    if not scored_markets:
        return None

    scored_markets.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
    live_markets = [market for is_live, _, _, _, market in scored_markets if is_live]

    if not live_markets:
        return None

    prepared = dict(event)
    prepared["markets"] = live_markets
    prepared["_live_market_count"] = len(live_markets)
    prepared["_query_score"] = max(rel for _, rel, _, _, _ in scored_markets)
    prepared["_max_market_volume"] = max(volume for _, _, volume, _, _ in scored_markets)
    prepared["_max_market_liquidity"] = max(liquidity for _, _, _, liquidity, _ in scored_markets)
    return prepared


def _rank_public_events(query: str, events: list[dict], limit: int) -> list[dict]:
    ranked: list[tuple[int, float, float, float, dict]] = []

    for event in events:
        prepared = _prepare_public_event(query, event)
        if prepared is None:
            continue

        event_text = _event_search_text(prepared)
        event_rel = score_relevance(query, event_text, prepared.get("slug"))
        query_score = max(event_rel, prepared.get("_query_score", 0.0))
        event_volume = float(prepared.get("volume24hr") or prepared.get("volume") or 0)
        market_volume = float(prepared.get("_max_market_volume") or 0)
        ranked.append(
            (
                int(prepared.get("_live_market_count") or 0),
                query_score,
                max(event_volume, market_volume),
                float(prepared.get("_max_market_liquidity") or 0),
                prepared,
            )
        )

    ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
    return [event for _, _, _, _, event in ranked[:limit]]


def _sort_event_markets(query: str, event: dict) -> dict:
    markets = event.get("markets") or []
    ranked: list[tuple[float, float, float, dict]] = []

    for market in markets:
        text = _raw_market_search_text(market)
        rel = score_relevance(query, text, market.get("slug") or market.get("marketSlug"))
        if rel <= 0:
            continue
        volume = float(market.get("volume24hr") or market.get("volume") or 0)
        liquidity = float(market.get("liquidity") or 0)
        ranked.append((rel, volume, liquidity, market))

    if not ranked:
        return event

    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    sorted_event = dict(event)
    sorted_event["markets"] = [market for _, _, _, market in ranked]
    return sorted_event


def _rank_events(query: str, events: list[dict], limit: int) -> list[dict]:
    ranked: list[tuple[float, float, float, dict]] = []
    for event in events:
        text = _event_search_text(event)
        rel = score_relevance(query, text, event.get("slug"))
        if rel <= 0:
            continue
        volume = float(event.get("volume24hr") or event.get("volume") or 0)
        liquidity = float(event.get("liquidity") or 0)
        ranked.append((rel, volume, liquidity, _sort_event_markets(query, event)))

    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [event for _, _, _, event in ranked[:limit]]


# ---------------------------------------------------------------------------
# Dedup helpers
# ---------------------------------------------------------------------------

def _dedupe_markets(markets: list["Market"]) -> list["Market"]:
    seen: set[str] = set()
    deduped: list[Market] = []
    for market in markets:
        key = market.id or market.slug or market.question
        if key in seen:
            continue
        seen.add(key)
        deduped.append(market)
    return deduped


def _dedupe_events(events: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for event in events:
        key = str(event.get("id") or event.get("slug") or event.get("title") or event.get("question"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def _coerce_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    if hasattr(value, "json"):
        try:
            return json.loads(value.json)
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            raw = value.__dict__
            return raw if isinstance(raw, dict) else dict(raw)
        except Exception:
            pass
    return value


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

SortBy = Literal[
    "volume", "volume24hr", "liquidity", "startDate", "endDate", "createdAt", "updatedAt"
]


class Token(BaseModel):
    token_id: str = Field(alias="token_id")
    outcome: str
    price: float
    winner: bool | None = None

    class Config:
        populate_by_name = True


class MarketQuality(BaseModel):
    """Quality assessment for a market."""
    tradability_score: float = 0.0
    liquidity_usd: float = 0.0
    volume_24h_usd: float = 0.0
    spread_pct: float | None = None
    is_tradable: bool = False
    warnings: list[str] = Field(default_factory=list)


class Market(BaseModel):
    id: str = Field(alias="id")
    condition_id: str | None = Field(default=None, alias="conditionId")
    slug: str | None = None
    question: str
    description: str | None = None
    end_date_iso: str | None = Field(default=None, alias="endDate")
    expiration_date: str | None = Field(default=None, alias="expirationDate")
    resolution_date: str | None = Field(default=None, alias="resolutionDate")
    category: str | None = None
    group_slug: str | None = Field(default=None, alias="groupSlug")
    market_slug: str | None = Field(default=None, alias="marketSlug")
    tags: list[str] | None = None
    rules: str | None = Field(default=None, alias="rules")
    active: bool = True
    closed: bool = False
    archived: bool = False
    resolved: bool = False
    neg_risk: bool = Field(default=False, alias="negRisk")
    tokens: list[Token] | None = None
    outcomes: list[str] | None = None
    outcome_prices: list[float] | None = Field(default=None, alias="outcomePrices")
    clob_token_ids: list[str] | None = Field(default=None, alias="clobTokenIds")
    volume: float | None = None
    volume_24hr: float | None = Field(default=None, alias="volume24hr")
    liquidity: float | None = None
    volume_num: float | None = Field(default=None, alias="volumeNum")
    liquidity_num: float | None = Field(default=None, alias="liquidityNum")

    # Extended fields from Gamma API (previously ignored)
    best_bid: float | None = Field(default=None, alias="bestBid")
    best_ask: float | None = Field(default=None, alias="bestAsk")
    spread: float | None = Field(default=None, alias="spread")
    open_interest: float | None = Field(default=None, alias="openInterest")
    comment_count: int | None = Field(default=None, alias="commentCount")
    accepting_orders: bool = Field(default=True, alias="acceptingOrders")
    ready: bool = Field(default=True, alias="ready")

    # Attached at ranking time, not from API
    _quality: MarketQuality | None = PrivateAttr(default=None)

    class Config:
        populate_by_name = True

    @field_validator("outcomes", mode="before")
    @classmethod
    def parse_outcomes(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

    @field_validator("outcome_prices", mode="before")
    @classmethod
    def parse_outcome_prices(cls, v):
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return [float(p) for p in parsed] if parsed else None
            except (json.JSONDecodeError, ValueError):
                return None
        elif isinstance(v, list):
            try:
                return [float(p) for p in v]
            except (ValueError, TypeError):
                return None
        return v

    @field_validator("clob_token_ids", mode="before")
    @classmethod
    def parse_clob_token_ids(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

    @field_validator("best_bid", "best_ask", "spread", "open_interest", mode="before")
    @classmethod
    def parse_optional_float(cls, v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    @field_validator("comment_count", mode="before")
    @classmethod
    def parse_optional_int(cls, v):
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    @field_validator("accepting_orders", "ready", mode="before")
    @classmethod
    def parse_bool_default_true(cls, v):
        if v is None:
            return True
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v)

    @property
    def yes_price(self) -> float | None:
        if self.tokens:
            for token in self.tokens:
                if token.outcome.lower() == "yes":
                    return token.price
        if self.outcomes and self.outcome_prices:
            for i, outcome in enumerate(self.outcomes):
                if outcome.lower() == "yes" and i < len(self.outcome_prices):
                    return self.outcome_prices[i]
        if self.outcome_prices and len(self.outcome_prices) >= 1:
            return self.outcome_prices[0]
        return None

    @property
    def end_date(self) -> datetime | None:
        date_str = self.end_date_iso or self.expiration_date or self.resolution_date
        if date_str:
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    @property
    def quality(self) -> MarketQuality:
        """Get or compute quality assessment."""
        if self._quality is not None:
            return self._quality
        return compute_market_quality(
            liquidity_usd=_get_market_liquidity(self),
            volume_24h=_get_market_volume(self),
            spread=_get_market_spread(self),
            active=self.active,
            closed=self.closed,
            accepting_orders=self.accepting_orders,
            ready=self.ready,
        )

    def get_token_id(self, outcome: str) -> str | None:
        """Resolve an outcome name (Yes/No/etc.) to its CLOB token_id."""
        outcome_lower = outcome.strip().lower()
        if self.tokens:
            for token in self.tokens:
                if token.outcome.lower() == outcome_lower:
                    return token.token_id
        if self.outcomes and self.clob_token_ids:
            for i, o in enumerate(self.outcomes):
                if o.lower() == outcome_lower and i < len(self.clob_token_ids):
                    return self.clob_token_ids[i]
        return None


# ---------------------------------------------------------------------------
# Pre-trade validation
# ---------------------------------------------------------------------------

class PreTradeCheck(BaseModel):
    name: str
    passed: bool
    message: str
    bypassable: bool = False


class PreTradeResult(BaseModel):
    can_trade: bool
    checks: list[PreTradeCheck]
    warnings: list[str] = Field(default_factory=list)


def validate_pre_trade(
    market: Market,
    outcome: str,
    amount_usd: float,
    price: float | None = None,
    is_market_order: bool = False,
    skip_liquidity_check: bool = False,
    skip_spread_check: bool = False,
    usdc_balance: float | None = None,
    book_depth_usd: float | None = None,
) -> PreTradeResult:
    """Run pre-trade validation cascade. Returns structured result."""
    checks: list[PreTradeCheck] = []
    warnings: list[str] = []

    # 1. Input validation
    if not outcome or not outcome.strip():
        checks.append(PreTradeCheck(name="input", passed=False, message="Outcome must be non-empty"))
    elif amount_usd <= 0:
        checks.append(PreTradeCheck(name="input", passed=False, message="Amount must be > 0"))
    elif price is not None and not is_market_order and not (0.01 <= price <= 0.99):
        checks.append(PreTradeCheck(name="input", passed=False, message=f"Price {price} out of range (0.01-0.99)"))
    else:
        checks.append(PreTradeCheck(name="input", passed=True, message="Input valid"))

    if not checks[-1].passed:
        return PreTradeResult(can_trade=False, checks=checks, warnings=warnings)

    # 2. Market status (non-bypassable)
    if not market.active:
        checks.append(PreTradeCheck(name="market_status", passed=False, message="Market is not active"))
    elif market.closed:
        checks.append(PreTradeCheck(name="market_status", passed=False, message="Market is closed"))
    elif market.archived:
        checks.append(PreTradeCheck(name="market_status", passed=False, message="Market is archived"))
    elif not market.accepting_orders:
        checks.append(PreTradeCheck(name="market_status", passed=False, message="Market not accepting orders"))
    else:
        end = market.end_date
        if end and end < datetime.now(UTC):
            checks.append(PreTradeCheck(name="market_status", passed=False, message="Market has expired"))
        else:
            checks.append(PreTradeCheck(name="market_status", passed=True, message="Market active and accepting orders"))

    if not checks[-1].passed:
        return PreTradeResult(can_trade=False, checks=checks, warnings=warnings)

    # 3. Outcome resolution
    token_id = market.get_token_id(outcome)
    if not token_id:
        available = market.outcomes or ([t.outcome for t in market.tokens] if market.tokens else [])
        checks.append(PreTradeCheck(
            name="outcome", passed=False,
            message=f"Outcome '{outcome}' not found. Available: {available}",
        ))
        return PreTradeResult(can_trade=False, checks=checks, warnings=warnings)
    checks.append(PreTradeCheck(name="outcome", passed=True, message=f"Outcome '{outcome}' resolved to token"))

    # 4. Liquidity check (bypassable)
    liquidity = _get_market_liquidity(market)
    if liquidity < MIN_LIQUIDITY_USD:
        if skip_liquidity_check:
            warnings.append(f"Liquidity check bypassed: ${liquidity:,.0f} < ${MIN_LIQUIDITY_USD:,}")
            checks.append(PreTradeCheck(
                name="liquidity", passed=True, bypassable=True,
                message=f"BYPASSED: Liquidity ${liquidity:,.0f} below ${MIN_LIQUIDITY_USD:,} minimum",
            ))
        else:
            checks.append(PreTradeCheck(
                name="liquidity", passed=False, bypassable=True,
                message=f"Liquidity ${liquidity:,.0f} below ${MIN_LIQUIDITY_USD:,} minimum. Use --skip-liquidity-check to override.",
            ))
            return PreTradeResult(can_trade=False, checks=checks, warnings=warnings)
    else:
        checks.append(PreTradeCheck(name="liquidity", passed=True, message=f"Liquidity OK: ${liquidity:,.0f}"))

    # 5. Spread check (bypassable) — applies to both limit and market orders
    market_spread = _get_market_spread(market)
    if market_spread is not None and market_spread > MAX_SPREAD_LIMIT:
        if skip_spread_check:
            warnings.append(f"Spread check bypassed: {market_spread:.2%} > {MAX_SPREAD_LIMIT:.0%}")
            checks.append(PreTradeCheck(
                name="spread", passed=True, bypassable=True,
                message=f"BYPASSED: Spread {market_spread:.2%} exceeds {MAX_SPREAD_LIMIT:.0%} limit",
            ))
        else:
            order_kind = "market order" if is_market_order else "limit order"
            checks.append(PreTradeCheck(
                name="spread", passed=False, bypassable=True,
                message=f"Spread {market_spread:.2%} exceeds {MAX_SPREAD_LIMIT:.0%} limit for {order_kind}. Use --skip-spread-check to override.",
            ))
            return PreTradeResult(can_trade=False, checks=checks, warnings=warnings)
    else:
        spread_msg = f"Spread OK: {market_spread:.2%}" if market_spread is not None else "Spread: unknown (not checked)"
        checks.append(PreTradeCheck(name="spread", passed=True, message=spread_msg))

    # 6. Book depth check for market orders
    if is_market_order and book_depth_usd is not None:
        required = amount_usd * BOOK_DEPTH_MULTIPLIER
        if book_depth_usd < required:
            checks.append(PreTradeCheck(
                name="book_depth", passed=False,
                message=f"Book depth ${book_depth_usd:,.2f} < required ${required:,.2f} (1.5x order size)",
            ))
            return PreTradeResult(can_trade=False, checks=checks, warnings=warnings)
        checks.append(PreTradeCheck(name="book_depth", passed=True, message=f"Book depth OK: ${book_depth_usd:,.2f}"))
    elif is_market_order:
        warnings.append("Book depth not checked (orderbook data unavailable)")

    # 7. Balance check
    if usdc_balance is not None:
        if usdc_balance < amount_usd:
            checks.append(PreTradeCheck(
                name="balance", passed=False,
                message=f"Insufficient balance: ${usdc_balance:,.2f} < ${amount_usd:,.2f} needed",
            ))
            return PreTradeResult(can_trade=False, checks=checks, warnings=warnings)
        checks.append(PreTradeCheck(name="balance", passed=True, message=f"Balance OK: ${usdc_balance:,.2f}"))
    else:
        warnings.append("Balance not checked (trading not configured or check skipped)")

    return PreTradeResult(can_trade=True, checks=checks, warnings=warnings)


# ---------------------------------------------------------------------------
# API URLs
# ---------------------------------------------------------------------------
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"
DATA_API_URL = "https://data-api.polymarket.com"
BRIDGE_API_URL = "https://bridge.polymarket.com"
GEOBLOCK_API_URL = "https://polymarket.com/api/geoblock"

# ---------------------------------------------------------------------------
# Polygon web3 constants (lazy-loaded for CTF token operations)
# ---------------------------------------------------------------------------
POLYGON_RPC_URL = os.environ.get("POLYGON_RPC_URL", "https://polygon.drpc.org")
CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
NEG_RISK_ADAPTER_ADDRESS = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
USDC_E_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
ZERO_BYTES32 = "0x" + "00" * 32
BINARY_PARTITION = [1, 2]

# Minimal ABIs for CTF operations
CTF_REDEEM_ABI = [
    {
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"},
        ],
        "name": "redeemPositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

CTF_SPLIT_MERGE_ABI = [
    {
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "splitPosition",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "mergePositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

NEG_RISK_ADAPTER_ABI = [
    {
        "inputs": [
            {"name": "conditionId", "type": "bytes32"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "splitPosition",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "conditionId", "type": "bytes32"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "mergePositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

ERC20_APPROVE_ABI = [
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

CTF_APPROVAL_ABI = [
    {
        "inputs": [
            {"name": "operator", "type": "address"},
            {"name": "approved", "type": "bool"},
        ],
        "name": "setApprovalForAll",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "account", "type": "address"},
            {"name": "operator", "type": "address"},
        ],
        "name": "isApprovedForAll",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class PMClient:

    def __init__(
        self,
        timeout: int = 30,
        private_key: str = "",
        funder_address: str = "",
        signature_type: int = 0,
        builder_api_key: str = "",
        builder_secret: str = "",
        builder_passphrase: str = "",
        builder_signer_url: str = "",
        builder_signer_token: str = "",
    ):
        self.timeout = timeout
        self._http: httpx.AsyncClient | None = None
        self._clob = None
        self._builder_client = None
        self._wallet_address: str = funder_address  # funder/proxy address for data lookups
        self._signer_address: str = ""  # derived from private key, used for signing
        self._signature_type: int = signature_type
        self._private_key: str = private_key
        self._clob_init_error: str = ""  # surface init failures to the user
        self.builder_config = self._build_builder_config(
            builder_api_key=builder_api_key,
            builder_secret=builder_secret,
            builder_passphrase=builder_passphrase,
            builder_signer_url=builder_signer_url,
            builder_signer_token=builder_signer_token,
        )
        if self.builder_config is not None:
            try:
                from py_clob_client.client import ClobClient

                self._builder_client = ClobClient(
                    host=CLOB_API_URL,
                    builder_config=self.builder_config,
                )
            except Exception as e:
                logger.error(f"Failed to initialize builder-only client: {e}")
                self._builder_client = None
        if private_key and funder_address:
            self._init_clob(private_key, funder_address)

    def _build_builder_config(
        self,
        *,
        builder_api_key: str,
        builder_secret: str,
        builder_passphrase: str,
        builder_signer_url: str,
        builder_signer_token: str,
    ):
        try:
            from py_builder_signing_sdk.config import BuilderConfig
            from py_builder_signing_sdk.sdk_types import BuilderApiKeyCreds, RemoteBuilderConfig

            if builder_api_key and builder_secret and builder_passphrase:
                return BuilderConfig(
                    local_builder_creds=BuilderApiKeyCreds(
                        key=builder_api_key,
                        secret=builder_secret,
                        passphrase=builder_passphrase,
                    ),
                )

            if builder_signer_url:
                return BuilderConfig(
                    remote_builder_config=RemoteBuilderConfig(
                        url=builder_signer_url,
                        token=builder_signer_token or None,
                    ),
                )
        except Exception as e:
            logger.error(f"Failed to initialize builder config: {e}")
        return None

    def _init_clob(self, private_key: str, funder_address: str) -> None:
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.constants import POLYGON

            self._clob = ClobClient(
                host=CLOB_API_URL,
                key=private_key,
                chain_id=POLYGON,
                funder=funder_address,
                signature_type=self._signature_type,
                builder_config=self.builder_config,
            )
            creds = self._clob.create_or_derive_api_creds()
            self._clob.set_api_creds(creds)

            from eth_account import Account
            self._signer_address = Account.from_key(private_key).address
            logger.info(f"CLOB client initialized for signer={self._signer_address} funder={self._wallet_address}")
            if self._clob.can_builder_auth():
                logger.info("Polymarket builder attribution enabled")
        except Exception as e:
            logger.error(f"Failed to initialize CLOB client: {e}")
            self._clob_init_error = str(e)
            self._clob = None

    @property
    def has_trading(self) -> bool:
        return self._clob is not None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self.timeout)
        return self._http

    async def close(self):
        if self._http:
            await self._http.aclose()
            self._http = None

    async def _request_with_retry(
        self, method: str, url: str, *, params: dict | None = None, json_body: dict | None = None,
        max_retries: int = 3,
    ) -> Any:
        import asyncio as _aio

        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                if method == "GET":
                    resp = await self.http.get(url, params=params)
                else:
                    resp = await self.http.post(url, json=json_body)
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                    wait = min(2 ** attempt, 8)
                    logger.warning(f"HTTP {resp.status_code} from {url}, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
                    await _aio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as e:
                last_exc = e
                if attempt < max_retries:
                    wait = min(2 ** attempt, 8)
                    logger.warning(f"Connection error for {url}: {e}, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
                    await _aio.sleep(wait)
                    continue
                raise
        raise last_exc  # should not reach here, but safety net

    async def _get(self, url: str, params: dict | None = None) -> Any:
        return await self._request_with_retry("GET", url, params=params)

    async def _post(self, url: str, json_body: dict) -> Any:
        return await self._request_with_retry("POST", url, json_body=json_body)

    # -- Gamma API (raw) --

    async def raw_markets(
        self,
        *,
        query: str | None = None,
        limit: int = 100,
        active: bool | None = True,
        closed: bool | None = False,
        archived: bool | None = False,
        tag: str | None = None,
        sort_by: SortBy | None = None,
        ascending: bool | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        if active is not None:
            params["active"] = active
        if closed is not None:
            params["closed"] = closed
        if archived is not None:
            params["archived"] = archived
        if tag:
            params["tag"] = tag
        if sort_by:
            params["order"] = sort_by
        if ascending is not None:
            params["ascending"] = ascending

        data = await self._get(f"{GAMMA_API_URL}/markets", params)
        return data if isinstance(data, list) else data.get("data", [])

    async def raw_events(
        self,
        *,
        query: str | None = None,
        limit: int = 100,
        active: bool | None = True,
        closed: bool | None = False,
        archived: bool | None = False,
        tag: str | None = None,
        order: str | None = "volume24hr",
        ascending: bool | None = False,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        if active is not None:
            params["active"] = active
        if closed is not None:
            params["closed"] = closed
        if archived is not None:
            params["archived"] = archived
        if tag:
            params["tag"] = tag
        if order:
            params["order"] = order
        if ascending is not None:
            params["ascending"] = ascending

        data = await self._get(f"{GAMMA_API_URL}/events", params)
        return data if isinstance(data, list) else data.get("data", [])

    async def raw_public_search(self, query: str, limit: int = 10) -> dict[str, Any]:
        return await self._get(f"{GAMMA_API_URL}/public-search", {"q": query, "limit": limit})

    # -- Gamma API (market discovery) --

    async def get_markets(
        self, limit: int = 100, active: bool = True, tag: str | None = None,
        sort_by: SortBy | None = None, ascending: bool = False,
        min_liquidity: float | None = None, min_volume: float | None = None,
    ) -> list[Market]:
        params: dict[str, Any] = {"limit": limit, "active": active, "closed": False}
        if tag:
            params["tag"] = tag
        if sort_by:
            params["order"] = sort_by
            params["ascending"] = ascending
        data = await self._get(f"{GAMMA_API_URL}/markets", params)
        markets = []
        for item in data if isinstance(data, list) else data.get("data", []):
            try:
                m = Market.model_validate(item)
                if m.yes_price is None:
                    continue
                if min_liquidity and (m.liquidity_num or m.liquidity or 0) < min_liquidity:
                    continue
                if min_volume and (m.volume or m.volume_num or 0) < min_volume:
                    continue
                markets.append(m)
                if len(markets) >= limit:
                    break
            except Exception:
                continue
        return markets

    async def get_market_by_slug(self, market_slug: str) -> Market | None:
        """Resolve an exact market slug via Gamma API, with event fallback."""
        normalized_slug = _normalize_text(market_slug)
        if not normalized_slug:
            return None

        # First try direct market lookup
        try:
            data = await self._get(
                f"{GAMMA_API_URL}/markets",
                {"slug": market_slug, "limit": 20, "active": True, "closed": False},
            )
            items = data if isinstance(data, list) else data.get("data", [])
            for item in items:
                try:
                    market = Market.model_validate(item)
                    if market.closed or market.archived or market.yes_price is None:
                        continue
                    if (
                        _normalize_text(market.slug) == normalized_slug
                        or _normalize_text(market.market_slug) == normalized_slug
                    ):
                        return market
                except Exception:
                    continue
        except Exception:
            pass

        # Then try event lookup and scan nested markets
        try:
            data = await self._get(
                f"{GAMMA_API_URL}/events",
                {"slug": market_slug, "limit": 10, "active": True, "closed": False},
            )
            events = data if isinstance(data, list) else data.get("data", [])
            for event in events:
                for item in event.get("markets") or []:
                    try:
                        market = Market.model_validate(item)
                        if market.closed or market.archived or market.yes_price is None:
                            continue
                        if (
                            _normalize_text(market.slug) == normalized_slug
                            or _normalize_text(market.market_slug) == normalized_slug
                        ):
                            return market
                    except Exception:
                        continue
        except Exception:
            pass

        return None

    async def search_markets(self, query: str, limit: int = 20, sort_by: SortBy | None = "volume") -> list[Market]:
        normalized_query = _normalize_text(query)
        if not normalized_query:
            return []

        fetch_limit = limit * 15
        params: dict[str, Any] = {"query": query, "limit": fetch_limit, "active": True, "closed": False}
        if sort_by:
            params["order"] = sort_by
            params["ascending"] = False

        direct_markets: list[Market] = []
        try:
            data = await self._get(f"{GAMMA_API_URL}/markets", params)
            for item in data if isinstance(data, list) else data.get("data", []):
                try:
                    market = Market.model_validate(item)
                    if market.closed or market.archived or market.yes_price is None:
                        continue
                    direct_markets.append(market)
                except Exception:
                    continue
        except Exception:
            direct_markets = []

        candidates = list(direct_markets)
        inferred_tags = _infer_tags(query)

        if inferred_tags:
            for tag in inferred_tags[:2]:
                candidates.extend(await self.get_markets(
                    limit=fetch_limit,
                    tag=tag,
                    sort_by="volume",
                ))
        else:
            candidates.extend(await self.get_markets(
                limit=fetch_limit,
                sort_by=sort_by or "volume",
            ))

        return rank_markets(query, _dedupe_markets(candidates), limit)

    async def get_events(self, query: str | None = None, slug: str | None = None, limit: int = 20, tag: str | None = None) -> list[dict]:
        """Search events via Gamma API. Returns raw event dicts with nested markets.

        If slug is provided, does an exact slug lookup (no fuzzy search).
        """
        params: dict[str, Any] = {"limit": limit, "active": True, "closed": False}
        if slug:
            params["slug"] = slug
        elif query:
            params["query"] = query
        if tag:
            params["tag"] = tag
        params["order"] = "volume24hr"
        params["ascending"] = False
        data = await self._get(f"{GAMMA_API_URL}/events", params)
        direct_events = data if isinstance(data, list) else data.get("data", [])

        if not query:
            return direct_events

        candidates = list(direct_events)
        inferred_tags = [tag] if tag else _infer_tags(query)
        fetch_limit = limit * 10
        if inferred_tags:
            for inferred_tag in inferred_tags[:2]:
                params = {
                    "limit": fetch_limit,
                    "active": True,
                    "closed": False,
                    "tag": inferred_tag,
                    "order": "volume24hr",
                    "ascending": False,
                }
                try:
                    more = await self._get(f"{GAMMA_API_URL}/events", params)
                    candidates.extend(more if isinstance(more, list) else more.get("data", []))
                except Exception:
                    continue
        else:
            params = {
                "limit": fetch_limit,
                "active": True,
                "closed": False,
                "order": "volume24hr",
                "ascending": False,
            }
            try:
                more = await self._get(f"{GAMMA_API_URL}/events", params)
                candidates.extend(more if isinstance(more, list) else more.get("data", []))
            except Exception:
                pass

        return _rank_events(query, _dedupe_events(candidates), limit)

    async def public_search(self, query: str, limit: int = 10) -> dict[str, Any]:
        collected_events: list[dict] = []
        pagination: dict[str, Any] | None = None

        for search_query in _build_public_search_queries(query):
            data = await self._get(
                f"{GAMMA_API_URL}/public-search",
                {"q": search_query, "limit": limit},
            )
            if pagination is None and isinstance(data, dict):
                pagination = data.get("pagination")
            events = data.get("events", []) if isinstance(data, dict) else []
            collected_events.extend(events)

            ranked_events = _rank_public_events(query, _dedupe_events(collected_events), limit)
            if ranked_events:
                break

        deduped_events = _dedupe_events(collected_events)
        ranked_events = _rank_public_events(query, deduped_events, limit)
        return {
            "events": ranked_events,
            "pagination": pagination,
            "inactive_match_count": max(len(deduped_events) - len(ranked_events), 0),
        }

    async def get_trending(self, limit: int = 20) -> list[Market]:
        markets = await self.get_markets(limit=limit * 3, active=True)
        def vol(m: Market) -> float:
            return m.volume_24hr or m.volume_num or m.volume or 0
        with_vol = [m for m in markets if vol(m) > 0]
        with_vol.sort(key=vol, reverse=True)
        return with_vol[:limit]

    async def get_high_volume(self, limit: int = 20) -> list[Market]:
        return await self.get_markets(limit=limit, sort_by="volume", min_volume=100000)

    async def get_ending_soon(self, limit: int = 20, min_volume: float = 50000) -> list[Market]:
        return await self.get_markets(limit=limit, sort_by="endDate", ascending=True, min_volume=min_volume)

    async def get_high_liquidity(self, limit: int = 20, min_liquidity: float = 50000) -> list[Market]:
        return await self.get_markets(limit=limit, sort_by="liquidity", min_liquidity=min_liquidity)

    async def get_recently_updated(self, limit: int = 20) -> list[Market]:
        return await self.get_markets(limit=limit, sort_by="updatedAt")

    async def get_top_markets(self, limit: int = 20, tag: str | None = None) -> list[Market]:
        """Get top markets by quality score. Unlike trending, this uses the full quality engine."""
        markets = await self.get_markets(limit=limit * 3, active=True, tag=tag, sort_by="volume")
        scored: list[tuple[float, Market]] = []
        for market in markets:
            quality = compute_market_quality(
                liquidity_usd=_get_market_liquidity(market),
                volume_24h=_get_market_volume(market),
                spread=_get_market_spread(market),
                active=market.active,
                closed=market.closed,
                accepting_orders=market.accepting_orders,
                ready=market.ready,
            )
            market._quality = quality
            scored.append((quality.tradability_score, market))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    # -- CLOB API (prices, orderbook) --

    @property
    def _read_clob(self):
        """Cached read-only CLOB client (no auth needed)."""
        if not hasattr(self, "_read_clob_client") or self._read_clob_client is None:
            from py_clob_client.client import ClobClient
            self._read_clob_client = ClobClient(host=CLOB_API_URL)
        return self._read_clob_client

    def get_orderbook(self, token_id: str) -> dict:
        """Get order book for a token from CLOB (no auth needed)."""
        book = _coerce_jsonable(self._read_clob.get_order_book(token_id))
        if isinstance(book, dict):
            return book
        return {"bids": [], "asks": []}

    def get_midpoint(self, token_id: str) -> float | None:
        """Get midpoint price from CLOB."""
        mid = self._read_clob.get_midpoint(token_id)
        try:
            return float(mid) if mid else None
        except (ValueError, TypeError):
            return None

    def get_spread(self, token_id: str) -> dict | None:
        """Get bid-ask spread from CLOB."""
        spread = self._read_clob.get_spread(token_id)
        return spread if isinstance(spread, dict) else None

    def get_tick_size(self, token_id: str) -> float:
        """Get minimum price increment for a token."""
        try:
            tick = self._read_clob.get_tick_size(token_id)
            return float(tick) if tick else 0.01
        except Exception:
            return 0.01

    def get_book_depth_usd(self, token_id: str, side: str = "bids") -> float:
        """Calculate total USD depth available on one side of the orderbook."""
        book = self.get_orderbook(token_id)
        levels = book.get(side) or []
        total_usd = 0.0
        for level in levels:
            try:
                price = float(level.get("price", 0))
                size = float(level.get("size", 0))
                total_usd += price * size
            except (ValueError, TypeError):
                continue
        return total_usd

    async def get_market_trades_events(
        self, condition_id: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"market": condition_id}
        if limit is not None:
            params["limit"] = limit
        data = await self._get(f"{DATA_API_URL}/trades", params=params)
        return data if isinstance(data, list) else []

    async def get_price_history(
        self,
        token_id: str,
        *,
        interval: str | None = None,
        fidelity: int | None = None,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"market": token_id}
        if interval:
            params["interval"] = interval
            if fidelity is None:
                default_fidelity = {
                    "1d": 1,
                    "1w": 5,
                    "1m": 10,
                }.get(interval)
                if default_fidelity is not None:
                    params["fidelity"] = default_fidelity
        if fidelity is not None:
            params["fidelity"] = fidelity
        if start_ts is not None:
            params["startTs"] = start_ts
        if end_ts is not None:
            params["endTs"] = end_ts
        return await self._get(f"{CLOB_API_URL}/prices-history", params)

    # -- Data API (positions, trades) --

    async def get_positions(self) -> list[dict]:
        """Get current positions from Data API."""
        if not self._wallet_address:
            return []
        try:
            data = await self._get(
                f"{DATA_API_URL}/positions",
                params={"user": self._wallet_address.lower(), "sizeThreshold": "0.01"},
            )
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    async def get_trades(self, limit: int = 50) -> list[dict]:
        """Get recent trades from Data API."""
        if not self._wallet_address:
            return []
        try:
            data = await self._get(
                f"{DATA_API_URL}/trades",
                params={"user": self._wallet_address.lower(), "limit": limit},
            )
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return []

    def get_builder_status(self) -> dict[str, Any]:
        builder_type = "none"
        if self.builder_config is not None:
            try:
                builder_type = self.builder_config.get_builder_type().name.lower()
            except Exception:
                builder_type = "configured"

        can_builder_auth = False
        if self._clob is not None:
            can_builder_auth = self._clob.can_builder_auth()
        elif self._builder_client is not None:
            can_builder_auth = self._builder_client.can_builder_auth()

        return {
            "configured": self.builder_config is not None,
            "builder_type": builder_type,
            "can_builder_auth": can_builder_auth,
            "trading_wallet_configured": self.has_trading,
        }

    def get_builder_trades(
        self,
        *,
        market: str | None = None,
        asset_id: str | None = None,
        maker_address: str | None = None,
        before: int | None = None,
        after: int | None = None,
    ) -> list[dict]:
        from py_clob_client.clob_types import TradeParams

        client = self._clob or self._builder_client
        if client is None:
            raise RuntimeError(
                "Builder auth not configured. Set POLY_BUILDER_API_KEY / SECRET / PASSPHRASE."
            )

        params = TradeParams(
            maker_address=maker_address,
            market=market,
            asset_id=asset_id,
            before=before,
            after=after,
        )
        return client.get_builder_trades(params=params)

    async def get_supported_bridge_assets(self) -> list[dict]:
        data = await self._get(f"{BRIDGE_API_URL}/supported-assets")
        return data.get("supportedAssets", [])

    async def get_bridge_quote(
        self,
        *,
        from_chain_id: str,
        from_token_address: str,
        recipient_address: str,
        to_chain_id: str,
        to_token_address: str,
        from_amount_base_unit: str,
    ) -> dict[str, Any]:
        body = {
            "fromAmountBaseUnit": from_amount_base_unit,
            "fromChainId": from_chain_id,
            "fromTokenAddress": from_token_address,
            "recipientAddress": recipient_address,
            "toChainId": to_chain_id,
            "toTokenAddress": to_token_address,
        }
        return await self._post(f"{BRIDGE_API_URL}/quote", body)

    async def get_bridge_deposit_address(self, address: str) -> dict[str, str]:
        data = await self._post(f"{BRIDGE_API_URL}/deposit", {"address": address})
        return data.get("address", {})

    async def get_bridge_status(self, deposit_address: str) -> list[dict]:
        data = await self._get(f"{BRIDGE_API_URL}/status/{deposit_address}")
        return data.get("transactions", [])

    async def initiate_bridge_withdrawal(self, address: str) -> dict[str, Any]:
        """Initiate a withdrawal from Polygon via the bridge. Returns deposit address info."""
        return await self._post(f"{BRIDGE_API_URL}/withdraw", {"address": address})

    async def get_geoblock(self, ip: str | None = None) -> dict[str, Any]:
        params = {"ip": ip} if ip else None
        return await self._get(GEOBLOCK_API_URL, params)

    # -- CLOB Trading --

    def _require_trading(self) -> None:
        if not self.has_trading:
            raise RuntimeError(
                "Polymarket trading not configured. "
                "Set EVM_PRIVATE_KEY and EVM_WALLET_ADDRESS."
            )

    def _needs_allowance_refresh(self, error: Any) -> bool:
        if isinstance(error, dict):
            haystack = json.dumps(error, default=str)
        else:
            haystack = str(error)
        normalized = haystack.lower()
        return "allowance" in normalized or "insufficient" in normalized

    def _refresh_order_allowance(self, side: str, token_id: str | None = None) -> None:
        from py_clob_client.clob_types import AssetType, BalanceAllowanceParams
        from py_clob_client.order_builder.constants import BUY

        asset_type = AssetType.COLLATERAL if side == BUY else AssetType.CONDITIONAL
        params = BalanceAllowanceParams(
            asset_type=asset_type,
            token_id=token_id if asset_type == AssetType.CONDITIONAL else None,
        )
        self._clob.update_balance_allowance(params)

    def _post_order_with_allowance_retry(
        self,
        signed_order: Any,
        order_type: Any,
        *,
        side: str,
        token_id: str | None = None,
    ) -> Any:
        try:
            resp = self._clob.post_order(signed_order, order_type)
            if isinstance(resp, dict) and not resp.get("success", True):
                if self._needs_allowance_refresh(resp):
                    self._refresh_order_allowance(side, token_id)
                    resp = self._clob.post_order(signed_order, order_type)
            return resp
        except Exception as e:
            if self._needs_allowance_refresh(e):
                self._refresh_order_allowance(side, token_id)
                return self._clob.post_order(signed_order, order_type)
            raise

    def _round_to_tick(self, price: float, tick_size: float) -> float:
        """Round price to nearest valid tick."""
        if tick_size <= 0:
            tick_size = 0.01
        return round(round(price / tick_size) * tick_size, 4)

    def buy(
        self,
        token_id: str,
        price: float,
        size: float,
        neg_risk: bool = False,
        order_type: str = "GTC",
        expire_seconds: int | None = None,
    ) -> str:
        """Place a limit buy order (GTC). Returns order_id."""
        from py_clob_client.order_builder.constants import BUY
        return self._place_order(
            token_id,
            price,
            size,
            BUY,
            neg_risk,
            order_type=order_type,
            expire_seconds=expire_seconds,
        )

    def sell(
        self,
        token_id: str,
        price: float,
        size: float,
        neg_risk: bool = False,
        order_type: str = "GTC",
        expire_seconds: int | None = None,
    ) -> str:
        """Place a limit sell order (GTC). Returns order_id."""
        from py_clob_client.order_builder.constants import SELL
        return self._place_order(
            token_id,
            price,
            size,
            SELL,
            neg_risk,
            order_type=order_type,
            expire_seconds=expire_seconds,
        )

    def market_buy(
        self,
        token_id: str,
        amount_usd: float,
        neg_risk: bool = False,
        order_type: str = "FOK",
    ) -> str:
        """Place a market buy order (FOK). Spends amount_usd. Returns order_id."""
        from py_clob_client.clob_types import MarketOrderArgs, OrderType, PartialCreateOrderOptions
        from py_clob_client.order_builder.constants import BUY
        self._require_trading()
        order_enum = getattr(OrderType, order_type)
        args = MarketOrderArgs(
            token_id=token_id,
            amount=amount_usd,
            side=BUY,
            order_type=order_enum,
        )
        options = PartialCreateOrderOptions(neg_risk=neg_risk) if neg_risk else None
        signed = self._clob.create_market_order(args, options=options)
        resp = self._post_order_with_allowance_retry(
            signed,
            order_enum,
            side=BUY,
            token_id=token_id,
        )
        return self._extract_order_id(resp)

    def market_sell(
        self,
        token_id: str,
        shares: float,
        neg_risk: bool = False,
        order_type: str = "FOK",
    ) -> str:
        """Place a market sell order. Sells shares immediately. Returns order_id."""
        from py_clob_client.clob_types import MarketOrderArgs, OrderType, PartialCreateOrderOptions
        from py_clob_client.order_builder.constants import SELL

        self._require_trading()
        order_enum = getattr(OrderType, order_type)
        args = MarketOrderArgs(
            token_id=token_id,
            amount=shares,
            side=SELL,
            order_type=order_enum,
        )
        options = PartialCreateOrderOptions(neg_risk=neg_risk) if neg_risk else None
        signed = self._clob.create_market_order(args, options=options)
        resp = self._post_order_with_allowance_retry(
            signed,
            order_enum,
            side=SELL,
            token_id=token_id,
        )
        return self._extract_order_id(resp)

    def _place_order(
        self,
        token_id: str,
        price: float,
        size: float,
        side: str,
        neg_risk: bool,
        *,
        order_type: str = "GTC",
        expire_seconds: int | None = None,
    ) -> str:
        from py_clob_client.clob_types import OrderArgs, OrderType, PartialCreateOrderOptions

        self._require_trading()

        tick = self.get_tick_size(token_id)
        price = self._round_to_tick(price, tick)
        size = math.floor(size * 100) / 100

        if size <= 0:
            raise ValueError("Size must be > 0 after rounding")
        if not (0.01 <= price <= 0.99):
            raise ValueError(f"Price {price} out of range (0.01-0.99)")
        if order_type == "GTD" and not expire_seconds:
            raise ValueError("GTD orders require expire_seconds")
        if expire_seconds is not None and expire_seconds <= 0:
            raise ValueError("expire_seconds must be > 0")

        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=side,
            expiration=int(datetime.now(UTC).timestamp()) + expire_seconds if expire_seconds else 0,
        )

        options = PartialCreateOrderOptions(neg_risk=neg_risk) if neg_risk else None
        signed_order = self._clob.create_order(order_args, options=options)
        order_enum = getattr(OrderType, order_type)
        resp = self._post_order_with_allowance_retry(
            signed_order,
            order_enum,
            side=side,
            token_id=token_id,
        )
        return self._extract_order_id(resp)

    def _extract_order_id(self, resp: Any) -> str:
        if isinstance(resp, dict):
            order_id = resp.get("orderID") or resp.get("id", "")
            if not resp.get("success", True):
                error_msg = (
                    resp.get("errorMsg")
                    or resp.get("error")
                    or resp.get("message")
                    or resp.get("error_message")
                    or ""
                )
                if not error_msg:
                    error_msg = json.dumps(resp)
                raise RuntimeError(f"Order rejected by exchange: {error_msg}")
            return order_id
        return str(resp)

    def cancel(self, order_id: str) -> bool:
        self._require_trading()
        try:
            resp = self._clob.cancel(order_id)
            if isinstance(resp, dict):
                return resp.get("canceled", False) or resp.get("success", False)
            return True
        except Exception as e:
            logger.error(f"Cancel failed for {order_id}: {e}")
            return False

    def cancel_all(self) -> int:
        self._require_trading()
        try:
            resp = self._clob.cancel_all()
            if isinstance(resp, dict):
                return resp.get("canceled", 0)
            return 0
        except Exception as e:
            logger.error(f"Cancel all failed: {e}")
            return 0

    def is_filled(self, order_id: str) -> dict[str, Any]:
        self._require_trading()
        try:
            order = self._clob.get_order(order_id)
            if isinstance(order, dict):
                status = order.get("status", "unknown")
                size_matched = float(order.get("size_matched", 0) or order.get("sizeMatched", 0))
                original_size = float(order.get("original_size", 0) or order.get("originalSize", 0))
                price = float(order.get("price", 0))
                return {
                    "order_id": order_id, "status": status,
                    "filled": status == "MATCHED",
                    "partially_filled": size_matched > 0 and status != "MATCHED",
                    "shares_matched": size_matched, "shares_total": original_size,
                    "price": price, "side": order.get("side", ""),
                }
            return {"order_id": order_id, "status": "unknown", "filled": False}
        except Exception as e:
            logger.error(f"Failed to check order {order_id}: {e}")
            return {"order_id": order_id, "status": "error", "filled": False, "error": str(e)}

    def get_open_orders(self) -> list[dict[str, Any]]:
        self._require_trading()
        try:
            orders = self._clob.get_orders()
            if not isinstance(orders, list):
                return []
            result = []
            for o in orders:
                if not isinstance(o, dict):
                    continue
                status = o.get("status", "")
                if status in ("LIVE", "ACTIVE", ""):
                    result.append({
                        "order_id": o.get("id") or o.get("orderID", ""),
                        "token_id": o.get("asset_id") or o.get("tokenID", ""),
                        "side": o.get("side", ""),
                        "price": float(o.get("price", 0)),
                        "size": float(o.get("original_size", 0) or o.get("originalSize", 0)),
                        "size_matched": float(o.get("size_matched", 0) or o.get("sizeMatched", 0)),
                        "status": status,
                    })
            return result
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    def get_open_orders_raw(self) -> list[dict[str, Any]]:
        self._require_trading()
        orders = self._clob.get_orders()
        return orders if isinstance(orders, list) else []

    def get_usdc_balance(self) -> float:
        """Get USDC.e balance from CLOB (trading-ready balance)."""
        self._require_trading()
        try:
            from py_clob_client.clob_types import AssetType, BalanceAllowanceParams
            resp = self._clob.get_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )
            raw = resp.get("balance", "0") if isinstance(resp, dict) else "0"
            return float(raw) / 1_000_000 if raw else 0.0
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return 0.0

    def get_wallet_usdc_balance(self) -> float:
        """Get on-chain USDC.e balance from the Polygon wallet (uses funder address for proxy wallets)."""
        try:
            w3 = self._get_w3()
            address = self._wallet_address  # funder/proxy address — where USDC.e actually lives
            usdc = w3.eth.contract(
                address=w3.to_checksum_address(USDC_E_ADDRESS),
                abi=ERC20_APPROVE_ABI,
            )
            raw = usdc.functions.balanceOf(w3.to_checksum_address(address)).call()
            return float(raw) / 1_000_000
        except Exception as e:
            logger.error(f"Failed to get wallet USDC.e balance: {e}")
            return 0.0

    def get_pol_balance(self) -> float:
        """Get native POL (gas token) balance on Polygon."""
        try:
            w3 = self._get_w3()
            address = self._signer_address or self._wallet_address
            raw = w3.eth.get_balance(w3.to_checksum_address(address))
            return float(w3.from_wei(raw, "ether"))
        except Exception as e:
            logger.error(f"Failed to get POL balance: {e}")
            return 0.0

    def approve_trading(self) -> dict[str, Any]:
        """Approve all Polymarket exchange contracts for trading.

        Follows the official Polymarket approval flow:
        - 3 targets: CTF Exchange, Neg Risk Exchange, Neg Risk Adapter
        - For each: ERC20 approve (USDC.e) + ERC1155 setApprovalForAll (CTF)
        - Then tell CLOB to re-read on-chain allowances
        """
        self._require_trading()
        self._require_web3()
        from eth_account import Account

        w3 = self._get_w3()
        account = Account.from_key(self._private_key)
        nonce = w3.eth.get_transaction_count(account.address)

        max_uint256 = 2**256 - 1
        usdc = w3.eth.contract(
            address=w3.to_checksum_address(USDC_E_ADDRESS),
            abi=ERC20_APPROVE_ABI,
        )
        ctf = w3.eth.contract(
            address=w3.to_checksum_address(CTF_ADDRESS),
            abi=CTF_APPROVAL_ABI,
        )

        # 3 targets per official Polymarket gist
        targets = [
            ("ctf_exchange", self._clob.get_exchange_address(neg_risk=False)),
            ("neg_risk_exchange", self._clob.get_exchange_address(neg_risk=True)),
            ("neg_risk_adapter", NEG_RISK_ADAPTER_ADDRESS),
        ]

        results = []
        for label, target in targets:
            if not target:
                continue
            target_cs = w3.to_checksum_address(target)

            # ERC20 approve USDC.e
            try:
                current_allowance = usdc.functions.allowance(account.address, target_cs).call()
                if current_allowance < max_uint256:
                    tx = usdc.functions.approve(target_cs, max_uint256).build_transaction({
                        "chainId": 137, "from": account.address, "nonce": nonce,
                    })
                    signed = account.sign_transaction(tx)
                    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                    w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                    nonce += 1
                    results.append({"target": label, "type": "erc20_approve", "tx": tx_hash.hex()})
                else:
                    results.append({"target": label, "type": "erc20_approve", "status": "already_approved"})
            except Exception as e:
                results.append({"target": label, "type": "erc20_approve", "error": str(e)})

            # ERC1155 setApprovalForAll for CTF
            try:
                is_approved = ctf.functions.isApprovedForAll(account.address, target_cs).call()
                if not is_approved:
                    tx = ctf.functions.setApprovalForAll(target_cs, True).build_transaction({
                        "chainId": 137, "from": account.address, "nonce": nonce,
                    })
                    signed = account.sign_transaction(tx)
                    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                    w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                    nonce += 1
                    results.append({"target": label, "type": "ctf_approval", "tx": tx_hash.hex()})
                else:
                    results.append({"target": label, "type": "ctf_approval", "status": "already_approved"})
            except Exception as e:
                results.append({"target": label, "type": "ctf_approval", "error": str(e)})

        # Tell CLOB to re-read on-chain allowances (always runs even if approvals fail)
        try:
            from py_clob_client.clob_types import AssetType, BalanceAllowanceParams
            self._clob.update_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )
        except Exception as e:
            results.append({"target": "clob", "type": "update_balance_allowance", "error": str(e)})

        return {"approved": True, "approvals": results}

    # -- Web3 CTF Operations --

    def _get_w3(self):
        """Lazy Web3 instance for Polygon with POA middleware."""
        if not hasattr(self, "_w3") or self._w3 is None:
            from web3 import Web3
            from web3.middleware import ExtraDataToPOAMiddleware

            self._w3 = Web3(Web3.HTTPProvider(POLYGON_RPC_URL))
            self._w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return self._w3

    def _require_web3(self) -> None:
        """Assert private key is available for web3 transactions."""
        if not self._private_key:
            raise RuntimeError(
                "Web3 operations require EVM_PRIVATE_KEY to be set."
            )

    def _sign_and_send_tx(self, tx: dict) -> dict[str, Any]:
        """Sign, send, and wait for a transaction receipt. Returns tx_hash, status, explorer_url."""
        from eth_account import Account

        self._require_web3()
        w3 = self._get_w3()
        account = Account.from_key(self._private_key)

        tx["from"] = account.address
        if "nonce" not in tx:
            tx["nonce"] = w3.eth.get_transaction_count(account.address)
        if "gas" not in tx:
            tx["gas"] = w3.eth.estimate_gas(tx)
        if "gasPrice" not in tx:
            tx["gasPrice"] = w3.eth.gas_price

        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        return {
            "tx_hash": receipt.transactionHash.hex(),
            "status": "success" if receipt.status == 1 else "failed",
            "gas_used": receipt.gasUsed,
            "explorer_url": f"https://polygonscan.com/tx/0x{receipt.transactionHash.hex()}",
        }

    def redeem_positions(
        self,
        condition_id: str,
        index_sets: list[int] | None = None,
    ) -> dict[str, Any]:
        """Redeem resolved CTF positions back to USDC.e."""
        self._require_web3()
        w3 = self._get_w3()

        ctf = w3.eth.contract(
            address=w3.to_checksum_address(CTF_ADDRESS),
            abi=CTF_REDEEM_ABI,
        )

        if index_sets is None:
            index_sets = BINARY_PARTITION

        tx = ctf.functions.redeemPositions(
            w3.to_checksum_address(USDC_E_ADDRESS),
            bytes.fromhex(ZERO_BYTES32[2:]),
            bytes.fromhex(condition_id if not condition_id.startswith("0x") else condition_id[2:]),
            index_sets,
        ).build_transaction({"chainId": 137})

        return self._sign_and_send_tx(tx)

    def _to_condition_bytes(self, condition_id: str) -> bytes:
        raw = condition_id[2:] if condition_id.startswith("0x") else condition_id
        return bytes.fromhex(raw)

    def _ensure_usdc_approval(self, spender: str, amount: int) -> dict[str, Any] | None:
        """Check USDC.e allowance for spender, approve max uint256 if needed."""
        self._require_web3()
        w3 = self._get_w3()
        from eth_account import Account

        account = Account.from_key(self._private_key)
        usdc = w3.eth.contract(
            address=w3.to_checksum_address(USDC_E_ADDRESS),
            abi=ERC20_APPROVE_ABI,
        )

        current = usdc.functions.allowance(account.address, w3.to_checksum_address(spender)).call()
        if current >= amount:
            return None

        max_uint256 = 2**256 - 1
        tx = usdc.functions.approve(
            w3.to_checksum_address(spender), max_uint256
        ).build_transaction({"chainId": 137, "from": account.address})
        return self._sign_and_send_tx(tx)

    def _ensure_ctf_approval(self, operator: str) -> dict[str, Any] | None:
        """Check CTF isApprovedForAll, set approval if needed."""
        self._require_web3()
        w3 = self._get_w3()
        from eth_account import Account

        account = Account.from_key(self._private_key)
        ctf = w3.eth.contract(
            address=w3.to_checksum_address(CTF_ADDRESS),
            abi=CTF_APPROVAL_ABI,
        )

        approved = ctf.functions.isApprovedForAll(
            account.address, w3.to_checksum_address(operator)
        ).call()
        if approved:
            return None

        tx = ctf.functions.setApprovalForAll(
            w3.to_checksum_address(operator), True
        ).build_transaction({"chainId": 137, "from": account.address})
        return self._sign_and_send_tx(tx)

    def split_position(
        self,
        condition_id: str,
        amount_usdc: float,
        neg_risk: bool = False,
    ) -> dict[str, Any]:
        """Split USDC.e into YES + NO outcome tokens."""
        self._require_web3()
        w3 = self._get_w3()
        amount_base = int(amount_usdc * 1_000_000)

        if neg_risk:
            spender = NEG_RISK_ADAPTER_ADDRESS
            self._ensure_usdc_approval(spender, amount_base)
            contract = w3.eth.contract(
                address=w3.to_checksum_address(NEG_RISK_ADAPTER_ADDRESS),
                abi=NEG_RISK_ADAPTER_ABI,
            )
            tx = contract.functions.splitPosition(
                self._to_condition_bytes(condition_id),
                amount_base,
            ).build_transaction({"chainId": 137})
        else:
            spender = CTF_ADDRESS
            self._ensure_usdc_approval(spender, amount_base)
            ctf = w3.eth.contract(
                address=w3.to_checksum_address(CTF_ADDRESS),
                abi=CTF_SPLIT_MERGE_ABI,
            )
            tx = ctf.functions.splitPosition(
                w3.to_checksum_address(USDC_E_ADDRESS),
                bytes.fromhex(ZERO_BYTES32[2:]),
                self._to_condition_bytes(condition_id),
                BINARY_PARTITION,
                amount_base,
            ).build_transaction({"chainId": 137})

        result = self._sign_and_send_tx(tx)
        result["amount_usdc"] = amount_usdc
        result["neg_risk"] = neg_risk
        return result

    def merge_positions(
        self,
        condition_id: str,
        amount_usdc: float,
        neg_risk: bool = False,
    ) -> dict[str, Any]:
        """Merge YES + NO outcome tokens back into USDC.e."""
        self._require_web3()
        w3 = self._get_w3()
        amount_base = int(amount_usdc * 1_000_000)

        if neg_risk:
            self._ensure_ctf_approval(NEG_RISK_ADAPTER_ADDRESS)
            contract = w3.eth.contract(
                address=w3.to_checksum_address(NEG_RISK_ADAPTER_ADDRESS),
                abi=NEG_RISK_ADAPTER_ABI,
            )
            tx = contract.functions.mergePositions(
                self._to_condition_bytes(condition_id),
                amount_base,
            ).build_transaction({"chainId": 137})
        else:
            ctf = w3.eth.contract(
                address=w3.to_checksum_address(CTF_ADDRESS),
                abi=CTF_SPLIT_MERGE_ABI,
            )
            tx = ctf.functions.mergePositions(
                w3.to_checksum_address(USDC_E_ADDRESS),
                bytes.fromhex(ZERO_BYTES32[2:]),
                self._to_condition_bytes(condition_id),
                BINARY_PARTITION,
                amount_base,
            ).build_transaction({"chainId": 137})

        result = self._sign_and_send_tx(tx)
        result["amount_usdc"] = amount_usdc
        result["neg_risk"] = neg_risk
        return result
