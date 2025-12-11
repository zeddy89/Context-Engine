#!/bin/bash
# ============================================================================
# Context Engine: Native Claude Code Hooks Mode
# ============================================================================
# 
# This sets up context management INSIDE Claude Code using native hooks.
# No external wrapper needed - works with /clear, /compact, and session resume.
#
# REQUIREMENTS:
#   - Claude Code 1.0.17+ (with SessionStart, PreCompact, Stop, PostToolUse hooks)
#   - Python 3.8+
#   - Linux/macOS (Windows users: use WSL)
#
# Usage:
#   cd ~/projects/myapp
#   ~/tools/context-engine/setup-native-hooks.sh
#
# After setup:
#   1. Run /hooks in Claude Code to review and approve the hooks
#   2. Hooks won't run until approved
#   3. Use Claude Code normally - context auto-restores on /clear, /compact, resume
#
# Directory structure (consistent with setup-context-engineered.sh):
#   .agent/
#   ├── memory/
#   │   ├── failures/       # What NOT to repeat
#   │   ├── strategies/     # What worked
#   │   └── constraints/    # Project rules
#   ├── working-context/    # Compiled context
#   ├── sessions/           # Snapshots, logs
#   └── metrics/            # Usage tracking
#   .claude/
#   ├── settings.json       # Hook configuration
#   └── hooks/              # Hook scripts
#
# Windows/WSL Quick Start:
#   1. Install WSL: wsl --install
#   2. Open WSL terminal: wsl
#   3. Navigate to project: cd /mnt/c/Users/YourName/projects/myapp
#   4. Run this script: ~/tools/context-engine/setup-native-hooks.sh
#
# ============================================================================

set -e

# Version info
SCRIPT_VERSION="3.1.0"
MIN_CLAUDE_VERSION="1.0.17"

echo "🔧 Context Engine: Native Hooks Mode v${SCRIPT_VERSION}"
echo "======================================================="
echo ""

# Platform check with WSL instructions
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    echo "❌ Windows detected. Please use WSL (Windows Subsystem for Linux)."
    echo ""
    echo "   Quick setup:"
    echo "   1. Open PowerShell as Administrator"
    echo "   2. Run: wsl --install"
    echo "   3. Restart your computer"
    echo "   4. Open 'Ubuntu' from Start menu"
    echo "   5. Navigate to your project:"
    echo "      cd /mnt/c/Users/\$USER/path/to/project"
    echo "   6. Run this script again"
    echo ""
    echo "   More info: https://learn.microsoft.com/en-us/windows/wsl/install"
    exit 1
fi

# Python check
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.8+."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    echo "❌ Python 3.8+ required. Found: Python $PYTHON_VERSION"
    exit 1
fi

# Claude Code version check (graceful - warn but don't block)
check_claude_version() {
    if command -v claude &> /dev/null; then
        CLAUDE_VERSION=$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        if [ -n "$CLAUDE_VERSION" ]; then
            echo "   Claude Code version: $CLAUDE_VERSION"
            
            # Parse version numbers
            MAJOR=$(echo "$CLAUDE_VERSION" | cut -d. -f1)
            MINOR=$(echo "$CLAUDE_VERSION" | cut -d. -f2)
            PATCH=$(echo "$CLAUDE_VERSION" | cut -d. -f3)
            
            MIN_MAJOR=$(echo "$MIN_CLAUDE_VERSION" | cut -d. -f1)
            MIN_MINOR=$(echo "$MIN_CLAUDE_VERSION" | cut -d. -f2)
            MIN_PATCH=$(echo "$MIN_CLAUDE_VERSION" | cut -d. -f3)
            
            # Version comparison
            if [ "$MAJOR" -lt "$MIN_MAJOR" ] || \
               ([ "$MAJOR" -eq "$MIN_MAJOR" ] && [ "$MINOR" -lt "$MIN_MINOR" ]) || \
               ([ "$MAJOR" -eq "$MIN_MAJOR" ] && [ "$MINOR" -eq "$MIN_MINOR" ] && [ "$PATCH" -lt "$MIN_PATCH" ]); then
                echo ""
                echo "⚠️  WARNING: Claude Code $CLAUDE_VERSION may not support all hook features."
                echo "   Minimum recommended: $MIN_CLAUDE_VERSION"
                echo "   SessionStart/PreCompact hooks were added in 1.0.17."
                echo ""
                echo "   Update with: npm update -g @anthropic-ai/claude-code"
                echo ""
                read -p "   Continue anyway? [y/N]: " choice
                if [ "$choice" != "y" ] && [ "$choice" != "Y" ]; then
                    echo "   Aborting. Please update Claude Code first."
                    exit 1
                fi
            fi
        fi
    else
        echo "   ⚠️  Claude Code not found in PATH (will verify hooks work after install)"
    fi
}

