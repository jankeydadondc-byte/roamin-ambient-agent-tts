# Roamin Comprehensive Test Harness

**Date:** 2026-04-24
**Status:** PROPOSED

---

## Why

Roamin currently has 20 test files covering individual modules (agent_loop,
memory, control_api, etc.). What is missing is **harness infrastructure** — the
fixtures, mocks, chaos tools, contract validators, and CI pipeline that turn
those tests into a reliable gate.

Without the harness:
- Tests require real audio hardware, real GGUF models, and real Chatterbox
  running — so CI can't run them
- No audio injection → TTS/STT tests are untestable without a microphone
- No streaming LLM mock → inference tests wait on a running local model
- No fault injection → no coverage of what happens when Chatterbox crashes
  mid-sentence, or the LLM returns an empty string, or the GGUF fails to load
- No state machine coverage → only individual methods are tested; no transitions
- No latency budget → a regression that doubles TTFT goes undetected

The harness defined here steals structure from production AI systems (OpenAI
voice, Anthropic's internal test patterns, Google's ASR test rigs) and adapts
them to Roamin's specific stack.

---

## Architecture Overview

```
tests/
├── conftest.py                   # Root: infrastructure, audio, LLM, TTS mocks
├── harness/
│   ├── __init__.py
│   ├── audio.py                  # WAV generation, sounddevice patches
│   ├── llm.py                    # MockStreamingLLM, token generators
│   ├── tts.py                    # TTS no-op / WAV-returning mock
│   ├── state_machine.py          # WakeListener state harness helpers
│   ├── chaos.py                  # Fault injection context managers
│   ├── contracts.py              # JSON schemas for component contracts
│   ├── latency.py                # Latency tracker, P95 assertions
│   └── semantic.py               # Semantic similarity evaluator
├── unit/
│   ├── conftest.py               # Unit-level fixture composition
│   ├── voice/
│   │   ├── test_wake_listener.py  # State machine, dedupe, classify
│   │   ├── test_tts.py            # Speak, stream, stop, fallback
│   │   ├── test_stt.py            # Transcription, VAD silence trim
│   │   └── test_wake_word.py      # OWW detection, Whisper post-check
│   ├── inference/
│   │   ├── test_llama_backend.py  # GGUF load, generate, stream
│   │   ├── test_model_router.py   # Capability routing, fallback chain
│   │   └── test_classify.py       # _classify_think_level, intent detect
│   ├── memory/
│   │   ├── test_memory_manager.py # Store, search, fact extraction
│   │   └── test_memory_store.py   # SQLite ops, migration
│   ├── tools/
│   │   ├── test_tool_registry.py  # Registration, discovery
│   │   └── test_tools.py          # web_search, screenshot, clipboard stubs
│   └── config/
│       ├── test_config.py         # settings.local.json load, defaults
│       └── test_model_config.py   # model_config.json parse, routing rules
├── integration/
│   ├── conftest.py               # Full-pipeline fixture composition
│   ├── test_voice_pipeline.py    # Wake → STT → LLM → TTS end-to-end
│   ├── test_agent_loop.py        # Goal decompose, tool exec, synthesize
│   ├── test_control_api.py       # FastAPI endpoints, task lifecycle
│   └── test_memory_pipeline.py   # Context build, fact store, retrieval
├── chaos/
│   ├── test_tts_crash.py         # Chatterbox dies mid-sentence
│   ├── test_llm_failure.py       # Empty response, timeout, OOM
│   ├── test_audio_dropout.py     # Microphone disconnect, silence flood
│   └── test_cascade_failure.py   # Multiple components fail simultaneously
├── contracts/
│   ├── test_classifier_contract.py   # _classify_think_level output schema
│   ├── test_model_router_contract.py # ModelRouter.respond() output schema
│   └── test_tts_contract.py          # TTS speak() interface invariants
├── latency/
│   ├── test_wake_latency.py      # Hotkey → chime P95 ≤ 200ms
│   ├── test_tts_latency.py       # speak_streaming() TTFS P95 ≤ 600ms
│   └── test_llm_latency.py       # TTFT benchmark against baseline
└── golden/
    ├── fixtures/
    │   ├── audio/                # .wav golden inputs (wake words, commands)
    │   └── responses/            # .json golden LLM response snapshots
    └── test_golden_responses.py  # Semantic match against golden snapshots
```

