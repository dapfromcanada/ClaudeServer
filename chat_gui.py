#!/usr/bin/env python3
"""
Claude Chat GUI — Qt6 Dark Mode Client with MCP Tool Support
A desktop chat interface for Claude with filesystem and bash access.
Features: model selector with pricing, Ask/Plan/Agent modes, cost tracking.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QScrollArea,
    QFrame, QComboBox, QMessageBox, QDialog, QFormLayout,
    QDialogButtonBox, QPlainTextEdit, QLineEdit, QFileDialog,
    QListWidget, QListWidgetItem, QSplitter
)

import anthropic

# ── Models & Pricing ──────────────────────────────────────────────────────────

# Known pricing (per 1M tokens). Updated manually when Anthropic changes pricing.
KNOWN_PRICING = {
    "claude-3-5-haiku-20241022": {"label": "Haiku 3.5",  "input_cost": 0.80,  "output_cost": 4.00,  "max_output": 8192},
    "claude-sonnet-4-20250514":  {"label": "Sonnet 4",   "input_cost": 3.00,  "output_cost": 15.00, "max_output": 16384},
    "claude-opus-4-20250514":    {"label": "Opus 4",     "input_cost": 15.00, "output_cost": 75.00, "max_output": 16384},
    # Older models
    "claude-3-5-sonnet-20241022": {"label": "Sonnet 3.5 v2", "input_cost": 3.00,  "output_cost": 15.00, "max_output": 8192},
    "claude-3-5-sonnet-20240620": {"label": "Sonnet 3.5",    "input_cost": 3.00,  "output_cost": 15.00, "max_output": 8192},
    "claude-3-opus-20240229":     {"label": "Opus 3",        "input_cost": 15.00, "output_cost": 75.00, "max_output": 4096},
    "claude-3-haiku-20240307":    {"label": "Haiku 3",       "input_cost": 0.25,  "output_cost": 1.25,  "max_output": 4096},
}

# Default max output tokens for unknown models
DEFAULT_MAX_OUTPUT = 4096

DEFAULT_MODELS = [
    {"id": "claude-3-5-haiku-20241022", "label": "Haiku 3.5",  "input_cost": 0.80,  "output_cost": 4.00,  "max_output": 8192},
    {"id": "claude-sonnet-4-20250514",  "label": "Sonnet 4",   "input_cost": 3.00,  "output_cost": 15.00, "max_output": 16384},
    {"id": "claude-opus-4-20250514",    "label": "Opus 4",     "input_cost": 15.00, "output_cost": 75.00, "max_output": 16384},
]

def model_entry_from_id(model_id: str) -> dict:
    """Build a model entry dict from an id, using known pricing if available."""
    pricing = KNOWN_PRICING.get(model_id, {})
    label = pricing.get("label", model_id)
    return {
        "id": model_id,
        "label": label,
        "input_cost": pricing.get("input_cost", 0.0),
        "output_cost": pricing.get("output_cost", 0.0),
        "max_output": pricing.get("max_output", DEFAULT_MAX_OUTPUT),
    }

def get_model_map(models: list[dict]) -> dict:
    return {m["id"]: m for m in models}

# ── Modes ─────────────────────────────────────────────────────────────────────

MODES = {
    "Ask": {
        "description": "Answer questions only — no tool access",
        "tools": [],
        "system_suffix": "\n\nYou are in ASK mode. Answer the user's question directly. Do NOT use any tools.",
    },
    "Plan": {
        "description": "Read & analyze — can read files but won't modify anything",
        "tools": ["read_file", "list_directory", "get_allowed_paths"],
        "system_suffix": "\n\nYou are in PLAN mode. You may read files and list directories to analyze the codebase, but you must NOT write files, delete anything, or run commands. Describe what changes you would make without executing them.",
    },
    "Agent": {
        "description": "Full autonomy — read, write, execute",
        "tools": None,
        "system_suffix": "\n\nYou are in AGENT mode. You have full access to filesystem tools and bash. Use them proactively when helpful.",
    },
}

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / "gui_config.json"
SERVER_SCRIPT = CONFIG_DIR / "server.py"

SERVER_CONFIG_FILE = CONFIG_DIR / "config.json"

def load_server_config() -> dict:
    if SERVER_CONFIG_FILE.exists():
        with open(SERVER_CONFIG_FILE) as f:
            return json.load(f)
    return {"allowed_paths": [], "allow_bash": True, "bash_timeout_seconds": 30, "blocked_commands": []}

def save_server_config(cfg: dict):
    with open(SERVER_CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

DEFAULT_CONFIG = {
    "api_key": "",
    "model": "claude-sonnet-4-20250514",
    "mode": "Agent",
    "max_tokens": 8192,
    "system_prompt": "You are Claude, a helpful AI assistant. You have access to filesystem and bash tools through MCP. Use them when helpful to answer user requests."
}

def load_gui_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
            return {**DEFAULT_CONFIG, **cfg}
    return DEFAULT_CONFIG.copy()

def save_gui_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

# ── Dark Mode Stylesheet ──────────────────────────────────────────────────────

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1e1e1e;
    color: #d4d4d4;
}

QTextEdit, QPlainTextEdit, QLineEdit {
    background-color: #252526;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    padding: 8px;
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 13px;
    selection-background-color: #264f78;
}

QTextEdit:focus, QPlainTextEdit:focus, QLineEdit:focus {
    border: 1px solid #007acc;
}

QPushButton {
    background-color: #0e639c;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
    min-width: 80px;
}

QPushButton:hover {
    background-color: #1177bb;
}

QPushButton:pressed {
    background-color: #0d5a8c;
}

QPushButton:disabled {
    background-color: #3c3c3c;
    color: #6e6e6e;
}

QPushButton#settingsBtn {
    background-color: #3c3c3c;
    min-width: 40px;
    padding: 8px;
}

QPushButton#settingsBtn:hover {
    background-color: #4e4e4e;
}

QPushButton#newChatBtn {
    background-color: #3c3c3c;
    min-width: 40px;
    padding: 8px;
}

QPushButton#newChatBtn:hover {
    background-color: #4e4e4e;
}

QComboBox {
    background-color: #2d2d30;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 6px 12px;
    font-size: 12px;
    min-width: 100px;
}

QComboBox:hover {
    border: 1px solid #007acc;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #d4d4d4;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #252526;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    selection-background-color: #094771;
    outline: none;
}

QLabel {
    color: #d4d4d4;
}

QLabel#titleLabel {
    font-size: 18px;
    font-weight: bold;
    color: #569cd6;
}

QLabel#statusLabel {
    color: #6a9955;
    font-size: 12px;
}

QLabel#costLabel {
    color: #dcdcaa;
    font-size: 12px;
}

QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollBar:vertical {
    background-color: #1e1e1e;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background-color: #424242;
    border-radius: 6px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #525252;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QFrame#messageFrame {
    background-color: #252526;
    border-radius: 8px;
    padding: 12px;
}

QFrame#userMessage {
    background-color: #264f78;
    border-radius: 8px;
}

QFrame#assistantMessage {
    background-color: #2d2d30;
    border-radius: 8px;
}

QFrame#toolMessage {
    background-color: #3c3c3c;
    border-radius: 8px;
    border-left: 3px solid #569cd6;
}

QDialog {
    background-color: #1e1e1e;
}

QDialogButtonBox QPushButton {
    min-width: 100px;
}
"""