echo "🔍 Checking requirements..."
echo "   Python version: $PYTHON_VERSION ✓"
check_claude_version
echo ""

# Check if .agent exists (from full setup)
if [ ! -d ".agent" ]; then
    echo "⚠️  No .agent directory found."
    echo "   Run setup-context-engineered.sh first, or continue for standalone hooks."
    read -p "   Continue with standalone hooks? [y/N]: " choice
    if [ "$choice" != "y" ] && [ "$choice" != "Y" ]; then
        exit 1
    fi
    
    # Create minimal .agent structure (consistent with setup-context-engineered.sh)
    mkdir -p .agent/memory/{failures,strategies,constraints}
    mkdir -p .agent/working-context
    mkdir -p .agent/sessions/snapshots
    mkdir -p .agent/metrics
fi

# Create .claude/hooks directory
mkdir -p .claude/hooks

echo "📝 Creating hook scripts..."

# ============================================================================
# SessionStart Hook - Injects compiled context
# ============================================================================
cat > .claude/hooks/session-start.py << 'PYTHON'
#!/usr/bin/env python3
"""
SessionStart Hook - Injects compiled context into Claude's window.

Fires when:
- Claude Code starts a new session
- Claude Code resumes an existing session
- After /clear command

Outputs additionalContext that gets injected into Claude's context.

IMPORTANT: This hook is READ-ONLY. It only reads from .agent/ and outputs context.
It does not modify files or make network requests.

Requires: Claude Code 1.0.17+ (with SessionStart hook support)
"""

import json
import sys
import os
from pathlib import Path

# ============================================================================
# Configuration
# ============================================================================

# Maximum characters for additionalContext to prevent silent truncation
# Claude Code's limit is ~10k chars; we stay well under
MAX_CONTEXT_CHARS = 6000

# Section priorities for truncation (higher = keep longer)
# When over budget, we trim lowest priority sections first
SECTION_PRIORITIES = {
    "header": 100,        # Always keep
    "current_task": 90,   # Critical - what to work on
    "constraints": 80,    # Important - project rules
    "failures": 70,       # Important - don't repeat mistakes
    "strategies": 60,     # Helpful but expendable
    "commands": 50,       # Reference - can be abbreviated
}

# Maximum items to include from each memory category
MAX_FAILURES = 3
MAX_STRATEGIES = 2
MAX_CONSTRAINTS = 3

# Truncation limits per item
FAILURE_CHAR_LIMIT = 400
STRATEGY_CHAR_LIMIT = 300
CONSTRAINT_CHAR_LIMIT = 200

def estimate_tokens(text):
    """Rough token estimate (1.3 tokens per word)."""
    return int(len(text.split()) * 1.3)

def build_section(name, content):
    """Build a section with metadata for priority-based truncation."""
    return {
        "name": name,
        "priority": SECTION_PRIORITIES.get(name, 0),
        "content": content,
        "size": len(content)
    }

def truncate_by_priority(sections, max_chars):
    """
    Truncate sections by priority to fit within max_chars.
    
    Strategy: Remove lowest-priority sections first, then truncate
    remaining sections if still over budget.
    """
    # Sort by priority (lowest first for removal)
    sorted_sections = sorted(sections, key=lambda s: s["priority"])
    
    total_size = sum(s["size"] for s in sections)
    
    # Remove lowest-priority sections until under budget
    while total_size > max_chars and sorted_sections:
        # Check if removing the lowest priority section helps
        lowest = sorted_sections[0]
        if lowest["priority"] < 80:  # Don't remove critical sections
            sorted_sections.pop(0)
            total_size -= lowest["size"]
        else:
            break
    
    # If still over, truncate the remaining sections proportionally
    if total_size > max_chars:
        ratio = max_chars / total_size
        for section in sorted_sections:
            max_section_size = int(section["size"] * ratio * 0.9)  # 10% safety margin
            if len(section["content"]) > max_section_size:
                # Truncate at a clean line break
                truncated = section["content"][:max_section_size]
                last_newline = truncated.rfind("\n")
                if last_newline > max_section_size // 2:
                    truncated = truncated[:last_newline]
                section["content"] = truncated + "\n[...truncated]"
    
    # Reassemble in original priority order (highest first for output)
    sorted_sections.sort(key=lambda s: s["priority"], reverse=True)
    return "\n\n".join(s["content"] for s in sorted_sections if s["content"].strip())

