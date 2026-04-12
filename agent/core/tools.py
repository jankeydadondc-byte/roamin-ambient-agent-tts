"""Tool implementations — callable functions for the agent loop."""

from __future__ import annotations

import json
import logging
import re
import shutil
import socket
import subprocess
import sys
import webbrowser
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from agent.core.validators import validate_path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _ok(result: str) -> dict:
    return {"success": True, "result": result}


def _fail(error: str, category: str = "error") -> dict:
    """Return a failure dict with an error category for structured reporting.

    Categories: "validation", "timeout", "unavailable", "permission", "error".
    """
    return {"success": False, "error": error, "category": category}


# ---------------------------------------------------------------------------
# Code Execution
# ---------------------------------------------------------------------------


def _run_python(params: dict) -> dict:
    code = params.get("code", "")
    if not code:
        return _fail("No code provided", "validation")
    if len(code) > 10_000:
        return _fail(f"Code too long ({len(code)} chars, max 10000)", "validation")
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(_PROJECT_ROOT),
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return _ok(output.strip()[:3000] or "(no output)")
    except subprocess.TimeoutExpired:
        return _fail("Python execution timed out (30s)")
    except Exception as e:
        return _fail(str(e))


def _run_powershell(params: dict) -> dict:
    command = params.get("command", "")
    if not command:
        return _fail("No command provided", "validation")
    if len(command) > 10_000:
        return _fail(f"Command too long ({len(command)} chars, max 10000)", "validation")
    try:
        proc = subprocess.run(
            ["powershell", "-Command", command],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(_PROJECT_ROOT),
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return _ok(output.strip()[:3000] or "(no output)")
    except subprocess.TimeoutExpired:
        return _fail("PowerShell execution timed out (30s)")
    except Exception as e:
        return _fail(str(e))


def _run_cmd(params: dict) -> dict:
    command = params.get("command", "")
    if not command:
        return _fail("No command provided", "validation")
    if len(command) > 10_000:
        return _fail(f"Command too long ({len(command)} chars, max 10000)", "validation")
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(_PROJECT_ROOT),
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return _ok(output.strip()[:3000] or "(no output)")
    except subprocess.TimeoutExpired:
        return _fail("Command execution timed out (30s)")
    except Exception as e:
        return _fail(str(e))


def _py_compile_check(params: dict) -> dict:
    path = params.get("path", "")
    if not path:
        return _fail("No path provided")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return _ok(f"{path} compiles OK")
        return _fail((proc.stderr or proc.stdout or "compile error").strip())
    except Exception as e:
        return _fail(str(e))


# ---------------------------------------------------------------------------
# File System
# ---------------------------------------------------------------------------


def _read_file(params: dict) -> dict:
    path = params.get("path", "")
    # Constrain reads to safe directories (project root, user home, temp)
    rejected = validate_path(path, mode="read")
    if rejected:
        return rejected
    p = Path(path)
    if not p.exists():
        return _fail(f"File not found: {path}")
    if not p.is_file():
        return _fail(f"Not a file: {path}")
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return _ok(text[:5000])
    except Exception as e:
        return _fail(str(e))


def _write_file(params: dict) -> dict:
    path = params.get("path", "")
    content = params.get("content", "")
    # Constrain writes to project root and temp dirs only
    rejected = validate_path(path, mode="write")
    if rejected:
        return rejected
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return _ok(f"Wrote {len(content)} chars to {path}")
    except Exception as e:
        return _fail(str(e))


def _list_directory(params: dict) -> dict:
    path = params.get("path", str(_PROJECT_ROOT))
    # Constrain directory listing to safe read roots
    rejected = validate_path(path, mode="read")
    if rejected:
        return rejected
    p = Path(path)
    if not p.exists():
        return _fail(f"Directory not found: {path}")
    if not p.is_dir():
        return _fail(f"Not a directory: {path}")
    try:
        entries = sorted(e.name + ("/" if e.is_dir() else "") for e in p.iterdir())
        return _ok("\n".join(entries[:100]))
    except Exception as e:
        return _fail(str(e))


def _glob_files(params: dict) -> dict:
    pattern = params.get("pattern", "")
    path = params.get("path", str(_PROJECT_ROOT))
    # Constrain glob root to safe read directories
    rejected = validate_path(path, mode="read")
    if rejected:
        return rejected
    if not pattern:
        return _fail("No pattern provided")
    try:
        matches = [str(p) for p in Path(path).glob(pattern)][:50]
        if not matches:
            return _ok("No matches found")
        return _ok("\n".join(matches))
    except Exception as e:
        return _fail(str(e))


def _grep_files(params: dict) -> dict:
    pattern = params.get("pattern", "")
    path = params.get("path", str(_PROJECT_ROOT))
    # Constrain grep root to safe read directories
    rejected = validate_path(path, mode="read")
    if rejected:
        return rejected
    if not pattern:
        return _fail("No pattern provided")
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return _fail(f"Invalid regex: {e}")
    matches = []
    root = Path(path)
    try:
        for fp in root.rglob("*"):
            if not fp.is_file() or fp.stat().st_size > 500_000:
                continue
            if fp.suffix in (".pyc", ".pyo", ".exe", ".dll", ".so", ".png", ".jpg", ".wav", ".mp3"):
                continue
            try:
                for i, line in enumerate(fp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if regex.search(line):
                        matches.append(f"{fp}:{i}: {line.strip()[:120]}")
                        if len(matches) >= 50:
                            break
            except Exception:
                continue
            if len(matches) >= 50:
                break
    except Exception as e:
        return _fail(str(e))
    if not matches:
        return _ok("No matches found")
    return _ok("\n".join(matches))


def _move_file(params: dict) -> dict:
    src = params.get("src", "")
    dst = params.get("dst", "")
    if not src or not dst:
        return _fail("Both src and dst required")
    # Constrain both source and destination to safe write directories
    for p in (src, dst):
        rejected = validate_path(p, mode="write")
        if rejected:
            return rejected
    if not Path(src).exists():
        return _fail(f"Source not found: {src}")
    try:
        shutil.move(src, dst)
        return _ok(f"Moved {src} -> {dst}")
    except Exception as e:
        return _fail(str(e))


def _delete_file(params: dict) -> dict:
    path = params.get("path", "")
    # Constrain deletes to safe write directories (project root, temp)
    rejected = validate_path(path, mode="write")
    if rejected:
        return rejected
    p = Path(path)
    if not p.exists():
        return _fail(f"Not found: {path}")
    try:
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
        return _ok(f"Deleted {path}")
    except Exception as e:
        return _fail(str(e))


def _file_info(params: dict) -> dict:
    path = params.get("path", "")
    if not path:
        return _fail("No path provided")
    p = Path(path)
    if not p.exists():
        return _fail(f"Not found: {path}")
    try:
        st = p.stat()
        info = {
            "path": str(p.resolve()),
            "is_file": p.is_file(),
            "is_dir": p.is_dir(),
            "size_bytes": st.st_size,
            "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
        }
        return _ok(json.dumps(info))
    except Exception as e:
        return _fail(str(e))


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------


def _git_status(params: dict) -> dict:
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(_PROJECT_ROOT),
        )
        output = proc.stdout.strip() or "(clean)"
        return _ok(output[:2000])
    except Exception as e:
        return _fail(str(e))


def _git_diff(params: dict) -> dict:
    path = params.get("path")
    cmd = ["git", "diff"]
    if path:
        cmd.append(path)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(_PROJECT_ROOT),
        )
        output = proc.stdout.strip() or "(no changes)"
        return _ok(output[:3000])
    except Exception as e:
        return _fail(str(e))


