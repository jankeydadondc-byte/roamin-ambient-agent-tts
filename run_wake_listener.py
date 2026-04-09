"""Startup entry point for WakeListener — run this to start ctrl+space."""

# Must be set before ANY imports — Rust extensions (primp/ddgs) read RUST_LOG
# at initialization time. Setting it inside main() is too late.
import os

os.environ["RUST_LOG"] = "warn"

import atexit  # noqa: E402
import ctypes  # noqa: E402
import logging  # noqa: E402
import signal  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import keyboard  # noqa: E402,F401 - validates keyboard is available before blocking

from agent.core import model_sync  # noqa: E402
from agent.core.agent_loop import AgentLoop  # noqa: E402
from agent.core.model_router import ModelRouter  # noqa: E402
from agent.core.voice.stt import SpeechToText  # noqa: E402
from agent.core.voice.tts import TextToSpeech  # noqa: E402
from agent.core.voice.wake_listener import WakeListener  # noqa: E402

# Constants
LOCK_FILE = Path(__file__).parent / "logs" / "_wake_listener.lock"
_MUTEX_NAME = "Global\\RoaminWakeListener"

logger = logging.getLogger(__name__)


def _acquire_single_instance_mutex() -> object:
    """Acquire a named Windows mutex. Exits immediately if another instance holds it.

    The OS releases the mutex automatically on any process exit — normal, crash, or
    SIGKILL — eliminating the PID-file race condition where two processes can both
    pass the lock-file check before either has written it.

    Returns the mutex handle; caller MUST keep it referenced for process lifetime.
    If the handle is garbage-collected, Windows releases the mutex.
    """
    handle = ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    err = ctypes.windll.kernel32.GetLastError()
    if err == 183:  # ERROR_ALREADY_EXISTS — another instance holds the mutex
        ctypes.windll.kernel32.CloseHandle(handle)
        return None  # signal to caller that we lost the race
    return handle


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


def _start_control_api(log_dir: Path) -> subprocess.Popen | None:
    """Launch the Control API as a sidecar subprocess. Returns the process or None."""
    api_script = Path(__file__).parent / "run_control_api.py"
    if not api_script.exists():
        return None
    api_log = open(log_dir / "control_api.log", "a", buffering=1, encoding="utf-8")  # noqa: SIM115
    try:
        proc = subprocess.Popen(
            [sys.executable, str(api_script)],
            cwd=str(Path(__file__).parent),
            stdout=api_log,
            stderr=api_log,
        )
        atexit.register(proc.terminate)
        return proc
    except Exception as e:
        print(f"[Control API] Failed to start: {e}", flush=True)
        return None


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

    # Configure logging — root at WARNING so unknown third-party loggers are silent;
    # agent.* re-enabled at DEBUG so our own structured logs still appear.
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[logging.StreamHandler(log_file)],
    )
    logging.getLogger("agent").setLevel(logging.DEBUG)
    for noisy in ("comtypes", "urllib3", "httpx", "chromadb", "posthog", "primp", "ddgs", "h2", "hpack", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Single-instance guard — named mutex (primary) + PID lock file (secondary)
    # Mutex: OS-held, released automatically on any exit including crash/SIGKILL.
    # PID file: kept for VBS launcher and tooling that need to inspect the running PID.
    _mutex = _acquire_single_instance_mutex()
    if _mutex is None:
        print("[Roamin] Already running (mutex held by another instance). Exiting.")
        sys.exit(0)

    # PID file fallback: also check the legacy lock in case mutex namespace differs
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            if check_stale_lock(pid):
                logger.warning("WakeListener already running (PID: %s). Exiting.", pid)
                ctypes.windll.kernel32.CloseHandle(_mutex)
                sys.exit(0)
        except ValueError:
            pass

    write_lock_file()
    atexit.register(remove_lock_file)

    # Start Control API sidecar (non-blocking, logs to logs/control_api.log)
    _start_control_api(log_dir)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, handle_signal)
        except (OSError, ValueError):
            pass

    # Load secrets from .env file before any component initialization
    from agent.core.secrets import check_secrets, load_secrets

    load_secrets()
    check_secrets(optional=["ROAMIN_CONTROL_API_KEY", "ROAMIN_DEBUG"])

    # Pre-load all components ONCE — passed into WakeListener so _on_wake reuses them
    print("[Roamin] Loading components...")

    try:
        added = model_sync.sync_from_providers()
        print(f"[Roamin] model_sync: {added} new model(s) added to config", flush=True)
    except Exception as e:
        logger.warning("model_sync: unexpected error at startup (continuing): %s", e)

    stt = SpeechToText()
    tts = TextToSpeech()
    agent_loop = AgentLoop()

    # Load plugins from agent/plugins/ and register their tools into the agent loop
    from agent.plugins import load_plugins, unload_plugins

    loaded_plugins = load_plugins(agent_loop.registry)
    if loaded_plugins:
        print(f"[Roamin] {len(loaded_plugins)} plugin(s) loaded: {', '.join(p.name for p in loaded_plugins)}")
    atexit.register(unload_plugins, loaded_plugins)

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

    # Periodic task cleanup (every 5 minutes — removes completed task_runs older than 24h)
    def _task_cleanup_loop():
        while True:
            time.sleep(300)
            try:
                result = agent_loop._cleanup_completed_tasks(older_than_hours=24)
                if result["deleted_count"] > 0:
                    print(f"[Roamin] Task cleanup: removed {result['deleted_count']} old task(s)")
            except Exception:
                pass

    threading.Thread(target=_task_cleanup_loop, daemon=True).start()

    try:
        keyboard.wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
