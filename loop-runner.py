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
from collections import deque

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_MODEL = "sonnet"
MAX_SESSIONS = 100
PAUSE_BETWEEN_SESSIONS = 3  # seconds

# ============================================================================
# Feature List Validation
# ============================================================================

REQUIRED_FIELDS = ['id', 'name', 'description']
OPTIONAL_FIELDS = ['priority', 'category', 'passes', 'blocked', 'blocked_reason', 
                   'blocked_by', 'suggested_fix', 'dependencies', 'tests', 
                   'complexity', 'needs_review', 'qa_origin', 'severity']

def validate_feature_list(project_path: Path) -> dict:
    """
    Validate feature_list.json for schema, missing fields, circular deps.
    Returns: {"valid": bool, "errors": [], "warnings": []}
    """
    result = {"valid": True, "errors": [], "warnings": []}
    feature_file = project_path / "feature_list.json"
    
    if not feature_file.exists():
        result["valid"] = False
        result["errors"].append("feature_list.json not found")
        return result
    
    try:
        with open(feature_file) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result["valid"] = False
        result["errors"].append(f"Invalid JSON: {e}")
        return result
    
    features = data.get("features", [])
    if not features:
        result["valid"] = False
        result["errors"].append("No features defined")
        return result
    
    feature_ids = set()
    
    for i, feat in enumerate(features):
        feat_id = feat.get('id', f'feature_{i}')
        
        # Check required fields
        for field in REQUIRED_FIELDS:
            if field not in feat:
                result["errors"].append(f"Feature '{feat_id}' missing required field: {field}")
                result["valid"] = False
        
        # Check for duplicate IDs
        if feat_id in feature_ids:
            result["errors"].append(f"Duplicate feature ID: {feat_id}")
            result["valid"] = False
        feature_ids.add(feat_id)
        
        # Validate priority
        priority = feat.get('priority')
        if priority is not None and not isinstance(priority, (int, float)):
            result["warnings"].append(f"Feature '{feat_id}' has non-numeric priority: {priority}")
        
        # Validate complexity override
        complexity = feat.get('complexity', '').lower()
        if complexity and complexity not in ('high', 'medium', 'low'):
            result["warnings"].append(f"Feature '{feat_id}' has invalid complexity: {complexity}")
        
        # Check dependencies exist
        deps = feat.get('dependencies', [])
        for dep in deps:
            if dep not in feature_ids and dep not in [f.get('id') for f in features]:
                result["warnings"].append(f"Feature '{feat_id}' depends on unknown feature: {dep}")
    
    # Check for circular dependencies
    circular = detect_circular_dependencies(features)
    if circular:
        result["errors"].append(f"Circular dependencies detected: {' -> '.join(circular)}")
        result["valid"] = False
    
    return result

def detect_circular_dependencies(features: list) -> list:
    """
    Detect circular dependencies using DFS.
    Returns: List of feature IDs in the cycle, or empty list if no cycle.
    """
    # Build adjacency list
    graph = {}
    for feat in features:
        feat_id = feat.get('id', '')
        graph[feat_id] = feat.get('dependencies', [])
    
    visited = set()
    rec_stack = set()
    path = []
    
    def dfs(node):
        visited.add(node)
        rec_stack.add(node)
        path.append(node)
        
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                cycle = dfs(neighbor)
                if cycle:
                    return cycle
            elif neighbor in rec_stack:
                # Found cycle
                cycle_start = path.index(neighbor)
                return path[cycle_start:] + [neighbor]
        
        path.pop()
        rec_stack.remove(node)
        return None
    
    for node in graph:
        if node not in visited:
            cycle = dfs(node)
            if cycle:
                return cycle
    
    return []

# ============================================================================
# Topological Sort for Dependencies
# ============================================================================

