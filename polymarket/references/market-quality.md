# Market Quality Scoring

## Overview

Every market receives a quality assessment composed of two independent axes:

- **Relevance** (0-100): How well the market matches a search query
- **Quality** (0-100): How tradable/healthy the market is

The composite ranking score is the geometric mean: `sqrt(relevance * quality)`. This ensures both axes matter equally --- a perfect query match on a dead market scores zero.

## Relevance Scoring (0-100)

### Term Coverage (60%)
Fraction of expanded query terms found in market text (question, slug, description, category, tags).

`(matched_terms / total_terms) * 60`

Query terms are expanded with:
- Alias mapping (btc <-> bitcoin, eth <-> ethereum, etc.)
- Numeric shorthand (100k -> 100000, 5m -> 5000000)
- Stopword removal

### Exact Substring (25%)
Full normalized query appears as substring in normalized text: +25 points.

### Slug Match (15%)
Query terms appear in the market slug: up to +15 points proportional to term coverage in slug.

## Quality Scoring (0-100)

Four components:

### Liquidity (0-30)
Log-scaled. Higher liquidity = more tradable.

| Liquidity | Score |
|-----------|-------|
| $0        | 0     |
| $1,000    | ~7    |
| $10,000   | ~15   |
| $50,000   | ~20   |
| $100,000  | ~23   |
| $1,000,000+ | 30  |

Formula: `min(30, 30 * log10(1 + liq/100) / log10(10001))`

### Volume 24h (0-25)
Log-scaled, same curve shape as liquidity.

| Volume 24h | Score |
|-----------|-------|
| $0        | 0     |
| $10,000   | ~12   |
| $100,000  | ~19   |
| $1,000,000+ | 25  |

Formula: `min(25, 25 * log10(1 + vol/100) / log10(10001))`

### Spread (0-25)
Tighter spread = higher score. Piecewise:

| Spread  | Score |
|---------|-------|
| <= 1%   | 25    |
| <= 3%   | 20    |
| <= 5%   | 15    |
| <= 10%  | 8     |
| > 10%   | 0     |

Unknown spread receives 12 (middle score).

### Status (0-20)
Binary checks:

| Check | Points |
|-------|--------|
| Active and not closed | 10 |
| Accepting orders | 5 |
| Ready | 5 |

## Tradability

A market is considered tradable (`is_tradable: true`) when ALL of:
- Active = true
- Closed = false
- Accepting orders = true
- Liquidity >= $5,000

## Warnings

The quality assessment generates warnings for:
- Liquidity below $5,000
- No 24h volume
- Spread > 10%
- Market not active or closed
- Market not accepting orders
- Market not ready

## Composite Ranking

For search results: `composite = sqrt(relevance * quality_score)`

Markets are sorted by composite score descending. This naturally pushes irrelevant markets AND dead markets to the bottom.
