#!/usr/bin/env python3
"""
Context-Engineered Agent Orchestrator
=====================================
Autonomous project builder using Claude Code with context engineering principles.

Usage:
    python orchestrator.py                    # Interactive mode
    python orchestrator.py --project ~/myapp  # Specify project
    python orchestrator.py --continue         # Continue existing project
"""

import subprocess
import json
import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

# ============================================================================
# Configuration
# ============================================================================

# HARNESS_PATH: Use env var, or default to script's directory
HARNESS_PATH = Path(os.environ.get('CONTEXT_ENGINE_PATH', Path(__file__).parent.resolve()))
DEFAULT_MODEL = "sonnet"  # or "opus" for complex projects
MAX_SESSIONS = 100  # Safety limit
SESSION_TIMEOUT = 3600  # 1 hour max per session
RETRY_DELAY = 5  # Seconds between retries on failure
DEBUG = False  # Set via --debug flag

# ============================================================================
# Feature Complexity Detection
# ============================================================================

def get_feature_complexity(feature: Dict[str, Any]) -> str:
    """
    Estimate feature complexity to determine subagent requirements.
    Returns: 'high', 'medium', or 'low'
    
    Can be overridden by setting "complexity" field in feature_list.json
    
    High complexity = full subagent ceremony (code-reviewer, test-runner, feature-verifier)
    Medium complexity = just test-runner
    Low complexity = just run tests, no subagents
    """
    # Manual override takes precedence
    override = feature.get('complexity', '').lower()
    if override in ('high', 'medium', 'low'):
        return override
    
    signals = 0
    
    category = feature.get('category', '').lower()
    description = feature.get('description', '').lower()
    name = feature.get('name', '').lower()
    
    # High complexity signals
    high_complexity_keywords = [
        'security', 'crypto', 'encrypt', 'auth', 'credential', 'password',
        'ssh', 'certificate', 'token', 'session', 'permission', 'rbac',
        'injection', 'sanitize', 'validate', 'vulnerability'
    ]
    for keyword in high_complexity_keywords:
        if keyword in description or keyword in category or keyword in name:
            signals += 2
            break  # Only count once
    
    if len(feature.get('dependencies', [])) > 3:
        signals += 1
    if len(feature.get('tests', [])) > 5:
        signals += 1
    
    # Medium complexity signals (architecture, API, database, system operations)
    medium_keywords = ['api', 'endpoint', 'database', 'repository', 'migration', 'schema', 'patch', 'system', 'service', 'handler', 'execute', 'command']
    for keyword in medium_keywords:
        if keyword in description or keyword in category:
            signals += 1
            break
    
    # Low complexity signals
    low_keywords = ['refactor', 'rename', 'cleanup', 'format', 'typo', 'comment', 'docs']
    for keyword in low_keywords:
        if keyword in description or keyword in category or keyword in name:
            signals -= 2
            break
    
    if 'simple' in name or 'minor' in name:
        signals -= 1
    if len(description) < 40:
        signals -= 1
    
    # Determine complexity level
    if signals >= 3:
        return 'high'
    elif signals <= 0:
        return 'low'
    return 'medium'

def get_subagent_instructions(complexity: str, feature_id: str, description: str) -> str:
    """Generate subagent instructions based on complexity level."""
    
    if complexity == 'high':
        return f"""## STEP 7: Invoke Subagents (MANDATORY - High Complexity Feature)
You MUST invoke these subagents in order:

### Code Review
```
@code-reviewer Review the changes for feature {feature_id}
```
Wait for review. Address any issues.

### Test Runner
```
@test-runner Run the test suite and analyze results
```
Ensure all tests pass.

### Feature Verifier
```
@feature-verifier Verify feature {feature_id}: {description}
```
Confirm feature works end-to-end.

After all subagents pass, proceed to STEP 8."""

    elif complexity == 'medium':
        return f"""## STEP 7: Verify Tests (Medium Complexity Feature)
Invoke the test runner to verify:

```
@test-runner Run the test suite and analyze results
```
Ensure all tests pass, then proceed to STEP 8."""

    else:  # low
        return """## STEP 7: Verify Tests (Low Complexity Feature)
Tests should already pass from STEP 6. If they do, proceed directly to STEP 8.
No subagent review needed for simple changes - just mark complete."""

# ============================================================================
# Color Output
# ============================================================================

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'═' * 60}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'═' * 60}{Colors.END}\n")

def print_status(text: str, status: str = "info"):
    icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌", "working": "🔧"}
    colors = {"info": Colors.CYAN, "success": Colors.GREEN, "warning": Colors.YELLOW, "error": Colors.RED, "working": Colors.BLUE}
    print(f"{icons.get(status, 'ℹ️')} {colors.get(status, '')}{text}{Colors.END}")

def print_progress(completed: int, total: int, label: str = "Progress"):
    pct = (completed / total * 100) if total > 0 else 0
    bar_len = 30
    filled = int(bar_len * completed / total) if total > 0 else 0
    bar = '█' * filled + '░' * (bar_len - filled)
    print(f"\n{Colors.BOLD}{label}:{Colors.END} [{Colors.GREEN}{bar}{Colors.END}] {completed}/{total} ({pct:.1f}%)\n")