def topological_sort_features(features: list) -> list:
    """
    Sort features respecting dependencies (Kahn's algorithm).
    Features with satisfied dependencies come first.
    Falls back to priority sort if no dependencies.
    """
    # Build graph
    in_degree = {}
    graph = {}
    feat_map = {}
    
    for feat in features:
        feat_id = feat.get('id', '')
        feat_map[feat_id] = feat
        in_degree[feat_id] = 0
        graph[feat_id] = []
    
    # Count incoming edges (dependencies)
    for feat in features:
        feat_id = feat.get('id', '')
        deps = feat.get('dependencies', [])
        for dep in deps:
            if dep in graph:
                graph[dep].append(feat_id)
                in_degree[feat_id] += 1
    
    # Start with features that have no unmet dependencies
    queue = deque()
    for feat_id, degree in in_degree.items():
        if degree == 0:
            queue.append(feat_id)
    
    # Sort by priority within the queue
    sorted_result = []
    while queue:
        # Sort current batch by priority
        batch = sorted(queue, key=lambda x: feat_map[x].get('priority', 99))
        queue.clear()
        
        for feat_id in batch:
            sorted_result.append(feat_map[feat_id])
            
            # Reduce in-degree for dependent features
            for neighbor in graph.get(feat_id, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
    
    # If some features weren't sorted (cycle), add them at the end
    if len(sorted_result) < len(features):
        sorted_ids = {f.get('id') for f in sorted_result}
        for feat in features:
            if feat.get('id') not in sorted_ids:
                sorted_result.append(feat)
    
    return sorted_result

# ============================================================================
# Enhanced Blocked Workflow
# ============================================================================

def mark_feature_blocked(project_path: Path, feature_id: str, reason: str, 
                         blocked_by: list = None, suggested_fix: str = None):
    """
    Mark a feature as blocked with detailed information.
    """
    feature_file = project_path / "feature_list.json"
    
    try:
        with open(feature_file) as f:
            data = json.load(f)
        
        for feat in data.get("features", []):
            if feat.get("id") == feature_id:
                feat["blocked"] = True
                feat["blocked_reason"] = reason
                feat["blocked_at"] = datetime.now().isoformat()
                if blocked_by:
                    feat["blocked_by"] = blocked_by
                if suggested_fix:
                    feat["suggested_fix"] = suggested_fix
                break
        
        with open(feature_file, "w") as f:
            json.dump(data, f, indent=2)
            
    except Exception as e:
        print(f"Error marking feature blocked: {e}")

def unblock_feature(project_path: Path, feature_id: str):
    """
    Unblock a feature, clearing blocked metadata.
    """
    feature_file = project_path / "feature_list.json"
    
    try:
        with open(feature_file) as f:
            data = json.load(f)
        
        for feat in data.get("features", []):
            if feat.get("id") == feature_id:
                feat["blocked"] = False
                feat.pop("blocked_reason", None)
                feat.pop("blocked_at", None)
                feat.pop("blocked_by", None)
                feat.pop("suggested_fix", None)
                break
        
        with open(feature_file, "w") as f:
            json.dump(data, f, indent=2)
            
    except Exception as e:
        print(f"Error unblocking feature: {e}")

def get_blocked_features(project_path: Path) -> list:
    """
    Get all blocked features with their details.
    """
    feature_file = project_path / "feature_list.json"
    blocked = []
    
    try:
        with open(feature_file) as f:
            data = json.load(f)
        
        for feat in data.get("features", []):
            if feat.get("blocked"):
                blocked.append({
                    "id": feat.get("id"),
                    "name": feat.get("name"),
                    "reason": feat.get("blocked_reason", "Unknown"),
                    "blocked_by": feat.get("blocked_by", []),
                    "suggested_fix": feat.get("suggested_fix", ""),
                    "blocked_at": feat.get("blocked_at", "")
                })
    except:
        pass
    
    return blocked

def check_needs_review(feature: dict) -> bool:
    """
    Check if a feature requires human review before proceeding.
    """
    return feature.get("needs_review", False)

# ============================================================================
# Metrics & Session Artifacts
# ============================================================================

def track_metrics(project_path: Path, event: str, feature_id: str, extra: str = None):
    """
    Track metrics for feedback loops.
    Calls the .agent/hooks/track-metrics.sh script if it exists.
    """
    metrics_script = project_path / ".agent" / "hooks" / "track-metrics.sh"
    if metrics_script.exists():
        cmd = ["bash", str(metrics_script), event, feature_id]
        if extra:
            cmd.append(extra)
        subprocess.run(cmd, cwd=str(project_path), capture_output=True)

def save_session_diff(project_path: Path, session_num: int, feature_id: str):
    """
    Save a diff artifact for the current session.
    Calls the .agent/hooks/save-session-diff.sh script if it exists.
    """
    diff_script = project_path / ".agent" / "hooks" / "save-session-diff.sh"
    if diff_script.exists():
        subprocess.run(
            ["bash", str(diff_script), str(session_num), feature_id],
            cwd=str(project_path),
            capture_output=True
        )

def print_metrics_report(project_path: Path):
    """
    Print a metrics report at the end of a run.
    """
    report_script = project_path / ".agent" / "hooks" / "metrics-report.sh"
    if report_script.exists():
        result = subprocess.run(
            ["bash", str(report_script)],
            cwd=str(project_path),
            capture_output=True,
            text=True
        )
        if result.stdout:
            print(result.stdout)

# ============================================================================
# Feature Complexity Detection
# ============================================================================

def get_feature_complexity(feature: dict) -> str:
    """
    Estimate feature complexity to determine subagent requirements.
    Returns: 'high', 'medium', or 'low'
    
    Can be overridden by setting "complexity" field in feature_list.json
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
    high_keywords = [
        'security', 'crypto', 'encrypt', 'auth', 'credential', 'password',
        'ssh', 'certificate', 'token', 'session', 'permission', 'rbac',
        'injection', 'sanitize', 'validate', 'vulnerability'
    ]
    for keyword in high_keywords:
        if keyword in description or keyword in category or keyword in name:
            signals += 2
            break
    
    if len(feature.get('dependencies', [])) > 3:
        signals += 1
    if len(feature.get('tests', [])) > 5:
        signals += 1
    
    # Medium complexity signals
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
    
    if signals >= 3:
        return 'high'
    elif signals <= 0:
        return 'low'
    return 'medium'

def get_subagent_instructions(complexity: str, feature_id: str, description: str, test_cmd: str) -> str:
    """Generate subagent instructions based on complexity level."""
    
    if complexity == 'high':
        return f"""## STEP 7: Invoke Subagents (MANDATORY - High Complexity)
You MUST invoke these subagents:

### Code Review
```
@code-reviewer Review the changes for feature {feature_id}
```
Wait for review. Address any issues.

### Test Runner
```
@test-runner Run the test suite and analyze results
```

### Feature Verifier
```
@feature-verifier Verify feature {feature_id}: {description}
```

After all subagents pass, proceed to STEP 8."""

    elif complexity == 'medium':
        return f"""## STEP 7: Verify Tests (Medium Complexity)
```
@test-runner Run the test suite and analyze results
```

After tests pass, proceed to STEP 8."""

    else:  # low
        return f"""## STEP 7: Verify Tests (Low Complexity)
Tests should already pass from STEP 6. If they do, proceed directly to STEP 8.
No subagent review needed for simple changes - just mark complete."""

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

def get_next_feature(project_path: Path, skip_needs_review: bool = False) -> dict | None:
    """
    Get next feature to implement, respecting dependencies.
    
    Uses topological sort to ensure dependencies are completed first.
    Optionally skips features marked needs_review (for unattended runs).
    """
    feature_file = project_path / "feature_list.json"
    
    if not feature_file.exists():
        return None
    
    try:
        with open(feature_file) as f:
            data = json.load(f)
        
        features = data.get("features", [])
        
        # Get completed feature IDs
        completed_ids = {f.get("id") for f in features if f.get("passes", False)}
        
        # Sort features respecting dependencies
        sorted_features = topological_sort_features(features)
        
        for feat in sorted_features:
            # Skip completed or blocked
            if feat.get("passes", False) or feat.get("blocked", False):
                continue
            
            # Check dependencies are met
            deps = feat.get("dependencies", [])
            deps_met = all(dep in completed_ids for dep in deps)
            if not deps_met:
                continue
            
            # Skip needs_review if in unattended mode
            if skip_needs_review and feat.get("needs_review", False):
                continue
            
            return feat
        
        return None
    except:
        return None

def get_features_needing_review(project_path: Path) -> list:
    """Get features that need human review before proceeding."""
    feature_file = project_path / "feature_list.json"
    needs_review = []
    
    try:
        with open(feature_file) as f:
            data = json.load(f)
        
        completed_ids = {f.get("id") for f in data.get("features", []) if f.get("passes", False)}
        
        for feat in data.get("features", []):
            if feat.get("needs_review") and not feat.get("passes") and not feat.get("blocked"):
                # Check if dependencies are met
                deps = feat.get("dependencies", [])
                if all(dep in completed_ids for dep in deps):
                    needs_review.append(feat)
    except:
        pass
    
    return needs_review

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

# Global QA mode setting
QA_MODE = "full"  # "full" or "lite"

def build_lite_qa_prompt(feature: dict, session_num: int) -> str:
    """Build a lighter QA prompt for faster testing."""
    feature_id = feature.get("id", "unknown")
    
    return f"""Session {session_num}: Quick QA Testing

## Feature Under Test
{json.dumps(feature, indent=2)}

## STEP 1: Setup
Ensure the app is running and accessible.

## STEP 2: Core Testing (Focus on Happy Path)

Use Playwright MCP to test:

1. **Load & Visual** - Page loads without errors, main elements visible
2. **Happy Path** - Primary action works end-to-end
3. **Data Persistence** - Refresh and verify data persists
4. **Basic Validation** - Submit empty/invalid, verify error messages

## STEP 3: Evaluate

### If tests PASS:
```bash
.agent/commands.sh success "{feature_id}" "QA passed - core functionality verified"
git add -A
git commit -m "session: completed {feature_id}"
```

### If issues found:
Create fix feature(s) with details:
```bash
cat > fix-features-{feature_id}.json << 'EOF'
{{
  "features": [
    {{
      "id": "fix-{feature_id}-001",
      "name": "Fix: [issue description]",
      "description": "PROBLEM: ...\\nLOCATION: ...\\nFIX: ...",
      "priority": 50,
      "category": "bugfix",
      "qa_origin": "{feature_id}",
      "passes": false
    }}
  ]
}}
EOF
```
Then merge and commit (do NOT mark QA complete).
"""

def build_qa_prompt(feature: dict, session_num: int, project_path: Path, mode: str = None) -> str:
    """Build QA prompt based on mode (full or lite)."""
    if mode is None:
        mode = QA_MODE
    
    if mode == "lite":
        return build_lite_qa_prompt(feature, session_num)
    
    # Full comprehensive QA prompt
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
git log --oneline --grep="{feature_id}" | head -5

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
git commit -m "session: {feature_id} QA findings - generated $(cat fix-features-{feature_id}.json | python3 -c 'import json,sys; print(len(json.load(sys.stdin)[\"features\"]))') fix features"
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

def run_session(project_path: Path, session_num: int, model: str) -> bool:
    """Run a single Claude Code session.
    
    Note: Claude Code uses MCPs registered via 'claude mcp add'.
    """
    
    feature = get_next_feature(project_path)
    
    if not feature:
        return False
    
    feature_id = feature.get("id", "unknown")
    feature_desc = feature.get("description", "")
    feature_desc_short = feature_desc[:50]
    feature_category = feature.get("category", "").lower()
    
    # Start session timer for metrics
    start_timer_script = project_path / ".agent" / "hooks" / "start-session-timer.sh"
    if start_timer_script.exists():
        subprocess.run(["bash", str(start_timer_script)], cwd=str(project_path), capture_output=True)
    
    # Track session start
    track_metrics(project_path, "session_start", feature_id)
    
    # Check if this is a QA feature
    is_qa_feature = feature_category == "qa" or feature_id.startswith("qa-")
    is_qa_feature = feature_category == "qa" or feature_id.startswith("qa-")
    
    if is_qa_feature:
        print(f"🎭 QA Testing: {cyan(feature_id)} - {feature_desc_short}...")
        prompt = build_qa_prompt(feature, session_num, project_path)
    else:
        # Detect complexity for smart subagent usage
        complexity = get_feature_complexity(feature)
        test_cmd = detect_test_command(project_path)
        subagent_instructions = get_subagent_instructions(complexity, feature_id, feature_desc, test_cmd)
        
        print(f"🔧 Implementing: {cyan(feature_id)} [{complexity.upper()}] - {feature_desc_short}...")
        
        # Adjust critical rules based on complexity
        if complexity == 'high':
            critical_rules = """## CRITICAL RULES
- DO use MCP tools (especially Ref) to look up documentation
- DO NOT guess at APIs - look them up first
- DO NOT mark passes: true unless tests actually pass
- DO NOT skip the subagents (@code-reviewer, @test-runner, @feature-verifier)
- DO NOT let any file exceed 500 lines - split into modules if needed
- If you find existing files over 500 lines, refactor them into smaller modules
- If tests fail after 3 attempts, mark feature as blocked"""
        elif complexity == 'medium':
            critical_rules = """## CRITICAL RULES
- DO use MCP tools for unfamiliar APIs
- DO NOT mark passes: true unless tests pass
- DO invoke @test-runner to verify
- DO NOT let any file exceed 500 lines - split into modules if needed
- If you find existing files over 500 lines, refactor them into smaller modules
- If tests fail after 3 attempts, mark feature as blocked"""
        else:
            critical_rules = """## CRITICAL RULES
- DO NOT mark passes: true unless tests pass
- DO NOT let any file exceed 500 lines - split into modules if needed
- If you find existing files over 500 lines, refactor them into smaller modules
- If tests fail after 3 attempts, mark feature as blocked"""
        
        # Build the prompt with complexity-aware subagent requirements
        prompt = f"""Session {session_num}: Implement feature [{complexity.upper()} complexity]

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
For unfamiliar APIs, use Ref MCP to look up documentation.

## STEP 5: Implement the Feature
Write the code for this feature.

## STEP 6: RUN TESTS (MANDATORY)
```bash
{test_cmd}
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
Your last action MUST be running the git commit. Do not just summarize - execute STEP 8."""

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
    global QA_MODE
    parser = argparse.ArgumentParser(description="Autonomous Claude Code Loop Runner")
    parser.add_argument("project", nargs="?", type=Path, default=Path.cwd(), help="Project path")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL, help="Model (sonnet/opus)")
    parser.add_argument("--max-sessions", "-n", type=int, default=MAX_SESSIONS, help="Max sessions")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run interactively (opens shell)")
    parser.add_argument("--skip-review", action="store_true", help="Skip features marked needs_review")
    parser.add_argument("--validate", action="store_true", help="Validate feature_list.json and exit")
    parser.add_argument("--show-blocked", action="store_true", help="Show blocked features and exit")
    parser.add_argument("--unblock", type=str, help="Unblock a feature by ID")
    parser.add_argument("--qa-mode", choices=["full", "lite"], default="full", 
                        help="QA testing mode: full (comprehensive) or lite (quick)")
    parser.add_argument("--metrics", action="store_true", help="Show metrics report and exit")
    args = parser.parse_args()
    
    # Set QA mode
    QA_MODE = args.qa_mode
    
    project_path = args.project.expanduser().resolve()
    
    if not project_path.exists():
        print(red(f"Project not found: {project_path}"))
        sys.exit(1)
    
    # Handle metrics report first (doesn't need feature_list)
    if args.metrics:
        print_metrics_report(project_path)
        sys.exit(0)
    
    if not (project_path / "feature_list.json").exists():
        print(red("No feature_list.json found. Initialize project first."))
        sys.exit(1)
    
    # Validate feature list
    validation = validate_feature_list(project_path)
    if args.validate:
        print(bold("\n📋 Feature List Validation"))
        if validation["valid"]:
            print(green("✅ Valid"))
        else:
            print(red("❌ Invalid"))
        for err in validation["errors"]:
            print(red(f"  ERROR: {err}"))
        for warn in validation["warnings"]:
            print(yellow(f"  WARNING: {warn}"))
        sys.exit(0 if validation["valid"] else 1)
    
    # Show blocked features
    if args.show_blocked:
        blocked = get_blocked_features(project_path)
        print(bold("\n🚫 Blocked Features"))
        if not blocked:
            print(green("  No blocked features"))
        else:
            for b in blocked:
                print(f"\n  {red(b['id'])}: {b['name']}")
                print(f"    Reason: {b['reason']}")
                if b['blocked_by']:
                    print(f"    Blocked by: {', '.join(b['blocked_by'])}")
                if b['suggested_fix']:
                    print(f"    Suggested fix: {b['suggested_fix']}")
        sys.exit(0)
    
    # Unblock a feature
    if args.unblock:
        unblock_feature(project_path, args.unblock)
        print(green(f"✅ Unblocked: {args.unblock}"))
        sys.exit(0)
    
    # Check for validation errors
    if not validation["valid"]:
        print(red("\n❌ Feature list validation failed:"))
        for err in validation["errors"]:
            print(red(f"  - {err}"))
        print("\nFix errors before running. Use --validate for details.")
        sys.exit(1)
    
    # Show warnings
    if validation["warnings"]:
        print(yellow("\n⚠️  Feature list warnings:"))
        for warn in validation["warnings"]:
            print(yellow(f"  - {warn}"))
    
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
    if args.skip_review:
        print(f"   Skip review: {yellow('Yes - features with needs_review will be skipped')}")
    
    # Check for features needing review
    needs_review = get_features_needing_review(project_path)
    if needs_review and not args.skip_review:
        print(yellow(f"\n⚠️  {len(needs_review)} feature(s) need human review:"))
        for feat in needs_review:
            print(yellow(f"   - {feat.get('id')}: {feat.get('name')}"))
        print("\nUse --skip-review to skip these, or review and unset needs_review.")
    
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
            blocked = get_blocked_features(project_path)
            for b in blocked[:3]:  # Show first 3
                print(f"   {b['id']}: {b['reason']}")
            print("   Use --show-blocked for details, --unblock <id> to unblock")
            break
        
        # Check if only needs_review features remain
        next_feat = get_next_feature(project_path, skip_needs_review=args.skip_review)
        if not next_feat:
            needs_review = get_features_needing_review(project_path)
            if needs_review:
                print(yellow("\n⏸️  Remaining features need human review:"))
                for feat in needs_review:
                    print(yellow(f"   - {feat.get('id')}: {feat.get('name')}"))
                print("\nReview these features and unset needs_review to continue.")
            break
        
        # Run session
        before_completed = status["completed"]
        
        if args.interactive:
            # Interactive mode
            import shlex
            feature = get_next_feature(project_path, skip_needs_review=args.skip_review)
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
        
        # Check if QA generated fix features (count new features added)
        features_added = new_status["total"] - status["total"]
        
        # Run independent test verification
        print(f"\n  📋 Post-session verification...")
        verification = verify_session_result(project_path)
        
        if new_status["completed"] > before_completed:
            if verification["tests_passed"]:
                print(green(f"✅ Feature completed and verified! ({new_status['completed']}/{new_status['total']})"))
            else:
                print(yellow(f"⚠️ Feature marked complete but tests failing!"))
            # Track metrics
            track_metrics(project_path, "feature_complete", feature_id if feature else "unknown")
            track_metrics(project_path, "session_complete", feature_id if feature else "unknown")
            save_session_diff(project_path, session, feature_id if feature else "unknown")
            consecutive_failures = 0
        elif features_added > 0:
            # QA generated fix features - this is progress!
            print(yellow(f"🔧 QA generated {features_added} fix feature(s) - will implement before retrying QA"))
            track_metrics(project_path, "qa_generated_fixes", feature_id if feature else "unknown", str(features_added))
            consecutive_failures = 0  # Reset - this is productive work
        else:
            # Tests passed but feature not marked - auto-complete it
            if verification["tests_passed"]:
                current_feature = get_next_feature(project_path)
                if current_feature:
                    feature_id = current_feature.get("id", "unknown")
                    feature_category = current_feature.get("category", "").lower()
                    
                    # Don't auto-complete QA features - they need explicit pass
                    if feature_category == "qa" or feature_id.startswith("qa-"):
                        print(yellow(f"⚠️  QA feature {feature_id} - waiting for explicit completion"))
                        track_metrics(project_path, "qa_awaiting_explicit", feature_id)
                        consecutive_failures += 1
                    else:
                        print(yellow(f"⚠️  Tests passed but feature not marked - auto-completing {feature_id}"))
                        
                        # Mark feature as passed
                        try:
                            feature_file = project_path / "feature_list.json"
                            with open(feature_file) as f:
                                data = json.load(f)
                            for feat in data.get("features", []):
                                if feat.get("id") == feature_id:
                                    feat["passes"] = True
                                    break
                            with open(feature_file, "w") as f:
                                json.dump(data, f, indent=2)
                            
                            # Commit
                            subprocess.run(["git", "add", "-A"], cwd=project_path, capture_output=True)
                            subprocess.run(
                                ["git", "commit", "-m", f"session: completed {feature_id} (auto-completed by harness)"],
                                cwd=project_path, capture_output=True
                            )
                            print(green(f"✅ Auto-completed {feature_id}"))
                            
                            # Track metrics
                            track_metrics(project_path, "feature_complete", feature_id)
                            track_metrics(project_path, "session_complete", feature_id)
                            save_session_diff(project_path, session, feature_id)
                            
                            consecutive_failures = 0
                            
                            # Update status
                            new_status = get_feature_status(project_path)
                        except Exception as e:
                            print(red(f"❌ Auto-complete failed: {e}"))
                            track_metrics(project_path, "auto_complete_failed", feature_id, str(e))
                            consecutive_failures += 1
                else:
                    print(yellow("⚠️  No progress this session"))
                    track_metrics(project_path, "no_progress", feature_id if feature else "unknown")
                    consecutive_failures += 1
            else:
                print(yellow("⚠️  No progress this session"))
                track_metrics(project_path, "no_progress", feature_id if feature else "unknown")
                consecutive_failures += 1
        
        if consecutive_failures >= 3:
            print(red("\n❌ Too many consecutive failures"))
            track_metrics(project_path, "consecutive_failures", "3")
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
    
    # Print metrics report
    print_metrics_report(project_path)

if __name__ == "__main__":
    main()