# ── Mode Button Colors ────────────────────────────────────────────────────────

MODE_COLORS = {
    "Ask":   {"bg": "#2d5a27", "hover": "#367030", "active": "#6a9955"},
    "Plan":  {"bg": "#6c5300", "hover": "#806200", "active": "#dcdcaa"},
    "Agent": {"bg": "#0e639c", "hover": "#1177bb", "active": "#4fc3f7"},
}

# ── Message Widget ────────────────────────────────────────────────────────────

class MessageWidget(QFrame):
    def __init__(self, role: str, content: str, parent=None):
        super().__init__(parent)
        self.role = role
        
        if role == "user":
            self.setObjectName("userMessage")
            label_text = "You"
            label_color = "#4fc3f7"
        elif role == "assistant":
            self.setObjectName("assistantMessage")
            label_text = "Claude"
            label_color = "#ce9178"
        else:  # tool
            self.setObjectName("toolMessage")
            label_text = "Tool Result"
            label_color = "#569cd6"
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        
        # Role label
        role_label = QLabel(label_text)
        role_label.setStyleSheet(f"color: {label_color}; font-weight: bold; font-size: 12px;")
        layout.addWidget(role_label)
        
        # Content
        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_label.setStyleSheet("color: #d4d4d4; font-size: 14px; line-height: 1.5;")
        layout.addWidget(content_label)