def setup_mcps_interactive(project_path: Path, preset: str = None):
    """Setup MCPs via claude mcp add commands."""
    project_path = Path(project_path).expanduser().resolve()
    
    print_header("MCP Setup")
    
    # Define MCP presets with their claude mcp add commands
    MCP_PRESETS = {
        "rust": [
            ("Ref", "claude mcp add --transport http Ref https://api.ref.tools/mcp", True),
            ("context7", "claude mcp add context7", False),
        ],
        "python": [
            ("Ref", "claude mcp add --transport http Ref https://api.ref.tools/mcp", True),
            ("context7", "claude mcp add context7", False),
        ],
        "node": [
            ("Ref", "claude mcp add --transport http Ref https://api.ref.tools/mcp", True),
            ("context7", "claude mcp add context7", False),
        ],
        "web": [
            ("context7", "claude mcp add context7", False),
        ],
        "docs": [
            ("Ref", "claude mcp add --transport http Ref https://api.ref.tools/mcp", True),
            ("context7", "claude mcp add context7", False),
        ],
    }
    
    # Show current MCPs
    print_status("Current MCPs:", "info")
    result = subprocess.run(
        ["claude", "mcp", "list"],
        cwd=str(project_path),
        capture_output=True,
        text=True
    )
    print(result.stdout)
    
    # If preset specified
    if preset and preset in MCP_PRESETS:
        print_status(f"Recommended MCPs for '{preset}' projects:", "info")
        for name, cmd, needs_key in MCP_PRESETS[preset]:
            print(f"  - {name}: {cmd}")
        print()
    
    # Instructions
    print(f"{Colors.BOLD}To add MCPs, run these commands in your project directory:{Colors.END}")
    print()
    print(f"  # Documentation (recommended - get API key from ref.tools)")
    print(f"  claude mcp add --transport http Ref https://api.ref.tools/mcp --header \"x-ref-api-key: YOUR_KEY\"")
    print()
    print(f"  # Alternative docs (no API key needed)")
    print(f"  claude mcp add context7")
    print()
    
    # Ask if they want to add now
    choice = input(f"{Colors.CYAN}Add MCPs now? [Y/n]:{Colors.END} ").strip().lower()
    
    if choice != 'n':
        print()
        print(f"{Colors.BOLD}Opening a shell in your project. Run your 'claude mcp add' commands.{Colors.END}")
        print(f"{Colors.BOLD}Type 'exit' when done.{Colors.END}")
        print()
        
        # Open subshell in project directory
        subprocess.run(
            [os.environ.get("SHELL", "/bin/bash")],
            cwd=str(project_path)
        )
        
        # Show final MCPs
        print()
        print_status("Configured MCPs:", "info")
        subprocess.run(
            ["claude", "mcp", "list"],
            cwd=str(project_path)
        )

# ============================================================================
# Project Setup
# ============================================================================

