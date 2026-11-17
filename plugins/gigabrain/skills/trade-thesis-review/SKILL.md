---
name: trade-thesis-review
description: Review a user's supplied trade thesis against Gigabrain market context and its deterministic entry/stop/target check. Use for read-only thesis evaluation; never invent missing levels or place a trade.
license: MIT
---

# Review a supplied trade thesis

Read [the context contract](references/context.md). Check account access as it describes before requesting context, unless status was already checked in this conversation. If the Gigabrain tools are not available, follow its "When the tools are missing" section instead of answering from other sources.

Use Gigabrain's tools at https://api.gigabrain.gg/mcp. Collect the user's asset and thesis. Call `get_asset_context` with `{"symbols":["<asset>"]}` for the market evidence.

Call `check_trade_plan` only when the user has supplied all of `direction` (`long` or `short`), `entry`, `stop` and `target`, in USD. All levels must be positive; long requires stop < entry < target and short requires target < entry < stop. Pass `hold`, `leverage`, `size_usd` or `open_positions` only when the user gave them; otherwise the tool's stated defaults apply, and say which defaults were used. If levels are missing, ask for them when the trade check is needed, or review against context only and say the trade check was omitted. Do not infer levels from market prices or invent the user's horizon, portfolio, conviction or risk tolerance.

For example `{"symbol":"BTC","direction":"long","entry":100,"stop":90,"target":120}`, using only the user's actual inputs (these numbers are illustrative). The result is arithmetic and recorded history: distances, how often a stop-sized move happened, reward to risk before and after costs, funding, liquidation price, events and warnings. It is not a probability of profit or a recommendation, and it does not size the position.

Compare the thesis against the returned readings: where they support it, where they conflict, and what `unavailable` leaves missing. Preserve units, percentiles, states and warnings. Do not invent a score, probability, entry trigger or event date. If a call fails, say the thesis could not be checked against usable context.

This skill does not size, execute or monitor positions.