def compile_context():
    """
    Compile fresh context from memory layers.
    
    Cache-stable: No timestamps or random values at the top.
    Size-capped: Uses priority-based truncation to stay under MAX_CONTEXT_CHARS.
    """
    sections = []
    
    # Header (highest priority - always keep)
    sections.append(build_section("header", "# Project Context"))
    
    # Current task from feature_list.json (critical)
    feature_file = Path("feature_list.json")
    if feature_file.exists():
        try:
            with open(feature_file) as f:
                data = json.load(f)
            
            features = data.get("features", [])
            completed = sum(1 for f in features if f.get("passes", False))
            total = len(features)
            
            # Find next incomplete feature (respecting dependencies)
            completed_ids = {f.get("id") for f in features if f.get("passes", False)}
            
            for feat in sorted(features, key=lambda x: x.get("priority", 99)):
                if feat.get("passes", False) or feat.get("blocked", False):
                    continue
                # Check dependencies
                deps = feat.get("dependencies", [])
                if all(d in completed_ids for d in deps):
                    task_content = f"""## Current Task
Progress: {completed}/{total} features complete
**{feat.get('id')}**: {feat.get('name')}
Description: {feat.get('description', '')[:300]}"""
                    sections.append(build_section("current_task", task_content))
                    break
        except Exception:
            pass
    
    # Active constraints (high priority)
    constraints_dir = Path(".agent/memory/constraints")
    if constraints_dir.exists():
        constraint_files = list(constraints_dir.glob("*.md"))[:MAX_CONSTRAINTS]
        if constraint_files:
            constraint_parts = ["## Constraints"]
            for c in constraint_files:
                try:
                    content = c.read_text()[:CONSTRAINT_CHAR_LIMIT]
                    constraint_parts.append(content.strip())
                except Exception:
                    pass
            if len(constraint_parts) > 1:
                sections.append(build_section("constraints", "\n".join(constraint_parts)))
    
    # Recent failures (important - don't repeat mistakes)
    failures_dir = Path(".agent/memory/failures")
    if failures_dir.exists():
        failure_files = sorted(
            failures_dir.glob("*.md"), 
            key=lambda x: x.stat().st_mtime, 
            reverse=True
        )[:MAX_FAILURES]
        
        if failure_files:
            failure_parts = ["## Known Failures (Don't Repeat)"]
            for f in failure_files:
                try:
                    content = f.read_text()[:FAILURE_CHAR_LIMIT]
                    failure_parts.append(content.strip())
                except Exception:
                    pass
            if len(failure_parts) > 1:
                sections.append(build_section("failures", "\n".join(failure_parts)))
    
    # Working strategies (helpful but expendable)
    strategies_dir = Path(".agent/memory/strategies")
    if strategies_dir.exists():
        strategy_files = sorted(
            strategies_dir.glob("*.md"), 
            key=lambda x: x.stat().st_mtime, 
            reverse=True
        )[:MAX_STRATEGIES]
        
        if strategy_files:
            strategy_parts = ["## Working Strategies"]
            for s in strategy_files:
                try:
                    content = s.read_text()[:STRATEGY_CHAR_LIMIT]
                    strategy_parts.append(content.strip())
                except Exception:
                    pass
            if len(strategy_parts) > 1:
                sections.append(build_section("strategies", "\n".join(strategy_parts)))
    
    # Quick reference (lowest priority - abbreviate if needed)
    commands_content = """## Commands
- `.agent/commands.sh recall failures` - See what NOT to do
- `.agent/commands.sh success <id> <msg>` - Mark feature complete
- `.agent/commands.sh failure <id> <msg>` - Record failure"""
    sections.append(build_section("commands", commands_content))
    
    # Apply priority-based truncation
    return truncate_by_priority(sections, MAX_CONTEXT_CHARS)