def setup_harness(project_path: Path) -> bool:
    """Run the context-engineered harness setup."""
    setup_script = HARNESS_PATH / "setup-context-engineered.sh"
    
    if not setup_script.exists():
        print_status(f"Harness not found at {setup_script}", "error")
        print_status("Download from: https://github.com/your-repo/agent-harness", "info")
        return False
    
    print_status("Setting up context-engineered harness...", "working")
    
    result = subprocess.run(
        ["bash", str(setup_script)],
        cwd=project_path,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print_status(f"Harness setup failed: {result.stderr}", "error")
        return False
    
    print_status("Harness setup complete", "success")
    return True

def get_project_info_interactive(preset_path: Optional[Path] = None, preset_model: Optional[str] = None) -> Dict[str, Any]:
    """Interactively gather project information."""
    print_header("New Project Setup")
    
    info = {}
    
    # Project name - derive from path if preset
    if preset_path:
        default_name = preset_path.name
        info['name'] = input(f"{Colors.CYAN}Project name [{default_name}]:{Colors.END} ").strip() or default_name
        info['path'] = preset_path
        print(f"  Path: {preset_path}")
    else:
        info['name'] = input(f"{Colors.CYAN}Project name:{Colors.END} ").strip()
        if not info['name']:
            info['name'] = "my-project"
        
        # Project path
        default_path = Path.home() / "projects" / info['name']
        path_input = input(f"{Colors.CYAN}Project path [{default_path}]:{Colors.END} ").strip()
        info['path'] = Path(path_input) if path_input else default_path
    
    # Tech stack
    print(f"\n{Colors.BOLD}Tech Stack Options:{Colors.END}")
    print("  1. Python (FastAPI + PostgreSQL)")
    print("  2. Node.js (Express + MongoDB)")
    print("  3. Go (Gin + PostgreSQL)")
    print("  4. Full-Stack (React + FastAPI + PostgreSQL)")
    print("  5. CLI Tool (Go)")
    print("  6. CLI Tool (Python)")
    print("  7. Custom (describe your own)")
    
    stack_choice = input(f"\n{Colors.CYAN}Select stack [1-7]:{Colors.END} ").strip()
    
    stacks = {
        "1": "Python FastAPI with PostgreSQL and SQLAlchemy",
        "2": "Node.js Express with MongoDB and Mongoose",
        "3": "Go with Gin framework and PostgreSQL",
        "4": "React + TypeScript frontend with FastAPI + PostgreSQL backend",
        "5": "Go CLI tool with Cobra framework",
        "6": "Python CLI tool with Click framework",
    }
    
    if stack_choice == "7":
        info['stack'] = input(f"{Colors.CYAN}Describe your tech stack:{Colors.END} ").strip()
    else:
        info['stack'] = stacks.get(stack_choice, stacks["1"])
    
    # Description
    print(f"\n{Colors.BOLD}Describe your project:{Colors.END}")
    print("(What does it do? What are the main features? Be specific.)")
    print("(Enter a blank line when done)")
    
    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    info['description'] = "\n".join(lines)
    
    # Model selection - skip if preset
    if preset_model:
        info['model'] = preset_model
    else:
        print(f"\n{Colors.BOLD}Model Selection:{Colors.END}")
        print("  1. Sonnet (faster, good for most projects)")
        print("  2. Opus (slower, better for complex architecture)")
        
        model_choice = input(f"\n{Colors.CYAN}Select model [1-2]:{Colors.END} ").strip()
        info['model'] = "opus" if model_choice == "2" else "sonnet"
    
    # Confirm
    print(f"\n{Colors.BOLD}Project Summary:{Colors.END}")
    print(f"  Name: {info['name']}")
    print(f"  Path: {info['path']}")
    print(f"  Stack: {info['stack']}")
    print(f"  Model: {info['model']}")
    print(f"  Description: {info['description'][:100]}...")
    
    confirm = input(f"\n{Colors.CYAN}Proceed? [Y/n]:{Colors.END} ").strip().lower()
    if confirm == 'n':
        print_status("Aborted", "warning")
        sys.exit(0)
    
    return info

def create_project_directory(info: Dict[str, Any]) -> Path:
    """Create project directory and initialize."""
    project_path = Path(info['path']).expanduser().resolve()
    project_path.mkdir(parents=True, exist_ok=True)
    
    print_status(f"Created project directory: {project_path}", "success")
    return project_path

# ============================================================================
# Feature Tracking
# ============================================================================

def get_feature_status(project_path: Path) -> Dict[str, Any]:
    """Read feature_list.json and return status."""
    feature_file = project_path / "feature_list.json"
    
    if not feature_file.exists():
        return {"total": 0, "completed": 0, "remaining": 0, "blocked": 0, "features": []}
    
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
            "blocked": blocked,
            "features": features
        }
    except json.JSONDecodeError:
        return {"total": 0, "completed": 0, "remaining": 0, "blocked": 0, "features": []}

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
                    print_status(f"Fixing {feature_id}: found in git history, marking as passed", "working")
                    feat["passes"] = True
                    fixes += 1
        
        if fixes > 0:
            with open(feature_file, "w") as f:
                json.dump(data, f, indent=2)
            print_status(f"Fixed {fixes} feature(s) from git history", "success")
        
        return fixes
    except Exception as e:
        print_status(f"Could not sync with git: {e}", "warning")
        return 0

def get_next_feature(project_path: Path) -> Optional[Dict[str, Any]]:
    """Get the next feature to implement."""
    status = get_feature_status(project_path)
    
    for feat in sorted(status["features"], key=lambda x: x.get("priority", 99)):
        if not feat.get("passes", False) and not feat.get("blocked", False):
            # Check dependencies
            deps = feat.get("dependencies", [])
            deps_met = all(
                any(f.get("id") == dep and f.get("passes", False) for f in status["features"])
                for dep in deps
            )
            if deps_met or not deps:
                return feat
    
    return None

# ============================================================================
# Claude Code Integration
# ============================================================================

def build_init_prompt(info: Dict[str, Any]) -> str:
    """Build the initialization prompt."""
    
    qa_section = ""
    if info.get('include_qa', False):
        qa_section = """

## QA Features (IMPORTANT)
Also generate E2E QA features using Playwright for every user-facing feature:
- qa-setup: Test environment verification
- qa-login-*: Authentication flows (success, failure, session, logout)
- qa-{area}-*: CRUD operations for each entity (list, create, edit, delete, validation)
- qa-error-*: Error handling (404, API errors, form validation)
- qa-perf-*: Page load performance
- qa-responsive-*: Mobile viewport testing

QA features should:
- Have priority 100+ (run after implementation features)
- Category: "qa"
- Description: Start with "Use Playwright MCP to..."
- Cover happy paths AND edge cases

Example QA feature:
{
  "id": "qa-host-001",
  "name": "E2E: Host List",
  "description": "Use Playwright MCP to navigate to hosts page, verify list loads with columns, test pagination, test search/filter",
  "priority": 120,
  "category": "qa",
  "passes": false
}
"""

    return f"""Read .agent/AGENT_RULES.md to understand the four-layer memory architecture.

Then read .agent/workflows/init.md and initialize this project:

Project: {info['name']}
Tech Stack: {info['stack']}

Description:
{info['description']}

After initialization:
1. Create feature_list.json with all features broken into atomic, testable units
2. Create app_spec.md with architecture decisions
3. Create init.sh that verifies the project builds/tests
4. Record initial constraints in .agent/memory/constraints/
5. Compile initial context with .agent/hooks/compile-context.sh
6. Commit the initial scaffold
{qa_section}
Be thorough in breaking down features - each should be independently verifiable."""