# ── Settings Dialog ───────────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self.server_config = load_server_config()
        self.setWindowTitle("Settings")
        self.setMinimumWidth(550)
        self.setMinimumHeight(500)
        self.setStyleSheet(DARK_STYLESHEET)
        
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # API Key
        self.api_key_edit = QLineEdit(self.config.get("api_key", ""))
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("sk-ant-...")
        layout.addRow("Anthropic API Key:", self.api_key_edit)
        
        # Max Tokens
        self.max_tokens_edit = QLineEdit(str(self.config.get("max_tokens", DEFAULT_CONFIG["max_tokens"])))
        layout.addRow("Max Tokens:", self.max_tokens_edit)
        
        # System Prompt
        self.system_edit = QPlainTextEdit(self.config.get("system_prompt", DEFAULT_CONFIG["system_prompt"]))
        self.system_edit.setMaximumHeight(80)
        layout.addRow("System Prompt:", self.system_edit)
        
        # ── Allowed Paths ──────────────────────────────────────────────
        paths_label = QLabel("Allowed Paths (filesystem access):")
        paths_label.setStyleSheet("color: #569cd6; font-weight: bold; margin-top: 8px;")
        layout.addRow(paths_label)
        
        # Path list
        self.paths_list = QListWidget()
        self.paths_list.setStyleSheet(
            "QListWidget { background-color: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; "
            "border-radius: 4px; font-size: 13px; } "
            "QListWidget::item { padding: 4px; } "
            "QListWidget::item:selected { background-color: #094771; }"
        )
        self.paths_list.setMinimumHeight(120)
        for p in self.server_config.get("allowed_paths", []):
            self.paths_list.addItem(p)
        layout.addRow(self.paths_list)
        
        # Path buttons
        path_buttons = QHBoxLayout()
        
        browse_btn = QPushButton("📁 Browse...")
        browse_btn.clicked.connect(self.browse_path)
        browse_btn.setStyleSheet(
            "background-color: #2d5a27; min-width: 100px;"
        )
        path_buttons.addWidget(browse_btn)
        
        remove_btn = QPushButton("✕ Remove")
        remove_btn.clicked.connect(self.remove_path)
        remove_btn.setStyleSheet(
            "background-color: #6c1717; min-width: 100px;"
        )
        path_buttons.addWidget(remove_btn)
        
        path_buttons.addStretch()
        layout.addRow(path_buttons)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
    
    def browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Directory", str(Path.home()))
        if path:
            # Don't add duplicates
            existing = [self.paths_list.item(i).text() for i in range(self.paths_list.count())]
            if path not in existing:
                self.paths_list.addItem(path)
    
    def remove_path(self):
        selected = self.paths_list.currentRow()
        if selected >= 0:
            self.paths_list.takeItem(selected)
    
    def get_config(self) -> dict:
        return {
            **self.config,
            "api_key": self.api_key_edit.text().strip(),
            "max_tokens": int(self.max_tokens_edit.text() or DEFAULT_CONFIG["max_tokens"]),
            "system_prompt": self.system_edit.toPlainText().strip() or DEFAULT_CONFIG["system_prompt"]
        }
    
    def get_allowed_paths(self) -> list[str]:
        return [self.paths_list.item(i).text() for i in range(self.paths_list.count())]

# ── MCP Client ────────────────────────────────────────────────────────────────

