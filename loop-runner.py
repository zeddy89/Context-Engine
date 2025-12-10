#!/usr/bin/env python3
"""
Autonomous Loop Runner
======================
Continuously runs Claude Code sessions until all features are complete.

Usage:
    ./loop-runner.py                  # Run in current directory
    ./loop-runner.py ~/projects/myapp # Run in specific project
    ./loop-runner.py --max-sessions 20
"""

import subprocess
import json
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_MODEL = "sonnet"
MAX_SESSIONS = 50
PAUSE_BETWEEN_SESSIONS = 3  # seconds

# ============================================================================
# Utilities
# ============================================================================

def color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"

def green(text): return color(text, "92")
def yellow(text): return color(text, "93")
def red(text): return color(text, "91")
def cyan(text): return color(text, "96")
def bold(text): return color(text, "1")

def detect_test_command(project_path: Path) -> str:
    """Detect the appropriate test command for the project."""
    if (project_path / "Cargo.toml").exists():
        return "cargo test"
    elif (project_path / "package.json").exists():
        return "npm test"
    elif (project_path / "go.mod").exists():
        return "go test ./..."
    elif (project_path / "requirements.txt").exists() or (project_path / "pyproject.toml").exists():
        return "pytest"
    elif (project_path / "Makefile").exists():
        return "make test"
    else:
        return None

def run_tests(project_path: Path) -> tuple[bool, str]:
    """Run tests and return (passed, output)."""
    test_cmd = detect_test_command(project_path)
    
    if not test_cmd:
        return True, "No test command detected, skipping"
    
    try:
        result = subprocess.run(
            test_cmd,
            shell=True,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=300  # 5 min timeout for tests
        )
        
        passed = result.returncode == 0
        output = result.stdout + result.stderr
        
        return passed, output
    except subprocess.TimeoutExpired:
        return False, "Tests timed out after 5 minutes"
    except Exception as e:
        return False, f"Error running tests: {e}"

def verify_session_result(project_path: Path) -> dict:
    """Verify the session actually produced working code."""
    results = {
        "tests_passed": False,
        "tests_output": "",
        "builds": False,
        "build_output": ""
    }
    
    # Run tests
    print(f"  🧪 Running tests...")
    passed, output = run_tests(project_path)
    results["tests_passed"] = passed
    results["tests_output"] = output[:500]  # Truncate
    
    if passed:
        print(f"  {green('✅ Tests passed')}")
    else:
        print(f"  {red('❌ Tests failed')}")
    
    return results

def is_feature_in_git_history(project_path: Path, feature_id: str) -> bool:
    """Check if feature was completed in git history (backup check)."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--grep", f"session: completed {feature_id}"],
            capture_output=True, text=True, cwd=project_path, timeout=10
        )
        return bool(result.stdout.strip())
    except:
        return False

def sync_features_with_git(project_path: Path) -> int:
    """Sync feature_list.json with git history. Returns number of fixes."""
    feature_file = project_path / "feature_list.json"
    
    if not feature_file.exists():
        return 0
    
    try:
        with open(feature_file) as f:
            data = json.load(f)
        
        fixes = 0
        for feat in data.get("features", []):
            if not feat.get("passes", False):
                feature_id = feat.get("id", "")
                if is_feature_in_git_history(project_path, feature_id):
                    print(f"  🔧 Fixing {feature_id}: found in git history, marking as passed")
                    feat["passes"] = True
                    fixes += 1
        
        if fixes > 0:
            with open(feature_file, "w") as f:
                json.dump(data, f, indent=2)
            print(f"  ✅ Fixed {fixes} feature(s) from git history")
        
        return fixes
    except Exception as e:
        print(f"  ⚠️ Could not sync with git: {e}")
        return 0

def get_feature_status(project_path: Path) -> dict:
    """Get current feature completion status."""
    feature_file = project_path / "feature_list.json"
    
    if not feature_file.exists():
        return {"total": 0, "completed": 0, "remaining": 0, "blocked": 0}
    
    try:
        with open(feature_file) as f:
            data = json.load(f)
        
        features = data.get("features", [])
        completed = sum(1 for f in features if f.get("passes", False))
        blocked = sum(1 for f in features if f.get("blocked", False))
        
        return {
            "total": len(features),
            "completed": completed,
            "remaining": len(features) - completed,
            "blocked": blocked
        }
    except:
        return {"total": 0, "completed": 0, "remaining": 0, "blocked": 0}

def get_next_feature(project_path: Path) -> dict | None:
    """Get next feature to implement."""
    feature_file = project_path / "feature_list.json"
    
    if not feature_file.exists():
        return None
    
    try:
        with open(feature_file) as f:
            data = json.load(f)
        
        features = data.get("features", [])
        
        for feat in sorted(features, key=lambda x: x.get("priority", 99)):
            if not feat.get("passes", False) and not feat.get("blocked", False):
                return feat
        
        return None
    except:
        return None

def print_status_bar(status: dict, session: int):
    """Print a nice status bar."""
    total = status["total"]
    completed = status["completed"]
    pct = (completed / total * 100) if total > 0 else 0
    
    bar_len = 30
    filled = int(bar_len * completed / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_len - filled)
    
    print(f"\n{'═' * 60}")
    print(f"  Session {session} | {green(bar)} {completed}/{total} ({pct:.0f}%)")
    print(f"  Remaining: {status['remaining']} | Blocked: {status['blocked']}")
    print(f"{'═' * 60}\n")

# ============================================================================
# Main Loop
# ============================================================================

def run_session(project_path: Path, session_num: int, model: str) -> bool:
    """Run a single Claude Code session.
    
    Note: Claude Code uses MCPs registered via 'claude mcp add'.
    """
    
    feature = get_next_feature(project_path)
    
    if not feature:
        return False
    
    feature_id = feature.get("id", "unknown")
    feature_desc = feature.get("description", "")[:50]
    
    print(f"🔧 Implementing: {cyan(feature_id)} - {feature_desc}...")
    
    # Build the prompt with explicit test requirements, MCP usage, and subagent invocation
    prompt = f"""Session {session_num}: Implement feature

