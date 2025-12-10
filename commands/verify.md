Verify that the project is in a working state:

1. Start the project:
```bash
./init.sh
```

2. Run all verification checks:
```bash
# Run tests
npm test 2>&1 || pytest 2>&1 || go test ./... 2>&1 || cargo test 2>&1

# Check for build errors
npm run build 2>&1 || go build ./... 2>&1 || cargo build 2>&1

# Run linting
npm run lint 2>&1 || flake8 . 2>&1 || go vet ./... 2>&1 || cargo clippy 2>&1
```

3. Check endpoint health (if applicable):
```bash
curl -s localhost:3000/health || curl -s localhost:8000/health || echo "No health endpoint"
```

4. Report results:
   - Tests: PASS/FAIL (X passed, Y failed)
   - Build: PASS/FAIL
   - Lint: PASS/FAIL (X warnings, Y errors)
   - Health: UP/DOWN

5. If anything failed, list the specific failures and suggest fixes.
