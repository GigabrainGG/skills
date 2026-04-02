# GigaBrain Agent Skills

Open-source skills for [GigaBrain](https://gigabrain.gg) agents. Compatible with the [Agent Skills](https://agentskills.io) open standard.

## Skills

| Skill | Description |
|---|---|
| `hyperliquid` | Trade perps, spot, and transfer USDC on HyperLiquid |
| `polymarket` | Trade prediction markets on Polymarket |
| `polymarket-deep-research` | Read-only thesis building and market research for Polymarket |
| `brain` | Primary Brain market intelligence stack for macro, microstructure, fundamentals, sentiment, and Polymarket context |
| `portfolio-tracker` | Portfolio overview and P&L tracking |

## How It Works

GigaBrain agents automatically sync skills from this repo. Each skill is a folder with:

- `SKILL.md` — Instructions the agent follows (YAML frontmatter + markdown)
- `scripts/` — Executable scripts (Python, Node, shell — any language)
- `references/` — Additional documentation the agent can read on demand

Scripts declare their own dependencies via [PEP 723](https://peps.python.org/pep-0723/) inline metadata and run in isolated environments via `uv run`. No dependency conflicts between skills.

## Contributing

1. Create a folder with your skill name
2. Add a `SKILL.md` with YAML frontmatter (`name`, `description`, `license`)
3. Add scripts in `scripts/` with inline dependency metadata
4. Open a PR

See any existing skill for the format.

## Using in Other Agents

These skills follow the Agent Skills standard and work with any compatible agent platform — OpenClaw, Claude Code, Cursor, and others.
