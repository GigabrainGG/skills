"""Polymarket service layer - market data and trading.

Self-contained module using:
- Gamma API (httpx) for market discovery
- CLOB API (py-clob-client) for trading
- Data API (httpx) for positions/trades

No daemon-specific dependencies.
"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("pm_services")

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


def _score_query_text(query: str, text: str) -> float:
    normalized_query = _normalize_text(query)
    normalized_text = _normalize_text(text)
    if not normalized_query or not normalized_text:
        return 0.0

    terms = _expand_query_terms(query)
    text_tokens = set(normalized_text.split())
    score = 0.0
    matched_terms = 0

    if normalized_query in normalized_text:
        score += 12.0

    for term in terms:
        if " " in term:
            if term in normalized_text:
                matched_terms += 1
                score += 5.0
            continue

        if term in text_tokens:
            matched_terms += 1
            score += 3.0 if any(ch.isdigit() for ch in term) else 2.0

    if matched_terms == 0:
        return 0.0

    if matched_terms >= 2:
        score += 3.0

    return score


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
        score = _score_query_text(query, _raw_market_search_text(market))
        volume = float(market.get("volume24hr") or market.get("volume") or 0)
        liquidity = float(market.get("liquidityClob") or market.get("liquidity") or 0)
        scored_markets.append(
            (
                1 if _is_live_public_market(market) else 0,
                score,
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
    prepared["_query_score"] = max(score for _, score, _, _, _ in scored_markets)
    prepared["_max_market_volume"] = max(volume for _, _, volume, _, _ in scored_markets)
    prepared["_max_market_liquidity"] = max(liquidity for _, _, _, liquidity, _ in scored_markets)
    return prepared


def _rank_public_events(query: str, events: list[dict], limit: int) -> list[dict]:
    ranked: list[tuple[int, float, float, float, dict]] = []

    for event in events:
        prepared = _prepare_public_event(query, event)
        if prepared is None:
            continue

        event_score = _score_query_text(query, _event_search_text(prepared))
        query_score = max(event_score, prepared.get("_query_score", 0.0))
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
        score = _score_query_text(query, _raw_market_search_text(market))
        if score <= 0:
            continue
        volume = float(market.get("volume24hr") or market.get("volume") or 0)
        liquidity = float(market.get("liquidity") or 0)
        ranked.append((score, volume, liquidity, market))

    if not ranked:
        return event

    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    sorted_event = dict(event)
    sorted_event["markets"] = [market for _, _, _, market in ranked]
    return sorted_event


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


def _rank_markets(query: str, markets: list["Market"], limit: int) -> list["Market"]:
    ranked: list[tuple[float, float, float, Market]] = []
    for market in markets:
        score = _score_query_text(query, _market_search_text(market))
        if score <= 0:
            continue
        volume = market.volume_24hr or market.volume_num or market.volume or 0
        liquidity = market.liquidity_num or market.liquidity or 0
        ranked.append((score, volume, liquidity, market))

    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [market for _, _, _, market in ranked[:limit]]


def _rank_events(query: str, events: list[dict], limit: int) -> list[dict]:
    ranked: list[tuple[float, float, float, dict]] = []
    for event in events:
        score = _score_query_text(query, _event_search_text(event))
        if score <= 0:
            continue
        volume = float(event.get("volume24hr") or event.get("volume") or 0)
        liquidity = float(event.get("liquidity") or 0)
        ranked.append((score, volume, liquidity, _sort_event_markets(query, event)))

    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [event for _, _, _, event in ranked[:limit]]


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
# API URLs
# ---------------------------------------------------------------------------
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"
DATA_API_URL = "https://data-api.polymarket.com"
BRIDGE_API_URL = "https://bridge.polymarket.com"
GEOBLOCK_API_URL = "https://polymarket.com/api/geoblock"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class PMClient:

    def __init__(
        self,
        timeout: int = 30,
        private_key: str = "",
        funder_address: str = "",
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
        self._wallet_address: str = funder_address
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
                signature_type=0,  # EOA wallet
                builder_config=self.builder_config,
            )
            creds = self._clob.create_or_derive_api_creds()
            self._clob.set_api_creds(creds)

            from eth_account import Account
            self._wallet_address = Account.from_key(private_key).address
            logger.info(f"CLOB client initialized for {self._wallet_address}")
            if self._clob.can_builder_auth():
                logger.info("Polymarket builder attribution enabled")
        except Exception as e:
            logger.error(f"Failed to initialize CLOB client: {e}")
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

    async def _get(self, url: str, params: dict | None = None) -> Any:
        resp = await self.http.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, url: str, json_body: dict) -> Any:
        resp = await self.http.post(url, json=json_body)
        resp.raise_for_status()
        return resp.json()

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
        params: dict[str, Any] = {"limit": limit * 3, "active": active, "closed": False}
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

    async def search_markets(self, query: str, limit: int = 20, sort_by: SortBy | None = "volume") -> list[Market]:
        normalized_query = _normalize_text(query)
        if not normalized_query:
            return []

        params: dict[str, Any] = {"query": query, "limit": limit * 5, "active": True, "closed": False}
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
                    limit=max(limit * 25, 150),
                    tag=tag,
                    sort_by="volume",
                ))
                candidates.extend(await self.get_markets(
                    limit=max(limit * 10, 75),
                    tag=tag,
                    sort_by="updatedAt",
                ))
        else:
            candidates.extend(await self.get_markets(
                limit=max(limit * 40, 250),
                sort_by=sort_by or "volume",
            ))
            candidates.extend(await self.get_markets(
                limit=max(limit * 15, 100),
                sort_by="updatedAt",
            ))

        ranked = _rank_markets(query, _dedupe_markets(candidates), limit)
        return ranked

    async def get_events(self, query: str | None = None, limit: int = 20, tag: str | None = None) -> list[dict]:
        """Search events via Gamma API. Returns raw event dicts with nested markets."""
        params: dict[str, Any] = {"limit": limit, "active": True, "closed": False}
        if query:
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
        if inferred_tags:
            for inferred_tag in inferred_tags[:2]:
                params = {
                    "limit": max(limit * 20, 100),
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
                "limit": max(limit * 20, 100),
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

    # -- CLOB API (prices, orderbook) --

    def get_orderbook(self, token_id: str) -> dict:
        """Get order book for a token from CLOB (no auth needed)."""
        from py_clob_client.client import ClobClient
        read_client = ClobClient(host=CLOB_API_URL)
        book = _coerce_jsonable(read_client.get_order_book(token_id))
        if isinstance(book, dict):
            return book
        return {"bids": [], "asks": []}

    def get_midpoint(self, token_id: str) -> float | None:
        """Get midpoint price from CLOB."""
        from py_clob_client.client import ClobClient
        read_client = ClobClient(host=CLOB_API_URL)
        mid = read_client.get_midpoint(token_id)
        try:
            return float(mid) if mid else None
        except (ValueError, TypeError):
            return None

    def get_spread(self, token_id: str) -> dict | None:
        """Get bid-ask spread from CLOB."""
        from py_clob_client.client import ClobClient
        read_client = ClobClient(host=CLOB_API_URL)
        spread = read_client.get_spread(token_id)
        return spread if isinstance(spread, dict) else None

    def get_tick_size(self, token_id: str) -> float:
        """Get minimum price increment for a token."""
        from py_clob_client.client import ClobClient
        read_client = ClobClient(host=CLOB_API_URL)
        try:
            tick = read_client.get_tick_size(token_id)
            return float(tick) if tick else 0.01
        except Exception:
            return 0.01

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
        from py_clob_client.clob_types import OrderArgs
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
        from py_clob_client.clob_types import OrderArgs
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
        from py_clob_client.clob_types import MarketOrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY
        self._require_trading()
        order_enum = getattr(OrderType, order_type)
        args = MarketOrderArgs(
            token_id=token_id,
            amount=amount_usd,
            side=BUY,
            order_type=order_enum,
        )
        signed = self._clob.create_market_order(args)
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
        from py_clob_client.clob_types import MarketOrderArgs, OrderType
        from py_clob_client.order_builder.constants import SELL

        self._require_trading()
        order_enum = getattr(OrderType, order_type)
        args = MarketOrderArgs(
            token_id=token_id,
            amount=shares,
            side=SELL,
            order_type=order_enum,
        )
        signed = self._clob.create_market_order(args)
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
        from py_clob_client.clob_types import OrderArgs, OrderType

        self._require_trading()

        # Validate and round price to tick size
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

        signed_order = self._clob.create_order(order_args)
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
            if not resp.get("success", True) and not order_id:
                raise RuntimeError(f"Order failed: {resp}")
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
            raw = self._clob.get_balance()
            return float(raw) / 1_000_000 if raw else 0.0
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return 0.0