def _git_log(params: dict) -> dict:
    n = params.get("n", 10)
    try:
        proc = subprocess.run(
            ["git", "log", "--oneline", f"-{n}"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(_PROJECT_ROOT),
        )
        return _ok(proc.stdout.strip()[:2000] or "(no commits)")
    except Exception as e:
        return _fail(str(e))


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


def _memory_write(params: dict) -> dict:
    data_type = params.get("type", "")
    data = params.get("data", {})
    if not data_type:
        return _fail("No type provided")
    try:
        from agent.core.memory import MemoryManager

        mm = MemoryManager()
        record_id = mm.write_to_memory(data_type, data)
        return _ok(f"Stored {data_type} (id={record_id})")
    except Exception as e:
        return _fail(str(e))


def _memory_recall(params: dict) -> dict:
    fact_name = params.get("fact_name", "")
    if not fact_name:
        return _fail("No fact_name provided")
    try:
        from agent.core.memory import MemoryManager

        mm = MemoryManager()
        fact = mm.recall_fact(fact_name)
        if fact:
            return _ok(f"{fact_name}: {fact.get('value', 'unknown')}")
        return _ok(f"No fact found for '{fact_name}'")
    except Exception as e:
        return _fail(str(e))


def _memory_search(params: dict) -> dict:
    query = params.get("query", "")
    if not query:
        return _fail("No query provided")
    try:
        from agent.core.memory import MemoryManager

        mm = MemoryManager()
        results = mm.search_memory(query)
        docs = results.get("documents", [])
        if docs:
            return _ok(" | ".join(docs[:3]))
        return _ok("No relevant memories found")
    except Exception as e:
        return _fail(str(e))


def _memory_recent(params: dict) -> dict:
    limit = params.get("limit", 10)
    try:
        from agent.core.memory import MemoryManager

        mm = MemoryManager()
        convos = mm.get_recent_conversations(limit=limit)
        if convos:
            lines = [c.get("content", "")[:100] for c in convos[:10]]
            return _ok("\n".join(lines))
        return _ok("No recent conversations")
    except Exception as e:
        return _fail(str(e))


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


def _list_processes(params: dict) -> dict:
    try:
        proc = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = proc.stdout.strip().splitlines()[:20]
        return _ok("\n".join(lines) or "(no processes)")
    except Exception as e:
        return _fail(str(e))


def _check_port(params: dict) -> dict:
    port = params.get("port", 0)
    if not port:
        return _fail("No port provided")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("127.0.0.1", int(port)))
        sock.close()
        if result == 0:
            return _ok(f"Port {port} is OPEN")
        return _ok(f"Port {port} is CLOSED")
    except Exception as e:
        return _fail(str(e))


