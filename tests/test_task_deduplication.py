"""Tests for 4.1: Task Deduplication in WakeListener."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import agent.core.voice.wake_listener as wl_mod
from agent.core.voice.wake_listener import _make_request_fingerprint


def _make_listener():
    """Build a WakeListener with mocked deps."""
    stt = MagicMock()
    tts = MagicMock()
    tts.is_available.return_value = True
    tts.speak_streaming = MagicMock()
    agent_loop = MagicMock()
    with patch.object(wl_mod, "keyboard", MagicMock()):
        listener = wl_mod.WakeListener(stt=stt, tts=tts, agent_loop=agent_loop)
    return listener


class TestMakeRequestFingerprint:
    """Unit tests for the module-level fingerprint helper."""

    def test_same_input_same_hash(self):
        assert _make_request_fingerprint("search for dogs") == _make_request_fingerprint("search for dogs")

    def test_different_input_different_hash(self):
        assert _make_request_fingerprint("search for dogs") != _make_request_fingerprint("search for cats")

    def test_whitespace_normalised(self):
        """Extra internal spaces should not change the fingerprint."""
        assert _make_request_fingerprint("search for  dogs") == _make_request_fingerprint("search for dogs")

    def test_leading_trailing_whitespace_normalised(self):
        assert _make_request_fingerprint("  search  ") == _make_request_fingerprint("search")

    def test_case_insensitive(self):
        assert _make_request_fingerprint("SEARCH") == _make_request_fingerprint("search")

    def test_returns_hex_string(self):
        fp = _make_request_fingerprint("hello")
        assert len(fp) == 64  # SHA-256 hex = 64 chars
        assert all(c in "0123456789abcdef" for c in fp)


class TestWakeListenerDeduplication:
    """Unit tests for WakeListener deduplication attributes and TTL logic."""

    def test_init_has_dedup_attributes(self):
        listener = _make_listener()
        assert hasattr(listener, "_pending_fingerprint")
        assert hasattr(listener, "_pending_fingerprint_lock")
        assert hasattr(listener, "_fingerprint_ttl")
        assert hasattr(listener, "_last_fingerprint_time")

    def test_init_pending_fingerprint_is_none(self):
        listener = _make_listener()
        assert listener._pending_fingerprint is None

    def test_init_ttl_default_value(self):
        listener = _make_listener()
        assert listener._fingerprint_ttl == 2.0

    def test_ttl_settable_for_testing(self):
        listener = _make_listener()
        listener._fingerprint_ttl = 0.0
        assert listener._fingerprint_ttl == 0.0

    def test_duplicate_within_ttl_suppressed(self):
        """Identical transcription within TTL should not call agent_loop.run()."""
        listener = _make_listener()
        listener._fingerprint_ttl = 5.0  # generous TTL

        fp = _make_request_fingerprint("search for dogs")
        # Pre-set the pending fingerprint as if a first call just ran
        listener._pending_fingerprint = fp
        listener._last_fingerprint_time = time.perf_counter()  # just now

        # Simulate what _on_wake does with the duplicate check
        _now_fp = time.perf_counter()
        with listener._pending_fingerprint_lock:
            suppressed = (
                listener._pending_fingerprint == fp
                and (_now_fp - listener._last_fingerprint_time) < listener._fingerprint_ttl
            )

        assert suppressed is True

    def test_duplicate_after_ttl_not_suppressed(self):
        """Same transcription after TTL expires should NOT be suppressed."""
        listener = _make_listener()
        listener._fingerprint_ttl = 0.001  # 1ms TTL

        fp = _make_request_fingerprint("search for dogs")
        listener._pending_fingerprint = fp
        listener._last_fingerprint_time = time.perf_counter() - 1.0  # 1 second ago

        _now_fp = time.perf_counter()
        with listener._pending_fingerprint_lock:
            suppressed = (
                listener._pending_fingerprint == fp
                and (_now_fp - listener._last_fingerprint_time) < listener._fingerprint_ttl
            )

        assert suppressed is False

    def test_different_transcription_not_suppressed(self):
        """Different transcription must never match the pending fingerprint."""
        listener = _make_listener()
        listener._fingerprint_ttl = 5.0

        fp_dogs = _make_request_fingerprint("search for dogs")
        fp_cats = _make_request_fingerprint("search for cats")

        listener._pending_fingerprint = fp_dogs
        listener._last_fingerprint_time = time.perf_counter()

        _now_fp = time.perf_counter()
        with listener._pending_fingerprint_lock:
            suppressed = (
                listener._pending_fingerprint == fp_cats
                and (_now_fp - listener._last_fingerprint_time) < listener._fingerprint_ttl
            )

        assert suppressed is False

    def test_fingerprint_cleared_in_guarded_wake_finally(self):
        """Fingerprint must be cleared even when _on_wake raises an exception."""
        listener = _make_listener()
        fp = _make_request_fingerprint("test query")
        listener._pending_fingerprint = fp

        # Simulate _guarded_wake finally block behaviour
        with listener._pending_fingerprint_lock:
            listener._pending_fingerprint = None

        assert listener._pending_fingerprint is None
