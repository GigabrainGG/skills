# Gigabrain market-context integration

Canonical source for the Gigabrain plugin: setup, asset briefing and trade-thesis review skills plus a remote OAuth MCP connection. It contains no local service, credentials, model runtime, trading tools or wallet skills. Gigabrain fetches evidence and performs deterministic calculations; the user's agent does the reasoning. MIT applies to this directory and its generated packages under `plugins/`.

## Install

Use the [Connect page](https://gigabrain.gg/connect). Its setup guide installs `gigabrain@gigabrain` from `main`. The package targets the public `asset-context.v3` contract.

## Build and validate

```sh
python3 -m pip install -r integration/requirements-dev.txt
python3 integration/build.py
python3 integration/build.py --check
python3 -m unittest discover -s integration/tests -v
```

`integration/config.json`, the three skill folders and the shared `context.md` generate both the portable Agent Plugins manifests and the Claude manifests and marketplaces. Generated files are committed so hosts can install directly; do not edit `plugins/` by hand. Validation checks reproducibility, the pinned official schemas, package contents, manifest paths and absence of credentials or local execution hooks. CI also runs Claude's native plugin validator. Vendored schemas come from https://agent-plugins.org/schemas/1.0.0/ and are checked offline; schema validation does not replace a real install and OAuth test on each host.

## Releases and updates

Change the canonical sources, bump the version, update CHANGELOG.md, regenerate, validate and review the diff. Tag approved release commits as `integration-v<version>` and never move an existing tag. Merging to `main` publishes the release; installed packages pick it up through the host's marketplace update. Roll back by reverting on `main`.

## Staging

`main` ships only the production package. The `staging` branch carries a `config.json` with only the staging environment, which generates `gigabrain-staging@gigabrain` for `staging-api.gigabrain.gg`; `staging.gigabrain.gg/connect` installs from that branch. To update it, merge `main` into `staging`, keep the staging `config.json`, run `python3 integration/build.py` and commit the regenerated packages.
