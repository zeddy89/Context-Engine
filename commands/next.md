Find and display the next feature to implement:

1. Check for in-progress work first:
```bash
grep -A 10 "Status: IN PROGRESS" claude-progress.txt | tail -15
```

2. If nothing in progress, find highest priority incomplete feature:
```bash
cat feature_list.json | jq -r '
  .features 
  | map(select(.passes == false)) 
  | sort_by(.priority) 
  | .[0] 
  | "Priority \(.priority): [\(.id)] \(.description)\n\nDependencies: \(.dependencies | if length == 0 then "none" else join(", ") end)\n\nVerification Steps:\n\(.steps | to_entries | map("  \(.key + 1). \(.value)") | join("\n"))"
'
```

3. Check if dependencies are met:
```bash
# Get the dependencies of the next feature and verify they all pass
cat feature_list.json | jq -r '
  (.features | map(select(.passes == false)) | sort_by(.priority) | .[0].dependencies) as $deps |
  .features | map(select(.id as $id | $deps | index($id))) | map(select(.passes == false)) | 
  if length > 0 then "BLOCKED: These dependencies are not complete: \(map(.id) | join(", "))" 
  else "All dependencies met" end
'
```

4. Display recommendation:
   - Feature ID and description
   - Priority level
   - Dependencies status
   - Verification steps
   - Estimated complexity (based on steps count)