class MCPClient:
    """Manages communication with the MCP server subprocess."""
    
    def __init__(self, server_script: Path):
        self.server_script = server_script
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0
        self.tools: list[dict] = []
    
    def start(self):
        """Start the MCP server subprocess."""
        if self.process is not None:
            return
        
        self.process = subprocess.Popen(
            [sys.executable, str(self.server_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        # Initialize the connection
        self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "claude-chat-gui", "version": "1.0.0"}
        })
        
        # Send initialized notification
        self._send_notification("notifications/initialized", {})
        
        # Get available tools
        response = self._send_request("tools/list", {})
        if response and "tools" in response:
            self.tools = response["tools"]
    
    def stop(self):
        """Stop the MCP server subprocess."""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None
    
    def _send_request(self, method: str, params: dict) -> Optional[dict]:
        """Send a JSON-RPC request and wait for response."""
        if not self.process:
            return None
        
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params
        }
        
        try:
            self.process.stdin.write(json.dumps(request) + "\n")
            self.process.stdin.flush()
            
            response_line = self.process.stdout.readline()
            if response_line:
                response = json.loads(response_line)
                return response.get("result")
        except Exception as e:
            print(f"MCP request error: {e}")
        
        return None
    
    def _send_notification(self, method: str, params: dict):
        """Send a JSON-RPC notification (no response expected)."""
        if not self.process:
            return
        
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        try:
            self.process.stdin.write(json.dumps(notification) + "\n")
            self.process.stdin.flush()
        except Exception as e:
            print(f"MCP notification error: {e}")
    
    def call_tool(self, name: str, arguments: dict) -> str:
        """Call an MCP tool and return the result as text."""
        response = self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })
        
        if response and "content" in response:
            texts = [c.get("text", "") for c in response["content"] if c.get("type") == "text"]
            return "\n".join(texts)
        
        return f"Error: No response from tool '{name}'"
    
    def get_tools_for_api(self, allowed_names: Optional[list[str]] = None) -> list[dict]:
        """Convert MCP tools to Anthropic API format, optionally filtered."""
        api_tools = []
        for tool in self.tools:
            if allowed_names is not None and tool["name"] not in allowed_names:
                continue
            api_tools.append({
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}})
            })
        return api_tools

# ── Chat Worker Thread ────────────────────────────────────────────────────────

class ChatWorker(QThread):
    """Background thread for API calls."""
    
    message_received = pyqtSignal(str, str)  # role, content
    tool_use = pyqtSignal(str, str, str)  # tool_id, name, input_json
    bash_output = pyqtSignal(str, str)    # command, result
    usage_update = pyqtSignal(int, int)   # input_tokens, output_tokens
    finished = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, client: anthropic.Anthropic, mcp: MCPClient, config: dict,
                 messages: list, mode: str):
        super().__init__()
        self.client = client
        self.mcp = mcp
        self.config = config
        self.messages = messages
        self.mode = mode
        self._stop = False
    
    def run(self):
        try:
            mode_cfg = MODES[self.mode]
            allowed = mode_cfg["tools"]
            # None = all tools, [] = no tools, [...] = specific tools
            tools = self.mcp.get_tools_for_api(allowed) if allowed is None or allowed else None

            system = self.config["system_prompt"] + mode_cfg["system_suffix"]
            
            while not self._stop:
                # Determine max tokens for this model
                model_id = self.config["model"]
                pricing = KNOWN_PRICING.get(model_id, {})
                max_tokens = min(
                    self.config.get("max_tokens", 8192),
                    pricing.get("max_output", DEFAULT_MAX_OUTPUT),
                )

                kwargs = dict(
                    model=model_id,
                    max_tokens=max_tokens,
                    system=system,
                    messages=self.messages,
                )
                if tools:
                    kwargs["tools"] = tools

                response = self.client.messages.create(**kwargs)
                
                # Emit usage
                if response.usage:
                    self.usage_update.emit(
                        response.usage.input_tokens,
                        response.usage.output_tokens,
                    )
                
                # Process response content
                text_parts = []
                tool_uses = []
                
                for block in response.content:
                    if block.type == "text":
                        text_parts.append(block.text)
                    elif block.type == "tool_use":
                        tool_uses.append(block)
                
                # Emit text response
                if text_parts:
                    self.message_received.emit("assistant", "\n".join(text_parts))
                
                # Handle tool calls
                if tool_uses and response.stop_reason == "tool_use":
                    # Add assistant message with tool use to history
                    self.messages.append({
                        "role": "assistant",
                        "content": response.content
                    })
                    
                    # Execute tools and collect results
                    tool_results = []
                    for tool_use in tool_uses:
                        self.tool_use.emit(tool_use.id, tool_use.name, json.dumps(tool_use.input, indent=2))
                        
                        # Call the MCP tool
                        result = self.mcp.call_tool(tool_use.name, tool_use.input)
                        self.message_received.emit("tool", f"**{tool_use.name}**\n{result}")
                        if tool_use.name == "run_bash":
                            self.bash_output.emit(tool_use.input.get("command", ""), result)
                        
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": result
                        })
                    
                    # Add tool results to messages
                    self.messages.append({
                        "role": "user",
                        "content": tool_results
                    })
                    
                    # Continue the loop to get Claude's response to tool results
                    continue
                else:
                    # No more tool calls, we're done
                    break
            
            self.finished.emit()
            
        except anthropic.APIError as e:
            self.error.emit(f"API Error: {e.message}")
        except Exception as e:
            self.error.emit(f"Error: {str(e)}")