def main():
    """
    Main entry point for SessionStart hook.
    
    Reads input from Claude Code via stdin, outputs JSON to stdout.
    Errors go to stderr (shown to user but don't block).
    """
    try:
        # Read input from Claude Code
        input_data = json.load(sys.stdin)
        
        source = input_data.get("source", "unknown")  # startup, resume, or clear
        
        # Compile context (no source-specific prefixes for cache stability)
        context = compile_context()
        
        # Output in format Claude Code expects
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context
            }
        }
        
        print(json.dumps(output))
        
        # Info to stderr (optional, shown to user)
        tokens = estimate_tokens(context)
        print(f"📋 Context injected (~{tokens} tokens, {len(context)} chars)", file=sys.stderr)
        
    except Exception as e:
        # Don't crash - just output empty and log error
        print(json.dumps({}))
        print(f"⚠️ SessionStart hook error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
PYTHON
chmod +x .claude/hooks/session-start.py

# ============================================================================
# PreCompact Hook - Saves state before compaction
# ============================================================================
cat > .claude/hooks/pre-compact.py << 'PYTHON'
#!/usr/bin/env python3
"""
PreCompact Hook - Saves state before context compaction.

Fires when:
- User runs /compact
- Auto-compaction triggers (context too large)

Saves a snapshot so SessionStart can restore context.

IMPORTANT: This hook is READ-ONLY except for writing to .agent/sessions/.
It does not modify project files or make network requests.

Requires: Claude Code 1.0.17+ (with PreCompact hook support)
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Maximum snapshots to keep (older ones are cleaned up)
MAX_SNAPSHOTS = 10

# Maximum snapshot size in characters
MAX_SNAPSHOT_SIZE = 50000

def cleanup_old_snapshots(snapshot_dir):
    """
    Remove old snapshots, keeping only the most recent MAX_SNAPSHOTS.
    
    Snapshots are named pre-compact-YYYYMMDD-HHMMSS.md which sorts
    lexicographically by timestamp (newest = highest string value).
    """
    try:
        snapshots = list(snapshot_dir.glob("pre-compact-*.md"))
        
        # Sort by filename (lexicographic = chronological for our timestamp format)
        # Reverse to get newest first
        snapshots.sort(key=lambda p: p.name, reverse=True)
        
        # Delete everything beyond MAX_SNAPSHOTS
        for old in snapshots[MAX_SNAPSHOTS:]:
            try:
                old.unlink()
            except Exception:
                pass  # Ignore deletion failures
    except Exception:
        pass

def save_pre_compact_state():
    """Save current state before compaction."""
    
    # Create snapshot directory
    snapshot_dir = Path(".agent/sessions/snapshots")
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot_file = None
    
    # Save current working context if it exists
    current_context = Path(".agent/working-context/current.md")
    if current_context.exists():
        try:
            content = current_context.read_text()
            
            # Truncate if too large
            if len(content) > MAX_SNAPSHOT_SIZE:
                content = content[:MAX_SNAPSHOT_SIZE] + "\n\n[Truncated]"
            
            snapshot_file = snapshot_dir / f"pre-compact-{timestamp}.md"
            snapshot_file.write_text(content)
        except Exception:
            pass
    
    # Log the compaction event
    try:
        log_file = Path(".agent/sessions/compact-log.jsonl")
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "pre_compact",
            "snapshot": str(snapshot_file) if snapshot_file else None
        }
        
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass
    
    # Cleanup old snapshots
    cleanup_old_snapshots(snapshot_dir)
    
    return timestamp

def main():
    """
    Main entry point for PreCompact hook.
    
    PreCompact cannot block or inject context - it's informational only.
    """
    try:
        # Read input from Claude Code
        input_data = json.load(sys.stdin)
        
        trigger = input_data.get("trigger", "unknown")  # manual or auto
        
        # Save state
        timestamp = save_pre_compact_state()
        
        # Log to stderr (shown to user)
        print(f"💾 Context snapshot saved: pre-compact-{timestamp}.md", file=sys.stderr)
        
        if trigger == "auto":
            print("⚠️  Auto-compaction triggered (context was large)", file=sys.stderr)
        
    except Exception as e:
        print(f"⚠️ PreCompact hook error: {e}", file=sys.stderr)
    
    # PreCompact doesn't support additionalContext - output empty
    print(json.dumps({}))

if __name__ == "__main__":
    main()
PYTHON
chmod +x .claude/hooks/pre-compact.py

# ============================================================================
# Stop Hook - Captures learnings when Claude finishes
# ============================================================================
cat > .claude/hooks/stop.py << 'PYTHON'
#!/usr/bin/env python3
"""
Stop Hook - Tracks progress when Claude finishes responding.

Fires when:
- Claude completes a response
- Can block to force continuation (we don't use this by default)

MODES:
- READ-ONLY (default): Only reads feature_list.json, writes to .agent/metrics/
- WRITE MODE (opt-in): Can auto-complete features if tests pass

To enable write mode:
  export CONTEXT_ENGINE_WRITE_MODE=1

Write mode will auto-mark features complete when:
  1. Tests pass (detected by recent test output in transcript)
  2. Feature verifier confirms completion
  
This is an advanced feature - use with caution.

Requires: Claude Code 1.0.17+ (with Stop hook support)
"""

import json
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

# Configuration
WRITE_MODE = os.environ.get("CONTEXT_ENGINE_WRITE_MODE", "0") == "1"

def log_metric(event_type, feature_id=None, extra=None):
    """
    Append a metric event to the metrics log.
    """
    try:
        metrics_file = Path(".agent/metrics/session-metrics.jsonl")
        metrics_file.parent.mkdir(parents=True, exist_ok=True)
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
        }
        if feature_id:
            entry["feature_id"] = feature_id
        if extra:
            entry.update(extra)
        
        with open(metrics_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

def get_progress():
    """
    Read current progress from feature_list.json (READ-ONLY).
    
    Returns (completed_count, total_count, next_feature_id, next_feature_name)
    """
    feature_file = Path("feature_list.json")
    
    if not feature_file.exists():
        return 0, 0, None, None
    
    try:
        with open(feature_file) as f:
            data = json.load(f)
        
        features = data.get("features", [])
        completed = sum(1 for f in features if f.get("passes", False))
        total = len(features)
        
        # Find next incomplete feature
        next_id = None
        next_name = None
        for feat in sorted(features, key=lambda x: x.get("priority", 99)):
            if not feat.get("passes", False) and not feat.get("blocked", False):
                next_id = feat.get("id")
                next_name = feat.get("name")
                break
        
        return completed, total, next_id, next_name
    except Exception:
        return 0, 0, None, None

def check_tests_passed():
    """
    Check if tests recently passed (for write mode).
    
    Looks for common test success indicators.
    Returns True if tests appear to have passed.
    """
    # Check for recent test output files
    test_indicators = [
        Path(".agent/sessions/last-test-result"),
        Path("test-results.json"),
        Path("coverage/lcov.info"),
    ]
    
    for indicator in test_indicators:
        if indicator.exists():
            try:
                # Check if modified in last 5 minutes
                mtime = indicator.stat().st_mtime
                if datetime.now().timestamp() - mtime < 300:
                    return True
            except Exception:
                pass
    
    return False

def auto_complete_feature(feature_id):
    """
    Mark a feature as complete (WRITE MODE ONLY).
    
    Only called if CONTEXT_ENGINE_WRITE_MODE=1 and tests pass.
    """
    feature_file = Path("feature_list.json")
    
    try:
        with open(feature_file) as f:
            data = json.load(f)
        
        for feat in data.get("features", []):
            if feat.get("id") == feature_id:
                feat["passes"] = True
                feat["completed_at"] = datetime.now().isoformat()
                break
        
        with open(feature_file, "w") as f:
            json.dump(data, f, indent=2)
        
        return True
    except Exception:
        return False

def main():
    """
    Main entry point for Stop hook.
    
    Default: READ-ONLY (metrics only)
    Opt-in: WRITE MODE (auto-complete features)
    """
    try:
        # Read input from Claude Code
        input_data = json.load(sys.stdin)
        
        stop_hook_active = input_data.get("stop_hook_active", False)
        
        # Don't create infinite loops
        if stop_hook_active:
            print(json.dumps({}))
            return
        
        # Get progress
        completed, total, next_id, next_name = get_progress()
        
        # Log the stop event
        log_metric("stop", extra={
            "progress": f"{completed}/{total}",
            "next_feature": next_id,
            "write_mode": WRITE_MODE
        })
        
        # Show progress to user (stderr)
        if total > 0:
            print(f"📊 Progress: {completed}/{total} features", file=sys.stderr)
            if next_id:
                print(f"   Next: {next_id}", file=sys.stderr)
        
        # Write mode: auto-complete if tests pass
        if WRITE_MODE and next_id and check_tests_passed():
            if auto_complete_feature(next_id):
                print(f"✅ Auto-completed: {next_id} (tests passed)", file=sys.stderr)
                log_metric("auto_complete", feature_id=next_id)
        
    except Exception as e:
        print(f"⚠️ Stop hook error: {e}", file=sys.stderr)
    
    # Don't block - output empty
    print(json.dumps({}))

if __name__ == "__main__":
    main()
PYTHON
chmod +x .claude/hooks/stop.py

# ============================================================================
# PostToolUse Hook - Tracks file changes
# ============================================================================
cat > .claude/hooks/post-tool-use.py << 'PYTHON'
#!/usr/bin/env python3
"""
PostToolUse Hook - Logs tool usage after Claude uses a tool.

Fires when:
- Claude uses Write, Edit, MultiEdit, Bash, etc.

IMPORTANT: This hook is READ-ONLY by default. It only logs to
.agent/sessions/activity.jsonl. It does NOT run linters, formatters,
or any external commands unless users explicitly enable them.

To enable linting (optional):
  Set CONTEXT_ENGINE_LINT=1 environment variable

Requires: Claude Code 1.0.17+ (with PostToolUse hook support)
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Optional linting (disabled by default for safety)
ENABLE_LINTING = os.environ.get("CONTEXT_ENGINE_LINT", "0") == "1"

def log_activity(tool_name, tool_input):
    """
    Log tool usage to activity log (READ-ONLY operation).
    """
    try:
        log_file = Path(".agent/sessions/activity.jsonl")
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Extract relevant info without storing full content
        summary = {}
        if tool_name in ("Write", "Edit", "MultiEdit"):
            summary["file"] = tool_input.get("file_path", "unknown")
        elif tool_name == "Bash":
            cmd = tool_input.get("command", "")
            summary["command"] = cmd[:100]  # Truncate long commands
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "summary": summary
        }
        
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Don't crash on logging failure

def main():
    """
    Main entry point for PostToolUse hook.
    
    READ-ONLY by default. Only logs activity.
    """
    try:
        # Read input from Claude Code
        input_data = json.load(sys.stdin)
        
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        
        # Log activity (always)
        log_activity(tool_name, tool_input)
        
        # Optional linting (only if explicitly enabled)
        # if ENABLE_LINTING and tool_name in ("Write", "Edit", "MultiEdit"):
        #     file_path = tool_input.get("file_path", "")
        #     # Run linter here if enabled
        #     pass
        
    except Exception as e:
        print(f"⚠️ PostToolUse hook error: {e}", file=sys.stderr)
    
    # Output empty - no blocking
    print(json.dumps({}))

if __name__ == "__main__":
    main()
PYTHON
chmod +x .claude/hooks/post-tool-use.py

# ============================================================================
# Create/Update .claude/settings.json
# ============================================================================
echo "⚙️  Configuring Claude Code settings..."

# Check if settings.json exists
SETTINGS_FILE=".claude/settings.json"
if [ -f "$SETTINGS_FILE" ]; then
    # Merge with existing settings (handles both old and new schema variants)
    python3 << 'PYEOF'
import json
import sys
from pathlib import Path

settings_file = Path(".claude/settings.json")

try:
    existing = json.loads(settings_file.read_text())
except json.JSONDecodeError:
    print("⚠️  Existing settings.json is invalid JSON, backing up and creating new")
    settings_file.rename(settings_file.with_suffix('.json.bak'))
    existing = {}

# Our hook definitions with unique identifiers for deduplication
our_hooks = {
    "SessionStart": {
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.py\"",
            "_context_engine": True  # Marker for deduplication
        }]
    },
    "PreCompact": {
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/pre-compact.py\"",
            "_context_engine": True
        }]
    },
    "Stop": {
        "matcher": "",
        "hooks": [{
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/stop.py\"",
            "_context_engine": True
        }]
    },
    "PostToolUse": {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [{
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/post-tool-use.py\"",
            "_context_engine": True
        }]
    }
}

