Show all blocked features and their blockers:

1. Find features with unmet dependencies:
```bash
cat feature_list.json | jq -r '
  .features as $all |
  .features 
  | map(select(.passes == false and (.dependencies | length > 0))) 
  | map(
      . as $f | 
      ($all | map(select(.id as $id | $f.dependencies | index($id))) | map(select(.passes == false))) as $unmet |
      if ($unmet | length) > 0 then
        {
          id: .id,
          description: .description,
          priority: .priority,
          blocked_by: ($unmet | map(.id))
        }
      else empty end
    )
  | if length == 0 then "No blocked features" 
    else map("[\(.id)] \(.description)\n  Priority: \(.priority)\n  Blocked by: \(.blocked_by | join(", "))\n") | join("\n") end
'
```

2. Find features marked as blocked in progress log:
```bash
echo ""
echo "Features marked BLOCKED in progress log:"
grep -B 2 "Status: BLOCKED" claude-progress.txt | grep "Feature:" || echo "None found"
```

3. Show dependency graph for blocked features:
```bash
echo ""
echo "Dependency chain analysis:"
cat feature_list.json | jq -r '
  .features as $all |
  .features 
  | map(select(.passes == false)) 
  | sort_by(.priority)
  | .[0:5]
  | map("[\(.id)] (P\(.priority)) depends on: \(if .dependencies | length == 0 then "nothing" else .dependencies | join(", ") end)")
  | join("\n")
'
```

4. Recommendation:
   - List features that can be unblocked by completing specific dependencies
   - Suggest optimal order to resolve blockers