# ── Main Window ───────────────────────────────────────────────────────────────

class ChatWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_gui_config()
        self.messages: list[dict] = []
        self.mcp = MCPClient(SERVER_SCRIPT)
        self.worker: Optional[ChatWorker] = None
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.models = self._load_cached_models()
        self.model_map = get_model_map(self.models)
        
        self.setup_ui()
        self.start_mcp()
        
        # Auto-refresh models on startup if we have an API key
        if self.config.get("api_key"):
            QTimer.singleShot(500, self._auto_refresh_models)
    
    def setup_ui(self):
        self.setWindowTitle("Claude Chat")
        self.setMinimumSize(800, 600)
        self.resize(1050, 750)
        self.setStyleSheet(DARK_STYLESHEET)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        
        # ── Row 1: Title + New Chat + Settings ────────────────────────────
        row1 = QHBoxLayout()
        
        title = QLabel("Claude Chat")
        title.setObjectName("titleLabel")
        row1.addWidget(title)
        
        row1.addStretch()
        
        new_chat_btn = QPushButton("🗒 New Chat")
        new_chat_btn.setObjectName("newChatBtn")
        new_chat_btn.setToolTip("Clear conversation and start fresh")
        new_chat_btn.clicked.connect(self.new_chat)
        row1.addWidget(new_chat_btn)
        
        settings_btn = QPushButton("⚙")
        settings_btn.setObjectName("settingsBtn")
        settings_btn.setToolTip("Settings")
        settings_btn.clicked.connect(self.open_settings)
        row1.addWidget(settings_btn)
        
        layout.addLayout(row1)
        
        # ── Row 2: Model + Mode + Status + Cost ──────────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        
        # Model dropdown
        model_label = QLabel("Model:")
        model_label.setStyleSheet("color: #858585; font-size: 12px;")
        row2.addWidget(model_label)
        
        self.model_combo = QComboBox()
        self._populate_model_combo()
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        row2.addWidget(self.model_combo)
        
        # Refresh models button
        refresh_btn = QPushButton("🔄")
        refresh_btn.setObjectName("settingsBtn")
        refresh_btn.setToolTip("Fetch available models from Anthropic API")
        refresh_btn.setFixedWidth(36)
        refresh_btn.clicked.connect(self.refresh_models)
        row2.addWidget(refresh_btn)
        
        # Separator
        sep1 = QLabel("│")
        sep1.setStyleSheet("color: #3c3c3c;")
        row2.addWidget(sep1)
        
        # Mode buttons
        mode_label = QLabel("Mode:")
        mode_label.setStyleSheet("color: #858585; font-size: 12px;")
        row2.addWidget(mode_label)
        
        self.mode_buttons: dict[str, QPushButton] = {}
        current_mode = self.config.get("mode", "Agent")
        
        for mode_name in MODES:
            btn = QPushButton(mode_name)
            btn.setFixedWidth(70)
            btn.setToolTip(MODES[mode_name]["description"])
            btn.clicked.connect(lambda checked, m=mode_name: self.set_mode(m))
            self.mode_buttons[mode_name] = btn
            row2.addWidget(btn)
        
        self._update_mode_buttons(current_mode)
        
        row2.addStretch()
        
        # Status
        self.status_label = QLabel("Connecting...")
        self.status_label.setObjectName("statusLabel")
        row2.addWidget(self.status_label)
        
        # Separator
        sep2 = QLabel("│")
        sep2.setStyleSheet("color: #3c3c3c;")
        row2.addWidget(sep2)
        
        # Cost
        self.cost_label = QLabel("Cost: $0.0000")
        self.cost_label.setObjectName("costLabel")
        self.cost_label.setToolTip("Estimated cost for this conversation session")
        row2.addWidget(self.cost_label)
        
        layout.addLayout(row2)
        
        # ── Chat area ─────────────────────────────────────────────────────
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_layout.setSpacing(12)
        self.chat_layout.setContentsMargins(0, 0, 8, 0)
        
        self.chat_scroll.setWidget(self.chat_container)

        # ── Terminal + Chat splitter ───────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet(
            "QSplitter::handle { background-color: #3c3c3c; }"
            "QSplitter::handle:hover { background-color: #007acc; }"
        )

        # Left: terminal panel
        terminal_panel = QWidget()
        term_layout = QVBoxLayout(terminal_panel)
        term_layout.setContentsMargins(0, 0, 4, 0)
        term_layout.setSpacing(4)

        term_header = QHBoxLayout()
        term_title = QLabel("⬛ Terminal")
        term_title.setStyleSheet("color: #4ec9b0; font-weight: bold; font-size: 12px;")
        term_header.addWidget(term_title)
        term_header.addStretch()
        term_clear_btn = QPushButton("Clear")
        term_clear_btn.setFixedHeight(24)
        term_clear_btn.setStyleSheet(
            "background-color: #3c3c3c; color: #858585; font-size: 11px; "
            "padding: 2px 8px; min-width: 40px; font-weight: normal;"
        )
        term_clear_btn.clicked.connect(self.clear_terminal)
        term_header.addWidget(term_clear_btn)
        term_layout.addLayout(term_header)

        self.terminal_edit = QTextEdit()
        self.terminal_edit.setReadOnly(True)
        self.terminal_edit.setStyleSheet(
            "QTextEdit { background-color: #0d1117; color: #e6edf3; "
            "border: 1px solid #3c3c3c; border-radius: 4px; "
            "font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace; "
            "font-size: 12px; padding: 8px; }"
        )
        term_layout.addWidget(self.terminal_edit)

        splitter.addWidget(terminal_panel)
        splitter.addWidget(self.chat_scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)
        splitter.setSizes([300, 700])

        layout.addWidget(splitter, stretch=1)

        # ── Input area ────────────────────────────────────────────────────
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)
        
        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText("Type a message... (Ctrl+Enter to send)")
        self.input_edit.setMaximumHeight(100)
        self.input_edit.installEventFilter(self)
        input_layout.addWidget(self.input_edit, stretch=1)
        
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_message)
        self.send_btn.setMinimumHeight(50)
        input_layout.addWidget(self.send_btn)
        
        layout.addLayout(input_layout)
    
    # ── Mode management ───────────────────────────────────────────────────
    
    def _update_mode_buttons(self, active_mode: str):
        for name, btn in self.mode_buttons.items():
            colors = MODE_COLORS[name]
            if name == active_mode:
                btn.setStyleSheet(
                    f"background-color: {colors['bg']}; color: {colors['active']}; "
                    f"border: 1px solid {colors['active']}; font-weight: bold; min-width: 60px;"
                )
            else:
                btn.setStyleSheet(
                    "background-color: #2d2d30; color: #858585; "
                    "border: 1px solid #3c3c3c; font-weight: normal; min-width: 60px;"
                )
    
    def set_mode(self, mode: str):
        self.config["mode"] = mode
        save_gui_config(self.config)
        self._update_mode_buttons(mode)
        self.update_status_ready()
    
    # ── Model management ──────────────────────────────────────────────────
    
    def _populate_model_combo(self):
        """Fill the model dropdown from self.models."""
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for m in self.models:
            cost_str = ""
            if m["input_cost"] > 0 or m["output_cost"] > 0:
                cost_str = f"  (${m['input_cost']:.2f} / ${m['output_cost']:.2f})"
            else:
                cost_str = "  (pricing TBD)"
            self.model_combo.addItem(f"{m['label']}{cost_str}", m["id"])
        # Select current model
        current_model = self.config.get("model", DEFAULT_MODELS[1]["id"])
        for i, m in enumerate(self.models):
            if m["id"] == current_model:
                self.model_combo.setCurrentIndex(i)
                break
        self.model_combo.blockSignals(False)
    
    def on_model_changed(self, index: int):
        model_id = self.model_combo.itemData(index)
        if model_id:
            self.config["model"] = model_id
            save_gui_config(self.config)
            self.update_status_ready()
    
    def refresh_models(self):
        """Fetch available models from the Anthropic API and update the dropdown."""
        api_key = self.config.get("api_key", "")
        if not api_key:
            QMessageBox.warning(self, "API Key Required",
                                "Set your API key in Settings first.")
            return
        
        self.status_label.setText("🔄 Fetching models...")
        self.status_label.setStyleSheet("color: #dcdcaa; font-size: 12px;")
        QApplication.processEvents()
        
        fetched = self._fetch_models_from_api(api_key)
        if fetched:
            self.models = fetched
            self.model_map = get_model_map(self.models)
            self._save_cached_models()
            self._populate_model_combo()
            QMessageBox.information(self, "Models Updated",
                f"Found {len(fetched)} models. Dropdown updated.")
        else:
            QMessageBox.warning(self, "No Models",
                "Could not fetch models. Keeping current list.")
        
        self.update_status_ready()
    
    def _auto_refresh_models(self):
        """Silently refresh models on startup — no popups."""
        api_key = self.config.get("api_key", "")
        if not api_key:
            return
        
        self.status_label.setText("🔄 Loading models...")
        self.status_label.setStyleSheet("color: #dcdcaa; font-size: 12px;")
        QApplication.processEvents()
        
        fetched = self._fetch_models_from_api(api_key)
        if fetched:
            self.models = fetched
            self.model_map = get_model_map(self.models)
            self._save_cached_models()
            self._populate_model_combo()
        
        self.update_status_ready()
    
    def _fetch_models_from_api(self, api_key: str) -> list[dict]:
        """Query the Anthropic API for available models. Returns sorted list or empty on failure."""
        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.models.list(limit=100)
            
            fetched = []
            for model in response.data:
                entry = model_entry_from_id(model.id)
                fetched.append(entry)
            
            def sort_key(m):
                has_price = m["input_cost"] > 0
                return (0 if has_price else 1, -m["input_cost"], m["label"])
            fetched.sort(key=sort_key)
            return fetched
        except Exception as e:
            print(f"Model fetch error: {e}")
            return []
    
    @staticmethod
    def _load_cached_models() -> list[dict]:
        """Load models from cache file, falling back to defaults."""
        cache_file = CONFIG_DIR / "models_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    cached = json.load(f)
                if cached:
                    return cached
            except Exception:
                pass
        return list(DEFAULT_MODELS)
    
    def _save_cached_models(self):
        """Save current model list to cache file."""
        cache_file = CONFIG_DIR / "models_cache.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(self.models, f, indent=2)
        except Exception as e:
            print(f"Failed to save model cache: {e}")
    
    # ── Helpers ───────────────────────────────────────────────────────────
    
    def get_current_model_info(self) -> dict:
        model_id = self.config.get("model", DEFAULT_MODELS[1]["id"])
        # Check dynamic model map first, then build from known pricing
        if model_id in self.model_map:
            return self.model_map[model_id]
        return model_entry_from_id(model_id)
    
    def calculate_cost(self) -> float:
        info = self.get_current_model_info()
        cost = (self.session_input_tokens * info["input_cost"] / 1_000_000 +
                self.session_output_tokens * info["output_cost"] / 1_000_000)
        return cost
    
    def update_cost_label(self):
        cost = self.calculate_cost()
        self.cost_label.setText(f"Cost: ${cost:.4f}")
        tokens = self.session_input_tokens + self.session_output_tokens
        self.cost_label.setToolTip(
            f"Input: {self.session_input_tokens:,} tokens\n"
            f"Output: {self.session_output_tokens:,} tokens\n"
            f"Total: {tokens:,} tokens"
        )
    
    def update_status_ready(self):
        model_info = self.get_current_model_info()
        mode = self.config.get("mode", "Agent")
        tool_count = len(self.mcp.tools)
        if mode == "Ask":
            tools_text = "no tools"
        elif mode == "Plan":
            tools_text = "read-only"
        else:
            tools_text = f"{tool_count} tools"
        self.status_label.setText(f"✓ {model_info['label']} · {mode} · {tools_text}")
        self.status_label.setStyleSheet("color: #6a9955; font-size: 12px;")
    
    def eventFilter(self, obj, event):
        """Handle Ctrl+Enter to send."""
        if obj == self.input_edit and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                self.send_message()
                return True
        return super().eventFilter(obj, event)
    
    def start_mcp(self):
        """Start the MCP server."""
        try:
            self.mcp.start()
            self.update_status_ready()
        except Exception as e:
            self.status_label.setText("✗ MCP Error")
            self.status_label.setStyleSheet("color: #f44747;")
            QMessageBox.warning(self, "MCP Error", f"Failed to start MCP server:\n{e}")
    
    def open_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.get_config()
            save_gui_config(self.config)
            
            # Save allowed paths to server config.json
            server_cfg = load_server_config()
            server_cfg["allowed_paths"] = dialog.get_allowed_paths()
            save_server_config(server_cfg)
            
            # Restart MCP server so it picks up the new paths
            self.mcp.stop()
            self.start_mcp()
            self.update_status_ready()
    
    def add_terminal_entry(self, command: str, output: str):
        """Append a bash command + output to the terminal panel."""
        def esc(s):
            return (s.replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;")
                     .replace("\n", "<br/>"))

        html = (
            f'<div style="margin-bottom:6px;">'
            f'<span style="color:#4ec9b0;">$</span>&nbsp;'
            f'<span style="color:#dcdcaa;font-weight:bold;">{esc(command)}</span>'
            f'<br/><span style="color:#abb2bf;">{esc(output)}</span>'
            f'</div>'
            f'<div style="border-top:1px solid #2a2a2a;margin:4px 0;"></div>'
        )
        self.terminal_edit.moveCursor(QTextCursor.MoveOperation.End)
        self.terminal_edit.insertHtml(html)
        self.terminal_edit.verticalScrollBar().setValue(
            self.terminal_edit.verticalScrollBar().maximum()
        )

    def clear_terminal(self):
        self.terminal_edit.clear()

    def new_chat(self):
        """Clear conversation and start fresh."""
        self.messages.clear()
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.update_cost_label()
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.terminal_edit.clear()
        self.update_status_ready()
    
    def add_message(self, role: str, content: str):
        """Add a message to the chat display."""
        widget = MessageWidget(role, content)
        self.chat_layout.addWidget(widget)
        QTimer.singleShot(50, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        ))
    
    def send_message(self):
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        
        if not self.config.get("api_key"):
            QMessageBox.warning(self, "API Key Required", 
                "Please set your Anthropic API key in Settings.")
            self.open_settings()
            return
        
        self.input_edit.clear()
        self.add_message("user", text)
        self.messages.append({"role": "user", "content": text})
        
        self.input_edit.setEnabled(False)
        self.send_btn.setEnabled(False)
        model_info = self.get_current_model_info()
        mode = self.config.get("mode", "Agent")
        self.status_label.setText(f"⏳ Thinking... ({model_info['label']} · {mode})")
        self.status_label.setStyleSheet("color: #dcdcaa; font-size: 12px;")
        
        client = anthropic.Anthropic(api_key=self.config["api_key"])
        self.worker = ChatWorker(client, self.mcp, self.config, self.messages.copy(), mode)
        self.worker.message_received.connect(self.on_message_received)
        self.worker.bash_output.connect(self.add_terminal_entry)
        self.worker.usage_update.connect(self.on_usage_update)
        self.worker.finished.connect(self.on_response_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()
    
    def on_message_received(self, role: str, content: str):
        self.add_message(role, content)
        if role == "assistant":
            self.messages.append({"role": "assistant", "content": content})
    
    def on_usage_update(self, input_tokens: int, output_tokens: int):
        self.session_input_tokens += input_tokens
        self.session_output_tokens += output_tokens
        self.update_cost_label()
    
    def on_response_finished(self):
        self.input_edit.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.input_edit.setFocus()
        self.update_status_ready()
    
    def on_error(self, error_msg: str):
        self.input_edit.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.status_label.setText("✗ Error")
        self.status_label.setStyleSheet("color: #f44747;")
        QMessageBox.critical(self, "Error", error_msg)
    
    def closeEvent(self, event):
        """Clean up on close."""
        if self.worker and self.worker.isRunning():
            self.worker._stop = True
            self.worker.wait(2000)
        self.mcp.stop()
        event.accept()

# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = ChatWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
