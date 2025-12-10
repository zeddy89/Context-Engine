Revert to the last known good state:

**WARNING: This is a destructive operation. Use only when the codebase is broken.**

1. First, show current state:
```bash
echo "Current HEAD:"
git log --oneline -1
echo ""
echo "Uncommitted changes:"
git status --short
echo ""
echo "Last 10 commits:"
git log --oneline -10
```

2. Find the last good commit (look for "session: completed" commits):
```bash
echo "Last successful session commits:"
git log --oneline --grep="session: completed" -5
```

3. Ask for confirmation before proceeding.

4. If confirmed, revert:
```bash
# Stash any uncommitted work
git stash push -m "Pre-revert stash $(date +%Y%m%d-%H%M%S)"

# Get the last successful commit
GOOD_COMMIT=$(git log --oneline --grep="session: completed" -1 --format="%H")

if [ -n "$GOOD_COMMIT" ]; then
    echo "Reverting to: $GOOD_COMMIT"
    git reset --hard $GOOD_COMMIT
    echo "Reverted successfully"
else
    echo "No 'session: completed' commits found"
    echo "Manual intervention required"
fi
```

5. After revert:
```bash
# Verify the state
./init.sh
echo "Verification needed - run /verify to confirm state"
```

6. Document in progress log:
```
---
Session: [DATE/TIME]
Action: REVERT
Reverted to: [commit hash]
Reason: [why revert was needed]
Stashed work: [stash reference if any]
---
```
