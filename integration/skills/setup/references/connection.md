# Host connection routes

Package: `@PLUGIN@@gigabrain`, version `@VERSION@`.
Endpoint: `@MCP_URL@` (Streamable HTTP).
Account: @ORIGIN@/connect?tab=connected.
Scopes: `account:read intelligence:read offline_access`.

Use the pinned revision from the official guide at @ORIGIN@/connect/setup. Check that each command below exists in the installed host's `--help`; plugin commands and OAuth behavior vary by version.

## Codex

Add the marketplace at the guide's pinned revision with `codex plugin marketplace add GigabrainGG/skills --ref <PINNED_REVISION>`, check `codex plugin list`, then `codex plugin add @PLUGIN@@gigabrain`. In desktop versions that install plugins through the UI, pick this package from the Gigabrain marketplace. Start a new session, then run this package's setup skill. Codex handles OAuth through its own connection UI.

If this Codex version cannot load a bundled remote MCP, install only the three skills with its skill installer and add the server with `codex mcp add @PLUGIN@ --url @MCP_URL@ --oauth-client-id https://chatgpt.com/oauth/codex/client.json`, then `codex mcp login @PLUGIN@ --scopes account:read,intelligence:read,offline_access`. Do not add this fallback alongside a working plugin server. If the version supports neither route, explain the required update.

## Claude Code

Clone the official repository at the guide's pinned revision into a dedicated directory, without overwriting an existing checkout. Run `claude plugin marketplace add <checkout>`, then `claude plugin install @PLUGIN@@gigabrain`. The local checkout keeps the installed snapshot fixed until you update it.

The package's `.mcp.json` declares HTTP transport and the public client ID `@CLAUDE_CLIENT_ID@`; there is no client secret. Start a new session or reload plugins, open `/mcp` and authenticate `plugin:@PLUGIN@:@PLUGIN@`. Claude handles the OAuth callback and token storage.

## Other agents

The host needs Agent Skills support plus remote Streamable HTTP MCP with OAuth authorization-code/PKCE. Install the three skill folders (skills alone do not configure MCP) and add the endpoint above through the host's OAuth connector. Unregistered OAuth clients may be rejected: report that instead of inventing a client ID or borrowing another client's.

## Updates and removal

For an update, read the release notes, move the marketplace to the new pinned revision and use the host's update command. For a local Claude marketplace, check out the new revision in its checkout, then `claude plugin marketplace update gigabrain` and `claude plugin update @PLUGIN@@gigabrain`. For Codex, update the marketplace ref first; a pinned ref does not follow `main`. Reload and verify with one authorized context call. The website changing does not update installed packages.

To remove, use `codex plugin remove @PLUGIN@@gigabrain` or `claude plugin uninstall @PLUGIN@@gigabrain`. Remove fallback configuration only if this setup created it. Revoking the account grant is a separate step.

Host references: https://developers.openai.com/plugins/build/plugins ; https://code.claude.com/docs/en/plugins ; https://code.claude.com/docs/en/mcp .