# Ensure hooks section exists
if "hooks" not in existing:
    existing["hooks"] = {}

# Handle both array format (new) and object format (old)
for hook_name, our_config in our_hooks.items():
    existing_hooks = existing["hooks"].get(hook_name, [])
    
    # Normalize: if it's a dict (old format), wrap in list
    if isinstance(existing_hooks, dict):
        existing_hooks = [existing_hooks]
    
    # Remove any existing context-engine hooks (for clean re-install)
    cleaned_hooks = []
    for hook in existing_hooks:
        # Check if this is one of ours by looking at the command
        is_ours = False
        for h in hook.get("hooks", []):
            if ".claude/hooks/" in h.get("command", "") and "session-start" in h.get("command", ""):
                is_ours = True
            if ".claude/hooks/" in h.get("command", "") and "pre-compact" in h.get("command", ""):
                is_ours = True
            if ".claude/hooks/" in h.get("command", "") and "stop.py" in h.get("command", ""):
                is_ours = True
            if ".claude/hooks/" in h.get("command", "") and "post-tool-use" in h.get("command", ""):
                is_ours = True
        if not is_ours:
            cleaned_hooks.append(hook)
    
    # Add our hook
    cleaned_hooks.append(our_config)
    
    existing["hooks"][hook_name] = cleaned_hooks

