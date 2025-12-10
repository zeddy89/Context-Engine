Debug current issues in the project:

1. Collect diagnostic information:
```bash
echo "=== System Info ==="
node --version 2>/dev/null || echo "Node: not installed"
npm --version 2>/dev/null || echo "npm: not installed"
python3 --version 2>/dev/null || echo "Python: not installed"
go version 2>/dev/null || echo "Go: not installed"
cargo --version 2>/dev/null || echo "Rust: not installed"
echo ""
echo "=== Project Structure ==="
ls -la
echo ""
echo "=== Git Status ==="
git status
echo ""
echo "=== Recent Changes ==="
git diff --stat HEAD~3..HEAD 2>/dev/null || echo "Not enough commits"
```

2. Check for common issues:
```bash
echo ""
echo "=== Dependency Check ==="
[ -f "package.json" ] && npm ls --depth=0 2>&1 | grep -E "(ERR|WARN)" | head -10
[ -f "requirements.txt" ] && pip check 2>&1 | head -10
[ -f "go.mod" ] && go mod verify 2>&1
[ -f "Cargo.toml" ] && cargo check 2>&1 | grep -E "(error|warning)" | head -10
echo ""
echo "=== Port Usage ==="
lsof -i :3000 2>/dev/null || netstat -tlnp 2>/dev/null | grep -E "(3000|8000|8080)" || echo "No common ports in use"
echo ""
echo "=== Process Check ==="
ps aux | grep -E "(node|python|go|cargo)" | grep -v grep | head -5
```

3. Check logs:
```bash
echo ""
echo "=== Recent Logs ==="
[ -f "logs/error.log" ] && tail -20 logs/error.log
[ -f "npm-debug.log" ] && tail -20 npm-debug.log
[ -d ".next" ] && cat .next/server/pages-manifest.json 2>/dev/null | head -20
```

4. Analyze and suggest:
   - Identify the most likely cause of issues
   - Suggest specific fixes
   - Reference relevant documentation