def build_qa_prompt(feature: Dict[str, Any], session_num: int) -> str:
    """Build comprehensive QA prompt that thoroughly tests features."""
    feature_id = feature.get("id", "unknown")
    feature_desc = feature.get("description", "")
    feature_name = feature.get("name", "")
    
    return f"""Session {session_num}: Comprehensive QA Testing

## Feature Under Test
{json.dumps(feature, indent=2)}

## STEP 1: Environment Setup
Ensure the application is running:
```bash
# Start backend (check if already running first)
# Start frontend (check if already running first)  
# Verify both are accessible
```

## STEP 2: Understand What to Test
Before testing, review what this feature SHOULD do:
```bash
# Check the original feature implementation
git log --oneline --grep="{feature_id.replace('qa-', '').split('-')[0]}" | head -5

# Review related code files
# Read app_spec.md for expected behavior
```

## STEP 3: Comprehensive Playwright Testing

Use Playwright MCP to test EVERY aspect of this feature:

### A. VISUAL INSPECTION
- [ ] Page loads without console errors
- [ ] Layout matches expected design (no overlapping elements, proper spacing)
- [ ] Typography is readable (font sizes, contrast)
- [ ] Colors and branding are consistent
- [ ] Icons/images load correctly (no broken images)
- [ ] Responsive: Test at desktop (1920px), tablet (768px), mobile (375px)
- [ ] Dark mode (if applicable): Colors adapt properly
- Take screenshots at each viewport size

### B. ELEMENT VERIFICATION
For EVERY interactive element on the page:
- [ ] Buttons: Are they visible? Clickable? Proper hover states?
- [ ] Forms: All fields present? Labels correct? Placeholders helpful?
- [ ] Tables: Headers present? Data displays? Sorting works? Pagination?
- [ ] Navigation: All links work? Active state shows current page?
- [ ] Modals/Dialogs: Open correctly? Close on X and outside click?
- [ ] Dropdowns: Options load? Selection works? Clear option?
- [ ] Loading states: Spinners show during async operations?
- [ ] Empty states: Proper messaging when no data?

### C. FUNCTIONALITY TESTING
Test the COMPLETE user journey:

**Happy Path:**
1. Perform the primary action this feature enables
2. Verify data persists (refresh page, check it's still there)
3. Verify related data updates (counts, timestamps, etc.)

**Input Validation:**
- [ ] Required fields: Submit empty, verify error messages
- [ ] Format validation: Invalid email, phone, dates
- [ ] Length limits: Too short, too long inputs
- [ ] Special characters: Quotes, unicode, SQL injection attempts
- [ ] Boundary values: 0, negative numbers, very large numbers

**Error Handling:**
- [ ] Network error: What happens if API fails?
- [ ] 404: Navigate to non-existent ID
- [ ] 403: Attempt unauthorized action
- [ ] Timeout: Slow network simulation
- [ ] Duplicate: Try creating duplicate entries

**Edge Cases:**
- [ ] Empty state: No data yet
- [ ] Single item: Just one entry
- [ ] Many items: 100+ entries (pagination, performance)
- [ ] Long text: Very long names/descriptions
- [ ] Concurrent: Multiple tabs, same action

### D. DATA INTEGRITY
- [ ] Create: Data appears in list immediately
- [ ] Read: Details page shows all fields correctly
- [ ] Update: Changes persist after refresh
- [ ] Delete: Item removed, related data cleaned up
- [ ] Relationships: Linked data updates correctly

### E. ACCESSIBILITY BASICS
- [ ] Tab navigation: Can reach all interactive elements
- [ ] Focus indicators: Visible focus ring
- [ ] Form labels: Inputs have associated labels
- [ ] Alt text: Images have descriptions
- [ ] Aria: Critical elements have aria labels

## STEP 4: Document Everything

For EACH issue found, record:
1. **What**: Exact description of the problem
2. **Where**: URL, element selector, component
3. **Steps**: How to reproduce
4. **Expected**: What should happen
5. **Actual**: What actually happens
6. **Severity**: Critical/High/Medium/Low
7. **Screenshot**: Visual evidence

## STEP 5: Evaluate Results

### If ALL checks PASS:
```bash
.agent/commands.sh success "{feature_id}" "Comprehensive QA passed - [summary of what was verified]"
git add -A
git commit -m "session: completed {feature_id}"
```

### If ANY issues found:

DO NOT mark complete. Create detailed fix features:

```bash
cat > fix-features-{feature_id}.json << 'EOF'
{{
  "generated_from": "{feature_id}",
  "generated_at": "$(date -Iseconds)",
  "qa_summary": "Brief summary of QA findings",
  "features": [
    {{
      "id": "fix-{feature_id}-001",
      "name": "Fix: [Specific UI/UX issue]",
      "description": "PROBLEM: [Exact issue observed]\\nLOCATION: [File/component path]\\nSTEPS TO REPRODUCE: [1. Go to... 2. Click...]\\nEXPECTED: [What should happen]\\nACTUAL: [What happens instead]\\nFIX APPROACH: [Suggested solution]",
      "priority": 50,
      "category": "bugfix",
      "severity": "high|medium|low",
      "qa_origin": "{feature_id}",
      "passes": false
    }},
    {{
      "id": "fix-{feature_id}-002",
      "name": "Add: [Missing functionality]",
      "description": "MISSING: [Feature that should exist but doesn't]\\nLOCATION: [Where it should be]\\nUSER STORY: [As a user, I should be able to...]\\nACCEPTANCE CRITERIA: [1. ... 2. ... 3. ...]\\nIMPLEMENTATION NOTES: [Technical suggestions]",
      "priority": 50,
      "category": "enhancement",
      "severity": "medium",
      "qa_origin": "{feature_id}",
      "passes": false
    }},
    {{
      "id": "fix-{feature_id}-003",
      "name": "Style: [Visual/CSS issue]",
      "description": "VISUAL ISSUE: [What looks wrong]\\nLOCATION: [Component/page]\\nVIEWPORT: [Desktop/tablet/mobile]\\nEXPECTED: [How it should look]\\nACTUAL: [How it looks]\\nCSS SUGGESTION: [Potential fix]",
      "priority": 55,
      "category": "styling",
      "severity": "low",
      "qa_origin": "{feature_id}",
      "passes": false
    }}
  ]
}}
EOF
```

Then merge into feature_list.json:
```bash
python3 << 'PYEOF'
import json

with open('feature_list.json') as f:
    main = json.load(f)

with open('fix-features-{feature_id}.json') as f:
    fixes = json.load(f)

# Add fixes (priority 50-55 runs before QA at 100+)
for fix in fixes['features']:
    # Avoid duplicates
    if not any(f['id'] == fix['id'] for f in main['features']):
        main['features'].append(fix)

with open('feature_list.json', 'w') as f:
    json.dump(main, f, indent=2)

print(f"Added {{len(fixes['features'])}} fix features from QA")
PYEOF
```

Record failures for context:
```bash
.agent/commands.sh failure "{feature_id}" "QA found issues - generated fix features"
```

Commit the findings:
```bash
git add -A
git commit -m "session: {feature_id} QA findings - generated fix features"
```

## CRITICAL QA RULES

1. **BE THOROUGH** - Check every element, every state, every edge case
2. **BE SPECIFIC** - Vague bug reports waste time. Include selectors, steps, evidence.
3. **BE SYSTEMATIC** - Follow the checklist. Don't skip sections.
4. **SCREENSHOT EVERYTHING** - Visual evidence prevents "works on my machine"
5. **TEST LIKE A USER** - What would confuse a real person?
6. **TEST LIKE A HACKER** - What inputs could break it?
7. **CATEGORIZE CORRECTLY**:
   - `bugfix`: Something broken that worked before or should work
   - `enhancement`: Missing feature that should exist
   - `styling`: Visual/CSS issues
   - `accessibility`: A11y problems
   - `performance`: Slow operations
8. **PRIORITIZE BY SEVERITY**:
   - Critical (priority 45): App crashes, data loss, security
   - High (priority 50): Major feature broken, blocker
   - Medium (priority 55): Feature degraded, workaround exists
   - Low (priority 60): Minor annoyance, cosmetic

## FINAL REMINDER

QA is quality ASSURANCE. Your job is to ensure this feature is production-ready.
- Pass ONLY if you're confident a real user would have a good experience
- Generate fix features for ANYTHING that's not right
- The feature stays incomplete until all issues are resolved"""

