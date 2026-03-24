#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# install.sh — Set up the MCP Filesystem + Bash Server (using uv)
# ─────────────────────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "📥  Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "📦  Setting up environment with uv..."
uv sync

echo ""
echo "✅  Installation complete!"
echo ""
echo "─────────────────────────────────────────────────────────────────────────"
echo "OPTION A: STANDALONE GUI (for Linux desktops)"
echo "─────────────────────────────────────────────────────────────────────────"
echo ""
echo "1. Edit config.json and set your allowed_paths"
echo ""
echo "2. Edit gui_config.json and add your Anthropic API key:"
echo "   \"api_key\": \"sk-ant-...\""
echo ""
echo "3. Launch the GUI:"
echo "   uv run python chat_gui.py"
echo ""
echo "─────────────────────────────────────────────────────────────────────────"
echo "OPTION B: CLAUDE DESKTOP (if you have Claude Desktop installed)"
echo "─────────────────────────────────────────────────────────────────────────"
echo ""
echo "1. Edit config.json and set your allowed_paths, e.g.:"
echo "   \"/home/$(whoami)\""
echo "   \"/mnt/my-drive\""
echo ""
echo "2. Add this block to your claude_desktop_config.json:"
echo ""
echo "   \"mcpServers\": {"
echo "     \"filesystem-bash\": {"
echo "       \"command\": \"uv\","
echo "       \"args\": [\"run\", \"--directory\", \"$SCRIPT_DIR\", \"python\", \"server.py\"]"
echo "     }"
echo "   }"
echo ""
echo "3. Restart the Claude Desktop app."
echo ""
echo "   Your claude_desktop_config.json is usually at:"
echo "   ~/.config/Claude/claude_desktop_config.json   (Linux)"
echo "   ~/Library/Application Support/Claude/claude_desktop_config.json  (macOS)"
echo "─────────────────────────────────────────────────────────────────────────"
