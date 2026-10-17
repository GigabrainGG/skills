---
name: setup
description: Install or reconnect the Gigabrain read-only market-context integration, authorize its hosted MCP with browser OAuth, and verify account and context access. Use for Gigabrain connection setup or recovery.
license: MIT
---

# Connect Gigabrain

This package is **Gigabrain staging**, version **0.2.0-rc.2**, for **https://staging-api.gigabrain.gg/mcp**.
Staging pilot. Universal policy context returns healthy sections even when individual data providers are unavailable.

Read [connection instructions](references/connection.md) for the actual host before changing configuration. Preserve existing installations; inspect the configured endpoint and package version first. Update an older package to the reviewed pinned revision using the host's supported updater or reinstall, while preserving its OAuth connection and unrelated configuration. Verify the loaded skills describe the six-section v2 contract. Reuse an equivalent connection rather than creating duplicates. Do not replace a legacy Brain research or trading integration silently.

The package contains instructions and a hosted MCP connection, with no local service or inference runtime. Core context needs Gigabrain OAuth, active account entitlement and available allowance. It does **not** require an API key or an AI provider connected in Gigabrain. The user's host agent reasons over the returned evidence using its own model. Hosted Research is a separate product path; do not invoke it as a fallback.

## Connect and verify

1. Identify the actual host and installed version. Use its supported plugin installer, or its documented skill plus remote MCP setup if plugins are unavailable. A generic hosted chat may not install local packages. Explain unsupported capabilities instead of inventing commands.
2. Let the host run OAuth in the browser, requesting `account:read intelligence:read offline_access`. The user signs in and approves the displayed access. The host stores and refreshes tokens. Never request, read, copy or print access/refresh tokens, browser cookies or unrelated credentials. Client IDs are public metadata, not secrets.
3. Discover the configured tools; host prefixes vary. Call `get_connection_status` on this package's server. Report authentication and account eligibility separately; `connected: true` alone does not prove context access.
4. Explain that one context check uses one shared Gigabrain request, with no Gigabrain model-provider charge. If setup/verification is already authorized, call `get_asset_context` once with `{"asset":"BTC"}`. Otherwise ask before consuming an allowance. Do not create a subscription or change membership.
5. Require a successful result with `schema_version: asset-context.v2`, the requested asset and all six sections: market, technicals, positioning, fundamentals, catalysts and macro. At least one section must have usable data. Report useful sections with sources/times and coverage gaps. An unavailable section, including CoinGlass positioning, must not discard healthy sections. A v1 response is an outdated contract, not successful six-section verification. Only then report market context ready. If the tool is absent, denied, gated or unavailable, report that exact stage and stop; an installation, OAuth grant or cached account-status result is not a successful market response.

## Recovery

- Canceled browser consent: leave the installation intact; resume native sign-in when requested.
- Expired/revoked authorization or 401: use native reconnect. An old account-only grant needs fresh consent for `intelligence:read`; refresh cannot add permissions.
- 403: inspect the tool error. Scope errors need reconnect; account eligibility errors need the user's account page, not another model key.
- 429: show the account limit/reset or Retry-After; do not loop or switch accounts/keys to evade limits.
- 409: this request ID was already admitted. Do not resubmit with a new ID automatically or claim a replayed result.
- 503 or unusable evidence: report context unavailable; do not fabricate a briefing, switch to hosted Research, or mark setup complete. A data-service outage is not a missing AI-provider connection.
- Manage/revoke access at https://staging.gigabrain.gg/connect?tab=connected. Uninstalling a plugin and revoking its OAuth grant are separate actions; offer the appropriate one for the user's request.

No trading, wallet signing, transfers, account creation, background jobs or recurring requests are part of this setup.