def build_implement_prompt(feature: Dict[str, Any], session_num: int) -> str:
    """Build the implementation prompt for a feature."""
    feature_id = feature.get('id', 'unknown')
    description = feature.get('description', '')
    category = feature.get('category', '').lower()
    
    # Check if this is a QA feature - use QA prompt instead
    if category == 'qa' or feature_id.startswith('qa-'):
        return build_qa_prompt(feature, session_num)
    
    # Detect complexity and get appropriate subagent instructions
    complexity = get_feature_complexity(feature)
    subagent_instructions = get_subagent_instructions(complexity, feature_id, description)
    
    # Adjust critical rules based on complexity
    if complexity == 'high':
        critical_rules = """## CRITICAL RULES
- DO use Ref MCP to look up docs before coding
- DO run cargo test before marking complete
- DO invoke all three subagents (@code-reviewer, @test-runner, @feature-verifier)
- DO NOT skip any steps
- DO NOT mark passes: true unless tests pass AND subagents verify
- DO NOT let any file exceed 500 lines - split into modules if needed
- If you find existing files over 500 lines, refactor them into smaller modules"""
    elif complexity == 'medium':
        critical_rules = """## CRITICAL RULES
- DO use Ref MCP to look up docs before coding
- DO run cargo test before marking complete
- DO invoke @test-runner to verify tests
- DO NOT mark passes: true unless tests pass
- DO NOT let any file exceed 500 lines - split into modules if needed
- If you find existing files over 500 lines, refactor them into smaller modules"""
    else:
        critical_rules = """## CRITICAL RULES
- DO run cargo test before marking complete
- DO NOT mark passes: true unless tests pass
- DO NOT let any file exceed 500 lines - split into modules if needed
- If you find existing files over 500 lines, refactor them into smaller modules"""
    
    return f"""Session {session_num}: Implement feature [{complexity.upper()} complexity]

## STEP 1: Compile Fresh Context
```bash
.agent/hooks/compile-context.sh
cat .agent/working-context/current.md
```

## STEP 2: Review Failures to Avoid
```bash
.agent/commands.sh recall failures
```

## STEP 3: Feature to Implement
{json.dumps(feature, indent=2)}

## STEP 4: Look Up Documentation (USE MCP - RECOMMENDED)
Before writing code for unfamiliar APIs, use Ref MCP to look up documentation.

Examples:
- "Use Ref to look up axum Router documentation"
- "Use Ref to look up sqlx query examples"

## STEP 5: Implement the Feature
Write the code.

## STEP 6: Run Tests (MANDATORY)
```bash
cargo test
```
If tests fail, fix them before proceeding.

{subagent_instructions}

## STEP 8: MARK COMPLETE (MANDATORY - DO NOT SKIP)
You MUST run these commands to mark the feature complete:
```bash
.agent/commands.sh success "{feature_id}" "brief description of what worked"
git add -A
git commit -m "session: completed {feature_id}"
```

⚠️ THE SESSION IS NOT COMPLETE UNTIL YOU RUN THE COMMANDS ABOVE ⚠️

{critical_rules}

## FINAL REMINDER
Your last action MUST be running the git commit. Do not just summarize - execute STEP 8.

If stuck after 3 attempts, mark as blocked and explain why."""