## STEP 1: Compile Fresh Context
```bash
.agent/hooks/compile-context.sh
cat .agent/working-context/current.md
```

## STEP 2: Check Failures to Avoid
```bash
.agent/commands.sh recall failures
```

## STEP 3: Feature to Implement
{json.dumps(feature, indent=2)}

## STEP 4: Look Up Documentation (USE MCP)
Before writing code, use the Ref MCP tool to look up documentation for any libraries you'll use.

Example queries:
- "Look up the axum Router documentation"
- "Look up sqlx query macro examples"
- "Look up how to use russh for SSH connections"

DO NOT guess at APIs. Look them up first using the mcp__ref tool.

## STEP 5: Implement the Feature
Write the code for this feature using the documentation you looked up.

## STEP 6: RUN TESTS (MANDATORY)
You MUST run tests before marking complete:
```bash
# For Rust:
cargo test

# For Python:
pytest

# For Node:
npm test

# For Go:
go test ./...
```

If tests fail, fix them before proceeding. Do NOT mark the feature as complete if tests fail.

## STEP 7: Use Code Review Subagent (MANDATORY)
You MUST invoke the code-reviewer subagent:
```
@code-reviewer Review the changes for feature {feature_id}
```
Wait for the review and address any issues.

## STEP 8: Use Test Runner Subagent (MANDATORY)
You MUST invoke the test-runner subagent:
```
@test-runner Run the test suite and analyze results
```
Ensure all tests pass.

## STEP 9: Use Feature Verifier Subagent (MANDATORY)
You MUST invoke the feature-verifier subagent:
```
@feature-verifier Verify feature {feature_id}: {feature.get('description', '')}
```
Confirm the feature works end-to-end.

## STEP 10: Update Status (ONLY IF ALL CHECKS PASS)
```bash
# Update feature_list.json - set passes: true
# Capture what worked:
.agent/commands.sh success "{feature_id}" "description of what worked"

# Commit:
git add -A
git commit -m "session: completed {feature_id}"
```