# ---------------------------------------------------------------------------
# Web
# ---------------------------------------------------------------------------


def _web_search(params: dict) -> dict:
    query = params.get("query", "")
    if not query:
        return _fail("No query provided", "validation")
    # Strip control characters and limit length
    query = re.sub(r"[\x00-\x1f\x7f]", " ", query).strip()
    if len(query) > 500:
        query = query[:500]
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        with DDGS() as ddgs_client:
            results = list(ddgs_client.text(query, max_results=5))
        if not results:
            return _ok("No results found")
        lines = []
        for r in results:
            lines.append(f"{r.get('title', '')}: {r.get('body', '')[:150]}")
        return _ok("\n".join(lines))
    except ImportError:
        return _fail("ddgs / duckduckgo-search not installed")
    except Exception as e:
        return _fail(str(e))


# Block loopback and RFC-1918 private ranges — prevents SSRF against local services
_SSRF_BLOCK = re.compile(
    r"^https?://(localhost|127\.|0\.0\.0\.0|10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)",
    re.IGNORECASE,
)


def _fetch_url(params: dict) -> dict:
    url = params.get("url", "")
    if not url:
        return _fail("No URL provided", "validation")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return _fail(f"URL must start with http:// or https:// — got: {url[:80]}", "validation")
    # Block SSRF: internal/loopback addresses must never be reachable via this tool
    if _SSRF_BLOCK.match(url):
        return _fail(
            f"URL '{url[:80]}' targets an internal address. " "fetch_url is for external URLs only.",
            "permission",
        )
    try:
        import requests

        resp = requests.get(url, timeout=10, headers={"User-Agent": "Roamin/1.0"})
        resp.raise_for_status()
        return _ok(resp.text[:5000])
    except Exception as e:
        return _fail(str(e))


