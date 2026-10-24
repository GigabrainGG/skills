#!/usr/bin/env python3
"""Generate both host formats from one reviewed source; no network or credentials."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "integration"


def encoded(value):
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def render():
    config = json.loads((SOURCE / "config.json").read_text())
    files, codex_entries, claude_entries = {}, [], []
    for env in config["environments"].values():
        name = env["name"]
        folder = Path("plugins") / name
        replacements = {
            "@PLUGIN@": name, "@LABEL@": env["label"], "@VERSION@": config["version"],
            "@ORIGIN@": env["origin"], "@MCP_URL@": env["mcp"], "@BRANCH@": env["branch"],
            "@CLAUDE_CLIENT_ID@": env["claudeClientId"], "@AVAILABILITY@": env["availability"],
        }
        def expand(text):
            for old, new in replacements.items():
                text = text.replace(old, new)
            return text
        identity = {
            "name": name, "version": config["version"],
            "description": f"{env['label']} read-only BTC/ETH market context for your AI agent, with browser OAuth.",
            "author": {"name": "Gigabrain", "url": "https://gigabrain.gg"},
            "homepage": env["origin"] + "/connect", "repository": config["repository"], "license": "MIT",
        }
        files[folder / "plugin.json"] = encoded({
            "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", **identity,
            "extensions": {"com.openai": {
                "onboardingSkill": "./skills/setup/SKILL.md",
                "interface": {"displayName": env["label"], "shortDescription": "Market context for your AI agent", "category": "Productivity", "capabilities": ["Read"]},
            }},
        })
        files[folder / "mcp.json"] = encoded({
            "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
            # OAuth is discovered from the protected-resource challenge. The
            # portable 1.0 schema does not accept host-specific auth extensions.
            "mcpServers": {name: {"type": "streamable-http", "url": env["mcp"]}},
        })
        files[folder / ".claude-plugin/plugin.json"] = encoded(identity)
        files[folder / ".mcp.json"] = encoded({"mcpServers": {name: {
            "type": "http", "url": env["mcp"], "oauth": {"clientId": env["claudeClientId"]},
        }}})
        files[folder / "LICENSE"] = (SOURCE / "LICENSE").read_text()
        for path in sorted((SOURCE / "skills").rglob("*")):
            if path.is_file():
                files[folder / "skills" / path.relative_to(SOURCE / "skills")] = expand(path.read_text())
        for skill in ("asset-briefing", "setup", "trade-thesis-review"):
            files[folder / "skills" / skill / "references/context.md"] = expand((SOURCE / "context.md").read_text())
        codex_entries.append({"name": name, "source": {"source": "local", "path": "./" + str(folder)},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Productivity"})
        claude_entries.append({"name": name, "source": "./" + str(folder), "description": identity["description"]})
    files[Path(".agents/plugins/marketplace.json")] = encoded({"name": config["marketplace"],
        "interface": {"displayName": "Gigabrain"}, "plugins": codex_entries})
    files[Path(".claude-plugin/marketplace.json")] = encoded({"name": config["marketplace"],
        "owner": {"name": "Gigabrain"}, "metadata": {"description": "Market intelligence for your AI agents"}, "plugins": claude_entries})
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail on changed, missing or unexpected package files")
    args = parser.parse_args()
    expected = render()
    actual = {p.relative_to(ROOT) for p in (ROOT / "plugins").rglob("*") if p.is_file()}
    extra = actual - set(expected)
    if extra:
        raise SystemExit("Unexpected package files (review before removing): " + ", ".join(map(str, sorted(extra))))
    changed = []
    for relative, content in expected.items():
        target = ROOT / relative
        if not target.exists() or target.read_text() != content:
            changed.append(str(relative))
            if not args.check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
    if args.check and changed:
        raise SystemExit("Regenerate with python3 integration/build.py: " + ", ".join(changed))
    print(f"{'Checked' if args.check else 'Generated'} {len(expected)} package files")


if __name__ == "__main__":
    main()