# Clean up our internal markers before saving
def clean_markers(obj):
    if isinstance(obj, dict):
        return {k: clean_markers(v) for k, v in obj.items() if k != "_context_engine"}
    elif isinstance(obj, list):
        return [clean_markers(item) for item in obj]
    return obj

existing = clean_markers(existing)

# Preserve key order: hooks first, then rest
ordered = {"hooks": existing["hooks"]}
for k, v in existing.items():
    if k != "hooks":
        ordered[k] = v

settings_file.write_text(json.dumps(ordered, indent=2))
print("✅ Merged with existing settings.json (preserved user hooks)")
PYEOF
else
    # Create new settings.json
    cat > "$SETTINGS_FILE" << 'JSON'
{
  "hooks": {
    "SessionStart": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.py\""
      }]
    }],
    "PreCompact": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/pre-compact.py\""
      }]
    }],
    "Stop": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/stop.py\""
      }]
    }],
    "PostToolUse": [{
      "matcher": "Write|Edit|MultiEdit",
      "hooks": [{
        "type": "command",
        "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/post-tool-use.py\""
      }]
    }]
  }
}
JSON
    echo "✅ Created new settings.json"
fi

# ============================================================================
# Create helper commands
# ============================================================================
echo "🛠️  Creating helper commands..."