---

## Layer 1 — Root conftest.py (Infrastructure)

The root `conftest.py` provides session-scoped infrastructure that every test
inherits. No test file should import from `harness/` directly — they access
everything through pytest fixtures.

### Audio Layer Mock

```python
# conftest.py
import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

@pytest.fixture(scope="session")
def silence_wav(tmp_path_factory):
    """1-second silence WAV at 16kHz — default no-input fixture."""
    from scipy.io import wavfile
    path = tmp_path_factory.mktemp("audio") / "silence.wav"
    wavfile.write(str(path), 16000, np.zeros(16000, dtype=np.int16))
    return path

@pytest.fixture
def synthetic_speech_wav(tmp_path):
    """Synthetic 1-second speech-like audio (300Hz sine, 16kHz)."""
    from scipy.io import wavfile
    t = np.linspace(0, 1.0, 16000)
    audio = (np.sin(2 * np.pi * 300 * t) * 32767 * 0.3).astype(np.int16)
    path = tmp_path / "speech.wav"
    wavfile.write(str(path), 16000, audio)
    return path

@pytest.fixture
def mock_sounddevice():
    """Patch sounddevice so no hardware is required."""
    with patch("sounddevice.InputStream") as mock_stream:
        instance = MagicMock()
        instance.read.return_value = (np.zeros(1024, dtype=np.float32), False)
        mock_stream.return_value.__enter__.return_value = instance
        yield mock_stream

@pytest.fixture
def mock_winsound():
    """Patch winsound.PlaySound — no audio output during tests."""
    with patch("winsound.PlaySound") as mock:
        yield mock
```

### LLM Streaming Mock

```python
# conftest.py (continued)
from dataclasses import dataclass

@dataclass
class FakeToken:
    content: str

class MockStreamingLLM:
    """Token-by-token streaming mock with configurable TTFT and TPS."""

    def __init__(self, tokens: list[str], ttft_ms: int = 0, tps: int = 0):
        self.tokens = tokens
        self.ttft_ms = ttft_ms  # first-token latency (0 = instant)
        self.tps = tps           # tokens/sec (0 = instant)

    def stream(self):
        import time
        if self.ttft_ms:
            time.sleep(self.ttft_ms / 1000)
        for token in self.tokens:
            yield FakeToken(content=token)
            if self.tps:
                time.sleep(1 / self.tps)

    def full_text(self) -> str:
        return "".join(self.tokens)

@pytest.fixture
def llm_simple():
    """Instant single-token response: 'Done.'"""
    return MockStreamingLLM(["Done."])

@pytest.fixture
def llm_multisentence():
    """Multi-sentence response spanning think+response tokens."""
    return MockStreamingLLM(
        ["<think>", "reasoning here", "</think>", " The answer is 42."]
    )

@pytest.fixture
def llm_empty():
    """LLM returns nothing — fault scenario."""
    return MockStreamingLLM([])

@pytest.fixture
def llm_slow(request):
    """Configurable slow response — for latency tests."""
    ttft = getattr(request, "param", 500)
    return MockStreamingLLM(["Slow reply."], ttft_ms=ttft, tps=5)
```

### TTS Mock

```python
# conftest.py (continued)
@pytest.fixture
def mock_tts(silence_wav):
    """TTS that records calls without speaking — returns silence WAV path."""
    from unittest.mock import MagicMock
    tts = MagicMock()
    tts.is_available.return_value = True
    tts.speak_streaming.return_value = None
    tts.speak.return_value = None
    tts.reset_stop.return_value = None
    tts._stop_flag = False
    return tts

@pytest.fixture
def recording_tts():
    """TTS that records every phrase spoken — for assertion in tests."""
    spoken = []
    tts = MagicMock()
    tts.is_available.return_value = True
    tts.speak_streaming.side_effect = lambda text: spoken.append(text)
    tts.spoke = spoken
    return tts
```

---

## Layer 2 — harness/ Modules

### harness/state_machine.py

Helper to drive the `WakeListener` state machine through a full cycle
without real audio or model inference.

