---
name: setup
description: Install or reconnect the Gigabrain read-only market-context integration, authorize its hosted MCP with browser OAuth, and verify account and context access. Use for Gigabrain connection setup or recovery.
license: MIT
---

# Connect Gigabrain

This package is **@LABEL@**, version **@VERSION@**, for **@MCP_URL@**.
@AVAILABILITY@

The package is instructions plus a hosted MCP connection; nothing runs locally. Access needs Gigabrain OAuth, an eligible account and available allowance. No API key is involved, and your own model does the reasoning.

Read [connection instructions](references/connection.md) for the actual host before changing configuration. Inspect any existing installation's endpoint and version first. Reuse an equivalent connection instead of creating a duplicate, and update an older package through the host's updater while preserving its OAuth connection and unrelated configuration.

## Connect and verify

1. Identify the host and its version. Use its plugin installer, or its documented skill plus remote MCP setup if plugins are unavailable. If the host supports neither, tell the user which capability is missing.
2. Sign in through the host's connection flow, which opens Gigabrain in the browser and requests `account:read intelligence:read offline_access`. The user approves access there, and the host keeps the connection signed in.
3. Discover the tools (host prefixes vary) and call `get_connection_status`. Report that OAuth is connected, then show `membership.message` and any `membership.upgradeUrl` (see [the context contract](references/context.md)). Stop here unless `membership.access` is `ready`.
4. Explain that one context check uses one request from the shared allowance. If the user's setup request already authorizes verification, call `get_asset_context` once with `{"asset":"BTC"}`; otherwise ask first.
5. Require a successful `asset-context.v3` response with `data_mode: live`, BTC, at least one useful section and `coverage.included` matching the returned sections. Summarize which of the six sections (market, technicals, positioning, fundamentals, catalysts, macro) came back and any material caveats. Only then report that context is ready. Installation and OAuth alone do not prove usable context.

## Recovery

- Canceled browser consent: leave the installation intact; resume sign-in when the user asks.
- 401 or expired/revoked authorization: use the host's reconnect. An old grant without `intelligence:read` needs fresh consent; refresh cannot add scopes.
- 403 `MEMBERSHIP_REQUIRED`: show `error.membership.message` and its upgrade link, then stop. Other 403s are scope or rollout restrictions; report them as such.
- 429: show the limit and reset time, then stop.
- 409: this request ID was already admitted; report it and let the user decide whether to run a new request.
- 503 or no usable evidence: report context unavailable; setup is not complete yet.
- Manage or revoke access at @ORIGIN@/connect?tab=connected. Uninstalling the plugin and revoking its OAuth grant are separate actions.

Setup includes no trading, wallet signing, transfers, account creation or recurring jobs.
