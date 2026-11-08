#!/usr/bin/env python3
"""
MCP stdio wrapper for ClaudeCodeBrowser

This wrapper translates between MCP stdio protocol and the HTTP-based browser server.
It handles the JSON-RPC communication that Claude Code expects.
"""

import sys
import json
import urllib.request
import urllib.error
import subprocess
import time
import os
import signal
from pathlib import Path
from typing import Optional

# Configuration
HTTP_HOST = os.environ.get('CLAUDE_BROWSER_HOST', '127.0.0.1')
HTTP_PORT = int(os.environ.get('CLAUDE_BROWSER_HTTP_PORT', '8765'))
HTTP_URL = f'http://{HTTP_HOST}:{HTTP_PORT}'

# Server process reference
server_process = None

_TOKEN_FILE = Path.home() / '.claudecodebrowser' / 'api_token'


def _api_headers(extra: Optional[dict] = None) -> dict:
    """Return HTTP headers including the API token if available."""
    headers = {'Content-Type': 'application/json'}
    try:
        if _TOKEN_FILE.exists():
            headers['X-API-Key'] = _TOKEN_FILE.read_text().strip()
    except Exception:
        pass
    if extra:
        headers.update(extra)
    return headers


def log(msg):
    """Log to stderr for debugging."""
    print(f"[stdio_wrapper] {msg}", file=sys.stderr, flush=True)

def start_http_server():
    """Start the HTTP server if not running."""
    global server_process

    # Check if server is already running
    try:
        req = urllib.request.Request(f'{HTTP_URL}/health')
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                log("HTTP server already running")
                return True
    except:
        pass

    # Start the server
    server_script = Path(__file__).parent / 'server.py'
    if not server_script.exists():
        log(f"Server script not found: {server_script}")
        return False

    log(f"Starting HTTP server: {server_script}")
    server_process = subprocess.Popen(
        [sys.executable, str(server_script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )

    # Wait for server to start
    for _ in range(20):
        time.sleep(0.25)
        try:
            req = urllib.request.Request(f'{HTTP_URL}/health')
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    log("HTTP server started successfully")
                    return True
        except:
            pass

    log("Failed to start HTTP server")
    return False

def get_tools():
    """Fetch available tools from the HTTP server."""
    try:
        req = urllib.request.Request(f'{HTTP_URL}/mcp/tools', headers=_api_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get('tools', [])
    except Exception as e:
        log(f"Error fetching tools: {e}")
        return []

# Tools that wait on a person, with their schema default wait (ms).
_HUMAN_WAIT_DEFAULTS_MS = {
    'browser_request_approval': 60000,
    'browser_solve_captcha': 180000,
}


def _http_timeout(name, arguments):
    """How long to wait for the HTTP server to answer this tool call.

    A flat 30 s cut off human-in-the-loop tools (captcha solving defaults to
    180 s) and any wait/poll tool given a long timeout, reporting "timed out"
    while the browser was still waiting.
    """
    arguments = arguments or {}
    if name == 'browser_run_workflow':
        return 900
    wait_ms = arguments.get('timeout') or arguments.get('timeout_ms') or 0
    if name in _HUMAN_WAIT_DEFAULTS_MS:
        if arguments.get('detect_only'):
            return 30
        wait_ms = wait_ms or _HUMAN_WAIT_DEFAULTS_MS[name]
    try:
        wait_s = float(wait_ms) / 1000.0
    except (TypeError, ValueError):
        wait_s = 0
    return max(30.0, wait_s + 20.0)


def call_tool(name, arguments):
    """Call a tool via the HTTP server."""
    try:
        data = json.dumps({'name': name, 'arguments': arguments}).encode('utf-8')
        req = urllib.request.Request(
            f'{HTTP_URL}/mcp/call',
            data=data,
            headers=_api_headers()
        )
        with urllib.request.urlopen(req, timeout=_http_timeout(name, arguments)) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        log(f"Error calling tool {name}: {e}")
        return {'success': False, 'error': str(e)}

def read_message():
    """Read a JSON-RPC message from stdin."""
    try:
        line = sys.stdin.readline()
        if not line:
            return None
        return json.loads(line.strip())
    except json.JSONDecodeError as e:
        log(f"JSON decode error: {e}")
        return None
    except Exception as e:
        log(f"Error reading message: {e}")
        return None

def write_message(msg):
    """Write a JSON-RPC message to stdout."""
    try:
        json_str = json.dumps(msg)
        print(json_str, flush=True)
    except Exception as e:
        log(f"Error writing message: {e}")

def handle_initialize(msg):
    """Handle the initialize request."""
    return {
        "jsonrpc": "2.0",
        "id": msg.get("id"),
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "claudecodebrowser",
                "version": "1.0.0"
            }
        }
    }

def handle_tools_list(msg):
    """Handle the tools/list request."""
    tools = get_tools()

    # Convert tools to MCP format
    mcp_tools = []
    for tool in tools:
        mcp_tools.append({
            "name": tool['name'],
            "description": tool.get('description', ''),
            "inputSchema": tool.get('inputSchema', {"type": "object", "properties": {}})
        })

    return {
        "jsonrpc": "2.0",
        "id": msg.get("id"),
        "result": {
            "tools": mcp_tools
        }
    }

def handle_tools_call(msg):
    """Handle the tools/call request."""
    params = msg.get("params", {})
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    result = call_tool(tool_name, arguments)

    return {
        "jsonrpc": "2.0",
        "id": msg.get("id"),
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }
            ]
        }
    }

def main():
    log("Starting MCP stdio wrapper")

    # Start HTTP server
    if not start_http_server():
        log("Failed to start HTTP server, exiting")
        sys.exit(1)

    log("Ready to handle requests")

    # Main message loop
    while True:
        msg = read_message()
        if msg is None:
            break

        method = msg.get("method", "")
        log(f"Received: {method}")

        response = None

        if method == "initialize":
            response = handle_initialize(msg)
        elif method == "notifications/initialized":
            # No response needed for notifications
            continue
        elif method == "tools/list":
            response = handle_tools_list(msg)
        elif method == "tools/call":
            response = handle_tools_call(msg)
        else:
            log(f"Unknown method: {method}")
            response = {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }

        if response:
            write_message(response)

    log("Shutting down")

def cleanup(signum, frame):
    """Clean up on exit."""
    global server_process
    if server_process:
        server_process.terminate()
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    try:
        main()
    except KeyboardInterrupt:
        cleanup(None, None)
