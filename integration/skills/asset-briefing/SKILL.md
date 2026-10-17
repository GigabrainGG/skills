---
name: asset-briefing
description: Build a sourced BTC or ETH market briefing using Gigabrain's deterministic context MCP, with timestamps, freshness, conflicting evidence and explicit coverage gaps. Use for current asset context, not execution or hosted AI research.
license: MIT
---

# Asset briefing

Use the configured @LABEL@ MCP at @MCP_URL@. Discover the host-prefixed `get_asset_context` tool, then request `{"asset":"BTC"}` or `{"asset":"ETH"}` for the asset the user chose. If the asset is missing or unsupported, clarify instead of substituting one silently. The server chooses the universal timeframes; do not ask the user to configure a venue, model or timeframe.

One successful context call uses the account's shared allowance. Reuse the result for the current answer; do not call separately for every timeframe or coverage section. This tool performs data retrieval/calculations without AI inference or user model credentials in Gigabrain. Use the host agent's reasoning to interpret its response. Do not fall back to the legacy `brain` skill or `/v1/chat`.

Read [the v1 contract](references/context.md) when interpreting fields. Require `asset-context.v1`, the requested asset, and usable evidence. Present the material price/positioning facts with source, venue, interval, units and source time. Distinguish source time from retrieval/generation time. Cite the provider endpoint/source returned by the tool; do not invent supporting news links.

Separate observations from your interpretation. Highlight opposing signals without inventing causation. Preserve stale/missing/invalid states and the returned coverage gaps; the current bundle does not supply fundamentals, macro, catalysts or comprehensive news. If evidence is partial, call the briefing partial. Do not invent probabilities, trading signals or absent prices. If all evidence is unusable or the tool fails, explain the failure rather than produce an apparently live briefing.

No trading, wallet operations, automatic monitoring or position sizing is authorized by this skill. A user's research request is not permission to execute a trade.
