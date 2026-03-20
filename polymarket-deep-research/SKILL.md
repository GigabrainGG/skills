---
name: polymarket-deep-research
description: Quality-aware deep research for Polymarket markets. Use when the user wants a research brief, thesis generation, market comparison, catalyst analysis, or evidence assessment before placing a Polymarket order.
license: MIT
metadata:
  author: gigabrain
  version: "2.0"
---

# Polymarket Deep Research

Quality-aware research for Polymarket events. This skill is read-only: it gathers candidate events and markets, assesses market quality, checks market structure, and pulls external research via GigaBrain Intel.

Resolve `SKILL_DIR` as the directory containing this `SKILL.md`, then run scripts from absolute paths under that directory. Do not rely on the current working directory or any injected `CLAUDE_*` skill path variable.

```bash
uv run "$SKILL_DIR/scripts/pm_deep_research.py" <command> [args]
```

All commands return JSON to stdout.

## When to Use

- The user wants a Polymarket thesis, not just current odds
- The prompt is broad or ambiguous and may map to multiple related markets
- You need evidence for and against the current market price before trading
- You want a structured brief before handing off to the `polymarket` trading skill
- You want to compare multiple candidate markets on the same topic
- You need a conviction score and sizing recommendation

## Commands

### Research

Broad quality-aware research across events, markets, and external sources. Each candidate market includes a quality assessment with tradability verdict.

```bash
# Broad research
uv run "$SKILL_DIR/scripts/pm_deep_research.py" research --query "Will BTC hit 150k in 2026?" --limit 5

# Focus on a specific outcome
uv run "$SKILL_DIR/scripts/pm_deep_research.py" research --query "Will BTC hit 150k in 2026?" --outcome Yes --limit 5

# Skip external research
uv run "$SKILL_DIR/scripts/pm_deep_research.py" research --query "Trump election odds" --skip-intel
```

Output includes:
- Public-search event summaries with open interest and comment counts
- Candidate events with nested markets
- Candidate markets with quality scores and tradability verdicts
- Count of tradable vs untradable markets
- Focus-market price history
- External research summary with dated evidence
- Suggested next step based on tradability

### Thesis (NEW)

Structured trade thesis for a specific market and outcome. Returns conviction score, recommended sizing, target/stop prices, catalysts, and monitoring triggers.

```bash
# Auto-pick best matching market
uv run "$SKILL_DIR/scripts/pm_deep_research.py" thesis --query "bitcoin 150k" --outcome Yes

# Target a specific market
uv run "$SKILL_DIR/scripts/pm_deep_research.py" thesis --query "bitcoin 150k" --outcome Yes --market-slug "will-bitcoin-hit-150k-in-2026"

# Skip external research
uv run "$SKILL_DIR/scripts/pm_deep_research.py" thesis --query "bitcoin 150k" --outcome Yes --skip-intel
```

Output includes:
- Market details with quality assessment
- Tradability verdict (TRADABLE / NOT TRADABLE)
- Orderbook snapshot (midpoint, bid/ask depth)
- Price history
- Structured thesis: conviction, sizing, targets, catalysts, bull/bear case, monitoring triggers
- Next step recommendation

### Compare (NEW)

Side-by-side comparison of candidate markets on the same topic. Identifies the best market to trade based on quality scores.

```bash
# Compare bitcoin markets
uv run "$SKILL_DIR/scripts/pm_deep_research.py" compare --query "bitcoin"

# Compare with orderbook data for a specific outcome
uv run "$SKILL_DIR/scripts/pm_deep_research.py" compare --query "bitcoin" --outcome Yes --limit 5
```

Output includes:
- All candidate markets with quality scores
- Tradability verdict for each
- Orderbook depth for each (bid/ask USD)
- Best market identified
- Count of tradable vs total markets

## Quality Assessment

Every candidate market includes:
- `tradability_score` (0-100): Composite quality metric
- `liquidity_usd`: Market liquidity in USD
- `volume_24h_usd`: 24-hour trading volume
- `spread_pct`: Bid-ask spread
- `is_tradable`: Meets minimum safety thresholds
- `warnings`: List of quality concerns
- `tradability_verdict`: "TRADABLE" or "NOT TRADABLE"

Markets with `is_tradable: false` should not be traded without understanding why.

## Workflow

1. Run `research` for broad exploration, or `compare` to find the best market on a topic.
2. Review quality scores and tradability verdicts.
3. If a specific market looks promising, run `thesis` for a structured trade recommendation.
4. Switch to the `polymarket` skill and run `assess` or `validate-trade` before execution.
5. Use exact `market_slug` values when trading.

## Safety Rules

1. This skill does not place orders.
2. Treat results as pre-trade research, not final execution.
3. If multiple candidate markets remain, pick one exact `market_slug` before trading.
4. Always check `is_tradable` before recommending a trade.
5. Markets with quality warnings should be treated with caution.
6. Conviction scores from `thesis` are estimates -- always validate with your own judgment.
