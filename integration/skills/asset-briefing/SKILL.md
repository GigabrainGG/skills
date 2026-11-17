---
name: asset-briefing
description: Build a sourced market briefing for one or more named assets from Gigabrain's market-context MCP, with percentiles, freshness, conflicting readings and explicit gaps. Use for current asset context, not trade execution.
license: MIT
---

# Asset briefing

Read [the context contract](references/context.md). Check account access as it describes before requesting context, unless status was already checked in this conversation. If the @LABEL@ tools are not available, follow its "When the tools are missing" section instead of answering from other sources.

Use the configured @LABEL@ MCP at @MCP_URL@. Discover the host-prefixed `get_asset_context` tool and request the assets the user named, for example `{"symbols":["BTC"]}`, in one call (up to ten). Use `"detail":"full"` when the user wants a complete briefing rather than what stands out. If the asset is missing, ask instead of substituting one, and check `resolved` when the user typed a name rather than a ticker. Make one call and reuse it for the whole answer.

Lead with the `verdict` and `headline`, then combine the readings, drivers, changes and levels into one coherent briefing. Preserve values, units, percentiles, states and observation wording, and say where readings conflict. Name what `unavailable` lists, and what `not_shown` leaves out in a summary, rather than treating it as neutral. Flag readings with `stale_min` or short `window_d`. Separate returned readings from your reasoning.

This skill does not authorize trading, wallet operations, monitoring or position sizing. A research request is not permission to execute a trade.
