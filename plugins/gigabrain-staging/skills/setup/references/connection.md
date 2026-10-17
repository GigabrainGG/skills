# Host connection routes

Package: `gigabrain-staging@gigabrain`, version `0.2.0-rc.1`.
Endpoint: `https://staging-api.gigabrain.gg/mcp` (Streamable HTTP).
Account: https://staging.gigabrain.gg/connect?tab=connected.
Scopes: `account:read intelligence:read offline_access`.
Staging pilot. Universal policy context returns healthy sections even when individual data providers are unavailable.

Use the immutable revision in the official guide at https://staging.gigabrain.gg/connect/setup when installing. Review the package source before installation. Commands below assume the current host exposes those commands in `--help`; plugin commands and OAuth behavior differ across host versions.

## Codex

Prefer the package's portable `plugin.json`, `mcp.json` and bundled skills. Register the official marketplace at the guide's pinned revision with `codex plugin marketplace add GigabrainGG/skills --ref <PINNED_REVISION>`, inspect `codex plugin list`, and install `codex plugin add gigabrain-staging@gigabrain` where supported. In desktop versions with UI-only installation, choose the Gigabrain source in the plugin directory and install this package. Start a new session after installation. Run this package's setup skill.

Modern Codex uses its trusted public client metadata document (`https://chatgpt.com/oauth/codex/client.json`). Let native OAuth discovery and the host's connection UI handle consent. Do not substitute DCR: this server does not enable open dynamic registration.

If this Codex version cannot load a bundled remote MCP, install just the three reviewed skills using its documented skill installer and configure the remote connection with `codex mcp add gigabrain-staging --url https://staging-api.gigabrain.gg/mcp --oauth-client-id https://chatgpt.com/oauth/codex/client.json` where `--oauth-client-id` is supported. Use `codex mcp login gigabrain-staging --scopes account:read,intelligence:read,offline_access`. Inspect existing entries first and do not configure this fallback alongside a working plugin server. If the installed version lacks these capabilities, explain the required update instead of changing global credentials.

## Claude Code

Use Claude's plugin marketplace route. Clone the official repository at the guide's immutable revision into a dedicated directory without overwriting an existing checkout. Add that reviewed directory with `claude plugin marketplace add <checkout>`, then `claude plugin install gigabrain-staging@gigabrain`. Local-path marketplace installation keeps the reviewed snapshot fixed; update it explicitly as described below.

The generated `.mcp.json` declares the native HTTP transport and public client ID `gigabrain-claude-staging`. No client secret is used. Start a new session or use the host's supported plugin reload, then open `/mcp` and authenticate `plugin:gigabrain-staging:gigabrain-staging`. Claude controls the OAuth callback and protected token storage. A Claude model subscription/API account is needed to run Claude itself; no separate AI-provider connection in Gigabrain is needed.

## Other agents

Require documented Agent Skills support plus remote Streamable HTTP MCP and OAuth authorization-code/PKCE support. Install only this package's three skill folders; importing skills alone does not connect MCP. Configure the stated remote endpoint using the host's native OAuth connector. This pilot accepts reviewed public client registrations and trusted Codex client metadata; unknown clients may be rejected. Report an unsupported OAuth client rather than inventing a client ID, sharing another client's credentials, or using an API-key fallback.

## Existing installs, updates and removal

Inspect installed package/version and remote endpoint before modifying them. Keep staging and production distinct. If the exact package is already installed, reuse it and verify access. Ask before replacing locally modified skills or changing a different endpoint.

For an update, review the release notes and new immutable revision, refresh only the relevant marketplace snapshot, and use the host's supported update/reinstall command. For a local Claude marketplace, fetch the reviewed revision in its dedicated checkout, update that marketplace, then `claude plugin update gigabrain-staging@gigabrain`. For Codex, update its marketplace ref explicitly before upgrade/reinstall; a pinned ref intentionally does not follow main. Restart/reload and verify tool discovery and one authorized context call. The website changing does not update installed packages.

For removal, use `codex plugin remove gigabrain-staging@gigabrain` or `claude plugin uninstall gigabrain-staging@gigabrain` if supported. Remove fallback configuration only when this setup created it and the user requests removal. Keep unrelated skills and servers. Revoke the account grant separately when the user wants access disconnected.

Host references: https://developers.openai.com/plugins/build/plugins ; https://code.claude.com/docs/en/plugins ; https://code.claude.com/docs/en/mcp .
