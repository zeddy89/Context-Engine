# Context Engine Architecture

## The Problem: Context Degradation

Large Language Models have a fundamental limitation: fixed context windows. As conversations grow, models must decide what to keep and what to forget. Most AI coding tools handle this poorly:

1. **Accumulation** - Keep adding messages until context is full
2. **Truncation** - Drop old messages when space runs out
3. **Summarization** - Compress history into summaries (loses detail)

All three approaches fail for long-running coding tasks because:

- Important early decisions get pushed out
- Error patterns repeat because failures aren't remembered
- Architecture coherence degrades as context fills with implementation details

## The Solution: Four-Layer Memory

Context Engine borrows from cognitive science and recent AI research to implement a hierarchical memory system:

```
┌─────────────────────────────────────────────────────────────┐
│                    WORKING CONTEXT                          │
│              (Rebuilt fresh each session)                   │
│                                                             │
│  Current feature + relevant memory + recent patterns        │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ compile
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌─────────────────┐   ┌─────────────────┐
│   EPISODIC    │   │    SEMANTIC     │   │   PROCEDURAL    │
│    MEMORY     │   │     MEMORY      │   │     MEMORY      │
├───────────────┤   ├─────────────────┤   ├─────────────────┤
│ Recent events │   │ Project facts   │   │ What worked     │
│ Decisions     │   │ Architecture    │   │ What failed     │
│ Patterns      │   │ Dependencies    │   │ Solutions       │
│               │   │ Conventions     │   │                 │
│ Rolling 10    │   │ Persistent      │   │ Append-only     │
└───────────────┘   └─────────────────┘   └─────────────────┘
```

### Layer 1: Working Context

**What:** The active context window for the current session.

**Lifecycle:** Destroyed and rebuilt at the start of each session.

**Contents:**
- Current feature specification
- Relevant architectural context (pulled from semantic memory)
- Recent patterns (pulled from episodic memory)
- Known failure modes to avoid (pulled from procedural memory)

**Key Insight:** Working context is *computed*, not *accumulated*. Each session starts with exactly what it needs, nothing more.

### Layer 2: Episodic Memory

**What:** Recent events and decisions across sessions.

**Lifecycle:** Rolling window (last N sessions).

**Contents:**
- What was implemented recently
- Decisions made and their rationale
- Emerging patterns in the codebase
- Cross-cutting concerns discovered

**Storage:** `.agent/memory/episodes/`

**Example:**
```markdown
## Session 12 (2025-01-15)
- Implemented F008: WebSocket connection handler
- Decision: Use tokio-tungstenite over ws-rs (better async support)
- Pattern: All WebSocket handlers follow connect -> auth -> subscribe flow
- Discovered: Need to handle reconnection in client SDK
```

### Layer 3: Semantic Memory

**What:** Stable project knowledge and architecture.

**Lifecycle:** Persistent, updated when architecture changes.

**Contents:**
- Tech stack and dependencies
- Module structure and responsibilities  
- API conventions and patterns
- Database schema overview
- Integration points

**Storage:** `.agent/memory/semantic/`

**Example:**
```markdown
# Architecture

## Core Modules
- `api/` - Axum handlers, middleware, extractors
- `domain/` - Business logic, no framework dependencies
- `infra/` - Database, external services, SSH client

## Conventions
- All handlers return `Result<Json<T>, AppError>`
- Database operations use SQLx with compile-time checked queries
- SSH operations go through `SshClient` abstraction
```

### Layer 4: Procedural Memory

**What:** Learned behaviors from successes and failures.

**Lifecycle:** Append-only (never deleted).

**Contents:**
- What approaches worked for specific problem types
- What approaches failed and why
- Solutions to recurring issues
- Performance optimizations discovered

**Storage:** `.agent/memory/procedures/`

**Example:**
```markdown
## Successes
- S001: Using `#[sqlx::test]` for database tests - automatic rollback
- S002: SSH connection pooling with 30s keepalive prevents timeout issues

## Failures  
- F001: Don't use `unwrap()` in async handlers - causes panic without context
- F002: SQLx migrations must be idempotent - use IF NOT EXISTS
```

## Context Compilation

Before each session, the `compile-context.sh` hook builds working context:

```bash
#!/bin/bash
# .agent/hooks/compile-context.sh

# 1. Get current feature
FEATURE=$(jq -r '.features[] | select(.passes != true and .blocked != true) | .id' feature_list.json | head -1)

# 2. Pull relevant semantic memory
cat .agent/memory/semantic/architecture.md > .agent/working-context/current.md

# 3. Add recent episodes (last 3)
tail -n 50 .agent/memory/episodes/recent.md >> .agent/working-context/current.md

# 4. Add relevant procedures
grep -A5 "$FEATURE" .agent/memory/procedures/successes.md >> .agent/working-context/current.md 2>/dev/null
cat .agent/memory/procedures/failures.md >> .agent/working-context/current.md

# 5. Add current feature spec
echo "## Current Task" >> .agent/working-context/current.md
jq ".features[] | select(.id == \"$FEATURE\")" feature_list.json >> .agent/working-context/current.md
```

The result: a focused context document with exactly what's needed for the current task.

## Artifact System

Large outputs (test results, error logs, generated files) are stored by reference:

```
.agent/artifacts/
├── test-output-001.log      # 500 lines of test output
├── error-trace-002.txt      # Stack trace from failure
└── generated-schema-003.sql # Migration file
```

Instead of pasting 500 lines of test output into context, Claude writes:

```markdown
Test output saved to: .agent/artifacts/test-output-001.log
Summary: 45 passed, 2 failed
Failed: test_ssh_connection_timeout, test_credential_encryption
```

The artifact can be retrieved if needed, but doesn't pollute working context.

## Feedback Loop

Every session captures what happened:

```bash
# On success
.agent/commands.sh success "F003" "SSH pooling with bb8 works well"

# On failure  
.agent/commands.sh failure "F003" "russh panics on invalid key format"
```

This feeds procedural memory, so future sessions know:
- What approaches work
- What to avoid
- How to solve recurring problems

## Why This Works

1. **Fresh Start** - Each session begins with computed context, not accumulated garbage

2. **Selective Memory** - Only relevant information is pulled into working context

3. **Learning** - Procedural memory captures patterns across sessions

4. **Scalability** - Memory layers can grow without bloating working context

5. **Recoverability** - If a session goes wrong, the next one starts fresh

## Research Foundation

This architecture draws from:

- **MemGPT** (Berkeley) - Hierarchical memory for LLM agents
- **Generative Agents** (Stanford) - Memory stream and reflection
- **Anthropic's Context Research** - Optimal context window utilization
- **Cognitive Architecture** - Working/episodic/semantic/procedural memory model

## Comparison

| Approach | Context Growth | Long-term Coherence | Recovery from Errors |
|----------|---------------|---------------------|---------------------|
| Accumulation | Linear (bad) | Degrades | Poor |
| Truncation | Bounded | Loses history | Moderate |
| Summarization | Bounded | Loses detail | Moderate |
| **Context Engine** | Constant | Maintained | Excellent |

## Limitations

1. **Setup Overhead** - Requires initialization and harness setup
2. **Feature Granularity** - Works best with well-defined atomic features
3. **Test Dependency** - Relies on tests to verify completeness
4. **Model Dependent** - Tuned for Claude, may need adjustment for others
