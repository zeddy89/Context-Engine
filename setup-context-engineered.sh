#!/bin/bash
# ============================================================================
# Context-Engineered Agent Harness v3.0
# Based on research from Google ADK, Stanford ACE, and Manus
# Implements the four-layer memory model and nine scaling principles
# ============================================================================

set -e

HARNESS_VERSION="3.0.0"

echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║       Context-Engineered Agent Harness v${HARNESS_VERSION}                       ║"
echo "║       Based on Google ADK, Stanford ACE, and Manus Research            ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "Setting up in: $(pwd)"
echo ""

# ============================================================================
# Four-Layer Memory Architecture
# ============================================================================
# Layer 1: Working Context - Computed view sent to model (minimal)
# Layer 2: Sessions - Full structured event log
# Layer 3: Memory - Searchable knowledge, retrieved on demand  
# Layer 4: Artifacts - Large objects stored by reference
# ============================================================================

echo "📁 Creating four-layer memory architecture..."

mkdir -p .agent/{working-context,sessions,memory,artifacts}
mkdir -p .agent/{workflows,rules,hooks,templates,subagents,metrics}
mkdir -p .agent/memory/{strategies,constraints,failures,entities}
mkdir -p .agent/artifacts/{tool-outputs,documents,code-snapshots}

# ============================================================================
# Core Rules - Context Engineering Principles
# ============================================================================
echo "📜 Creating context engineering rules..."

cat > .agent/AGENT_RULES.md << 'EOF'
# Context Engineering Rules

Based on research from Google ADK, Stanford ACE, and Manus on building reliable long-running agents.

## The Core Problem

Agents degrade over time not because they run out of memory, but because **every token competes for attention**. Stuff 100K tokens of history into the window and the model's ability to reason about what actually matters degrades.

## Four-Layer Memory Model

### Layer 1: Working Context (Cache - Expensive, Limited)
What actually gets sent to the model on each call.
- Should be as SMALL as possible while remaining sufficient
- Computed fresh for each step, not accumulated
- Contains: current task, relevant constraints, necessary context only

### Layer 2: Sessions (RAM - Larger, Bounded)
Structured event log of everything that happened.
- Full history in typed records (not raw prompts)
- Source of truth for reconstruction
- Never sent directly to model - used to compute working context

### Layer 3: Memory (Disk - Searchable)
Queryable knowledge retrieved on demand.
- Strategies that worked
- Constraints still active
- Failures to avoid
- Key entities and references

### Layer 4: Artifacts (External Storage)
Large objects stored by reference.
- Tool outputs written to files
- Code snapshots
- Documents
- Model sees pointers, not content

## Nine Scaling Principles

### 1. Context is Computed, Not Accumulated
Every LLM call gets a freshly computed view. Ask:
- What's relevant NOW?
- What instructions apply NOW?
- Which artifacts matter NOW?

❌ Wrong: Append everything to growing transcript
✅ Right: Compute minimal relevant context per step

### 2. Separate Storage from Presentation
- Sessions store everything (full fidelity)
- Working context is computed subset (optimized for decision)
- Compilation logic can change without touching storage

### 3. Scope by Default
- Default context contains nearly nothing
- Information enters through explicit retrieval
- Forces agent to decide what's worth including

### 4. Retrieval Over Pinning
- Don't pin everything permanently in context
- Treat memory as something queried on demand
- Relevance-ranked results, not accumulated history

### 5. Schema-Driven Summarization
Before compressing, define what MUST survive:
- **Causal steps**: Chain of decisions and why
- **Active constraints**: Rules still in effect
- **Failures**: What was tried and didn't work
- **Open commitments**: Promises not yet fulfilled
- **Key entities**: Names and references that must stay resolvable

❌ Wrong: Summarize "to save space" without preservation schema
✅ Right: Explicit schema guarantees critical info survives

### 6. Offload to Filesystem
- Don't feed model raw tool results at scale
- Write to disk, pass pointers
- Filesystem is unlimited context with persistence

### 7. Isolate Context with Sub-Agents
- Sub-agents exist to give different work its own window
- NOT to roleplay human teams
- Communication through structured artifacts, not shared transcripts

### 8. Design for Cache Stability
- Keep prompt prefix stable (no timestamps at start!)
- Make context append-only
- Deterministic serialization
- Cache hit = 10x cost savings

### 9. Let Context Evolve
- Static prompts freeze agents at version one
- Capture execution feedback
- Update strategies based on what worked/failed
- Agent that ran this morning informs agent running this afternoon

## Failure Modes to Avoid

1. **Append-everything trap**: Growing transcript until degradation
2. **Blind summarization**: Compressing without preservation schema
3. **Long-context delusion**: Thinking bigger windows solve the problem
4. **Observability as context**: Mixing debug logs with task instructions
5. **Tool schema bloat**: Too many overlapping tools
6. **Anthropomorphic multi-agent**: Agents roleplaying teams, sharing giant context
7. **Static configurations**: Never learning from execution
8. **Over-structured harness**: Architecture that bottlenecks model capability
9. **Cache destruction**: Unstable prefixes, non-deterministic serialization

## Working Context Assembly

For each LLM call, assemble working context by:

1. Start with stable system prefix (cached)
2. Load current task from feature_list.json
3. Retrieve relevant memory items (not all!)
4. Include only active constraints
5. Reference artifacts by path (not content)
6. Add recent session events (last N, not all)
7. Include current step instructions

Total should be minimal - justify every token.
EOF

# ============================================================================
# Context Compiler
# ============================================================================
echo "🔧 Creating context compiler..."

cat > .agent/hooks/compile-context.sh << 'EOF'
#!/bin/bash
# Context Compiler - Assembles minimal working context for each step
# Implements: Computed context, schema-driven summarization, retrieval

WORKING_CONTEXT=".agent/working-context/current.md"
SESSION_LOG=".agent/sessions/current.jsonl"

echo "🔧 Compiling working context..."

# Start fresh (context is computed, not accumulated)
cat > "$WORKING_CONTEXT" << CONTEXT
# Working Context

## Current Task
CONTEXT

# Add current feature (from feature_list.json)
if [ -f "feature_list.json" ]; then
    echo '```json' >> "$WORKING_CONTEXT"
    # Get only the current/next feature, not all
    python3 -c "
import json
with open('feature_list.json') as f:
    data = json.load(f)
for feat in sorted(data.get('features', []), key=lambda x: x.get('priority', 99)):
    if not feat.get('passes', False):
        print(json.dumps(feat, indent=2))
        break