mkdir -p .agent

cat > .agent/commands.sh << 'BASH'
#!/bin/bash
# Context Engine Commands (Native Hooks Mode)

MEMORY_DIR=".agent/memory"
mkdir -p "$MEMORY_DIR"/{failures,strategies,constraints}

case "$1" in
    recall)
        # Recall from memory
        CATEGORY="${2:-failures}"
        echo "=== Recalling: $CATEGORY ==="
        for f in "$MEMORY_DIR/$CATEGORY"/*.md; do
            [ -f "$f" ] && cat "$f"
        done
        ;;
    
    success)
        # Mark feature as complete
        FEATURE_ID="$2"
        MESSAGE="$3"
        
        if [ -f "feature_list.json" ]; then
            python3 -c "
import json
with open('feature_list.json') as f:
    data = json.load(f)
for feat in data.get('features', []):
    if feat.get('id') == '$FEATURE_ID':
        feat['passes'] = True
        break
with open('feature_list.json', 'w') as f:
    json.dump(data, f, indent=2)
print('✅ Marked $FEATURE_ID as complete')
"
        fi
        
        # Record to strategies
        TIMESTAMP=$(date +%Y%m%d-%H%M%S)
        echo "# Success: $FEATURE_ID" > "$MEMORY_DIR/strategies/$TIMESTAMP.md"
        echo "$MESSAGE" >> "$MEMORY_DIR/strategies/$TIMESTAMP.md"
        ;;
    
    failure)
        # Record failure
        FEATURE_ID="$2"
        MESSAGE="$3"
        
        TIMESTAMP=$(date +%Y%m%d-%H%M%S)
        echo "# Failure: $FEATURE_ID" > "$MEMORY_DIR/failures/$TIMESTAMP.md"
        echo "$MESSAGE" >> "$MEMORY_DIR/failures/$TIMESTAMP.md"
        echo "❌ Recorded failure for $FEATURE_ID"
        ;;
    
    compile)
        # Manually compile context
        python3 .claude/hooks/session-start.py < /dev/null 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
ctx = data.get('hookSpecificOutput', {}).get('additionalContext', '')
print(ctx)
" > .agent/working-context/current.md
        echo "✅ Context compiled to .agent/working-context/current.md"
        ;;
    
    status)
        # Show feature status
        if [ -f "feature_list.json" ]; then
            python3 -c "
import json
with open('feature_list.json') as f:
    data = json.load(f)
features = data.get('features', [])
completed = sum(1 for f in features if f.get('passes', False))
blocked = sum(1 for f in features if f.get('blocked', False))
total = len(features)
print(f'Features: {completed}/{total} completed, {blocked} blocked')
for f in features:
    if not f.get('passes') and not f.get('blocked'):
        print(f\"  Next: {f.get('id')} - {f.get('name')}\")
        break
"
        else
            echo "No feature_list.json found"
        fi
        ;;
    
    *)
        echo "Usage: .agent/commands.sh <command>"
        echo ""
        echo "Commands:"
        echo "  recall [category]  - Recall from memory (failures/strategies/constraints)"
        echo "  success <id> <msg> - Mark feature complete"
        echo "  failure <id> <msg> - Record failure"
        echo "  compile            - Manually compile context"
        echo "  status             - Show feature status"
        ;;
esac
BASH
chmod +x .agent/commands.sh

# ============================================================================
# Add to CLAUDE.md
# ============================================================================
echo "📄 Updating CLAUDE.md..."

if [ -f "CLAUDE.md" ]; then
    # Check if already has native hooks section
    if ! grep -q "Native Hooks Mode" CLAUDE.md; then
        cat >> CLAUDE.md << 'MD'

## Native Hooks Mode (Context Engine)

This project uses Claude Code native hooks for context management.

**Automatic behaviors:**
- SessionStart: Fresh context injected on /clear, resume, or new session
- PreCompact: State saved before compaction
- Stop: Progress tracked when you finish responding

**Commands:**
- `.agent/commands.sh recall failures` - See what NOT to do
- `.agent/commands.sh success <id> <msg>` - Mark feature complete
- `.agent/commands.sh failure <id> <msg>` - Record failure
- `.agent/commands.sh status` - Check progress

**After /clear or /compact:** Context is automatically restored. Just continue working.
MD
        echo "   Added native hooks section to CLAUDE.md"
    else
        echo "   CLAUDE.md already has native hooks section"
    fi
else
    cat > CLAUDE.md << 'MD'
# Claude Code Instructions

## Native Hooks Mode (Context Engine)

This project uses Claude Code native hooks for context management.

**Automatic behaviors:**
- SessionStart: Fresh context injected on /clear, resume, or new session
- PreCompact: State saved before compaction
- Stop: Progress tracked when you finish responding

**Commands:**
- `.agent/commands.sh recall failures` - See what NOT to do
- `.agent/commands.sh success <id> <msg>` - Mark feature complete
- `.agent/commands.sh failure <id> <msg>` - Record failure
- `.agent/commands.sh status` - Check progress

**After /clear or /compact:** Context is automatically restored. Just continue working.

## Workflow

1. Check current task: `.agent/commands.sh status`
2. Check failures: `.agent/commands.sh recall failures`
3. Implement the feature
4. Run tests
5. Mark complete: `.agent/commands.sh success <id> "what you did"`
6. Commit: `git add -A && git commit -m "completed <id>"`

The context engine handles the rest automatically.
MD
    echo "   Created CLAUDE.md"
fi

# ============================================================================
# Done
# ============================================================================
echo ""
echo "✅ Native hooks setup complete! (v${SCRIPT_VERSION})"
echo ""
echo "📁 Created:"
echo "   .claude/hooks/session-start.py  - Injects context on session start"
echo "   .claude/hooks/pre-compact.py    - Saves state before compaction"
echo "   .claude/hooks/stop.py           - Tracks progress on completion (read-only)"
echo "   .claude/hooks/post-tool-use.py  - Logs activity (read-only)"
echo "   .claude/settings.json           - Hook configuration"
echo "   .agent/commands.sh              - Helper commands"
echo ""
echo "🚀 How it works:"
echo "   1. Start Claude Code normally: claude"
echo "   2. Work on features as usual"
echo "   3. Use /clear or /compact freely - context auto-restores"
echo "   4. Session resume? Context auto-restores"
echo ""
echo "⚠️  Important:"
echo "   - Requires Claude Code 1.0.17+ (with SessionStart/PreCompact hooks)"
echo "   - Run /hooks in Claude Code to review and approve the hooks"
echo "   - Hooks won't run until approved"
echo "   - Check your version: claude --version"
echo ""
echo "🔒 Safety notes:"
echo "   - All hooks are read-only by default"
echo "   - No network requests from hooks"
echo "   - Context injection capped at 6000 chars to prevent overflow"
echo ""
