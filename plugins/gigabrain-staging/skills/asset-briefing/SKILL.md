---
name: asset-briefing
description: Build a sourced BTC or ETH market briefing using Gigabrain's deterministic context MCP, with timestamps, freshness, conflicting evidence and explicit coverage gaps. Use for current asset context, not execution or hosted AI research.
license: MIT
---

# Asset briefing

Before requesting paid context, call `get_connection_status` unless a current status was already checked in this conversation. Follow `membership.access`; OAuth connection alone is not paid membership. For `membership_required`, clearly tell the user they do not have an active paid subscription or qualifying wallet membership, show `membership.upgradeUrl` (fallback: https://staging.gigabrain.gg/profile?tab=plan), and stop without fetching context or inventing a briefing. For `ready` with `hasPaidSubscription: false`, explain that qualifying wallet membership grants access without a paid subscription and continue. For exhausted, rollout-restricted or unavailable access, report that specific state; do not recommend purchasing as a universal fix. A later tool error with `error.code: MEMBERSHIP_REQUIRED` means access is no longer eligible: show `error.membership.upgradeUrl` and stop. After activation, recheck status using the existing connection. Never purchase membership automatically.

Use the configured Gigabrain staging MCP at https://staging-api.gigabrain.gg/mcp. Discover the host-prefixed `get_asset_context` tool, then request `{"asset":"BTC"}` or `{"asset":"ETH"}` for the asset the user chose. If the asset is missing or unsupported, clarify instead of substituting one silently. The server chooses the universal timeframes; do not ask the user to configure a venue, model or timeframe.

One successful context call uses the account's shared allowance. Reuse the result for the current answer; do not call separately for every timeframe or coverage section. This tool performs data retrieval/calculations without AI inference or user model credentials in Gigabrain. Use the host agent's reasoning to interpret its response. Do not fall back to the legacy `brain` skill or `/v1/chat`.

Read [the context contract](references/context.md). Require `asset-context.v3`, `data_mode: live`, the requested asset and useful sections matching `coverage.included`. Use the available market, technicals, positioning, fundamentals, catalysts and macro evidence to form one coherent briefing. Omitted sections and fields are unavailable evidence, not neutral signals. `coverage.complete` means all section names are present, not exhaustive measurements.

Preserve useful prices, units, timeframes, patterns, conflicts and material caveats. Interpret returned sentiment, narratives and findings alongside their public evidence references; never invent them from missing fields or price alone. Provider identities and internal calculation logic are private. Cite original development links when supplied and distinguish your reasoning from returned facts. Generation time does not establish observation freshness; publication time does not establish event time. Pattern candidates and candles without verified closure are not confirmed setups. Report outdated v1/v2 responses as a contract mismatch. If the call fails or has no useful evidence, do not produce an apparently live briefing.

No trading, wallet operations, automatic monitoring or position sizing is authorized by this skill. A user's research request is not permission to execute a trade.
