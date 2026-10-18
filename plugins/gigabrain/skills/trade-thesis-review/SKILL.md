---
name: trade-thesis-review
description: Review a user's supplied BTC or ETH trade thesis against Gigabrain market context and deterministic entry/stop/target arithmetic. Use for read-only thesis evaluation; never invent missing levels or place a trade.
license: MIT
---

# Review a supplied trade thesis

Use Gigabrain's hosted `get_asset_context` tool at https://api.gigabrain.gg/mcp. Collect the user's asset and thesis. Only include `trade` when the user has supplied all four fields: `direction` (`long` or `short`), `entry`, `stop`, and `target`, in USDT per asset. All levels must be positive; long requires stop < entry < target and short requires target < entry < stop.

If levels are missing, ask for the missing information when arithmetic is needed, or call asset-only context and explicitly omit trade math. Do not infer levels from market prices or invent the user's horizon, portfolio, conviction or risk tolerance. The server selects a universal context bundle; any user-stated horizon is interpretive context, not a tool parameter.

Call once with `{"asset":"BTC","trade":{"direction":"long","entry":100,"stop":90,"target":120}}` only when those are the user's actual inputs (the numbers here are illustrative, not current prices). The response's `trade_math` is deterministic distance and reward/risk arithmetic, not profitability, probability or a recommendation. Fees, slippage, leverage and liquidation risk are not modeled. Use [the context contract](references/context.md) for evidence units and quality.

Require `asset-context.v3` and compare the thesis against the sections in `coverage.included`. Preserve numeric units, timestamps, pattern confirmation states and material caveats. Omitted evidence is not zero or neutral. Sentiment, narratives and findings are optional: follow their returned public evidence references and separate your interpretation from facts. Cite original development links when supplied; do not infer providers or ask for hidden raw data or policy logic. Do not invent a score, probability, entry trigger or missing event date. If the service fails or returns an outdated contract, say the thesis could not be checked against usable public context.

Core MCP does not run AI inference or require AI-provider settings in Gigabrain. The host agent interprets the data. Do not call hosted Research or a trading skill as a fallback. Account quota/auth failures should be reported without automatic retries. Do not size, execute or monitor a position unless the user separately requests a supported action outside this read-only package.
