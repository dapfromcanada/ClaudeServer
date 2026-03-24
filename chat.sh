#!/usr/bin/env bash
# Launch the Claude Chat GUI
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
exec uv run python chat_gui.py "$@"
