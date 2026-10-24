# Host connection routes

Package: `@PLUGIN@@gigabrain`, version `@VERSION@`.
Endpoint: `@MCP_URL@` (Streamable HTTP).
Account: @ORIGIN@/connect?tab=connected.
Scopes: `account:read intelligence:read offline_access`.

Commands vary by host version; check them against the installed host's `--help`.

## Codex

Run `codex plugin marketplace add GigabrainGG/skills --ref @BRANCH@`, then `codex plugin add @PLUGIN@@gigabrain`. In desktop versions that install plugins through the UI, pick this package from the Gigabrain marketplace. Start a new session and run the setup skill.

If this Codex version cannot load a bundled remote MCP, install the three skills with its skill installer, add the server with `codex mcp add @PLUGIN@ --url @MCP_URL@ --oauth-client-id https://chatgpt.com/oauth/codex/client.json`, then run `codex mcp login @PLUGIN@ --scopes account:read,intelligence:read,offline_access`. Use this fallback only when no plugin server is configured.

## Claude Code

Run `claude plugin marketplace add https://github.com/GigabrainGG/skills.git#@BRANCH@`, then `claude plugin install @PLUGIN@@gigabrain`. Start a new session, open `/mcp` and authenticate `plugin:@PLUGIN@:@PLUGIN@`.

## Other agents

The host needs Agent Skills support plus remote Streamable HTTP MCP with OAuth. Install the three skill folders from https://github.com/GigabrainGG/skills/tree/@BRANCH@/plugins/@PLUGIN@ and add the endpoint above through the host's OAuth connector. If sign-in reports an unknown client, tell the user the host is not supported yet.

## Updates and removal

Update with `codex plugin marketplace upgrade`, or `claude plugin marketplace update gigabrain` then `claude plugin update @PLUGIN@@gigabrain`, and start a new session. Remove with `codex plugin remove @PLUGIN@@gigabrain` or `claude plugin uninstall @PLUGIN@@gigabrain`; revoke the account grant separately at @ORIGIN@/connect?tab=connected.