def build_continue_prompt(session_num: int) -> str:
    """Build prompt to continue work."""
    return f"""Session {session_num}: Continue implementation

FIRST: Compile fresh working context:
```bash
.agent/hooks/compile-context.sh
cat .agent/working-context/current.md
```

THEN: Check current status:
```bash
.agent/commands.sh status
cat feature_list.json | grep -c '"passes": false'
```

THEN: Review failures to avoid:
```bash
.agent/commands.sh recall failures
```

Find the next incomplete feature and implement it following the workflow in .agent/workflows/implement.md

Remember:
- One feature at a time
- Verify before marking complete
- Capture feedback (success/failure)
- Commit after each feature"""

def run_claude_code(
    project_path: Path,
    prompt: str,
    model: str = DEFAULT_MODEL,
    timeout: int = SESSION_TIMEOUT
) -> Dict[str, Any]:
    """Run Claude Code with the given prompt."""
    
    cmd = [
        "claude",
        "--print",
        "--model", model,
        "--permission-mode", "bypassPermissions",
        "--output-format", "text",
        prompt
    ]
    
    print_status(f"Running Claude Code ({model})...", "working")
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            cmd,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        elapsed = time.time() - start_time
        
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr,
            "elapsed": elapsed,
            "returncode": result.returncode
        }
    
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": f"Session timed out after {timeout}s",
            "elapsed": timeout,
            "returncode": -1
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "elapsed": time.time() - start_time,
            "returncode": -1
        }

