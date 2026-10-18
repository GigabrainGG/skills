---
name: setup
description: Install or reconnect the Gigabrain read-only market-context integration, authorize its hosted MCP with browser OAuth, and verify account and context access. Use for Gigabrain connection setup or recovery.
license: MIT
---

# Connect Gigabrain

This package is **Gigabrain**, version **0.3.1-rc.1**, for **https://api.gigabrain.gg/mcp**.
Prepared for production; not activated. Do not attempt sign-in until the official Connect page enables setup.

Read [connection instructions](references/connection.md) for the actual host before changing configuration. Preserve existing installations; inspect the configured endpoint and package version first. Update an older package to the reviewed pinned revision using the host's supported updater or reinstall, while preserving its OAuth connection and unrelated configuration. Verify the loaded skills describe the public v3 contract and its six supported sections. Reuse an equivalent connection rather than creating duplicates. Do not replace a legacy Brain research or trading integration silently.

The package contains instructions and a hosted MCP connection, with no local service or inference runtime. Core context needs Gigabrain OAuth, active account entitlement and available allowance. It does **not** require an API key or an AI provider connected in Gigabrain. The user's host agent reasons over the returned evidence using its own model. Hosted Research is a separate product path; do not invoke it as a fallback.

## Connect and verify

1. Identify the actual host and installed version. Use its supported plugin installer, or its documented skill plus remote MCP setup if plugins are unavailable. A generic hosted chat may not install local packages. Explain unsupported capabilities instead of inventing commands.
2. Let the host run OAuth in the browser, requesting `account:read intelligence:read offline_access`. The user signs in and approves the displayed access. The host stores and refreshes tokens. Never request, read, copy or print access/refresh tokens, browser cookies or unrelated credentials. Client IDs are public metadata, not secrets.
3. Discover the configured tools; host prefixes vary. Call `get_connection_status` on this package's server. Report authentication, paid subscription and context access separately. `connected: true` only means OAuth works. Read `membership.hasPaidSubscription`, `subscriptionStatus`, `source`, `access` and `message`; never infer subscription from a connected tool or a quota number.
   - `access: membership_required`: explicitly say “You do not have an active paid subscription or qualifying wallet membership. Gigabrain is connected, but market intelligence is locked.” Show the returned `upgradeUrl` (fallback: https://gigabrain.gg/profile?tab=plan) as “View membership options.” Stop before the context check. Do not purchase, reconnect, ask for an AI key or imply checkout is open.
   - `access: ready` with `hasPaidSubscription: false`: explain that wallet membership grants access without a paid subscription. Do not upsell or block a qualifying holder.
   - `allowance_exhausted`: explain the limit/reset; buying another membership does not add quota. `not_enabled`: explain the rollout restriction. `temporarily_unavailable` or null/unknown subscription status: do not label the user unpaid or recommend payment as a fix. Stop at that stage.
   - Once the user activates membership, recheck status on the same connection; no reinstall or new OAuth consent is needed unless authorization itself expired or was revoked. If an older response lacks these explicit fields, do not claim membership is verified.
4. Only when `membership.access` is `ready`, explain that one context check uses one shared Gigabrain request, with no Gigabrain model-provider charge. If setup/verification is already authorized, call `get_asset_context` once with `{"asset":"BTC"}`. Otherwise ask before consuming an allowance. Do not create a subscription or change membership.
5. Require a successful `asset-context.v3` result with `data_mode: live`, the requested asset, and at least one useful section. Check that `coverage.included` matches the returned sections. The six supported sections are market, technicals, positioning, fundamentals, catalysts and macro; unavailable sections and fields are omitted. Explain useful coverage and material caveats without requesting hidden providers, raw data or internal logic. Missing fields do not mean zero or neutral. v1/v2 are outdated contracts, not successful public-context verification. Only then report context ready. If the tool is absent, denied, gated or unavailable, report that stage and stop; installation and OAuth alone do not prove a usable market response.

## Recovery

- Canceled browser consent: leave the installation intact; resume native sign-in when requested.
- Expired/revoked authorization or 401: use native reconnect. An old account-only grant needs fresh consent for `intelligence:read`; refresh cannot add permissions.
- 403 with `error.code: MEMBERSHIP_REQUIRED`: use `error.membership` and the unpaid-account wording above; show its upgrade link and stop. Other 403 errors may be scope or rollout restrictions; do not describe every denial as an unpaid subscription. Scope errors need fresh consent.
- 429: show the account limit/reset or Retry-After; do not loop or switch accounts/keys to evade limits.
- 409: this request ID was already admitted. Do not resubmit with a new ID automatically or claim a replayed result.
- 503 or unusable evidence: report context unavailable; do not fabricate a briefing, switch to hosted Research, or mark setup complete. A data-service outage is not a missing AI-provider connection.
- Manage/revoke access at https://gigabrain.gg/connect?tab=connected. Uninstalling a plugin and revoking its OAuth grant are separate actions; offer the appropriate one for the user's request.

No trading, wallet signing, transfers, account creation, background jobs or recurring requests are part of this setup.
