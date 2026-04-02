"""Startup entry point for WakeListener — run this to start ctrl+space."""

import atexit
import logging
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path

import keyboard  # noqa: F401 - validates keyboard is available before blocking

from agent.core.agent_loop import AgentLoop
from agent.core.model_router import ModelRouter
from agent.core.voice.stt import SpeechToText
from agent.core.voice.tts import TextToSpeech
from agent.core.voice.wake_listener import WakeListener

# Constants
LOCK_FILE = Path(__file__).parent / "logs" / "_wake_listener.lock"

logger = logging.getLogger(__name__)


def check_stale_lock(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def write_lock_file() -> None:
    """Write current PID to lock file and ensure logs directory exists."""
    LOCK_FILE.parent.mkdir(exist_ok=True)
    LOCK_FILE.write_text(str(os.getpid()))


def remove_lock_file() -> None:
    """Remove the lock file on exit."""
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except OSError as e:
        logger.warning("Failed to remove lock file: %s", e)


def handle_signal(signum: int, frame: object | None) -> None:
    """Handle SIGTERM/SIGINT signals for clean exit."""
    raise SystemExit(0)


# Log size limit (~40KB ≈ ~10k tokens at ~4 chars/token)
_LOG_MAX_BYTES = 40_000
_LOG_KEEP_BYTES = 15_000  # keep tail ~15KB after prune


def _prune_log(log_path: Path) -> None:
    """Trim log file when it exceeds _LOG_MAX_BYTES, keeping the tail."""
    try:
        if not log_path.exists():
            return
        size = log_path.stat().st_size
        if size <= _LOG_MAX_BYTES:
            return
        data = log_path.read_bytes()
        # Find a newline near the keep boundary so we don't split a line
        cut = len(data) - _LOG_KEEP_BYTES
        nl = data.find(b"\n", cut)
        if nl == -1:
            nl = cut
        log_path.write_bytes(b"[log pruned]\n" + data[nl + 1 :])
        print(f"[Roamin] Log pruned: {size} -> {log_path.stat().st_size} bytes", flush=True)
    except Exception:
        pass  # never crash over log maintenance


def _warmup(stt: SpeechToText, tts: TextToSpeech, agent_loop: AgentLoop) -> None:
    """Pre-load all components so first ctrl+space is instant."""
    t0 = time.perf_counter()
    print("[Roamin] Warmup starting...")

    # Check if LM Studio is running (may occupy VRAM)
    try:
        with socket.create_connection(("127.0.0.1", 1234), timeout=1):
            print(
                "[Roamin] WARNING: LM Studio detected on port 1234 — "
                "its loaded model may consume VRAM. If GPU warmup fails, "
                "consider unloading the LM Studio model."
            )
    except OSError:
        pass  # LM Studio not running, good

    # Trigger GPU model load with a minimal dummy inference
    # This forces Qwen3 8B into VRAM now instead of on first real call
    # HTTP fallback has a 5s timeout (from a9eee05) so we won't hang forever
    try:
        router = ModelRouter()
        router.respond(
            "default",
            "hello",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=1,
            temperature=0.1,
            no_think=True,
        )
        print(f"[Roamin] GPU model warm ({time.perf_counter() - t0:.1f}s)")
    except Exception as e:
        print(f"[Roamin] GPU warmup failed (non-fatal): {e}")

    # Trigger Chatterbox warmup with a silent short phrase
    try:
        tts.warm_phrase_cache()
        print(f"[Roamin] TTS warm ({time.perf_counter() - t0:.1f}s)")
    except Exception as e:
        print(f"[Roamin] TTS warmup failed (non-fatal): {e}")

    print(f"[Roamin] Warmup complete in {time.perf_counter() - t0:.1f}s")


def main() -> None:
    """Main entry point with single-instance guard, warmup, and cleanup."""
    log_dir = LOCK_FILE.parent
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "wake_listener.log"

    # Suppress Rust/primp TLS debug output (bypasses Python logging)
    os.environ.setdefault("RUST_LOG", "warn")

    # Prune log before opening if it's too large
    _prune_log(log_path)

    # Tee stdout/stderr to both the visible console (if any) AND the log file.
    # This means the terminal window launched by _start_wake_listener.vbs shows live output
    # while wake_listener.log still captures everything for persistence.
    class _TeeStream:
        def __init__(self, *streams: object) -> None:
            self._streams = streams

        def write(self, data: str) -> int:
            for s in self._streams:
                try:
                    s.write(data)  # type: ignore[union-attr]
                except Exception:
                    pass
            return len(data)

        def flush(self) -> None:
            for s in self._streams:
                try:
                    s.flush()  # type: ignore[union-attr]
                except Exception:
                    pass

    log_file = open(log_path, "a", buffering=1, encoding="utf-8")  # noqa: SIM115
    sys.stdout = _TeeStream(sys.stdout, log_file)  # type: ignore[assignment]
    sys.stderr = _TeeStream(sys.stderr, log_file)  # type: ignore[assignment]

    # Configure logging — suppress noisy third-party loggers
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(log_file)],
    )
    for noisy in ("comtypes", "urllib3", "httpx", "chromadb", "posthog", "primp", "ddgs"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Single-instance guard
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            if check_stale_lock(pid):
                logger.warning("WakeListener already running (PID: %s). Exiting.", pid)
                sys.exit(0)
        except ValueError:
            pass

    write_lock_file()
    atexit.register(remove_lock_file)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, handle_signal)
        except (OSError, ValueError):
            pass

    # Pre-load all components ONCE — passed into WakeListener so _on_wake reuses them
    print("[Roamin] Loading components...")
    stt = SpeechToText()
    tts = TextToSpeech()
    agent_loop = AgentLoop()

    # Warmup GPU + Chatterbox before registering hotkey
    _warmup(stt, tts, agent_loop)

    # Start listener with pre-loaded instances
    listener = WakeListener(hotkey="ctrl+space", stt=stt, tts=tts, agent_loop=agent_loop)
    listener.start()
    print("[Roamin] Ready. Press ctrl+space to activate.")
    print(f"\n[Roamin] Log file: {log_path}")
    print("[Roamin] Terminal will remain open for monitoring. Close to stop Roamin.\n")

    # Periodic log pruning (every 10 minutes)
    def _log_prune_loop():
        while True:
            time.sleep(600)
            _prune_log(log_path)

    threading.Thread(target=_log_prune_loop, daemon=True).start()

    try:
        keyboard.wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