# ---------------------------------------------------------------------------
# Screen & UI
# ---------------------------------------------------------------------------


def _take_screenshot(params: dict) -> dict:
    try:
        from agent.core.screen_observer import ScreenObserver

        obs = ScreenObserver()
        result = obs.observe()
        screenshot_path = result.get("screenshot_path")

        if "description" in result:
            return {
                "success": True,
                "result": result["description"],
                "screenshot_path": screenshot_path,
            }

        # Vision API failed but screenshot was captured — still return success
        # so the wake_listener vision fast-path can send image bytes to local LLM
        if screenshot_path:
            return {
                "success": True,
                "result": "Screenshot captured (no description available)",
                "screenshot_path": screenshot_path,
            }

        return _fail(result.get("error", "Screenshot failed"))
    except Exception as e:
        return _fail(str(e))


def _notify(params: dict) -> dict:
    title = params.get("title", "Roamin")
    message = params.get("message", "")
    if not message:
        return _fail("No message provided")
    try:
        from agent.core.screen_observer import _notify_windows

        _notify_windows(message, title=title)
        return _ok(f"Notification sent: {message}")
    except Exception as e:
        return _fail(str(e))


def _open_url(params: dict) -> dict:
    url = params.get("url", "")
    if not url:
        return _fail("No URL provided", "validation")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return _fail(f"URL must start with http:// or https:// — got: {url[:80]}", "validation")
    try:
        webbrowser.open(url)
        return _ok(f"Opened {url}")
    except Exception as e:
        return _fail(str(e))


def _clipboard_read(params: dict) -> dict:
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        try:
            data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        except TypeError:
            data = "(clipboard empty or not text)"
        finally:
            win32clipboard.CloseClipboard()
        return _ok(str(data)[:2000])
    except ImportError:
        return _fail("win32clipboard not available")
    except Exception as e:
        return _fail(str(e))


def _clipboard_write(params: dict) -> dict:
    text = params.get("text", "")
    if not text:
        return _fail("No text provided", "validation")
    # Strip null bytes and enforce a sane size limit
    text = text.replace("\x00", "")
    if len(text) > 10_000:
        return _fail(f"Text too large for clipboard ({len(text)} chars, max 10000)", "validation")
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return _ok(f"Copied {len(text)} chars to clipboard")
    except ImportError:
        return _fail("win32clipboard not available")
    except Exception as e:
        return _fail(str(e))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TOOL_IMPLEMENTATIONS: dict[str, Callable[[dict], dict]] = {
    "run_python": _run_python,
    "run_powershell": _run_powershell,
    "run_cmd": _run_cmd,
    "py_compile_check": _py_compile_check,
    "read_file": _read_file,
    "write_file": _write_file,
    "list_directory": _list_directory,
    "glob": _glob_files,
    "grep": _grep_files,
    "move_file": _move_file,
    "delete_file": _delete_file,
    "file_info": _file_info,
    "git_status": _git_status,
    "git_diff": _git_diff,
    "git_log": _git_log,
    "memory_write": _memory_write,
    "memory_recall": _memory_recall,
    "memory_search": _memory_search,
    "memory_recent": _memory_recent,
    "list_processes": _list_processes,
    "check_port": _check_port,
    "web_search": _web_search,
    "fetch_url": _fetch_url,
    "take_screenshot": _take_screenshot,
    "notify": _notify,
    "open_url": _open_url,
    "clipboard_read": _clipboard_read,
    "clipboard_write": _clipboard_write,
}
