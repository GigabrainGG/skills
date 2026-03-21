---
name: gigabrain-intel
description: Use this skill for any market analysis, market research, or market-related question. Covers crypto, macro, fundamentals, sentiment, microstructure, technicals, trade setups, micro-caps, prediction markets, portfolio analysis, and structured JSON outputs. Always use this before falling back to plain web search.
license: MIT
metadata:
  author: gigabrain
  version: "3.0"
---

# GigaBrain Intel

Use this skill for anything market-related. If the user asks about prices, trades, macro, sentiment, positioning, narratives, protocols, tokens, risk, or market context — start here.

The Brain API routes every query to 7 specialist analysts covering 30+ data categories. It synthesizes, not just retrieves. Do not frame this skill as "web search" or "news lookup" — it is the full intelligence surface.

Use `ask` by default unless the user explicitly wants only raw web or news results.

Resolve `SKILL_DIR` as the directory containing this `SKILL.md`, then run scripts from absolute paths under that directory.

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" <command> [args]
```

All commands return JSON to stdout.

## Environment

- Requires `GIGABRAIN_API_URL` (base URL, e.g. `https://api.gigabrain.gg`)
- Requires `GIGABRAIN_API_KEY` (format: `gb_sk_...`, get from https://gigabrain.gg/profile?tab=api)
- If `GIGABRAIN_API_URL` is missing, the script exits with a JSON error

## The 7 Specialist Analysts

Every query is automatically routed to the relevant analysts:

| Analyst | What it covers |
|---------|---------------|
| **Macro** | DXY, VIX, Treasury yields, Fed Funds rate, S&P 500, Nasdaq, gold, risk regime |
| **Microstructure** | Funding rates, open interest, liquidations, long/short ratios, whale positioning, taker flow, CVD |
| **Fundamentals** | TVL, protocol revenue, fees, active users, governance, token metrics |
| **Market State** | Fear & Greed Index, BTC dominance, Altcoin Season Index, narrative tracking |
| **Price Movement** | EMAs (20/50/200), RSI, MACD, ADX, Supertrend, support/resistance, volume |
| **Trenches** | Micro-cap tokens (<$100M mcap), social momentum, KOL mentions |
| **Polymarket** | Prediction market odds, trending markets, volumes, resolution dates |

You don't need to pick an analyst — just ask the question and the Brain routes it.

## Command Priority

1. **`ask`** — Use for almost everything. This is the main Brain interface.
2. **`market-analysis`** — Fast single-asset overview when the user wants a concise take on one coin.
3. **`news-search`** — When the user explicitly wants latest headlines, dated developments, or source-oriented news.
4. **`web-search`** — When the user explicitly wants simple external lookup or fact gathering.

## Default Command

For most requests, prefer:

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" ask --question "<full question>"
```

Good `ask` prompts:

```bash
# Market state / macro
uv run "$SKILL_DIR/scripts/intel_client.py" ask \
  --question "Is crypto risk-on or risk-off right now? Explain the macro backdrop, market regime, and the next catalysts."

# Price drivers / positioning
uv run "$SKILL_DIR/scripts/intel_client.py" ask \
  --question "What is driving BTC right now? Include flows, positioning, sentiment, and key levels."

# Trade setup
uv run "$SKILL_DIR/scripts/intel_client.py" ask \
  --question "Analyze ETH here as a trade. Include trend, levels, invalidation, upside/downside scenarios, and what would change your view."

# Fundamentals
uv run "$SKILL_DIR/scripts/intel_client.py" ask \
  --question "Give me the bull and bear case for HYPE over the next 3 months. Include product, usage, catalysts, and risks."

# Polymarket context
uv run "$SKILL_DIR/scripts/intel_client.py" ask \
  --question "What information should matter most for a Polymarket market on Fed cuts in March? Include macro drivers, watch items, and timing risk."

# Portfolio / watchlist
uv run "$SKILL_DIR/scripts/intel_client.py" ask \
  --question "Review this watchlist: BTC, ETH, SOL, HYPE. Rank where the best opportunity is and explain why."
```

## Structured JSON Outputs

For automation and downstream skills, append "Respond as JSON with:" to any query. The Brain returns parseable JSON in the `content` field.

### Trade Setup Pattern

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" ask \
  --question "Analyze BTC as a trade setup. Respond as JSON with: direction, entry_price, stop_loss, take_profit_1, take_profit_2, risk_reward_ratio, confidence, reasoning"
```

### Squeeze Detection Pattern

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" ask \
  --question "Scan top 10 perps for squeeze risk. Respond as JSON array with: symbol, funding_rate, open_interest, long_short_ratio, squeeze_direction, liquidation_risk, catalyst"
```

### Macro Risk Pattern

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" ask \
  --question "What is the current macro risk regime for crypto? Respond as JSON with: risk_regime, dxy_trend, vix_level, yield_curve_signal, equity_correlation, recommended_exposure, reasoning"
```

### Narrative Momentum Pattern

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" ask \
  --question "What are the strongest crypto narratives right now? Respond as JSON array with: narrative, momentum_score, top_tokens, sentiment, key_catalyst, risk_level"
```

### Custom Fields

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" ask \
  --question "Analyze SOL and respond as JSON with keys: thesis, bull_case, bear_case, catalysts, risks, levels, conclusion"
```

Use structured outputs when another skill or workflow needs consistent, machine-readable fields.

## Convenience Commands

### Market Analysis

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" market-analysis --coin ETH
```

Use for quick single-coin read: price drivers, market structure, sentiment, levels, catalysts, risks.

### News Search

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" news-search --query "BTC news today"
```

Use for latest headlines, dated developments, event-driven updates.

### Web Search

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" web-search --query "latest Fed interest rate decision"
```

Use for narrow fact lookup or simple external research.

## Response Times

| Query type | Typical time |
|-----------|-------------|
| Simple lookups (prices, funding rates, Fear & Greed) | 40–60 seconds |
| Multi-domain analysis (trade setups, protocol deep dives) | 60–120 seconds |
| Complex aggregations (yield opportunities, perp DEX rankings) | 120–180 seconds |
| Maximum timeout | ~600 seconds |

Queries can take time — the Brain is synthesizing across multiple data sources, not just doing a lookup. Do not retry prematurely.

## Rate Limits and Errors

- **60 requests per minute**. Each query consumes credits ($0.05/call).
- **429**: Rate limited — respect `Retry-After` header.
- **401**: Invalid or revoked API key.
- **504**: Query timed out — break into smaller, more specific requests.
- **500/503**: Server error — retry with exponential backoff.

## Response Format

The Brain API returns:

```json
{
  "session_id": "uuid",
  "content": "analysis text or JSON string",
  "timestamp": "ISO-8601"
}
```

The response is in the `content` field, not `message`. When you request structured JSON, parse the `content` field.

## Rules

1. Use `ask` unless you specifically need news-only or web-only behavior.
2. Use this skill as the primary research dependency for strategy skills.
3. Ask multi-part questions directly — the Brain synthesizes across analysts, not just retrieves.
4. For production workflows, use structured JSON patterns for stable downstream fields.
5. When a user asks any live market question, use this skill before falling back to generic search.
6. Do not retry on timeout — break the query into smaller pieces instead.
7. Log `session_id` from responses when debugging API issues.
