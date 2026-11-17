# Context contract

Gigabrain serves read-only market context through MCP tools; host prefixes vary. Every context tool returns the same `context.v4` envelope; only `data` differs. Gigabrain returns measured readings and deterministic calculations; you supply the reasoning.

| Tool | Use |
| --- | --- |
| `get_connection_status` | Connection, plan, requests used, limit and reset date. Uses no allowance |
| `get_market_brief` | Whole-market overview; the starting point of a session |
| `get_asset_context` | Everything measured about one to ten named assets |
| `get_asset_drivers` | What an asset moves with |
| `screen_markets` | Find markets that meet conditions |
| `test_condition` | What followed the same state in the past |
| `get_period_performance` | Returns over a past period |
| `check_trade_plan` | Arithmetic and recorded data for a user's entry, stop and target |
| `score_trades` | Judge past trades |
| `report_issue` | Report a wrong value, missing data or a blocking error |

Each successful context call uses one request from the account's shared allowance; reuse a response instead of repeating the call.

## When the tools are missing

A host hides a server's tools until it is signed in. If no `get_connection_status` or `get_asset_context` tool is available under any prefix, Gigabrain is installed but not signed in, or its sign-in expired or was revoked. Do not answer from other sources as if they were Gigabrain context. Tell the user Gigabrain needs sign-in and how to do it in their host:

- Codex app: Settings → MCP servers → `gigabrain` → Authenticate. In a terminal: `codex mcp login gigabrain`.
- Claude Code: open `/mcp` and authenticate `plugin:gigabrain:gigabrain`.

Sign-in opens https://gigabrain.gg in the browser, where the user approves access. Codex adds the tools to the current conversation once sign-in completes; in other hosts, start a new conversation. Then continue with the user's request. If the user wants an answer without Gigabrain instead, name the sources you used.

## Account access

Call `get_connection_status` before the first context call in a conversation. `connected: true` only means OAuth works. Show the user `membership.message`, which the server words for their exact state (free tier, paid, wallet, locked, exhausted, rollout or unavailable); add `membership.upgradeUrl` as "View membership options" when it is present. Request context only when `membership.access` is `ready`; otherwise stop there. `membership.requestsRemaining` and `membership.resetsAt` give the remaining allowance. A 403 `MEMBERSHIP_REQUIRED` tool error carries the same fields under `error.membership`. After the user activates membership, recheck status on the same connection; no reinstall is needed. Membership changes happen on the user's plan page.

## context.v4

Require `schema_version: context.v4` and the `tool` you called. Any other schema version is a contract mismatch: report it instead of interpreting the payload. Within v4, fields are only added, never removed or redefined.

| Field | Meaning |
| --- | --- |
| `id` | Response id; quote it in `report_issue` |
| `as_of` | The time the answer describes, in UTC (a past time when `as_of` was sent) |
| `resolved` | Each plain-text input and the symbol it was matched to. Check it before relying on a match |
| `verdict` | `quiet`, `normal`, `unusual` or `insufficient_history` |
| `headline` | One templated sentence naming the readings behind the verdict |
| `listing_venue` | The venue the positioning and liquidity readings describe, when present |
| `data` | The tool's own content |
| `unavailable` | Readings that could not be computed, each with a `reason` and, when it applies to one market, a `symbol` |
| `next` | At most one suggested call, only when the verdict is `unusual`. A suggestion, not an instruction; each call costs a request |

Every reading, in every tool, has the same shape: `value` at human scale (2.1 means 2.1%; a word for category readings such as trend), `unit` in words, `percentile` against the market's own history, `state` (`extreme_low` ≤5, `low` 6–25, `normal` 26–74, `high` 75–94, `extreme_high` ≥95) and a one-sentence `observation`. `window_d` appears when the percentile rests on short history; `stale_min` appears when the data is older than its normal freshness. The sign of `value` carries direction. Readings with no venue prefix are measured on Hyperliquid.

`get_asset_context` takes `symbols` (always a list, one to ten) and `detail`: `summary` (default) returns only readings at an extreme, changed categories, set flags, `return_24h` and the nearest levels, with a per-symbol count in `data.not_shown`; `full` returns every reading, every level and matched posts. Its `data` holds `readings`, `drivers`, `changes` and `levels`, keyed by symbol.

An `observation` states what a reading is, never what it means for price; keep it distinct from your interpretation. A percentile describes the market's own history, not a forecast. An entry in `unavailable` is missing, not zero, neutral or no risk; `insufficient_history` and `no_data` are normal and are not issues to report. A reading with `stale_min` is not current; say so.

## Failures

MCP failures use `isError` with JSON status details. Do not retry automatically after authentication, membership or quota failures. If a call fails or returns no useful readings, say so; never produce an apparently live answer. Use `report_issue` only when a value looks wrong, a reading you expected is missing without a stated reason, or an error blocks the task.
