import importlib.util
import json
from pathlib import Path
import re
import unittest

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build", ROOT / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class Packages(unittest.TestCase):
    def test_committed_artifacts_are_reproducible_and_contained(self):
        expected = build.render()
        actual = {p.relative_to(ROOT.parent) for p in (ROOT.parent / "plugins").rglob("*") if p.is_file()}
        self.assertEqual(actual, {p for p in expected if p.parts[0] == "plugins"})
        for relative, content in expected.items():
            target = ROOT.parent / relative
            self.assertFalse(target.is_symlink())
            self.assertEqual(target.read_text(), content, str(relative))
            self.assertNotRegex(content, r"@(PLUGIN|LABEL|VERSION|ORIGIN|MCP_URL|CLAUDE_CLIENT_ID|AVAILABILITY)@")

    def test_manifests_validate_against_official_portable_schemas(self):
        for folder in (ROOT.parent / "plugins").iterdir():
            for kind in ("plugin", "mcp"):
                schema = json.loads((ROOT / "schemas" / f"{kind}.schema.json").read_text())
                value = json.loads((folder / f"{kind}.json").read_text())
                jsonschema.Draft202012Validator.check_schema(schema)
                jsonschema.validate(value, schema)

    def test_only_expected_skills_and_remote_oauth_are_shipped(self):
        config = json.loads((ROOT / "config.json").read_text())
        for env in config["environments"].values():
            folder = ROOT.parent / "plugins" / env["name"]
            skills = sorted(p.name for p in (folder / "skills").iterdir())
            self.assertEqual(skills, ["asset-briefing", "setup", "trade-thesis-review"])
            for name in skills:
                text = (folder / "skills" / name / "SKILL.md").read_text()
                frontmatter = yaml.safe_load(text.split("---", 2)[1])
                self.assertEqual(frontmatter["name"], name)
                self.assertTrue(frontmatter["description"])
                for link in re.findall(r"\]\(([^)]+)\)", text):
                    if "://" not in link:
                        target = (folder / "skills" / name / link).resolve()
                        self.assertTrue(target.is_relative_to(folder.resolve()))
                        self.assertTrue(target.is_file(), str(target))
            portable = json.loads((folder / "mcp.json").read_text())["mcpServers"]
            claude = json.loads((folder / ".mcp.json").read_text())["mcpServers"]
            self.assertEqual(list(portable), [env["name"]])
            self.assertEqual(list(claude), [env["name"]])
            remote = portable[env["name"]]
            self.assertEqual(set(remote), {"type", "url"})
            self.assertEqual(remote["type"], "streamable-http")
            self.assertEqual(remote["url"], env["mcp"])
            self.assertEqual(claude[env["name"]], {"type": "http", "url": env["mcp"], "oauth": {"clientId": env["claudeClientId"]}})
            self.assertFalse(any(p.suffix in {".py", ".js", ".sh", ".env"} for p in folder.rglob("*")))
            manifest = json.loads((folder / "plugin.json").read_text())
            onboarding = manifest["extensions"]["com.openai"]["onboardingSkill"]
            self.assertTrue((folder / onboarding).is_file())
            self.assertEqual(manifest["version"], config["version"])
            self.assertNotIn("hooks", manifest)

    def test_marketplaces_point_to_the_same_reviewed_packages(self):
        portable = json.loads((ROOT.parent / ".agents/plugins/marketplace.json").read_text())
        claude = json.loads((ROOT.parent / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(portable["name"], claude["name"])
        self.assertEqual({p["name"] for p in portable["plugins"]}, {p["name"] for p in claude["plugins"]})
        for entry in portable["plugins"]:
            path = entry["source"]["path"]
            self.assertEqual(path, next(p["source"] for p in claude["plugins"] if p["name"] == entry["name"]))
            self.assertTrue(path.startswith("./plugins/"))
            self.assertTrue((ROOT.parent / path / "plugin.json").is_file())
            self.assertEqual(entry["policy"]["installation"], "AVAILABLE")

    def test_production_package_contains_no_staging_references(self):
        config = json.loads((ROOT / "config.json").read_text())
        for env in config["environments"].values():
            if "staging" in env["name"]:
                continue
            for path in (ROOT.parent / "plugins" / env["name"]).rglob("*"):
                if path.is_file():
                    self.assertNotIn("staging", path.read_text().lower(), str(path))


if __name__ == "__main__":
    unittest.main()
