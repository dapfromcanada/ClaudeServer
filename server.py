#!/usr/bin/env python3
"""
MCP Filesystem + Bash Server
Gives Claude access to specific drives and the ability to run bash commands.
Configure allowed paths and security settings in config.json.
"""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_FILE = Path(__file__).parent / "config.json"

def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    # Sensible defaults if no config found
    return {
        "allowed_paths": [str(Path.home())],
        "allow_bash": True,
        "bash_timeout_seconds": 30,
        "blocked_commands": ["rm -rf /", "mkfs", "dd if=", ":(){:|:&};:"]
    }

config = load_config()

# ── Path safety ───────────────────────────────────────────────────────────────

def is_path_allowed(path: str) -> bool:
    """Return True only if `path` lives inside one of the allowed directories."""
    try:
        resolved = Path(path).resolve()
        for allowed in config.get("allowed_paths", []):
            try:
                resolved.relative_to(Path(allowed).resolve())
                return True
            except ValueError:
                continue
    except Exception:
        pass
    return False

def path_error(path: str) -> list[types.TextContent]:
    allowed = config.get("allowed_paths", [])
    return [types.TextContent(
        type="text",
        text=(
            f"❌ Access denied: '{path}' is outside allowed directories.\n"
            f"Allowed paths: {', '.join(allowed)}\n"
            f"Edit config.json to add more paths."
        )
    )]

# ── Server setup ──────────────────────────────────────────────────────────────

server = Server("filesystem-bash-server")

# ── Tool definitions ──────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="read_file",
            description="Read and return the full text contents of a file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file."}
                },
                "required": ["path"]
            }
        ),
        types.Tool(
            name="write_file",
            description="Write text content to a file (creates or overwrites).",
            inputSchema={
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "Path to write to."},
                    "content": {"type": "string", "description": "Text content to write."}
                },
                "required": ["path", "content"]
            }
        ),
        types.Tool(
            name="list_directory",
            description="List the files and subdirectories inside a directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to list."}
                },
                "required": ["path"]
            }
        ),
        types.Tool(
            name="create_directory",
            description="Create a directory (including any missing parents).",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to create."}
                },
                "required": ["path"]
            }
        ),
        types.Tool(
            name="move_file",
            description="Move or rename a file or directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source":      {"type": "string", "description": "Current path."},
                    "destination": {"type": "string", "description": "New path."}
                },
                "required": ["source", "destination"]
            }
        ),
        types.Tool(
            name="delete_path",
            description="Delete a file or directory (directories are removed recursively).",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to delete."}
                },
                "required": ["path"]
            }
        ),
        types.Tool(
            name="run_bash",
            description=(
                "Execute a bash command and return stdout, stderr, and exit code. "
                "Working directory defaults to the user's home directory."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run."},
                    "cwd":     {"type": "string", "description": "Working directory (optional)."}
                },
                "required": ["command"]
            }
        ),
        types.Tool(
            name="get_allowed_paths",
            description="Return the list of directories this server is permitted to access.",
            inputSchema={"type": "object", "properties": {}}
        ),
    ]

# ── Tool handlers ─────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:

        # ── read_file ──────────────────────────────────────────────────────────
        if name == "read_file":
            path = arguments["path"]
            if not is_path_allowed(path):
                return path_error(path)
            content = Path(path).read_text(errors="replace")
            return [types.TextContent(type="text", text=content)]

        # ── write_file ─────────────────────────────────────────────────────────
        elif name == "write_file":
            path = arguments["path"]
            if not is_path_allowed(path):
                return path_error(path)
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(arguments["content"])
            return [types.TextContent(type="text", text=f"✅ Written to {path}")]

        # ── list_directory ─────────────────────────────────────────────────────
        elif name == "list_directory":
            path = arguments["path"]
            if not is_path_allowed(path):
                return path_error(path)
            p = Path(path)
            if not p.is_dir():
                return [types.TextContent(type="text", text=f"❌ Not a directory: {path}")]
            lines = []
            for item in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
                if item.is_dir():
                    lines.append(f"📁  {item.name}/")
                else:
                    size = item.stat().st_size
                    size_str = f"{size:,} B" if size < 1024 else f"{size/1024:.1f} KB" if size < 1_048_576 else f"{size/1_048_576:.1f} MB"
                    lines.append(f"📄  {item.name}  ({size_str})")
            text = "\n".join(lines) if lines else "(empty directory)"
            return [types.TextContent(type="text", text=text)]

        # ── create_directory ───────────────────────────────────────────────────
        elif name == "create_directory":
            path = arguments["path"]
            if not is_path_allowed(path):
                return path_error(path)
            Path(path).mkdir(parents=True, exist_ok=True)
            return [types.TextContent(type="text", text=f"✅ Directory created: {path}")]

        # ── move_file ──────────────────────────────────────────────────────────
        elif name == "move_file":
            src, dst = arguments["source"], arguments["destination"]
            if not is_path_allowed(src):
                return path_error(src)
            if not is_path_allowed(dst):
                return path_error(dst)
            shutil.move(src, dst)
            return [types.TextContent(type="text", text=f"✅ Moved: {src} → {dst}")]

        # ── delete_path ────────────────────────────────────────────────────────
        elif name == "delete_path":
            path = arguments["path"]
            if not is_path_allowed(path):
                return path_error(path)
            p = Path(path)
            if not p.exists():
                return [types.TextContent(type="text", text=f"❌ Path does not exist: {path}")]
            if p.is_dir():
                shutil.rmtree(path)
            else:
                p.unlink()
            return [types.TextContent(type="text", text=f"✅ Deleted: {path}")]

        # ── run_bash ───────────────────────────────────────────────────────────
        elif name == "run_bash":
            if not config.get("allow_bash", True):
                return [types.TextContent(type="text", text="❌ Bash execution is disabled in config.json.")]

            command = arguments["command"]
            blocked = config.get("blocked_commands", [])
            for pattern in blocked:
                if pattern in command:
                    return [types.TextContent(
                        type="text",
                        text=f"❌ Command blocked — contains forbidden pattern: '{pattern}'"
                    )]

            cwd = arguments.get("cwd") or str(Path.home())
            if not is_path_allowed(cwd):
                return path_error(cwd)

            timeout = config.get("bash_timeout_seconds", 30)
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout
            )

            parts = []
            if result.stdout.strip():
                parts.append(f"STDOUT:\n{result.stdout.rstrip()}")
            if result.stderr.strip():
                parts.append(f"STDERR:\n{result.stderr.rstrip()}")
            parts.append(f"Exit code: {result.returncode}")
            return [types.TextContent(type="text", text="\n\n".join(parts))]

        # ── get_allowed_paths ──────────────────────────────────────────────────
        elif name == "get_allowed_paths":
            paths = config.get("allowed_paths", [])
            text = "Allowed paths:\n" + "\n".join(f"  • {p}" for p in paths)
            return [types.TextContent(type="text", text=text)]

        else:
            return [types.TextContent(type="text", text=f"❌ Unknown tool: {name}")]

    except subprocess.TimeoutExpired:
        return [types.TextContent(type="text", text=f"❌ Command timed out after {config.get('bash_timeout_seconds', 30)}s.")]
    except PermissionError as e:
        return [types.TextContent(type="text", text=f"❌ Permission denied: {e}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ Error ({type(e).__name__}): {e}")]


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