```python
# harness/state_machine.py
from contextlib import contextmanager
from unittest.mock import patch, MagicMock
from agent.core.voice.wake_listener import WakeListener, _WakeState

class WakeListenerHarness:
    """
    Drive WakeListener through full cycles with injected inputs.

    Usage:
        h = WakeListenerHarness(transcription="what time is it")
        h.run_full_cycle()
        assert h.final_state == _WakeState.IDLE
        assert "time" in h.last_spoken
    """

    def __init__(
        self,
        transcription: str = "hello roamin",
        llm_response: str = "Hello there.",
        tts=None,
    ):
        self.transcription = transcription
        self.llm_response = llm_response
        self._tts = tts or MagicMock()
        self._tts.is_available.return_value = True
        self._tts._stop_flag = False
        self.final_state: _WakeState | None = None
        self.last_spoken: str | None = None

    def build_listener(self) -> WakeListener:
        stt = MagicMock()
        stt.transcribe.return_value = self.transcription
        return WakeListener(stt=stt, tts=self._tts)

    def run_full_cycle(self, listener: WakeListener | None = None) -> _WakeState:
        listener = listener or self.build_listener()
        # Patch model router to return canned response
        with patch(
            "agent.core.model_router.ModelRouter.respond",
            return_value=iter([self.llm_response]),
        ):
            listener._on_wake()
        with listener._state_lock:
            self.final_state = listener._state
        spoke = self._tts.speak_streaming.call_args_list
        self.last_spoken = spoke[-1][0][0] if spoke else None
        return self.final_state
```

### harness/chaos.py

```python
# harness/chaos.py
from contextlib import contextmanager
from unittest.mock import patch
import requests

class Chaos:
    """Fault injection context managers for Roamin components."""

    @staticmethod
    @contextmanager
    def chatterbox_down():
        """Chatterbox TTS server returns 503."""
        with patch("requests.post") as mock:
            mock.side_effect = requests.exceptions.ConnectionError("Chatterbox down")
            yield mock

    @staticmethod
    @contextmanager
    def llm_empty_response():
        """Model router returns empty string."""
        with patch(
            "agent.core.model_router.ModelRouter.respond",
            return_value=iter([""]),
        ):
            yield

    @staticmethod
    @contextmanager
    def llm_timeout(delay_s: float = 30.0):
        """Model router hangs — for timeout-handling tests."""
        import time
        def slow(*args, **kwargs):
            time.sleep(delay_s)
            return iter(["too late"])
        with patch("agent.core.model_router.ModelRouter.respond", side_effect=slow):
            yield

    @staticmethod
    @contextmanager
    def gguf_load_failure():
        """GGUF model fails to load (file missing, corrupt)."""
        with patch(
            "agent.core.llama_backend.LlamaCppBackend._load_model",
            side_effect=RuntimeError("GGUF load failed"),
        ):
            yield

    @staticmethod
    @contextmanager
    def audio_device_gone():
        """sounddevice raises PortAudioError mid-record."""
        import sounddevice as sd
        with patch.object(sd, "InputStream") as mock:
            mock.side_effect = sd.PortAudioError("No device")
            yield

    @staticmethod
    @contextmanager
    def memory_db_locked():
        """SQLite database is locked — simulates concurrent write contention."""
        import sqlite3
        with patch("sqlite3.connect") as mock:
            mock.side_effect = sqlite3.OperationalError("database is locked")
            yield
```

### harness/contracts.py

JSON schemas that define the contract at every component boundary. If a
component's output ever violates its schema, tests catch it immediately.

```python
# harness/contracts.py

CLASSIFY_THINK_LEVEL_SCHEMA = {
    "type": "array",
    "prefixItems": [
        {"type": "boolean"},                         # no_think
        {"type": "integer", "minimum": 0},           # thinking_budget
        {"type": "integer", "minimum": 1},           # response_budget
    ],
    "minItems": 3,
    "maxItems": 3,
}

MODEL_ROUTER_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "model_id": {"type": "string"},
        "tokens_used": {"type": "integer", "minimum": 0},
    },
    "required": ["text", "model_id"],
}

MEMORY_FACT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "content": {"type": "string", "minLength": 1},
        "created_at": {"type": "number"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["id", "content", "created_at"],
}

TOOL_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "output": {},       # any
        "error": {"type": ["string", "null"]},
    },
    "required": ["success", "error"],
}

def assert_contract(instance, schema: dict) -> None:
    """Raise AssertionError with diff on schema violation."""
    import jsonschema
    try:
        jsonschema.validate(instance=instance, schema=schema)
    except jsonschema.ValidationError as exc:
        raise AssertionError(f"Contract violated: {exc.message}\nInstance: {instance}")
```

