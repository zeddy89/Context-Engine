#!/bin/bash
# Context Engine Installer

set -e

INSTALL_DIR="${HOME}/tools/context-engine"

echo "═══════════════════════════════════════════════════════════"
echo "           Context Engine Installer                        "
echo "═══════════════════════════════════════════════════════════"

# Check for Claude Code
if ! command -v claude &> /dev/null; then
    echo "⚠️  Claude Code CLI not found"
    echo "   Install from: https://docs.anthropic.com/en/docs/claude-code"
    echo "   Then run this installer again."
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required"
    exit 1
fi

# Create install directory
mkdir -p "$INSTALL_DIR"

# Copy files
echo "📦 Installing to $INSTALL_DIR..."

cp orchestrator.py "$INSTALL_DIR/"
cp loop-runner.py "$INSTALL_DIR/"
cp mcp-setup.py "$INSTALL_DIR/"
cp setup-context-engineered.sh "$INSTALL_DIR/"

# Copy supporting files
cp -r agents "$INSTALL_DIR/" 2>/dev/null || true
cp -r commands "$INSTALL_DIR/" 2>/dev/null || true
cp *.md "$INSTALL_DIR/" 2>/dev/null || true
cp mcp-config.example.json "$INSTALL_DIR/" 2>/dev/null || true

# Make executable
chmod +x "$INSTALL_DIR"/*.py
chmod +x "$INSTALL_DIR"/*.sh

echo "✅ Installed to $INSTALL_DIR"
echo ""
echo "Usage:"
echo "  python3 ~/tools/context-engine/orchestrator.py --new ~/projects/my-app --model opus"
echo ""
echo "Or add to PATH:"
echo "  echo 'export PATH=\"\$PATH:$INSTALL_DIR\"' >> ~/.zshrc"
echo ""
