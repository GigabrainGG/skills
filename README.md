# Gigabrain Skills

**Market intelligence for your AI agents.**

Official open-source workflow skills and client packages for connecting your AI to [Gigabrain](https://gigabrain.gg). Your AI supplies the reasoning; Gigabrain supplies sourced market context, evidence, timestamps, coverage information and deterministic calculations through a hosted, read-only MCP connection.

## Connect Gigabrain

Start at [Connect Gigabrain](https://gigabrain.gg/connect), choose a supported client, and follow its installation and browser OAuth flow. Verify setup with an authenticated market briefing. Installation or sign-in alone does not confirm that market context is available.

Core market context does not require connecting an AI-provider key in Gigabrain. Account membership and shared usage limits still apply. See Connect for current client support and the [integration guide](integration/README.md) for package maintenance and release details.

## Workflows

| Skill | Purpose |
|---|---|
| `setup` | Install/connect the reviewed package, authorize the account and verify useful context. |
| `asset-briefing` | Build a sourced asset briefing with freshness, coverage gaps and conflicting evidence. |
| `trade-thesis-review` | Review a supplied thesis against market evidence and explicit assumptions. |

These workflows are read-only. Customers and their configured agents retain responsibility for strategy, sizing and execution.

## Repository structure

- `integration/skills/`: canonical workflow skill source.
- `integration/`: shared references, environment configuration, package generator and validation.
- `plugins/`: generated production and staging client packages.
- `.agents/plugins/` and `.claude-plugin/`: generated marketplace manifests.

Keep one canonical skill source and generate the client packages from it. Provider integrations, calculations, authentication, membership and usage enforcement remain on Gigabrain servers.

## Contributing

Edit the canonical source, regenerate the packages and validate:

```sh
python3 -m pip install -r integration/requirements-dev.txt
python3 integration/build.py
python3 integration/build.py --check
python3 -m unittest discover -s integration/tests -v
```

See [release and update instructions](integration/README.md#releases-and-updates). Do not edit generated packages by hand or move existing release tags. Package contents are licensed under [MIT](integration/LICENSE); vendored schemas retain their own notices.

## SuperAgent skills

Hosted SuperAgent runtime skills have moved to [GigabrainGG/superagent-skills](https://github.com/GigabrainGG/superagent-skills). That maintenance repository contains the legacy Brain API-key client, wallet, swap, trading and agent-specific portfolio skills, plus the third-party sync manifest. Their folder names are preserved there.

This repository distributes the official Gigabrain market-context integration. Existing pinned Git revisions and release tags remain available for compatibility.
