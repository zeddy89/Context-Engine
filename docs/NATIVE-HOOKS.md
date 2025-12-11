# Native Hooks Mode

Context management inside Claude Code using native hooks. No external wrapper needed.

## Overview

Native Hooks mode uses Claude Code's hook system to:
- Inject compiled context on session start/resume
- Save snapshots before compaction
- Restore context after `/clear` or `/compact`
- Track progress and activity metrics

This is ideal for **interactive** Claude Code sessions where you want context to persist without running the full autonomous loop.

## Requirements

- Claude Code 1.0.17+ (tested on 2.0.65)
- Python 3.8+
- Linux/macOS (Windows users: use WSL)

## Installation

```bash
cd ~/projects/your-project
~/tools/context-engine/setup-native-hooks.sh
```

The script will:
1. Check your Python and Claude Code versions
2. Create `.agent/` directory structure (if not present)
3. Create `.claude/hooks/` with the hook scripts
4. Update `.claude/settings.json` with hook configuration
5. Create `.agent/commands.sh` helper

**Important:** After setup, run `/hooks` in Claude Code to review and approve the hooks. Hooks won't run until approved.

## Directory Structure

```
your-project/
├── .agent/
│   ├── memory/
│   │   ├── failures/       # What NOT to repeat
│   │   ├── strategies/     # What worked
│   │   └── constraints/    # Project rules
│   ├── working-context/    # Compiled context
│   ├── sessions/
│   │   ├── snapshots/      # Pre-compact snapshots
│   │   ├── activity.jsonl  # Tool usage log
│   │   └── compact-log.jsonl
│   ├── metrics/
│   │   └── session-metrics.jsonl
│   └── commands.sh         # Helper commands
├── .claude/
│   ├── settings.json       # Hook configuration
│   └── hooks/
│       ├── session-start.py
│       ├── pre-compact.py
│       ├── stop.py
│       └── post-tool-use.py
└── feature_list.json       # Optional: task tracking
```

## Hooks

### SessionStart

**Fires:** When Claude Code starts, resumes, or after `/clear`

**What it does:**
- Compiles context from memory layers
- Injects into Claude's context via `additionalContext`
- Shows token/char count in stderr

**Priority-based truncation:** If context exceeds 6000 chars, sections are removed in order:
1. Strategies (lowest priority)
2. Failures
3. Constraints
4. Commands
5. Current task (highest priority, never removed)

### PreCompact

**Fires:** Before `/compact` (manual or auto)

**What it does:**
- Saves snapshot to `.agent/sessions/snapshots/`
- Logs compaction event
- Keeps last 10 snapshots (cleans up older ones)

### Stop

**Fires:** When Claude finishes responding

**What it does:**
- Logs progress metrics
- Shows feature progress in stderr
- Optionally auto-completes features (write mode)

**Read-only by default.** Enable write mode:
```bash
export CONTEXT_ENGINE_WRITE_MODE=1
```

### PostToolUse

**Fires:** After Claude uses Write, Edit, or MultiEdit

**What it does:**
- Logs file changes to `.agent/sessions/activity.jsonl`
- Read-only (no linting by default)

## Commands

Helper script for common operations:

```bash
# See what NOT to repeat
.agent/commands.sh recall failures

# Mark feature complete
.agent/commands.sh success feat-001 "Implemented login flow"

# Record a failure
.agent/commands.sh failure feat-002 "API rate limiting not handled"

# Check progress
.agent/commands.sh status

# Manually compile context
.agent/commands.sh compile
```

## Feature Tracking

Create `feature_list.json` to track tasks:

```json
{
  "features": [
    {
      "id": "feat-001",
      "name": "User Authentication",
      "description": "Implement login/logout with JWT",
      "priority": 1,
      "passes": false
    },
    {
      "id": "feat-002",
      "name": "Dashboard UI",
      "description": "Create main dashboard layout",
      "priority": 2,
      "dependencies": ["feat-001"],
      "passes": false
    }
  ]
}
```

The SessionStart hook will show the next incomplete feature in the injected context.

## Memory Management

### Recording Failures

When something doesn't work:

```bash
.agent/commands.sh failure feat-001 "Circular import when using relative imports"
```

Or create a file directly:

```bash
echo "# Failure: circular-import
Don't use relative imports between api/ and core/ modules.
Use absolute imports instead." > .agent/memory/failures/$(date +%Y%m%d-%H%M%S).md
```

### Recording Strategies

When something works well:

```bash
.agent/commands.sh success feat-001 "Used dependency injection for testability"
```

### Adding Constraints

For project-wide rules:

```bash
echo "# Constraint: Testing
All new functions must have unit tests.
Use pytest fixtures for database setup." > .agent/memory/constraints/testing.md
```

## Windows/WSL

Native hooks require bash. Windows users should use WSL:

```powershell
# Install WSL (PowerShell as Administrator)
wsl --install

# Restart computer, then open Ubuntu from Start menu

# Navigate to your project
cd /mnt/c/Users/YourName/projects/your-project

# Run setup
~/tools/context-engine/setup-native-hooks.sh
```

## Troubleshooting

### Hooks not firing

1. Check if hooks are approved: run `/hooks` in Claude Code
2. Verify settings.json exists: `cat .claude/settings.json`
3. Check Claude Code version: `claude --version` (need 1.0.17+)

### Context not appearing

1. Check stderr output for `📋 Context injected`
2. Verify hook script is executable: `ls -la .claude/hooks/`
3. Test hook manually:
   ```bash
   echo '{"source": "startup"}' | python3 .claude/hooks/session-start.py
   ```

### Context too large

The hook automatically truncates to 6000 chars using priority-based removal. If you need more control:

1. Clean up old failures: `rm .agent/memory/failures/old-*.md`
2. Consolidate strategies
3. Keep constraints concise

### Settings merge issues

If you had existing hooks that got overwritten:

1. Check backup: `ls .claude/settings.json.bak`
2. The script deduplicates on re-run (won't add duplicate hooks)

## Comparison with Autonomous Loop

| Feature | Native Hooks | Autonomous Loop |
|---------|--------------|-----------------|
| Human interaction | Interactive | Unattended |
| Context persistence | Yes (via hooks) | Yes (via loop-runner) |
| Test enforcement | Manual | Automatic |
| Feature progression | Manual | Automatic |
| Use case | Daily coding | "Build overnight" |

**Use both together:**
- Native hooks for interactive work during the day
- Autonomous loop for overnight builds

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTEXT_ENGINE_WRITE_MODE` | `0` | Set to `1` to enable auto-completing features |
| `CONTEXT_ENGINE_LINT` | `0` | Set to `1` to enable linting in PostToolUse (not implemented) |

## Security Notes

- All hooks are read-only by default
- No network requests from hooks
- Hooks run with your user permissions
- Review hooks with `/hooks` before approving
