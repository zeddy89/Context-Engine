# Context Engine

**Autonomous project builder for Claude Code that doesn't forget what it's doing.**

Built 46 features for a Rust API server without human intervention. No degradation. No loops. No "I've lost track of what we're building."

## The Problem

AI coding agents degrade over long sessions. Context windows fill with stale information, the model loses track of decisions, and you end up babysitting what should be autonomous work.

This happens because most agent setups treat context like a pile - just keep adding until it breaks.

## The Solution

Context Engine uses a **four-layer memory architecture** based on research from Google, Stanford, and Anthropic:

| Layer | Purpose | Lifecycle |
|-------|---------|-----------|
| **Working Context** | Current task only | Rebuilt each session |
| **Episodic Memory** | Recent decisions, patterns | Rolling window |
| **Semantic Memory** | Project knowledge, architecture | Persistent |
| **Procedural Memory** | What worked, what failed | Append-only |

Each session starts fresh with computed context instead of accumulated garbage.

## Results

**RustSat** - A Rust API for Linux patch management:
- 46 features implemented
- 42 sessions
- Fully autonomous (no human intervention after init)
- Zero context degradation

The loop ran overnight. Each session: compile context → implement feature → run tests → commit → exit. Repeat until done.

## Quick Start

```bash
# Clone
git clone https://github.com/yourusername/context-engine.git
cd context-engine

# Install (just copies scripts)
./install.sh

# Create a new project
python3 ~/tools/context-engine/orchestrator.py --new ~/projects/my-app --model opus

# Or run fully autonomous after init
~/tools/context-engine/loop-runner.py ~/projects/my-app --model opus
```

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI installed
- Python 3.10+
- Git

## Usage

### Interactive Mode (Recommended for New Projects)

```bash
python3 orchestrator.py --new ~/projects/my-app --model opus --mcp-preset rust
```

Walks you through:
1. Project name and path
2. Tech stack selection
3. Project description
4. Initializes with context-engineered harness
5. Creates `feature_list.json` with atomic features

### Autonomous Mode (Set and Forget)

After initialization:

```bash
./loop-runner.py ~/projects/my-app --model opus
```

This will:
1. Pick the next incomplete feature
2. Compile fresh context
3. Run Claude Code session
4. Verify tests pass
5. Commit and repeat

Stop it anytime with Ctrl+C. Resume later - it picks up where it left off.

### Continue Existing Project

```bash
python3 orchestrator.py --project ~/projects/my-app --model opus
```

### Check Status

```bash
python3 orchestrator.py --status --project ~/projects/my-app
```

## MCP Integration (Optional)

Model Context Protocol servers give Claude access to databases, documentation, and more during sessions.

### Presets

```bash
# Rust development (includes Ref docs)
--mcp-preset rust

# Python development
--mcp-preset python

# Web development (filesystem + fetch + postgres)
--mcp-preset web

# Full-stack
--mcp-preset fullstack

# DevOps (kubernetes + docker)
--mcp-preset devops
```

### Interactive MCP Setup

```bash
python3 mcp-setup.py
```

### Add Specific MCPs

```bash
# Known MCP
python3 mcp-setup.py --add postgres

# From GitHub
python3 mcp-setup.py --add "github.com/anthropics/mcp-server-sqlite"

# From claude command
python3 mcp-setup.py --add "claude mcp add --transport http Ref https://api.ref.tools/mcp"
```

## How It Works

### Project Structure

After initialization, your project gets:

```
my-app/
├── .agent/
│   ├── AGENT_RULES.md        # Memory model instructions
│   ├── working-context/      # Rebuilt each session
│   ├── memory/               # Persistent knowledge
│   ├── artifacts/            # Large outputs by reference
│   ├── hooks/                # Context compilation scripts
│   └── workflows/            # Init, implement, debug workflows
├── .claude/
│   └── agents/               # Subagents (code-reviewer, test-runner)
├── feature_list.json         # Atomic features with status
├── mcp-config.json           # MCP server configuration
└── CLAUDE.md                 # Instructions for Claude Code
```