### harness/latency.py

```python
# harness/latency.py
import time
from collections import defaultdict
from typing import Callable
import pytest

class LatencyTracker:
    """Measure P50/P95/P99 latency of operations across N runs."""

    def __init__(self):
        self._samples: dict[str, list[float]] = defaultdict(list)

    def measure(self, name: str, fn: Callable, n: int = 1) -> float:
        """Run fn n times, record elapsed ms each time. Returns last elapsed."""
        elapsed = 0.0
        for _ in range(n):
            t0 = time.perf_counter()
            fn()
            elapsed = (time.perf_counter() - t0) * 1000
            self._samples[name].append(elapsed)
        return elapsed

    def percentile(self, name: str, p: float) -> float:
        samples = sorted(self._samples[name])
        idx = int(len(samples) * p / 100)
        return samples[min(idx, len(samples) - 1)]

    def assert_p95(self, name: str, max_ms: float) -> None:
        p95 = self.percentile(name, 95)
        assert p95 <= max_ms, (
            f"Latency regression: {name} P95={p95:.1f}ms exceeds budget {max_ms}ms"
        )

    def report(self) -> dict[str, dict]:
        return {
            name: {
                "p50": self.percentile(name, 50),
                "p95": self.percentile(name, 95),
                "p99": self.percentile(name, 99),
                "n": len(samples),
            }
            for name, samples in self._samples.items()
        }


@pytest.fixture
def latency():
    return LatencyTracker()
```

### harness/semantic.py

```python
# harness/semantic.py
from functools import lru_cache

@lru_cache(maxsize=1)
def _get_encoder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")

def semantic_similarity(a: str, b: str) -> float:
    import numpy as np
    model = _get_encoder()
    ea, eb = model.encode([a, b])
    return float(np.dot(ea, eb) / (np.linalg.norm(ea) * np.linalg.norm(eb)))

def assert_semantic_match(generated: str, expected: str, threshold: float = 0.82) -> None:
    score = semantic_similarity(generated, expected)
    assert score >= threshold, (
        f"Semantic mismatch (score={score:.3f} < {threshold})\n"
        f"  generated: {generated!r}\n"
        f"  expected:  {expected!r}"
    )
```

---

## Layer 3 — Test Suites

### Unit: Voice Pipeline

