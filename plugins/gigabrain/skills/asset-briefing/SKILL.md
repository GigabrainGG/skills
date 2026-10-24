---
name: asset-briefing
description: Build a sourced BTC or ETH market briefing from Gigabrain's market-context MCP, with timestamps, freshness, conflicting evidence and explicit coverage gaps. Use for current asset context, not trade execution.
license: MIT
---

# Asset briefing

Read [the context contract](references/context.md). Check account access as it describes before requesting context, unless status was already checked in this conversation.

Use the configured Gigabrain MCP at https://api.gigabrain.gg/mcp. Discover the host-prefixed `get_asset_context` tool and request `{"asset":"BTC"}` or `{"asset":"ETH"}` for the asset the user chose. If the asset is missing or unsupported, ask instead of substituting one. The server chooses the timeframes; do not ask the user for a venue, model or timeframe. Make one call and reuse it for the whole answer.

Combine the returned market, technicals, positioning, fundamentals, catalysts and macro evidence into one coherent briefing. Preserve prices, units, timeframes, patterns, conflicts and material caveats. Name the sections that were omitted rather than treating them as neutral. Separate returned facts from your reasoning, and cite original development links when supplied.

This skill does not authorize trading, wallet operations, monitoring or position sizing. A research request is not permission to execute a trade.