" >> "$WORKING_CONTEXT" 2>/dev/null || echo "No pending features"
    echo '```' >> "$WORKING_CONTEXT"
fi

# Add active constraints from memory (retrieved, not pinned)
echo "" >> "$WORKING_CONTEXT"
echo "## Active Constraints" >> "$WORKING_CONTEXT"
if [ -d ".agent/memory/constraints" ]; then
    for constraint in .agent/memory/constraints/*.md; do
        [ -f "$constraint" ] && cat "$constraint" >> "$WORKING_CONTEXT"
    done
fi

# Add relevant failures (avoid repeating mistakes)
echo "" >> "$WORKING_CONTEXT"
echo "## Known Failures (Don't Repeat)" >> "$WORKING_CONTEXT"
if [ -d ".agent/memory/failures" ]; then
    # Only recent failures, not all
    ls -t .agent/memory/failures/*.md 2>/dev/null | head -5 | while read f; do
        [ -f "$f" ] && cat "$f" >> "$WORKING_CONTEXT"
    done
fi

# Add relevant strategies (what worked)
echo "" >> "$WORKING_CONTEXT"
echo "## Working Strategies" >> "$WORKING_CONTEXT"
if [ -d ".agent/memory/strategies" ]; then
    ls -t .agent/memory/strategies/*.md 2>/dev/null | head -3 | while read f; do
        [ -f "$f" ] && cat "$f" >> "$WORKING_CONTEXT"
    done
fi

# Reference artifacts by path (not content!)
echo "" >> "$WORKING_CONTEXT"
echo "## Available Artifacts (fetch if needed)" >> "$WORKING_CONTEXT"
if [ -d ".agent/artifacts/tool-outputs" ]; then
    ls .agent/artifacts/tool-outputs/ 2>/dev/null | head -10 | while read f; do
        echo "- .agent/artifacts/tool-outputs/$f" >> "$WORKING_CONTEXT"
    done
fi

# Add recent session summary (compressed, not raw)
echo "" >> "$WORKING_CONTEXT"
echo "## Recent Session Summary" >> "$WORKING_CONTEXT"
if [ -f "agent-progress.txt" ]; then
    tail -30 agent-progress.txt >> "$WORKING_CONTEXT"
fi

# ============================================================================
# Context Budget Enforcement
# ============================================================================
MAX_TOKENS=8000  # Hard cap for context budget

# Calculate token estimate
TOKENS=$(wc -w "$WORKING_CONTEXT" | awk '{print int($1 * 1.3)}')

# If over budget, trim content
if [ "$TOKENS" -gt "$MAX_TOKENS" ]; then
    echo "⚠️  Context over budget ($TOKENS > $MAX_TOKENS tokens), trimming..."
    
    # Create trimmed version
    TRIMMED_CONTEXT=".agent/working-context/trimmed.md"
    
    # Keep header and current task (most important)
    head -50 "$WORKING_CONTEXT" > "$TRIMMED_CONTEXT"
    
    # Add only most recent failures (last 3 instead of 5)
    echo "" >> "$TRIMMED_CONTEXT"
    echo "## Known Failures (Trimmed - Last 3)" >> "$TRIMMED_CONTEXT"
    if [ -d ".agent/memory/failures" ]; then
        ls -t .agent/memory/failures/*.md 2>/dev/null | head -3 | while read f; do
            [ -f "$f" ] && head -20 "$f" >> "$TRIMMED_CONTEXT"
        done
    fi
    
    # Add only most recent strategies (last 2)
    echo "" >> "$TRIMMED_CONTEXT"
    echo "## Working Strategies (Trimmed)" >> "$TRIMMED_CONTEXT"
    if [ -d ".agent/memory/strategies" ]; then
        ls -t .agent/memory/strategies/*.md 2>/dev/null | head -2 | while read f; do
            [ -f "$f" ] && head -15 "$f" >> "$TRIMMED_CONTEXT"
        done
    fi
    
    # Truncate session summary
    echo "" >> "$TRIMMED_CONTEXT"
    echo "## Recent Session Summary (Trimmed)" >> "$TRIMMED_CONTEXT"
    if [ -f "agent-progress.txt" ]; then
        tail -15 agent-progress.txt >> "$TRIMMED_CONTEXT"
    fi
    
    # Replace with trimmed version
    mv "$TRIMMED_CONTEXT" "$WORKING_CONTEXT"
    TOKENS=$(wc -w "$WORKING_CONTEXT" | awk '{print int($1 * 1.3)}')
    echo "   Trimmed to ~$TOKENS tokens"
fi

echo "" >> "$WORKING_CONTEXT"
echo "---" >> "$WORKING_CONTEXT"
echo "Estimated tokens: ~$TOKENS" >> "$WORKING_CONTEXT"
echo "Compiled: $(date -Iseconds)" >> "$WORKING_CONTEXT"

echo "✅ Working context compiled: $WORKING_CONTEXT (~$TOKENS tokens)"
EOF
chmod +x .agent/hooks/compile-context.sh

# ============================================================================
# Session Logger (Structured Events)
# ============================================================================
echo "📝 Creating session logger..."

cat > .agent/hooks/log-event.sh << 'EOF'
#!/bin/bash
# Log structured event to session (Layer 2)
# Events are typed records, not raw prompts

SESSION_LOG=".agent/sessions/current.jsonl"
EVENT_TYPE="$1"
EVENT_DATA="$2"

# Create session file if doesn't exist
[ ! -f "$SESSION_LOG" ] && echo "" > "$SESSION_LOG"

# Log structured event
python3 -c "
import json
import datetime

event = {
    'timestamp': datetime.datetime.now().isoformat(),
    'type': '$EVENT_TYPE',
    'data': '''$EVENT_DATA''',
    'session_id': '$(date +%Y%m%d)'
}
print(json.dumps(event))
" >> "$SESSION_LOG"

echo "📝 Logged event: $EVENT_TYPE"
EOF
chmod +x .agent/hooks/log-event.sh

# ============================================================================
# Session Diff Artifacts
# ============================================================================
echo "📊 Creating session diff generator..."

cat > .agent/hooks/save-session-diff.sh << 'EOF'
#!/bin/bash
# Save a diff summary artifact for the current session
# Usage: .agent/hooks/save-session-diff.sh <session_number> <feature_id>

SESSION_NUM="${1:-unknown}"
FEATURE_ID="${2:-unknown}"
DIFF_DIR=".agent/artifacts/code-snapshots"
mkdir -p "$DIFF_DIR"

DIFF_FILE="$DIFF_DIR/session-${SESSION_NUM}.diff"
SUMMARY_FILE="$DIFF_DIR/session-${SESSION_NUM}-summary.md"

# Get diff since last session tag or last 50 commits
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD 2>/dev/null | head -1)

# Save full diff
git diff "$LAST_TAG"..HEAD > "$DIFF_FILE" 2>/dev/null || git diff HEAD~10..HEAD > "$DIFF_FILE" 2>/dev/null

# Generate summary
cat > "$SUMMARY_FILE" << SUMMARY
# Session $SESSION_NUM Diff Summary
Feature: $FEATURE_ID
Generated: $(date -Iseconds)

## Files Changed
$(git diff --stat "$LAST_TAG"..HEAD 2>/dev/null || git diff --stat HEAD~10..HEAD 2>/dev/null)

## Summary
- Lines added: $(git diff --numstat "$LAST_TAG"..HEAD 2>/dev/null | awk '{s+=$1}END{print s+0}')
- Lines removed: $(git diff --numstat "$LAST_TAG"..HEAD 2>/dev/null | awk '{s+=$2}END{print s+0}')
- Files changed: $(git diff --name-only "$LAST_TAG"..HEAD 2>/dev/null | wc -l | tr -d ' ')
SUMMARY

echo "✅ Session diff saved: $DIFF_FILE"
EOF
chmod +x .agent/hooks/save-session-diff.sh

# ============================================================================
# Metrics Tracking
# ============================================================================
echo "📈 Creating metrics tracker..."

mkdir -p .agent/metrics

cat > .agent/hooks/track-metrics.sh << 'EOF'
#!/bin/bash
# Track metrics for feedback loops
# Usage: .agent/hooks/track-metrics.sh <event> <feature_id> [extra_data]

EVENT="$1"
FEATURE_ID="$2"
EXTRA="$3"
METRICS_FILE=".agent/metrics/session-metrics.jsonl"

# Calculate session wall time if start time exists
WALL_TIME=""
if [ -f ".agent/metrics/.session-start" ]; then
    START=$(cat .agent/metrics/.session-start)
    NOW=$(date +%s)
    WALL_TIME=$((NOW - START))
fi

python3 << PYEOF
import json
from datetime import datetime

metrics = {
    "timestamp": datetime.now().isoformat(),
    "event": "$EVENT",
    "feature_id": "$FEATURE_ID",
    "wall_time_seconds": $WALL_TIME if "$WALL_TIME" else None,
    "extra": "$EXTRA" if "$EXTRA" else None
}

# Remove None values
metrics = {k: v for k, v in metrics.items() if v is not None}

with open("$METRICS_FILE", "a") as f:
    f.write(json.dumps(metrics) + "\n")
PYEOF

echo "📈 Tracked: $EVENT for $FEATURE_ID"
EOF
chmod +x .agent/hooks/track-metrics.sh

cat > .agent/hooks/start-session-timer.sh << 'EOF'
#!/bin/bash
# Start session timer for wall time tracking
date +%s > .agent/metrics/.session-start
EOF
chmod +x .agent/hooks/start-session-timer.sh

cat > .agent/hooks/metrics-report.sh << 'EOF'
#!/bin/bash
# Generate metrics report
# Usage: .agent/hooks/metrics-report.sh

METRICS_FILE=".agent/metrics/session-metrics.jsonl"

if [ ! -f "$METRICS_FILE" ]; then
    echo "No metrics collected yet"
    exit 0
fi

python3 << 'PYEOF'
import json
from collections import defaultdict

metrics_file = ".agent/metrics/session-metrics.jsonl"
events = []

with open(metrics_file) as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except:
                pass

if not events:
    print("No metrics collected yet")
    exit(0)

# Aggregate metrics
total_sessions = len([e for e in events if e.get("event") == "session_complete"])
total_features = len([e for e in events if e.get("event") == "feature_complete"])
retries = len([e for e in events if e.get("event") == "retry"])
reverts = len([e for e in events if e.get("event") == "revert"])

wall_times = [e.get("wall_time_seconds", 0) for e in events if e.get("wall_time_seconds")]
avg_wall_time = sum(wall_times) / len(wall_times) if wall_times else 0

# Per-feature stats
feature_attempts = defaultdict(int)
for e in events:
    if e.get("event") in ("session_start", "retry"):
        feature_attempts[e.get("feature_id", "unknown")] += 1

flaky_features = [f for f, count in feature_attempts.items() if count > 2]

print("=" * 50)
print("📊 METRICS REPORT")
print("=" * 50)
print(f"Total sessions:     {total_sessions}")
print(f"Features completed: {total_features}")
print(f"Retries:            {retries}")
print(f"Reverts:            {reverts}")
print(f"Avg wall time:      {avg_wall_time:.1f}s")
print(f"Flaky features:     {len(flaky_features)}")
if flaky_features:
    print(f"  - {', '.join(flaky_features[:5])}")
print("=" * 50)
PYEOF
EOF
chmod +x .agent/hooks/metrics-report.sh

# ============================================================================
# Memory Manager (Layer 3)
# ============================================================================
echo "🧠 Creating memory manager..."

cat > .agent/hooks/memory-manager.sh << 'EOF'
#!/bin/bash
# Memory Manager - Store and retrieve knowledge
# Implements: Retrieval over pinning, schema-driven storage

ACTION="$1"
CATEGORY="$2"  # strategies, constraints, failures, entities
CONTENT="$3"

MEMORY_DIR=".agent/memory"

case "$ACTION" in
    store)
        # Store with metadata for retrieval
        FILENAME="$MEMORY_DIR/$CATEGORY/$(date +%Y%m%d-%H%M%S).md"
        mkdir -p "$MEMORY_DIR/$CATEGORY"
        
        cat > "$FILENAME" << MEMORY
---
created: $(date -Iseconds)
category: $CATEGORY
---
$CONTENT
MEMORY
        echo "🧠 Stored to memory: $FILENAME"
        ;;
        
    retrieve)
        # Retrieve relevant items (not all!)
        echo "🔍 Retrieving from $CATEGORY..."
        if [ -d "$MEMORY_DIR/$CATEGORY" ]; then
            # Simple recency-based retrieval
            # In production, use embeddings or structured queries
            ls -t "$MEMORY_DIR/$CATEGORY"/*.md 2>/dev/null | head -5 | while read f; do
                echo "--- $f ---"
                cat "$f"
                echo ""
            done
        else
            echo "No items in $CATEGORY"
        fi
        ;;
        
    search)
        # Search across memory
        QUERY="$CONTENT"
        echo "🔍 Searching memory for: $QUERY"
        grep -rl "$QUERY" "$MEMORY_DIR" 2>/dev/null | while read f; do
            echo "Found in: $f"
        done
        ;;
        
    *)
        echo "Usage: memory-manager.sh [store|retrieve|search] [category] [content]"
        echo "Categories: strategies, constraints, failures, entities"
        ;;
esac
EOF
chmod +x .agent/hooks/memory-manager.sh

# ============================================================================
# Artifact Manager (Layer 4)
# ============================================================================
echo "📦 Creating artifact manager..."

cat > .agent/hooks/artifact-manager.sh << 'EOF'
#!/bin/bash
# Artifact Manager - Store large objects by reference
# Implements: Offload to filesystem principle

ACTION="$1"
NAME="$2"
CONTENT="$3"

ARTIFACT_DIR=".agent/artifacts"

case "$ACTION" in
    store)
        # Store content to file, return reference
        CATEGORY="${4:-tool-outputs}"
        FILEPATH="$ARTIFACT_DIR/$CATEGORY/$NAME"
        mkdir -p "$ARTIFACT_DIR/$CATEGORY"
        
        if [ -n "$CONTENT" ]; then
            echo "$CONTENT" > "$FILEPATH"
        else
            # Read from stdin
            cat > "$FILEPATH"
        fi
        
        # Return reference (not content!)
        echo "📦 Artifact stored: $FILEPATH"
        echo "Reference: $FILEPATH"
        ;;
        
    fetch)
        # Fetch artifact content
        FILEPATH="$ARTIFACT_DIR/$NAME"
        if [ -f "$FILEPATH" ]; then
            cat "$FILEPATH"
        else
            # Try with category prefix
            find "$ARTIFACT_DIR" -name "$NAME" -type f | head -1 | xargs cat 2>/dev/null || echo "Artifact not found: $NAME"
        fi
        ;;
        
    list)
        # List available artifacts
        echo "📦 Available artifacts:"
        find "$ARTIFACT_DIR" -type f | while read f; do
            SIZE=$(wc -c < "$f" | tr -d ' ')
            echo "  $f ($SIZE bytes)"
        done
        ;;
        
    *)
        echo "Usage: artifact-manager.sh [store|fetch|list] [name] [content]"
        ;;
esac
EOF
chmod +x .agent/hooks/artifact-manager.sh

# ============================================================================
# Schema-Driven Summarizer
# ============================================================================
echo "📋 Creating schema-driven summarizer..."

cat > .agent/hooks/summarize.sh << 'EOF'
#!/bin/bash
# Schema-Driven Summarizer
# Implements: Preservation schema for critical information

INPUT="$1"
OUTPUT="${2:-.agent/working-context/summary.md}"

# Summarization schema - what MUST survive
SCHEMA_PROMPT='Summarize the following while PRESERVING these required elements:

## Required Preservation Schema:
1. **Causal Steps**: Chain of decisions and WHY they were made
2. **Active Constraints**: Rules and requirements still in effect
3. **Failures**: What was tried and did NOT work (prevent repetition)
4. **Open Commitments**: Promises or tasks not yet fulfilled
5. **Key Entities**: Names, IDs, paths that must stay resolvable

## Rules:
- Preserve decision-relevant structure
- Keep specific identifiers (file paths, function names, error codes)
- Maintain causal relationships
- Do NOT compress away constraints
- Do NOT lose failure information

## Content to Summarize:
'

if [ -f "$INPUT" ]; then
    echo "📋 Summarizing with preservation schema..."
    echo "$SCHEMA_PROMPT" > "$OUTPUT.prompt"
    cat "$INPUT" >> "$OUTPUT.prompt"
    echo ""
    echo "Schema prompt written to: $OUTPUT.prompt"
    echo "Run through LLM to generate summary, then save to: $OUTPUT"
else
    echo "Usage: summarize.sh [input-file] [output-file]"
    echo ""
    echo "Preservation schema ensures these survive:"
    echo "  - Causal steps (decisions and why)"
    echo "  - Active constraints"
    echo "  - Failures (what didn't work)"
    echo "  - Open commitments"
    echo "  - Key entities"
fi
EOF
chmod +x .agent/hooks/summarize.sh

# ============================================================================
# Execution Feedback Capturer (ACE-style)
# ============================================================================
echo "🔄 Creating feedback capturer..."

cat > .agent/hooks/capture-feedback.sh << 'EOF'
#!/bin/bash
# Capture execution feedback for context evolution
# Implements: Let context evolve through execution (ACE pattern)

OUTCOME="$1"  # success or failure
FEATURE_ID="$2"
DESCRIPTION="$3"

FEEDBACK_DIR=".agent/memory"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

case "$OUTCOME" in
    success)
        # Capture what worked as a strategy
        mkdir -p "$FEEDBACK_DIR/strategies"
        cat > "$FEEDBACK_DIR/strategies/${FEATURE_ID}-${TIMESTAMP}.md" << STRATEGY
---
feature: $FEATURE_ID
outcome: success
created: $(date -Iseconds)
---
## Strategy That Worked

$DESCRIPTION

### Key Decisions:
- [Extract from description]

### Why It Worked:
- [To be analyzed]

### Reusable Pattern:
- [To be extracted]
STRATEGY
        echo "✅ Strategy captured for future reference"
        ;;
        
    failure)
        # Capture what failed to avoid repetition
        mkdir -p "$FEEDBACK_DIR/failures"
        cat > "$FEEDBACK_DIR/failures/${FEATURE_ID}-${TIMESTAMP}.md" << FAILURE
---
feature: $FEATURE_ID
outcome: failure
created: $(date -Iseconds)
---
## Approach That Failed

$DESCRIPTION

### What Was Tried:
- [Extract from description]

### Why It Failed:
- [To be analyzed]

### Avoid In Future:
- [Extract lesson]
FAILURE
        echo "❌ Failure captured to prevent repetition"
        ;;
        
    constraint)
        # Record active constraint
        mkdir -p "$FEEDBACK_DIR/constraints"
        cat > "$FEEDBACK_DIR/constraints/${FEATURE_ID}-${TIMESTAMP}.md" << CONSTRAINT
---
feature: $FEATURE_ID
type: constraint
active: true
created: $(date -Iseconds)
---
## Active Constraint

$DESCRIPTION
CONSTRAINT
        echo "📌 Constraint recorded"
        ;;
        
    *)
        echo "Usage: capture-feedback.sh [success|failure|constraint] [feature-id] [description]"
        ;;
esac
EOF
chmod +x .agent/hooks/capture-feedback.sh

# ============================================================================
# Init Workflow (Context-Aware)
# ============================================================================
echo "🚀 Creating init workflow..."

cat > .agent/workflows/init.md << 'EOF'
---
trigger: "init", "initialize", "setup"
description: Initialize project with context-engineered architecture
---

# Project Initializer (Context-Engineered)

## Before Starting
Read `.agent/AGENT_RULES.md` to understand the four-layer memory model.

## Step 1: Detect Stack
Look for project files and determine tech stack.

## Step 2: Create Project Files

### feature_list.json
Each feature should be atomic and independently verifiable.

### app_spec.md  
Document architecture, not implementation details.

### init.sh
Minimal script to verify baseline works.

## Step 3: Initialize Memory Layers

### Working Context (.agent/working-context/)
- Will be computed fresh each step
- Never accumulate here

### Sessions (.agent/sessions/)
- Log all events as structured records
- Use: `.agent/hooks/log-event.sh [type] [data]`

### Memory (.agent/memory/)
- Store strategies, constraints, failures, entities
- Use: `.agent/hooks/memory-manager.sh store [category] [content]`

### Artifacts (.agent/artifacts/)
- Large outputs go here, referenced by path
- Use: `.agent/hooks/artifact-manager.sh store [name] [content]`

## Step 4: Record Initial Constraints
```bash
.agent/hooks/capture-feedback.sh constraint "init" "Project constraints..."
```

## Step 5: Compile Initial Context
```bash
.agent/hooks/compile-context.sh
```

## Step 6: Commit
```bash
git add .
git commit -m "chore: initialize context-engineered project"
```
EOF

# ============================================================================
# Implement Workflow (Context-Aware)
# ============================================================================
echo "🔨 Creating implement workflow..."

cat > .agent/workflows/implement.md << 'EOF'
---
trigger: "implement", "next", "continue", "build"
description: Implement features using context engineering principles
---

# Feature Implementation (Context-Engineered)

## Critical Principles
1. Context is COMPUTED, not accumulated
2. Retrieve what's needed, don't pin everything
3. Offload large outputs to artifacts
4. Capture feedback for evolution

## Session Startup

### 1. Compile Fresh Working Context
```bash
.agent/hooks/compile-context.sh
```
This gives you minimal relevant context, not full history.

### 2. Review Working Context
```bash
cat .agent/working-context/current.md
```
This is what you're working with. If something's missing, retrieve it explicitly.

### 3. Verify Baseline
```bash
./init.sh
```

### 4. If Broken, Revert
```bash
GOOD=$(git log --oneline --grep="session:" -1 --format="%H")
git stash && git reset --hard $GOOD
```

## During Implementation

### Log Significant Events
```bash
.agent/hooks/log-event.sh "tool_call" "description of what was done"
.agent/hooks/log-event.sh "decision" "what was decided and why"
.agent/hooks/log-event.sh "error" "what went wrong"
```

### Store Large Outputs as Artifacts
Don't paste large tool outputs into conversation. Instead:
```bash
echo "[large output]" | .agent/hooks/artifact-manager.sh store "output-name.txt"
```
Then reference by path: `.agent/artifacts/tool-outputs/output-name.txt`

### Retrieve Memory When Needed
```bash
.agent/hooks/memory-manager.sh retrieve strategies
.agent/hooks/memory-manager.sh retrieve failures
.agent/hooks/memory-manager.sh search "relevant term"
```

### Commit Frequently
```bash
git add -A && git commit -m "feat(category): description"
```

## Session End

### 1. Capture What Worked
```bash
.agent/hooks/capture-feedback.sh success "feature-id" "Description of approach that worked"
```

### 2. Capture What Failed (if applicable)
```bash
.agent/hooks/capture-feedback.sh failure "feature-id" "Description of what didn't work and why"
```

### 3. Record New Constraints
```bash
.agent/hooks/capture-feedback.sh constraint "feature-id" "New constraint discovered"
```

### 4. Update Feature List
Only if verified working.

### 5. Update Progress Log
Include schema-preserving summary:
- Causal steps taken
- Active constraints
- What failed
- What's committed to next

### 6. Final Commit
```bash
git add -A && git commit -m "session: completed [feature-id]"
```

### 7. Recompile Context for Next Session
```bash
.agent/hooks/compile-context.sh
```

## Key Reminders

❌ Don't: Accumulate everything in context
✅ Do: Compute minimal working context per step

❌ Don't: Paste large outputs into conversation
✅ Do: Store as artifacts, reference by path

❌ Don't: Summarize blindly to save space
✅ Do: Use schema-driven summarization

❌ Don't: Forget what failed
✅ Do: Capture failures to prevent repetition

❌ Don't: Start fresh every session
✅ Do: Let context evolve through feedback
EOF

# ============================================================================
# Quality Gates
# ============================================================================
echo "✅ Creating quality gates..."

cat > .agent/hooks/quality-gate.sh << 'EOF'
#!/bin/bash
# Quality gates with context-aware checks

echo "🔍 Running Quality Gates..."

PASS=true

# Standard checks
echo -n "  Tests: "
cargo test 2>/dev/null || npm test 2>/dev/null || pytest 2>/dev/null || go test ./... 2>/dev/null && echo "✅" || { echo "❌"; PASS=false; }

echo -n "  Lint: "
cargo clippy 2>/dev/null || npm run lint 2>/dev/null || flake8 . 2>/dev/null || go vet ./... 2>/dev/null && echo "✅" || echo "⚠️"

echo -n "  Build: "
cargo build 2>/dev/null || npm run build 2>/dev/null || go build ./... 2>/dev/null && echo "✅" || { echo "❌"; PASS=false; }

# Context-specific checks
echo -n "  Working context size: "
if [ -f ".agent/working-context/current.md" ]; then
    TOKENS=$(wc -w .agent/working-context/current.md | awk '{print int($1 * 1.3)}')
    if [ "$TOKENS" -gt 8000 ]; then
        echo "⚠️ Large ($TOKENS tokens) - consider compaction"
    else
        echo "✅ ($TOKENS tokens)"
    fi
else
    echo "⚠️ Not compiled"
fi

echo -n "  Failures captured: "
FAILURES=$(ls .agent/memory/failures/*.md 2>/dev/null | wc -l)
echo "$FAILURES recorded"

echo -n "  Strategies captured: "
STRATEGIES=$(ls .agent/memory/strategies/*.md 2>/dev/null | wc -l)
echo "$STRATEGIES recorded"

if [ "$PASS" = true ]; then
    echo ""
    echo "✅ Quality gates passed"
    exit 0
else
    echo ""
    echo "❌ Quality gates failed"
    exit 1
fi
EOF
chmod +x .agent/hooks/quality-gate.sh

# ============================================================================
# Subagents with Isolated Context
# ============================================================================
echo "🤖 Creating context-isolated subagents..."

mkdir -p .agent/subagents
mkdir -p .claude/agents  # Claude Code looks here for subagents

cat > .agent/subagents/README.md << 'EOF'
# Sub-Agents

Sub-agents exist to give different work its own context window.
They do NOT exist to roleplay human teams.

## Principle
Each sub-agent:
- Has its own working context (isolated)
- Communicates through structured artifacts (not shared transcripts)
- Returns results via defined schema

## Usage in Claude Code
Invoke with: @agent-name your request

Available agents:
- @code-reviewer - Review code changes
- @test-runner - Run and analyze tests
- @feature-verifier - End-to-end verification

## Anti-Pattern
❌ Shared giant context between agents
❌ Agents "chatting" with each other
❌ Designer Agent, PM Agent, Engineer Agent roleplaying
EOF

# Create in BOTH locations for compatibility
for DIR in ".agent/subagents" ".claude/agents"; do
    mkdir -p "$DIR"

cat > "$DIR/code-reviewer.md" << 'EOF'
---
name: code-reviewer
description: Reviews code in isolated context. Use PROACTIVELY after implementing features. Invoke with @code-reviewer
tools: Read, Bash, Grep, Glob
model: opus
---

# Code Reviewer

You review code changes for quality, security, and correctness.

## When Invoked
1. Run `git diff` to see recent changes
2. Review each modified file
3. Check for common issues
4. Provide structured feedback

## Review Checklist
- [ ] Code compiles/builds without errors
- [ ] No obvious bugs or logic errors
- [ ] Error handling is appropriate
- [ ] No hardcoded secrets or credentials
- [ ] No debug/console.log statements left in
- [ ] Code follows project conventions
- [ ] Security considerations addressed

## Output Format
**🔴 Critical** (must fix):
- [issue with file:line reference]

**🟡 Warnings** (should fix):
- [issue with file:line reference]

**🟢 Suggestions** (nice to have):
- [suggestion]

**✅ Looks Good**:
- [positive feedback]
EOF

cat > "$DIR/test-runner.md" << 'EOF'
---
name: test-runner
description: Runs tests and analyzes results. MUST be used before marking any feature as complete. Invoke with @test-runner
tools: Read, Edit, Bash, Grep, Glob
model: opus
---

# Test Runner

You run the test suite and analyze results.

## Process
1. Detect test framework:
   - Rust: `cargo test`
   - Python: `pytest`
   - Node: `npm test`
   - Go: `go test ./...`

2. Run the tests:
```bash
cargo test 2>&1 || pytest 2>&1 || npm test 2>&1 || go test ./... 2>&1
```

3. Parse the output:
   - Count total/passed/failed
   - Extract failure messages
   - Identify root causes

4. If failures exist:
   - Analyze each failure
   - Suggest fixes
   - Optionally fix simple issues

## Output Format
**Test Results:**
- Total: X
- Passed: X ✅
- Failed: X ❌

**Failures:**
1. `test_name` - Error message
   - Cause: [analysis]
   - Fix: [suggestion]

**Verdict:** PASS ✅ / FAIL ❌
EOF

cat > "$DIR/feature-verifier.md" << 'EOF'
---
name: feature-verifier
description: Verifies features work end-to-end. Use PROACTIVELY before marking features complete. Invoke with @feature-verifier
tools: Read, Bash, Grep, Glob
model: opus
---

# Feature Verifier

You verify features actually work for real users, not just that tests pass.

## Process
1. Understand the feature requirements
2. Design verification steps
3. Execute each step
4. Collect evidence
5. Report verdict

## Verification Methods

**For APIs:**
```bash
# Start the server (if not running)
# Make actual HTTP requests
curl -X POST http://localhost:8080/api/endpoint -d '{"test": "data"}'
```

**For CLI tools:**
```bash
# Run actual commands
./my-tool --help
./my-tool create --name test
```

**For Libraries:**
```bash
# Write and run a quick integration test
```

## Output Format
**Feature:** [ID] - [Description]

**Verification Steps:**
1. [Step] - ✅ PASS / ❌ FAIL
   Evidence: [what you observed]

2. [Step] - ✅ PASS / ❌ FAIL
   Evidence: [what you observed]

**Verdict:** PASS ✅ / FAIL ❌
**Confidence:** High / Medium / Low
**Notes:** [any observations]
EOF

done

echo "  Created subagents in .agent/subagents/ and .claude/agents/"

# ============================================================================
# Cache Stability Configuration
# ============================================================================
echo "💾 Creating cache stability config..."

cat > .agent/cache-config.md << 'EOF'
# Cache Stability Guidelines

KV-cache hit rate is critical for cost and latency.
Cached tokens: $0.30/M vs Uncached: $3.00/M (10x difference)

## Rules for Cache Stability

### 1. Stable Prefix
The system prompt should be IDENTICAL across calls.

❌ Wrong:
```
Current time: 2025-01-15T14:32:15Z  # Changes every call!
You are a helpful assistant...
```

✅ Right:
```
You are a helpful assistant...
[stable instructions]
---
[variable content below the break]
```

### 2. Append-Only History
Don't modify previous messages. Only append new ones.

### 3. Deterministic Serialization
Ensure JSON keys are always in same order.
```python
import json
json.dumps(data, sort_keys=True)  # Always sorted
```

### 4. Separate Stable from Variable
```
[STABLE PREFIX - cached]
System instructions
Agent identity
Long-lived summaries

[VARIABLE SUFFIX - not cached]
Current task
New tool outputs
Latest input
```

### 5. Mark Cache Breakpoints
If using explicit caching, ensure breakpoints cover system prompt.
EOF

# ============================================================================
# Agent Integration Files
# ============================================================================
echo "🔗 Creating agent integrations..."

# Get version from environment or default
HARNESS_VERSION="${CONTEXT_ENGINE_VERSION:-3.1.0}"

cat > CLAUDE.md << EOF
# Claude Code Instructions
<!-- harness_version: $HARNESS_VERSION -->
<!-- generated: $(date -Iseconds) -->

## Context Engineering
This project uses a four-layer memory architecture. Read \`.agent/AGENT_RULES.md\`.

## Before Each Step
\`\`\`bash
.agent/hooks/compile-context.sh
cat .agent/working-context/current.md
.agent/commands.sh recall failures  # Don't repeat mistakes!
\`\`\`

## ⚠️ MANDATORY: Use MCP Tools for Documentation
If this project has MCP configured (check mcp-config.json), you MUST use MCP tools:

### Ref Documentation (if available)
Before implementing anything with external libraries, query Ref for current docs:
\`\`\`
Use the Ref MCP tool to look up documentation for [library/crate/package]
\`\`\`

Examples:
- "Use Ref to look up axum router documentation"
- "Use Ref to look up sqlx query macro syntax"
- "Use Ref to look up russh SSH client examples"

**DO NOT guess at APIs. Look them up first.**

### Other MCP Tools
- **fetch** - Make HTTP requests to test endpoints
- **postgres** - Query the database directly
- **filesystem** - Read/write files outside the project

## During Implementation
- Log events: `.agent/hooks/log-event.sh [type] [data]`
- Store large outputs: `.agent/hooks/artifact-manager.sh store [name]`
- Retrieve memory: `.agent/hooks/memory-manager.sh retrieve [category]`

## ⚠️ MANDATORY: Run Tests Before Completing Any Feature
You MUST run tests before marking any feature as complete:

```bash
# Rust
cargo test

# Python  
pytest

# Node.js
npm test

# Go
go test ./...
```

**Do NOT set `passes: true` unless tests actually pass!**

## ⚠️ MANDATORY: Use Subagents
After implementing a feature, you MUST invoke these subagents:

### 1. Code Review (REQUIRED)
```
@code-reviewer Review the changes for this feature
```
Wait for the review. Address any issues before proceeding.

### 2. Test Runner (REQUIRED)
```
@test-runner Run the test suite and analyze results
```
If tests fail, fix them before proceeding.

### 3. Feature Verifier (REQUIRED)
```
@feature-verifier Verify feature [ID]: [description]
```
Confirm the feature works end-to-end.

**Do NOT skip subagents. They catch issues before they compound.**

## After Completing Work
```bash
# Only if tests pass and verification succeeds!
.agent/commands.sh success "[feature-id]" "what worked"
git add -A
git commit -m "session: completed [feature-id]"
```

If something fails:
```bash
.agent/commands.sh failure "[feature-id]" "what failed and why"
```

## Key Principles
1. Context is computed, not accumulated
2. Store large outputs as artifacts, reference by path
3. Retrieve memory on demand, don't pin everything
4. **USE MCP** - look up docs before guessing at APIs
5. **RUN TESTS** - no exceptions
6. **USE SUBAGENTS** - code-reviewer, test-runner, feature-verifier
7. Capture feedback for context evolution

## Search Guidelines
Do NOT include years in documentation searches.
EOF

cat > .cursorrules << 'EOF'
This project uses context-engineered architecture.

Key files:
- .agent/AGENT_RULES.md - Memory model and principles
- .agent/working-context/current.md - Compiled context for current step
- .agent/memory/ - Retrievable knowledge
- .agent/artifacts/ - Large objects by reference
- .claude/agents/ - Subagents (code-reviewer, test-runner, feature-verifier)

MANDATORY WORKFLOW:
1. Compile context: .agent/hooks/compile-context.sh
2. Check failures: .agent/commands.sh recall failures
3. Implement feature
4. RUN TESTS (cargo test / pytest / npm test / go test)
5. Use @code-reviewer for review
6. Use @test-runner to verify tests
7. Use @feature-verifier for end-to-end check
8. Only then mark feature complete

Do NOT skip tests or subagents!
Do NOT include years in documentation searches.
EOF

# ============================================================================
# Quick Commands
# ============================================================================
echo "⚡ Creating quick commands..."

cat > .agent/commands.sh << 'EOF'
#!/bin/bash

case "$1" in
    compile)
        ./.agent/hooks/compile-context.sh
        ;;
    context)
        cat .agent/working-context/current.md
        ;;
    store-artifact)
        ./.agent/hooks/artifact-manager.sh store "$2" "$3"
        ;;
    fetch-artifact)
        ./.agent/hooks/artifact-manager.sh fetch "$2"
        ;;
    remember)
        ./.agent/hooks/memory-manager.sh store "$2" "$3"
        ;;
    recall)
        ./.agent/hooks/memory-manager.sh retrieve "$2"
        ;;
    search)
        ./.agent/hooks/memory-manager.sh search "$2"
        ;;
    success)
        ./.agent/hooks/capture-feedback.sh success "$2" "$3"
        ;;
    failure)
        ./.agent/hooks/capture-feedback.sh failure "$2" "$3"
        ;;
    constraint)
        ./.agent/hooks/capture-feedback.sh constraint "$2" "$3"
        ;;
    verify)
        ./.agent/hooks/quality-gate.sh
        ;;
    summarize)
        ./.agent/hooks/summarize.sh "$2" "$3"
        ;;
    status)
        echo "📊 Project Status"
        echo "================"
        echo "Features: $(grep -c '"passes": true' feature_list.json 2>/dev/null || echo 0) / $(grep -c '"id"' feature_list.json 2>/dev/null || echo 0)"
        echo "Strategies: $(ls .agent/memory/strategies/*.md 2>/dev/null | wc -l)"
        echo "Failures: $(ls .agent/memory/failures/*.md 2>/dev/null | wc -l)"
        echo "Artifacts: $(find .agent/artifacts -type f 2>/dev/null | wc -l)"
        ;;
    *)
        echo "Context-Engineered Agent Commands"
        echo "=================================="
        echo ""
        echo "Context:"
        echo "  compile        - Compile fresh working context"
        echo "  context        - View current working context"
        echo ""
        echo "Artifacts (Layer 4):"
        echo "  store-artifact [name] [content]  - Store artifact"
        echo "  fetch-artifact [name]            - Fetch artifact"
        echo ""
        echo "Memory (Layer 3):"
        echo "  remember [category] [content]    - Store to memory"
        echo "  recall [category]                - Retrieve from memory"
        echo "  search [query]                   - Search memory"
        echo ""
        echo "Feedback:"
        echo "  success [id] [description]       - Capture what worked"
        echo "  failure [id] [description]       - Capture what failed"
        echo "  constraint [id] [description]    - Record constraint"
        echo ""
        echo "Other:"
        echo "  verify         - Run quality gates"
        echo "  summarize      - Schema-driven summarization"
        echo "  status         - Project status"
        ;;
esac
EOF
chmod +x .agent/commands.sh

# ============================================================================
# Gitignore
# ============================================================================
cat >> .gitignore << 'EOF'

# Context Engineering
.agent/working-context/
.agent/sessions/
.agent/artifacts/tool-outputs/
EOF

# ============================================================================
# Initialize
# ============================================================================
echo '{"sessions": []}' > .agent/sessions/current.jsonl
.agent/hooks/compile-context.sh 2>/dev/null || true

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║                        ✅ Setup Complete!                              ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "📐 Four-Layer Memory Architecture:"
echo "   Layer 1: .agent/working-context/  - Computed view (minimal)"
echo "   Layer 2: .agent/sessions/         - Full event log"
echo "   Layer 3: .agent/memory/           - Retrievable knowledge"
echo "   Layer 4: .agent/artifacts/        - Large objects by reference"
echo ""
echo "🔧 Key Commands:"
echo "   .agent/commands.sh compile     - Compile fresh working context"
echo "   .agent/commands.sh context     - View working context"
echo "   .agent/commands.sh remember    - Store to memory"
echo "   .agent/commands.sh recall      - Retrieve from memory"
echo "   .agent/commands.sh success/failure - Capture feedback"
echo ""
echo "📜 Nine Scaling Principles:"
echo "   1. Context is computed, not accumulated"
echo "   2. Separate storage from presentation"
echo "   3. Scope by default (start minimal)"
echo "   4. Retrieval over pinning"
echo "   5. Schema-driven summarization"
echo "   6. Offload to filesystem"
echo "   7. Isolate context with sub-agents"
echo "   8. Design for cache stability"
echo "   9. Let context evolve through execution"

# ============================================================================
# Multi-Stack Presets Config
# ============================================================================
echo ""
echo "📦 Creating stack presets config..."

cat > .agent/stack-presets.yaml << 'EOF'
# Stack Presets Configuration
# Define custom stacks or override defaults
# Usage: Set STACK_PRESET env var or specify in feature_list.json

presets:
  rust:
    name: "Rust"
    init_commands:
      - cargo init
    test_command: cargo test
    build_command: cargo build
    lint_command: cargo clippy
    mcp_preset: rust-docs
    file_extensions: [.rs]
    
  node:
    name: "Node.js"
    init_commands:
      - npm init -y
    test_command: npm test
    build_command: npm run build
    lint_command: npm run lint
    mcp_preset: web-dev
    file_extensions: [.js, .ts, .jsx, .tsx]
    
  python:
    name: "Python"
    init_commands:
      - python -m venv venv
      - pip install pytest
    test_command: pytest
    build_command: python -m build
    lint_command: flake8 .
    mcp_preset: python-docs
    file_extensions: [.py]
    
  go:
    name: "Go"
    init_commands:
      - go mod init
    test_command: go test ./...
    build_command: go build ./...
    lint_command: go vet ./...
    mcp_preset: go-docs
    file_extensions: [.go]

  react:
    name: "React"
    init_commands:
      - npx create-react-app .
    test_command: npm test
    build_command: npm run build
    lint_command: npm run lint
    mcp_preset: web-dev
    file_extensions: [.jsx, .tsx, .js, .ts]

# Custom presets can be added here
# my-stack:
#   name: "My Custom Stack"
#   test_command: ./run-tests.sh
#   ...
EOF

# ============================================================================
# CI/CD Template
# ============================================================================
echo "🔄 Creating CI template..."

mkdir -p .github/workflows

cat > .github/workflows/context-engine-ci.yml << 'EOF'
# Context Engine CI
# Runs quality gates on each commit to keep the autonomous loop honest

name: Context Engine CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  quality-gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup project
        run: |
          # Install dependencies based on stack
          if [ -f "Cargo.toml" ]; then
            rustup update stable
          elif [ -f "package.json" ]; then
            npm ci
          elif [ -f "requirements.txt" ]; then
            pip install -r requirements.txt
          elif [ -f "go.mod" ]; then
            go mod download
          fi
      
      - name: Run tests
        run: |
          if [ -f "Cargo.toml" ]; then
            cargo test
          elif [ -f "package.json" ]; then
            npm test
          elif [ -f "requirements.txt" ]; then
            pytest
          elif [ -f "go.mod" ]; then
            go test ./...
          fi
      
      - name: Run lints
        run: |
          if [ -f "Cargo.toml" ]; then
            cargo clippy -- -D warnings
          elif [ -f "package.json" ]; then
            npm run lint || true
          elif [ -f "requirements.txt" ]; then
            flake8 . || true
          elif [ -f "go.mod" ]; then
            go vet ./...
          fi
      
      - name: Check feature list
        run: |
          if [ -f "feature_list.json" ]; then
            # Validate JSON syntax
            python3 -c "import json; json.load(open('feature_list.json'))"
            echo "✅ feature_list.json is valid JSON"
          fi
      
      - name: Context size check
        run: |
          if [ -f ".agent/working-context/current.md" ]; then
            TOKENS=$(wc -w .agent/working-context/current.md | awk '{print int($1 * 1.3)}')
            echo "Working context: ~$TOKENS tokens"
            if [ "$TOKENS" -gt 10000 ]; then
              echo "⚠️ Warning: Context is large, consider compaction"
            fi
          fi
EOF

echo "   Created .github/workflows/context-engine-ci.yml"

# ============================================================================
# Version File
# ============================================================================
cat > .agent/VERSION << EOF
# Context Engine Version
version: ${CONTEXT_ENGINE_VERSION:-3.1.0}
initialized: $(date -Iseconds)
features:
  - four-layer-memory
  - context-budget-enforcement
  - topological-dependency-sort
  - session-diff-artifacts
  - metrics-tracking
  - needs-review-gates
  - multi-stack-presets
  - ci-integration
EOF

echo ""
echo "🚀 Next Steps:"
echo "   1. Read .agent/AGENT_RULES.md"
echo "   2. Run: .agent/commands.sh compile"
echo "   3. Tell agent: 'Read .agent/workflows/init.md'"
echo ""
