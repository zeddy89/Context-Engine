Display and analyze the application specification:

1. Show the full spec:
```bash
cat app_spec.txt 2>/dev/null || cat APP_SPEC.md 2>/dev/null || echo "No app spec found"
```

2. Extract key information:
```bash
echo ""
echo "=== Quick Reference ==="
echo ""
echo "Tech Stack:"
grep -A 10 "Tech Stack" app_spec.txt 2>/dev/null | head -12 || echo "Not specified"
echo ""
echo "API Endpoints:"
grep -A 20 "API Endpoints" app_spec.txt 2>/dev/null | head -22 || echo "Not specified"
echo ""
echo "Verification Commands:"
grep -A 10 "Verification Commands" app_spec.txt 2>/dev/null | head -12 || echo "Not specified"
```

3. Cross-reference with feature list:
```bash
echo ""
echo "=== Coverage Analysis ==="
TOTAL_FEATURES=$(cat feature_list.json | jq '.features | length')
COMPLETED=$(cat feature_list.json | jq '[.features[] | select(.passes == true)] | length')
echo "Features defined: $TOTAL_FEATURES"
echo "Features completed: $COMPLETED"
echo "Coverage: $(( COMPLETED * 100 / TOTAL_FEATURES ))%"
```

4. If the spec seems incomplete or unclear, suggest what sections need more detail.
