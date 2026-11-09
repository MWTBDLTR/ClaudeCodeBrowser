"""
Code fingerprint for the ClaudeCodeBrowser MCP server.

The HTTP server is a long-lived background process that outlives the Claude
Code session (and the Firefox native host) that started it. Without a check,
the next session finds it healthy and keeps using it, so edits to server.py
never take effect until someone kills it by hand.

The server reports a hash of its own source in /health. Launchers
(stdio_wrapper.py, the native host) hash the files on disk; if the two differ,
the running server is stale and is replaced with one started from disk.
"""

import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Optional

# Every module the server process imports from this directory.
SOURCE_FILES = ('server.py', 'safety.py', 'headless_backend.py', 'code_version.py')


def code_fingerprint(server_dir: Optional[Path] = None) -> str:
    """Hash of the server's source files in server_dir (default: this dir)."""
    server_dir = Path(server_dir) if server_dir else Path(__file__).resolve().parent
    h = hashlib.sha256()
    for name in SOURCE_FILES:
        h.update(name.encode())
        try:
            # Normalise line endings so a CRLF/LF checkout difference alone
            # does not count as a code change.
            h.update((server_dir / name).read_bytes().replace(b'\r\n', b'\n'))
        except OSError:
            h.update(b'<missing>')
    return h.hexdigest()[:16]


def get_health(url: str, timeout: float = 2) -> Optional[dict]:
    """Return the server's /health JSON, or None if it is not answering."""
    try:
        with urllib.request.urlopen(f'{url}/health', timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode('utf-8'))
    except Exception:
        pass
    return None


def is_stale(health: dict, server_dir: Optional[Path] = None) -> bool:
    """True if a running server is not running the code currently on disk."""
    return health.get('code_hash') != code_fingerprint(server_dir)


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _pids_on_port(port: int) -> list:
    """PIDs listening on a TCP port (fallback for servers without a pid in /health)."""
    pids = set()
    try:
        if os.name == 'nt':
            out = subprocess.run(['netstat', '-ano', '-p', 'TCP'], capture_output=True,
                                 text=True, timeout=5).stdout
            for line in out.splitlines():
                parts = line.split()
                if (len(parts) >= 5 and parts[3].upper() == 'LISTENING'
                        and re.search(rf':{port}$', parts[1])):
                    pids.add(int(parts[4]))
        else:
            out = subprocess.run(['lsof', '-ti', f'tcp:{port}', '-sTCP:LISTEN'],
                                 capture_output=True, text=True, timeout=5).stdout
            pids.update(int(p) for p in out.split() if p.strip().isdigit())
    except Exception:
        pass
    pids.discard(os.getpid())
    return sorted(pids)


def stop_server(health: dict, host: str, port: int, timeout: float = 5.0) -> bool:
    """Stop the server described by `health`. Returns True once the port is free."""
    pids = [health['pid']] if health.get('pid') else _pids_on_port(port)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)  # TerminateProcess on Windows
        except (OSError, ValueError):
            pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _port_open(host, port):
            return True
        time.sleep(0.2)
    return not _port_open(host, port)