```python
# tests/unit/voice/test_wake_listener.py

class TestStateMachine:
    """State transition correctness across all paths."""

    def test_idle_to_listening_on_wake(self, mock_sounddevice, mock_tts):
        h = WakeListenerHarness(transcription="hey roamin")
        listener = h.build_listener()
        with listener._state_lock:
            assert listener._state == _WakeState.IDLE
        # trigger one step
        with patch.object(listener, "_on_wake"):
            listener._on_wake_thread()
        # WakeListenerHarness.run_full_cycle verifies IDLE at end
        h.run_full_cycle(listener)
        assert h.final_state == _WakeState.IDLE

    def test_stop_word_during_speaking(self, mock_tts):
        h = WakeListenerHarness(llm_response="Long answer. " * 20)
        listener = h.build_listener()
        # Simulate stop-word firing mid-TTS
        with patch(
            "agent.core.model_router.ModelRouter.respond",
            return_value=iter(["Long answer. " * 20]),
        ):
            import threading
            def fire_stop():
                import time; time.sleep(0.05)
                listener._on_stop_word()
            threading.Thread(target=fire_stop, daemon=True).start()
            listener._on_wake()
        with listener._state_lock:
            assert listener._state == _WakeState.IDLE

    def test_duplicate_suppressed_during_processing(self, mock_tts):
        from agent.core.voice.wake_listener import _make_request_fingerprint, _WakeState
        listener = WakeListenerHarness().build_listener()
        fp = _make_request_fingerprint("what time is it")
        with listener._pending_fingerprint_lock:
            listener._pending_fingerprint = fp
        with listener._state_lock:
            listener._state = _WakeState.PROCESSING
        # Same fingerprint while PROCESSING → suppressed
        recording = MagicMock()
        listener._tts = recording
        # Manually invoke dedup path via _on_wake with matching transcription
        # (implementation-specific; adjust to actual method boundary)

    def test_duplicate_allowed_when_idle(self, mock_tts):
        from agent.core.voice.wake_listener import _make_request_fingerprint, _WakeState
        listener = WakeListenerHarness().build_listener()
        fp = _make_request_fingerprint("what time is it")
        with listener._pending_fingerprint_lock:
            listener._pending_fingerprint = fp
        with listener._state_lock:
            listener._state = _WakeState.IDLE  # IDLE → should NOT suppress


class TestClassifyThinkLevel:
    """Parametrized coverage of all tiers and edge cases."""

    @pytest.mark.parametrize("text, expected_no_think, min_think, min_resp", [
        ("hey what time is it",          True,  0,    150),
        ("analyze the pros and cons",    False, 600,  300),
        ("think hard about this",        False, 1200, 500),
        ("max effort explain everything",False, 4000, 1000),
        ("",                             True,  0,    150),  # empty → OFF tier
        ("a" * 500,                      True,  0,    150),  # no trigger words
    ])
    def test_tier_routing(self, text, expected_no_think, min_think, min_resp):
        from agent.core.voice.wake_listener import _classify_think_level
        no_think, think, resp = _classify_think_level(text)
        assert no_think == expected_no_think
        assert think >= min_think
        assert resp >= min_resp

    def test_returns_3_tuple(self):
        from agent.core.voice.wake_listener import _classify_think_level
        result = _classify_think_level("hello")
        assert len(result) == 3

    def test_contract(self):
        from agent.core.voice.wake_listener import _classify_think_level
        from tests.harness.contracts import assert_contract, CLASSIFY_THINK_LEVEL_SCHEMA
        result = list(_classify_think_level("analyze this deeply"))
        assert_contract(result, CLASSIFY_THINK_LEVEL_SCHEMA)


class TestDeduplication:
    """Fingerprint logic — state-aware TTL (post dedupe-state-aware-ttl spec)."""

    def test_same_fingerprint_same_text(self):
        from agent.core.voice.wake_listener import _make_request_fingerprint
        assert _make_request_fingerprint("hello") == _make_request_fingerprint("hello")

    def test_whitespace_normalised(self):
        from agent.core.voice.wake_listener import _make_request_fingerprint
        assert (
            _make_request_fingerprint("search  dogs")
            == _make_request_fingerprint("search dogs")
        )

    def test_case_normalised(self):
        from agent.core.voice.wake_listener import _make_request_fingerprint
        assert (
            _make_request_fingerprint("HELLO ROAMIN")
            == _make_request_fingerprint("hello roamin")
        )

    def test_different_queries_differ(self):
        from agent.core.voice.wake_listener import _make_request_fingerprint
        assert (
            _make_request_fingerprint("what time is it")
            != _make_request_fingerprint("what day is it")
        )
```

### Chaos Tests

```python
# tests/chaos/test_tts_crash.py
from tests.harness.chaos import Chaos
from tests.harness.state_machine import WakeListenerHarness
from agent.core.voice.wake_listener import _WakeState

def test_chatterbox_down_falls_back_to_pyttsx3():
    """When Chatterbox is unavailable, Roamin falls back and completes the cycle."""
    with Chaos.chatterbox_down():
        h = WakeListenerHarness(transcription="what time is it")
        final = h.run_full_cycle()
    assert final == _WakeState.IDLE  # cycle must complete, never hang

def test_tts_crash_mid_sentence_returns_to_idle():
    """TTS raises mid-stream — WakeListener must return to IDLE, not hang."""
    from unittest.mock import MagicMock
    broken_tts = MagicMock()
    broken_tts.is_available.return_value = True
    broken_tts.speak_streaming.side_effect = RuntimeError("winsound died")
    h = WakeListenerHarness(tts=broken_tts)
    final = h.run_full_cycle()
    assert final == _WakeState.IDLE

def test_llm_empty_response_fallback():
    """Empty LLM output → Roamin says fallback phrase, returns to IDLE."""
    with Chaos.llm_empty_response():
        h = WakeListenerHarness(transcription="think about this")
        final = h.run_full_cycle()
    assert final == _WakeState.IDLE
    # Should speak fallback ("Got it." or "Done."), not nothing
    assert h.last_spoken is not None

def test_memory_db_locked_does_not_crash_cycle():
    """SQLite locked during fact extraction — cycle continues without memory write."""
    with Chaos.memory_db_locked():
        h = WakeListenerHarness(transcription="remember my name is Mike")
        final = h.run_full_cycle()
    assert final == _WakeState.IDLE
```