### Session Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Session Start                                               │
├─────────────────────────────────────────────────────────────┤
│ 1. Compile fresh working context                            │
│    └─ Pull relevant memory, not everything                  │
│ 2. Check failure log                                        │
│    └─ Don't repeat past mistakes                            │
│ 3. Implement single feature                                 │
│ 4. Run tests (mandatory)                                    │
│ 5. Subagent review (@code-reviewer, @test-runner)           │
│ 6. Update feature_list.json                                 │
│ 7. Commit with "session: completed {feature_id}"            │
│ 8. Exit cleanly                                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    Loop runner starts next session
```

### Feature List

Features are defined in `feature_list.json`:

```json
{
  "features": [
    {
      "id": "F001",
      "description": "Project scaffold with Cargo.toml",
      "priority": 1,
      "passes": true
    },
    {
      "id": "F002", 
      "description": "Database connection pool",
      "priority": 2,
      "dependencies": ["F001"],
      "passes": false
    }
  ]
}
```

The loop runner:
- Respects dependencies
- Skips completed features
- Marks blocked features after repeated failures
- Syncs with git history (recovers from missed updates)

## Configuration

### Models

```bash
--model sonnet    # Faster, good for most features (default)
--model opus      # Better for complex architecture decisions
```

### Flags

| Flag | Description |
|------|-------------|
| `--new PATH` | Create new project at path |
| `--project PATH` | Continue existing project |
| `--model MODEL` | sonnet or opus |
| `--mcp-preset NAME` | Use MCP preset |
| `--mcp-config FILE` | Custom MCP config |
| `--mcp` | Interactive MCP setup |
| `--debug` | Show debug output |
| `--status` | Show project status |

## Subagents

The harness includes specialized subagents:

| Agent | Purpose |
|-------|---------|
| `@code-reviewer` | Reviews changes for issues |
| `@test-runner` | Runs tests and analyzes failures |
| `@feature-verifier` | End-to-end feature verification |
| `@debugger` | Analyzes errors and suggests fixes |

Claude Code invokes these automatically during implementation.

## Troubleshooting

### "feature_list.json not created"

The init session didn't complete properly. Run:

```bash
cd ~/projects/my-app
claude --model opus -p "Read .agent/workflows/init.md and create feature_list.json"
```

### Features completed but not marked

The harness auto-syncs with git history. If a commit says "session: completed F003" but `feature_list.json` shows `passes: false`, the next loop iteration fixes it.

Manual fix:

```bash
cd ~/projects/my-app
python3 -c "
import json, subprocess
with open('feature_list.json') as f: data = json.load(f)
for feat in data['features']:
    fid = feat.get('id', '')
    r = subprocess.run(['git', 'log', '--oneline', '--grep', f'session: completed {fid}'], capture_output=True, text=True)
    if r.stdout.strip() and not feat.get('passes'):
        print(f'Fixing {fid}')
        feat['passes'] = True
with open('feature_list.json', 'w') as f: json.dump(data, f, indent=2)
"
```

### MCP config not found

Ensure absolute paths:

```bash
# Check config exists
cat ~/projects/my-app/mcp-config.json

# Run with explicit path
./loop-runner.py ~/projects/my-app --mcp-config ~/projects/my-app/mcp-config.json
```

### Tests not running

The harness enforces tests, but Claude might skip them. Check:

1. Test framework is set up (cargo test / pytest / npm test works manually)
2. CLAUDE.md mentions test requirements
3. Run with `--debug` to see what's happening

## Architecture Deep Dive

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full explanation of:

- Four-layer memory model
- Context compilation algorithm  
- Artifact reference system
- Feedback capture loop

## Contributing

Issues and PRs welcome. This is actively developed.

Key areas:
- More MCP integrations
- Better test enforcement
- Support for other AI coding tools (Cursor, Aider, etc.)
- Parallel feature implementation

## License

MIT

## Acknowledgments

- Research foundation from Google's MemGPT, Stanford's Generative Agents, and Anthropic's context management papers
- Built for use with [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
