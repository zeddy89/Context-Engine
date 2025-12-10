Show current project status:

1. Run these commands and show the output:
```bash
echo "=== Project Status ==="
echo ""
echo "Git Status:"
git status --short
echo ""
echo "Recent Commits:"
git log --oneline -10
echo ""
echo "Feature Progress:"
cat feature_list.json | jq '[.features[] | .passes] | {total: length, completed: (map(select(. == true)) | length), remaining: (map(select(. == false)) | length)}'
echo ""
echo "Last Session:"
tail -30 claude-progress.txt
```

2. Summarize:
   - Total features: X
   - Completed: X
   - Remaining: X
   - Last session status
   - Any uncommitted changes