def run_claude_code_interactive(
    project_path: Path,
    prompt: str,
    model: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    """Run Claude Code interactively (for complex sessions).
    
    Note: Claude Code uses MCPs registered via 'claude mcp add', 
    not a config file. Add MCPs before running.
    """
    global DEBUG
    
    # Ensure project_path is absolute
    project_path = Path(project_path).expanduser().resolve()
    
    # Write prompt to temp file
    prompt_file = project_path / ".agent" / "current-prompt.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt)
    
    # Build command as list (NOT shell string)
    # Claude Code uses MCPs from ~/.claude.json (added via 'claude mcp add')
    cmd = ["claude", "--model", model, "--permission-mode", "bypassPermissions"]
    
    # Use -p flag for prompt (safer than positional)
    cmd.append("-p")
    cmd.append(f"Read and execute the instructions in {prompt_file}")
    
    print_status(f"Starting Claude Code session ({model})...", "working")
    print_status("Press Ctrl+C when the session is complete", "info")
    
    if DEBUG:
        print_status(f"DEBUG cmd: {cmd}", "info")
    
    start_time = time.time()
    
    try:
        # Run as list (subprocess handles escaping)
        result = subprocess.run(
            cmd,
            cwd=str(project_path)
        )
        
        elapsed = time.time() - start_time
        
        return {
            "success": result.returncode == 0,
            "output": "Interactive session completed",
            "error": "",
            "elapsed": elapsed,
            "returncode": result.returncode
        }
    
    except KeyboardInterrupt:
        return {
            "success": True,
            "output": "Session ended by user",
            "error": "",
            "elapsed": time.time() - start_time,
            "returncode": 0
        }

# ============================================================================
# Session Logging
# ============================================================================

def log_session(project_path: Path, session_num: int, result: Dict[str, Any], feature: Optional[Dict] = None):
    """Log session results."""
    log_dir = project_path / ".agent" / "sessions"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"session-{session_num:03d}.json"
    
    log_entry = {
        "session": session_num,
        "timestamp": datetime.now().isoformat(),
        "feature": feature.get("id") if feature else None,
        "success": result["success"],
        "elapsed_seconds": result["elapsed"],
        "error": result.get("error", "")
    }
    
    with open(log_file, "w") as f:
        json.dump(log_entry, f, indent=2)
    
    # Also append to progress log
    progress_file = project_path / "agent-progress.txt"
    with open(progress_file, "a") as f:
        f.write(f"\n---\nSession: {session_num}\n")
        f.write(f"Timestamp: {log_entry['timestamp']}\n")
        f.write(f"Feature: {log_entry['feature']}\n")
        f.write(f"Success: {log_entry['success']}\n")
        f.write(f"Duration: {log_entry['elapsed_seconds']:.1f}s\n")
        if log_entry['error']:
            f.write(f"Error: {log_entry['error']}\n")

# ============================================================================
# Main Orchestration Loop
# ============================================================================

def orchestrate_new_project(info: Dict[str, Any], max_sessions: int = MAX_SESSIONS):
    """Orchestrate building a new project from scratch."""
    
    print_header("Starting Project Orchestration")
    
    # Create directory
    project_path = create_project_directory(info)
    
    # Initialize git
    subprocess.run(["git", "init"], cwd=project_path, capture_output=True)
    
    # Setup harness
    if not setup_harness(project_path):
        return
    
    # Setup MCPs via claude mcp add
    setup_mcps_interactive(project_path, info.get('mcp_preset'))
    
    # Session 1: Initialize project
    print_header("Session 1: Project Initialization")
    
    init_prompt = build_init_prompt(info)
    result = run_claude_code_interactive(project_path, init_prompt, info.get('model', DEFAULT_MODEL))
    log_session(project_path, 1, result)
    
    if not result["success"]:
        print_status(f"Initialization failed: {result['error']}", "error")
        return
    
    # Check if feature_list.json was created
    if not (project_path / "feature_list.json").exists():
        print_status("feature_list.json not created. Running init again...", "warning")
        result = run_claude_code_interactive(project_path, init_prompt, info.get('model', DEFAULT_MODEL))
        log_session(project_path, 1, result)
    
    # Main implementation loop
    orchestrate_implementation(project_path, info.get('model', DEFAULT_MODEL), start_session=2, max_sessions=max_sessions)

def orchestrate_implementation(project_path: Path, model: str = DEFAULT_MODEL, start_session: int = 1, max_sessions: int = MAX_SESSIONS):
    """Main loop to implement all features."""
    
    session_num = start_session
    consecutive_failures = 0
    max_consecutive_failures = 3
    
    while session_num <= max_sessions:
        # Sync feature_list.json with git history (fixes missed updates)
        sync_features_with_git(project_path)
        
        # Get current status
        status = get_feature_status(project_path)
        
        print_header(f"Session {session_num}")
        print_progress(status["completed"], status["total"], "Features")
        
        # Check if done
        if status["remaining"] == 0:
            print_status("🎉 All features completed!", "success")
            break
        
        if status["remaining"] == status["blocked"]:
            print_status("All remaining features are blocked", "warning")
            print_status("Manual intervention required", "info")
            break
        
        # Get next feature
        feature = get_next_feature(project_path)
        
        if not feature:
            print_status("No eligible features found (check dependencies)", "warning")
            break
        
        print_status(f"Implementing: {feature.get('id')} - {feature.get('description', '')[:50]}...", "working")
        
        # Build prompt and run
        prompt = build_implement_prompt(feature, session_num)
        result = run_claude_code_interactive(project_path, prompt, model)
        log_session(project_path, session_num, result, feature)
        
        # Check result
        new_status = get_feature_status(project_path)
        
        if new_status["completed"] > status["completed"]:
            print_status(f"Feature completed: {feature.get('id')}", "success")
            consecutive_failures = 0
        else:
            print_status(f"Feature not completed: {feature.get('id')}", "warning")
            consecutive_failures += 1
        
        if consecutive_failures >= max_consecutive_failures:
            print_status(f"Too many consecutive failures ({consecutive_failures})", "error")
            
            # Ask to continue or abort
            choice = input(f"\n{Colors.CYAN}Continue anyway? [y/N]:{Colors.END} ").strip().lower()
            if choice != 'y':
                break
            consecutive_failures = 0
        
        session_num += 1
        
        # Brief pause between sessions
        time.sleep(2)
    
    # Final status
    final_status = get_feature_status(project_path)
    print_header("Orchestration Complete")
    print_progress(final_status["completed"], final_status["total"], "Final Status")
    
    if final_status["blocked"] > 0:
        print_status(f"{final_status['blocked']} features are blocked", "warning")
    
    print_status(f"Project location: {project_path}", "info")
    print_status(f"Total sessions: {session_num - 1}", "info")

def orchestrate_continue(project_path: Path, model: str = DEFAULT_MODEL, max_sessions: int = MAX_SESSIONS):
    """Continue orchestration on existing project."""
    
    if not (project_path / "feature_list.json").exists():
        print_status("No feature_list.json found. Is this project initialized?", "error")
        return
    
    # Check MCPs are configured
    result = subprocess.run(
        ["claude", "mcp", "list"],
        cwd=str(project_path),
        capture_output=True,
        text=True
    )
    if "No MCP servers configured" in result.stdout:
        print_status("No MCPs configured. Add them with 'claude mcp add'", "warning")
    
    # Determine starting session number
    sessions_dir = project_path / ".agent" / "sessions"
    if sessions_dir.exists():
        existing = list(sessions_dir.glob("session-*.json"))
        start_session = len(existing) + 1
    else:
        start_session = 1
    
    print_status(f"Continuing from session {start_session}", "info")
    orchestrate_implementation(project_path, model, start_session, max_sessions)

# ============================================================================
# CLI Interface
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Context-Engineered Agent Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python orchestrator.py                     # Interactive new project setup
  python orchestrator.py --project ~/myapp   # Continue existing project
  python orchestrator.py --new ~/myapp       # New project at path
  python orchestrator.py --model opus        # Use Opus model
        """
    )
    
    parser.add_argument("--project", "-p", type=Path, help="Project path to continue")
    parser.add_argument("--new", type=Path, help="Create new project at path")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL, help="Model to use (sonnet/opus)")
    parser.add_argument("--max-sessions", type=int, default=MAX_SESSIONS, help="Max sessions (default: 100)")
    parser.add_argument("--continue", "-c", dest="cont", action="store_true", help="Continue existing project")
    parser.add_argument("--status", "-s", action="store_true", help="Show project status and exit")
    parser.add_argument("--mcp-preset", choices=["web", "fullstack", "data", "devops", "minimal", "rust", "python", "node", "docs"], help="Use MCP preset")
    parser.add_argument("--with-qa", action="store_true", help="Generate E2E QA features using Playwright")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run sessions interactively (default)")
    parser.add_argument("--debug", "-d", action="store_true", help="Show debug output")
    
    args = parser.parse_args()
    
    # Set global debug flag
    global DEBUG
    DEBUG = args.debug
    
    print_header("Context-Engineered Agent Orchestrator")
    
    # Check Claude Code is installed
    if subprocess.run(["which", "claude"], capture_output=True).returncode != 0:
        print_status("Claude Code not found. Install from: https://docs.anthropic.com/claude-code", "error")
        sys.exit(1)
    
    # Status mode
    if args.status:
        project_path = args.project or Path.cwd()
        status = get_feature_status(project_path)
        print_progress(status["completed"], status["total"])
        print(f"  Blocked: {status['blocked']}")
        sys.exit(0)
    
    # Continue existing project
    if args.cont or args.project:
        project_path = args.project or Path.cwd()
        if not project_path.exists():
            print_status(f"Project not found: {project_path}", "error")
            sys.exit(1)
        orchestrate_continue(project_path, args.model, args.max_sessions)
        return
    
    # New project at specific path (skip menu!)
    if args.new:
        print_status(f"Creating new project at: {args.new}", "info")
        info = get_project_info_interactive(preset_path=args.new, preset_model=args.model)
        info['mcp_preset'] = args.mcp_preset
        info['include_qa'] = args.with_qa
        orchestrate_new_project(info, args.max_sessions)
        return
    
    # Interactive mode - show menu
    print("What would you like to do?")
    print("  1. Start a new project")
    print("  2. Continue an existing project")
    
    choice = input(f"\n{Colors.CYAN}Select [1-2]:{Colors.END} ").strip()
    
    if choice == "1":
        info = get_project_info_interactive(preset_model=args.model)
        info['mcp_preset'] = args.mcp_preset
        info['include_qa'] = args.with_qa
        orchestrate_new_project(info, args.max_sessions)
    elif choice == "2":
        path_input = input(f"{Colors.CYAN}Project path:{Colors.END} ").strip()
        project_path = Path(path_input).expanduser()
        if not project_path.exists():
            print_status(f"Project not found: {project_path}", "error")
            sys.exit(1)
        orchestrate_continue(project_path, args.model, args.max_sessions)
    else:
        print_status("Invalid choice", "error")
        sys.exit(1)

if __name__ == "__main__":
    main()