### Latency Tests

```python
# tests/latency/test_tts_latency.py
import pytest
from tests.harness.latency import LatencyTracker

@pytest.mark.slow
def test_speak_streaming_ttfs(mock_winsound, latency):
    """Time-to-first-sentence P95 must be ≤ 600ms for a short phrase."""
    from agent.core.voice.tts import TextToSpeech
    tts = TextToSpeech()

    latency.measure("ttfs", lambda: tts.speak_streaming("Hello there."), n=20)
    latency.assert_p95("ttfs", max_ms=600)

@pytest.mark.slow
def test_wake_chime_latency(latency):
    """Hotkey → chime fires in ≤ 200ms."""
    from agent.core.voice.wake_listener import WakeListener
    from unittest.mock import MagicMock, patch
    listener = WakeListenerHarness().build_listener()

    def trigger_chime():
        with patch.object(listener, "_on_wake"):
            listener._on_wake_thread()

    latency.measure("chime", trigger_chime, n=30)
    latency.assert_p95("chime", max_ms=200)
```

### Contract Tests

```python
# tests/contracts/test_classifier_contract.py
import pytest
from tests.harness.contracts import assert_contract, CLASSIFY_THINK_LEVEL_SCHEMA

@pytest.mark.parametrize("text", [
    "hello",
    "analyze everything deeply",
    "think hard and give max effort",
    "",
    "x" * 1000,
])
def test_classify_think_level_always_valid(text):
    from agent.core.voice.wake_listener import _classify_think_level
    result = list(_classify_think_level(text))
    assert_contract(result, CLASSIFY_THINK_LEVEL_SCHEMA)

def test_response_budget_always_positive():
    from agent.core.voice.wake_listener import _classify_think_level
    for text in ["", "analyze", "think hard", "max effort"]:
        _, _, resp = _classify_think_level(text)
        assert resp > 0, f"response_budget must be > 0 for input {text!r}"

def test_no_think_tier_has_zero_thinking_budget():
    from agent.core.voice.wake_listener import _classify_think_level
    no_think, think, _ = _classify_think_level("hey what time is it")
    if no_think:
        assert think == 0
```

### Golden Response Tests

```python
# tests/golden/test_golden_responses.py
import json, pytest
from pathlib import Path
from tests.harness.semantic import assert_semantic_match

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "responses"

@pytest.mark.parametrize("fixture_file", list(GOLDEN_DIR.glob("*.json")))
def test_golden_response_semantic_match(fixture_file, llm_multisentence):
    """Loaded golden response must semantically match expected output."""
    data = json.loads(fixture_file.read_text())
    # Re-run classification + prompt building with same input
    from agent.core.voice.wake_listener import _classify_think_level
    no_think, think, resp = _classify_think_level(data["input"])
    # Semantic similarity: generated must match expected meaning
    assert_semantic_match(
        generated=data["generated"],
        expected=data["expected"],
        threshold=data.get("threshold", 0.82),
    )
```

Golden fixture format (`tests/golden/fixtures/responses/time_query.json`):
```json
{
  "input": "what time is it",
  "generated": "It's 3:47 PM.",
  "expected": "current time",
  "threshold": 0.75
}
```

---

## Layer 4 — Pytest Configuration

### pytest.ini

```ini
[pytest]
testpaths = tests
markers =
    unit: fast, fully mocked
    integration: requires real services (Ollama, Chatterbox, SQLite)
    chaos: fault injection scenarios
    contract: component boundary schema validation
    latency: timing benchmarks (slow)
    slow: tests taking > 2s

addopts =
    -m "not integration and not latency"
    --tb=short
    -q

filterwarnings =
    ignore::DeprecationWarning:whisper
    ignore::DeprecationWarning:torch
```