## CRITICAL RULES
- DO use MCP tools (especially Ref) to look up documentation
- DO NOT guess at APIs - look them up first
- DO NOT mark passes: true unless tests actually pass
- DO NOT skip running tests
- DO NOT skip the subagents (@code-reviewer, @test-runner, @feature-verifier)
- If tests fail after 3 attempts, mark feature as blocked with reason"""

    # Build command - Claude Code uses MCPs from ~/.claude.json (added via 'claude mcp add')
    cmd = [
        "claude",
        "--model", model,
        "--permission-mode", "bypassPermissions",
        "-p", prompt
    ]

    # Run Claude Code (will execute and modify files)
    result = subprocess.run(
        cmd,
        cwd=str(project_path),
        timeout=3600  # 1 hour max
    )
    
    return result.returncode == 0

def main():
    parser = argparse.ArgumentParser(description="Autonomous Claude Code Loop Runner")
    parser.add_argument("project", nargs="?", type=Path, default=Path.cwd(), help="Project path")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL, help="Model (sonnet/opus)")
    parser.add_argument("--max-sessions", "-n", type=int, default=MAX_SESSIONS, help="Max sessions")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run interactively (opens shell)")
    args = parser.parse_args()
    
    project_path = args.project.expanduser().resolve()
    
    if not project_path.exists():
        print(red(f"Project not found: {project_path}"))
        sys.exit(1)
    
    if not (project_path / "feature_list.json").exists():
        print(red("No feature_list.json found. Initialize project first."))
        sys.exit(1)
    
    # Check MCPs
    result = subprocess.run(
        ["claude", "mcp", "list"],
        cwd=str(project_path),
        capture_output=True,
        text=True
    )
    if "No MCP servers configured" in result.stdout:
        print(yellow("⚠️  No MCPs configured. Add with 'claude mcp add' for best results."))
    
    print(bold("\n🚀 Autonomous Loop Runner"))
    print(f"   Project: {project_path}")
    print(f"   Model: {args.model}")
    print(f"   Max sessions: {args.max_sessions}")
    
    session = 1
    consecutive_failures = 0
    
    while session <= args.max_sessions:
        # Sync feature_list.json with git history (fixes missed updates)
        sync_features_with_git(project_path)
        
        status = get_feature_status(project_path)
        print_status_bar(status, session)
        
        # Check if done
        if status["remaining"] == 0:
            print(green("\n🎉 All features completed!"))
            break
        
        if status["remaining"] == status["blocked"]:
            print(yellow("\n⚠️  All remaining features are blocked"))
            print("   Manual intervention required")
            break
        
        # Run session
        before_completed = status["completed"]
        
        if args.interactive:
            # Interactive mode
            import shlex
            feature = get_next_feature(project_path)
            if feature:
                feature_id = feature.get('id', 'unknown')
                prompt = f"""Implement feature {feature_id}: {feature.get('description')}

REQUIREMENTS:
1. Run .agent/hooks/compile-context.sh first
2. Check .agent/commands.sh recall failures
3. Use MCP Ref tool to look up documentation before coding
4. Implement the feature
5. RUN TESTS: cargo test / pytest / npm test / go test ./...
6. INVOKE @code-reviewer to review changes
7. INVOKE @test-runner to verify tests pass
8. INVOKE @feature-verifier to verify end-to-end
9. Only mark passes: true if ALL checks pass
10. Commit: git commit -m "session: completed {feature_id}"

CRITICAL:
- Use Ref MCP to look up docs BEFORE guessing at APIs
- Do NOT skip tests or subagents
- Do NOT mark complete unless tests pass"""
                # Build command - Claude Code uses MCPs from ~/.claude.json
                cmd_parts = [
                    "claude",
                    "--model", shlex.quote(args.model),
                    "--permission-mode", "bypassPermissions",
                    "-p", shlex.quote(prompt)
                ]
                shell_cmd = " ".join(cmd_parts)
                subprocess.run(shell_cmd, shell=True, cwd=str(project_path))
        else:
            # Non-interactive mode
            try:
                run_session(project_path, session, args.model)
            except subprocess.TimeoutExpired:
                print(yellow("⏱️  Session timed out"))
            except Exception as e:
                print(red(f"❌ Session error: {e}"))
        
        # Check progress
        new_status = get_feature_status(project_path)
        
        # Run independent test verification
        print(f"\n  📋 Post-session verification...")
        verification = verify_session_result(project_path)
        
        if new_status["completed"] > before_completed:
            if verification["tests_passed"]:
                print(green(f"✅ Feature completed and verified! ({new_status['completed']}/{new_status['total']})"))
            else:
                print(yellow(f"⚠️ Feature marked complete but tests failing!"))
            consecutive_failures = 0
        else:
            print(yellow("⚠️  No progress this session"))
            consecutive_failures += 1
        
        if consecutive_failures >= 3:
            print(red("\n❌ Too many consecutive failures"))
            choice = input("Continue? [y/N]: ").strip().lower()
            if choice != 'y':
                break
            consecutive_failures = 0
        
        session += 1
        time.sleep(PAUSE_BETWEEN_SESSIONS)
    
    # Final status
    final = get_feature_status(project_path)
    print(f"\n{'═' * 60}")
    print(bold("Final Status"))
    print(f"  Completed: {final['completed']}/{final['total']}")
    print(f"  Blocked: {final['blocked']}")
    print(f"  Sessions: {session - 1}")
    print(f"{'═' * 60}\n")

if __name__ == "__main__":
    main()
