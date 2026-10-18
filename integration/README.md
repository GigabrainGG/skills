# Gigabrain market-context integration

Canonical source: **GigabrainGG/skills**, `integration/`. Maintained by Gigabrain; report problems or propose changes through this repository's issues and pull requests. MIT applies to this directory and its generated packages under `plugins/`.

The new read-only package contains setup, asset briefing and supplied trade-thesis review skills, plus remote MCP configuration. It contains no local service, credentials, model runtime, trading tools or wallet skills. Gigabrain fetches evidence and performs deterministic calculations; the user's host agent supplies AI reasoning. Users do not need to connect an AI provider in Gigabrain. Hosted Research and the legacy `brain/` API-key skill remain separate.

## Install

Use the official [Connect page](https://gigabrain.gg/connect) or the authorized [staging pilot](https://staging.gigabrain.gg/connect). The setup request reads an environment-specific guide, installs only the reviewed plugin, opens native browser OAuth and verifies account/context access. The guide pins an immutable Git revision. See the generated setup skill for host-specific instructions.

This release candidate prepares both `gigabrain@gigabrain` (production) and `gigabrain-staging@gigabrain` (pilot). **Production is not activated.** Staging OAuth and six-section context are verified. CoinGlass positioning may remain unavailable; other sections continue independently. A successful OAuth connection is not a successful market-context response. An unavailable service must never redirect the user to AI-provider or API-key setup.

## Build and validate

```sh
python3 integration/build.py
python3 integration/build.py --check
python3 -m unittest discover -s integration/tests -v
```

`integration/config.json`, three canonical skill folders and the shared contract reference generate both portable Agent Plugins manifests and Claude manifests/marketplaces. Generated files are committed for direct host installation. Do not edit `plugins/` by hand. Validation checks reproducibility, pinned official schemas, package boundaries, manifest paths, environment separation and absence of credentials/local execution hooks. CI additionally runs the native Claude manifest validator.

For schema validation install the pinned development requirements with `python3 -m pip install -r integration/requirements-dev.txt`. These dependencies are only for maintainers, not skill users. Vendored schemas come from https://agent-plugins.org/schemas/1.0.0/ and are checked offline. Host compatibility still needs native installation/OAuth evidence; schema validation alone is insufficient.

## Releases and updates

Change canonical sources, bump the semantic version, update CHANGELOG.md, regenerate, validate, and review the diff. Tag approved release commits as `integration-v<version>`. Publish a prerelease until live client/data acceptance passes. Frontend setup pins the reviewed commit; installed packages update only through the host's explicit marketplace/plugin update flow. Do not move existing release tags or silently upgrade pinned installs. Roll back by selecting a prior reviewed revision; leave account grants and usage records intact.

## Legacy compatibility and service ownership

The root `brain/`, trading/wallet skills and `skills_manifest.yaml` retain their existing paths and behavior. Do not bundle them into the new integration. `GigabrainGG/agent-skills` is a legacy API-key documentation source, not a second source for this package; existing links remain valid. New website setup points here. Legacy research users migrate by explicitly installing the new package and authorizing OAuth; do not delete or overwrite their old configuration automatically.

NestJS owns public authentication, entitlement and shared quotas. Python owns `asset-context.v3`, existing policy adapters, provider data and deterministic calculations. Next.js owns Connect and account consent. This package owns workflow instructions and host-specific metadata only. Production activation requires working provider entitlement, subscriber/holder checks and supported native-client acceptance; packaging does not waive those gates. The production Claude public client ID in config is the intended registration contract, not evidence that it is registered or active.