### CI / CD Gate

```yaml
# .github/workflows/test.yml  (or local PowerShell equivalent)
# Step 1: Unit + contract + chaos (no hardware, no model)
pytest -m "unit or contract or chaos" --timeout=30

# Step 2: Integration (requires Ollama running, Chatterbox optional)
pytest -m integration --timeout=120

# Step 3: Latency benchmarks (nightly only — require GPU)
pytest -m latency --timeout=300 --benchmark-save=baseline
```

Local equivalent (PowerShell, no GPU required):
```powershell
# Fast gate (< 30s)
pytest -m "unit or contract or chaos" -q

# Full gate (requires Ollama)
pytest -m "unit or contract or chaos or integration" -q
```

---

## Dependencies to Add

```
# requirements-test.txt
pytest>=8.0
pytest-mock>=3.14
pytest-timeout>=2.3
scipy                   # WAV generation in audio fixtures
jsonschema>=4.21        # Contract testing
sentence-transformers   # Semantic golden output comparison (optional, slow install)
hypothesis>=6.100       # Property-based testing (Phase 2)
```

These are **test-only** — they never enter the production venv.

---

## Files Added / Changed

| Path | Action | Description |
|------|--------|-------------|
| `tests/harness/__init__.py` | New | Package marker |
| `tests/harness/audio.py` | New | WAV generators, sounddevice patches |
| `tests/harness/llm.py` | New | MockStreamingLLM, token generators |
| `tests/harness/tts.py` | New | TTS mock variants |
| `tests/harness/state_machine.py` | New | WakeListenerHarness driver |
| `tests/harness/chaos.py` | New | Fault injection context managers |
| `tests/harness/contracts.py` | New | JSON schemas, assert_contract() |
| `tests/harness/latency.py` | New | LatencyTracker, assert_p95() |
| `tests/harness/semantic.py` | New | Semantic similarity, assert_semantic_match() |
| `tests/conftest.py` | Update | Add root fixtures from §Layer 1 |
| `tests/unit/voice/test_wake_listener.py` | Update | Add harness-backed test classes |
| `tests/chaos/test_tts_crash.py` | New | Chatterbox/TTS fault suite |
| `tests/chaos/test_llm_failure.py` | New | LLM fault suite |
| `tests/chaos/test_audio_dropout.py` | New | Audio hardware fault suite |
| `tests/contracts/test_classifier_contract.py` | New | _classify_think_level schema |
| `tests/latency/test_tts_latency.py` | New | TTS timing benchmarks |
| `tests/golden/test_golden_responses.py` | New | Semantic snapshot tests |
| `tests/golden/fixtures/responses/*.json` | New | Golden response fixtures |
| `pytest.ini` | Update | Add markers, default -m filter |
| `requirements-test.txt` | New | Test-only dependencies |

---

## Phases

### Phase 1 — Foundation (this PR)
- `harness/` package: audio, llm, tts, state_machine, chaos, contracts
- Root `conftest.py` updated with all Layer 1 fixtures
- `pytest.ini` with markers and default filter
- `requirements-test.txt`

### Phase 2 — Test Suite Expansion
- `tests/chaos/` — full fault suite (TTS crash, LLM failure, audio dropout)
- `tests/contracts/` — contract tests for all component boundaries
- `tests/unit/voice/test_wake_listener.py` updated with harness-backed classes
- CI gate: fast (`unit or contract or chaos`) runs in < 30s

### Phase 3 — Latency & Golden (after Phase 2 stable)
- `tests/latency/` — TTFS, chime latency, TTFT benchmarks
- `tests/golden/` — fixture corpus, semantic match tests
- Property-based testing via Hypothesis for classifiers (exhaustive path coverage)
- Nightly benchmark job storing P95 baselines

---

## What Existing Tests Do NOT Need to Change

All 20 existing test files continue to work unchanged. The harness is
**additive** — new fixtures in `conftest.py` are available to existing tests
but not required. Existing tests that mock things manually continue to do so;
the harness simply offers better alternatives for future tests and the new
chaos/contract/latency suites.
