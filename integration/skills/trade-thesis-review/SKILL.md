---
name: trade-thesis-review
description: Review a user's supplied BTC or ETH trade thesis against Gigabrain market context and deterministic entry/stop/target arithmetic. Use for read-only thesis evaluation; never invent missing levels or place a trade.
license: MIT
---

# Review a supplied trade thesis

Read [the context contract](references/context.md). Check account access as it describes before requesting context, unless status was already checked in this conversation.

Use @LABEL@'s `get_asset_context` tool at @MCP_URL@. Collect the user's asset and thesis. Only include `trade` when the user has supplied all four fields: `direction` (`long` or `short`), `entry`, `stop` and `target`, in USDT per asset. All levels must be positive; long requires stop < entry < target and short requires target < entry < stop.

If levels are missing, ask for them when arithmetic is needed, or request asset-only context and say trade math was omitted. Do not infer levels from market prices or invent the user's horizon, portfolio, conviction or risk tolerance. A stated horizon is interpretive context, not a tool parameter.

Call once, for example `{"asset":"BTC","trade":{"direction":"long","entry":100,"stop":90,"target":120}}`, using only the user's actual inputs (these numbers are illustrative). `trade_math` is distance and reward/risk arithmetic, not profitability, probability or a recommendation; fees, slippage, leverage and liquidation are not modeled.

Compare the thesis against each section in `coverage.included`: where the evidence supports it, where it conflicts, and what is missing. Preserve units, timestamps, pattern confirmation states and material caveats. Do not invent a score, probability, entry trigger or event date. If the call fails, say the thesis could not be checked against usable context.

This skill does not size, execute or monitor positions.
