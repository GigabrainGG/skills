---
name: setup
description: Install or reconnect the Gigabrain read-only market-context integration, authorize its hosted MCP with browser OAuth, and verify account and context access. Use for Gigabrain connection setup or recovery.
license: MIT
---

# Connect Gigabrain

This package is **Gigabrain**, version **0.3.2**, for **https://api.gigabrain.gg/mcp**.
Sections are returned independently; unsupported data is omitted.

The package is instructions plus a hosted MCP connection; nothing runs locally. Access needs Gigabrain OAuth, an eligible account and available allowance. No API key is involved, and your own model does the reasoning.

Read [connection instructions](references/connection.md) for the actual host before changing configuration. Inspect any existing installation's endpoint and version first. Reuse an equivalent connection instead of creating a duplicate, and update an older package through the host's updater while preserving its OAuth connection and unrelated configuration.

## Connect and verify

1. Identify the host and its version. Use its plugin installer, or its documented skill plus remote MCP setup if plugins are unavailable. If the host cannot install packages, explain that instead of inventing commands.
2. Let the host run browser OAuth, requesting `account:read intelligence:read offline_access`. The user signs in and approves access; the host stores and refreshes tokens. Never request, read, copy or print tokens, cookies or other credentials. Client IDs are public metadata, not secrets.
3. Discover the tools (host prefixes vary) and call `get_connection_status`. Report authentication, membership and context access separately, following the account access rules in [the context contract](references/context.md). Stop here unless `membership.access` is `ready`.
4. Explain that one context check uses one request from the shared allowance. If the user's setup request already authorizes verification, call `get_asset_context` once with `{"asset":"BTC"}`; otherwise ask first.
5. Require a successful `asset-context.v3` response with `data_mode: live`, BTC, at least one useful section and `coverage.included` matching the returned sections. Summarize which of the six sections (market, technicals, positioning, fundamentals, catalysts, macro) came back and any material caveats. Only then report that context is ready. Installation and OAuth alone do not prove usable context.

## Recovery

- Canceled browser consent: leave the installation intact; resume sign-in when the user asks.
- 401 or expired/revoked authorization: use the host's reconnect. An old grant without `intelligence:read` needs fresh consent; refresh cannot add scopes.
- 403 `MEMBERSHIP_REQUIRED`: follow the membership guidance and stop. Other 403s may be scope or rollout restrictions; do not call every denial an unpaid account.
- 429: show the limit and reset or Retry-After; do not loop or switch accounts.
- 409: this request ID was already admitted; do not resubmit with a new ID automatically.
- 503 or no usable evidence: report context unavailable and do not mark setup complete.
- Manage or revoke access at https://gigabrain.gg/connect?tab=connected. Uninstalling the plugin and revoking its OAuth grant are separate actions.

Setup includes no trading, wallet signing, transfers, account creation or recurring jobs.
