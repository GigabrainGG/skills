# Host connection routes

Package: `gigabrain-staging@gigabrain`, version `0.3.5`.
Endpoint: `https://staging-api.gigabrain.gg/mcp` (Streamable HTTP).
Account: https://staging.gigabrain.gg/connect?tab=connected.
Scopes: `account:read intelligence:read offline_access`.

Commands vary by host version; check them against the installed host's `--help`.

## Codex

Run `codex plugin marketplace add GigabrainGG/skills --ref staging`, then `codex plugin add gigabrain-staging@gigabrain`. In desktop versions that install plugins through the UI, pick this package from the Gigabrain marketplace. Start a new session and run the setup skill.

If this Codex version cannot load a bundled remote MCP, install the three skills with its skill installer, add the server with `codex mcp add gigabrain-staging --url https://staging-api.gigabrain.gg/mcp --oauth-client-id https://chatgpt.com/oauth/codex/client.json`, then run `codex mcp login gigabrain-staging --scopes account:read,intelligence:read,offline_access`. Use this fallback only when no plugin server is configured.

## Claude Code

Run `claude plugin marketplace add https://github.com/GigabrainGG/skills.git#staging`, then `claude plugin install gigabrain-staging@gigabrain`. Start a new session, open `/mcp` and authenticate `plugin:gigabrain-staging:gigabrain-staging`.

## Other agents

The host needs Agent Skills support plus remote Streamable HTTP MCP with OAuth. Install the three skill folders from https://github.com/GigabrainGG/skills/tree/staging/plugins/gigabrain-staging and add the endpoint above through the host's OAuth connector. If sign-in reports an unknown client, tell the user the host is not supported yet.

## Updates and removal

Update with `codex plugin marketplace upgrade`, or `claude plugin marketplace update gigabrain` then `claude plugin update gigabrain-staging@gigabrain`, and start a new session. Remove with `codex plugin remove gigabrain-staging@gigabrain` or `claude plugin uninstall gigabrain-staging@gigabrain`; revoke the account grant separately at https://staging.gigabrain.gg/connect?tab=connected.
