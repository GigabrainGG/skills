---
name: polymarket-deep-research
description: Read-only deep research for Polymarket markets. Use when the user wants a research brief, catalyst analysis, evidence for and against a market price, or a trade thesis before placing a Polymarket order.
license: MIT
metadata:
  author: gigabrain
  version: "1.1"
---

# Polymarket Deep Research

Research a Polymarket event before trading. This skill is read-only: it gathers
candidate events and markets, checks market structure, and pulls external
research via GigaBrain Intel.

Resolve `SKILL_DIR` as the directory containing this `SKILL.md`, then run scripts from absolute paths under that directory. Do not rely on the current working directory or any injected `CLAUDE_*` skill path variable.

```bash
uv run "$SKILL_DIR/scripts/pm_deep_research.py" research --query "Will BTC hit 150k in 2026?" --limit 5
```

All commands return JSON to stdout.

## When to Use
- The user wants a Polymarket thesis, not just current odds
- The prompt is broad or ambiguous and may map to multiple related markets
- You need evidence for and against the current market price before trading
- You want a structured brief before handing off to the `polymarket` trading skill

## Output Shape
- Public-search event summaries with open interest and comment counts
- Candidate events with nested markets
- Candidate markets with slugs, outcomes, liquidity, and current prices
- Focus-market price history for the top candidate when available
- Optional order-book snapshot for a focus outcome
- External research summary with dated evidence and key catalysts
- Suggested next step: watch, research more, or resolve to a specific market slug before trading

## Commands

### Research
```bash
# Broad research across events, markets, and external sources
uv run "$SKILL_DIR/scripts/pm_deep_research.py" research --query "Will BTC hit 150k in 2026?" --limit 5

# Focus the brief on a specific outcome
uv run "$SKILL_DIR/scripts/pm_deep_research.py" research --query "Will BTC hit 150k in 2026?" --outcome Yes --limit 5

# Skip external research and return only Polymarket-native data
uv run "$SKILL_DIR/scripts/pm_deep_research.py" research --query "Trump election odds" --skip-intel
```

## Workflow
1. Run `research` first.
2. Review `public_search_events`, `candidate_markets`, and `focus_market_history` together.
3. If the brief returns multiple candidate markets, pick one exact `market_slug`.
4. Switch to the `polymarket` skill and run `readiness` before any `orderbook`, `buy`, or `sell`.

## Safety Rules
1. This skill does not place orders.
2. Treat the result as a pre-trade brief, not final execution.
3. If multiple candidate markets remain, do not trade until one exact `market_slug` is selected.
