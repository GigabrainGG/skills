---
name: gigabrain-intel
description: Primary GigaBrain market intelligence skill. Query the Brain API for crypto and macro research, market microstructure, fundamentals, sentiment, trade setup analysis, Polymarket context, portfolio questions, and structured JSON outputs. Use for nearly any live market question before falling back to plain web search.
license: MIT
metadata:
  author: gigabrain
  version: "2.0"
---

# GigaBrain Intel

This is the default Brain skill for market intelligence.

Treat it as the primary research layer for:
- macro and market regime
- price drivers and narrative shifts
- market microstructure and positioning
- technical levels and trade setup framing
- protocol and token fundamentals
- sentiment and crowding
- Polymarket and event-market context
- portfolio and watchlist questions
- structured JSON research outputs

Do not frame this skill as just "web search" or "news". The Brain API is the full intelligence surface. Use `ask` by default unless the user explicitly wants only raw web or news lookup behavior.

Resolve `SKILL_DIR` as the directory containing this `SKILL.md`, then run scripts from absolute paths under that directory. Do not rely on the current working directory or any injected `CLAUDE_*` skill path variable.

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" <command> [args]
```

All commands return JSON to stdout.

## Setup

No manual setup needed. Scripts declare their own dependencies and run in isolated environments via `uv run`.

## Environment

- Requires `GIGABRAIN_API_URL`
- Optionally uses `GIGABRAIN_API_KEY`
- If `GIGABRAIN_API_URL` is missing, the script exits with a JSON error

## Command Priority

Use the commands in this order:

1. `ask`
   Use for almost everything. This is the main Brain interface.
2. `market-analysis`
   Use for a fast single-asset overview when the user wants a concise take on one coin.
3. `news-search`
   Use when the user explicitly wants latest headlines, dated developments, or source-oriented news summaries.
4. `web-search`
   Use when the user explicitly wants simple external lookup or fact gathering rather than synthesized market intelligence.

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

## Structured JSON

If another skill or workflow needs machine-readable output, ask for JSON explicitly:

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" ask \
  --question "Analyze SOL and respond as JSON with keys: thesis, bull_case, bear_case, catalysts, risks, levels, conclusion."
```

Use this when downstream strategy skills need consistent fields rather than prose.

## Convenience Commands

### Market Analysis

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" market-analysis --coin ETH
```

Use for:
- quick single-coin read
- brief market brief before deeper follow-up
- fast price-driver + catalyst summary

### News Search

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" news-search --query "BTC news today"
```

Use for:
- latest headlines
- recent developments with dates
- event-driven updates
- source-oriented summaries

### Web Search

```bash
uv run "$SKILL_DIR/scripts/intel_client.py" web-search --query "latest Fed interest rate decision"
```

Use for:
- narrow fact lookup
- simple external research
- targeted source gathering

## Usage Rules

1. Prefer `ask` unless you specifically need simple news-only or web-only behavior.
2. Use this skill as the primary research dependency for strategy skills.
3. Ask multi-part questions directly; the Brain API is meant to synthesize, not just retrieve.
4. For production workflows, ask for explicit structure when another skill needs stable fields.
5. When a user asks a live market question, use this skill before relying on generic search.
