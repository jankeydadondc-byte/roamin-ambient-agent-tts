"""Tests for ObservationLoop — passive observation (Priority 11.4)."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from agent.core.observation import _PRIVACY_WINDOW_KEYWORDS, _VPN_ADAPTER_PATTERNS, ObservationLoop

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loop(**kwargs) -> ObservationLoop:
    """Create an ObservationLoop with temp dirs for testing."""
    td = tempfile.mkdtemp()
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    defaults = {
        "interval_seconds": 999,  # Don't actually loop
        "observations_dir": td,
        "db_path": db_path,
    }
    defaults.update(kwargs)
    return ObservationLoop(**defaults)


# ---------------------------------------------------------------------------
# Privacy detection: window title
# ---------------------------------------------------------------------------


class TestPrivacyWindowTitle:
    def test_incognito_detected(self):
        loop = _make_loop()
        with patch("agent.core.observation.ObservationLoop._check_window_title") as mock:
            mock.return_value = "window_title:incognito"
            result = loop._detect_privacy()
            assert result == "window_title:incognito"

    def test_no_privacy_window(self):
        loop = _make_loop()
        with (
            patch("agent.core.observation.ObservationLoop._check_window_title", return_value=None),
            patch("agent.core.observation.ObservationLoop._check_vpn", return_value=None),
        ):
            result = loop._detect_privacy()
            assert result is None

    def test_all_privacy_keywords_exist(self):
        assert "incognito" in _PRIVACY_WINDOW_KEYWORDS
        assert "inprivate" in _PRIVACY_WINDOW_KEYWORDS
        assert "private browsing" in _PRIVACY_WINDOW_KEYWORDS


# ---------------------------------------------------------------------------
# Privacy detection: VPN
# ---------------------------------------------------------------------------


class TestPrivacyVPN:
    def test_vpn_adapter_detected(self):
        loop = _make_loop()
        # Mock psutil to return a VPN adapter
        mock_addrs = {"WireGuard Tunnel": [], "Ethernet": []}
        with patch("psutil.net_if_addrs", return_value=mock_addrs):
            result = loop._check_vpn()
            assert result is not None
            assert "WireGuard" in result

    def test_no_vpn_adapter(self):
        loop = _make_loop()
        mock_addrs = {"Ethernet": [], "Wi-Fi": []}
        with patch("psutil.net_if_addrs", return_value=mock_addrs):
            result = loop._check_vpn()
            assert result is None

    def test_vpn_patterns_comprehensive(self):
        assert "wireguard" in _VPN_ADAPTER_PATTERNS
        assert "openvpn" in _VPN_ADAPTER_PATTERNS
        assert "tap" in _VPN_ADAPTER_PATTERNS


# ---------------------------------------------------------------------------
# Sensitive content detection
# ---------------------------------------------------------------------------


class TestSensitiveContent:
    def test_banking_detected(self):
        loop = _make_loop()
        assert loop._has_sensitive_content("Account Balance: $1,234.56")

    def test_medical_detected(self):
        loop = _make_loop()
        assert loop._has_sensitive_content("Medical diagnosis report")

    def test_api_key_detected(self):
        loop = _make_loop()
        assert loop._has_sensitive_content("API KEY: sk-12345")

    def test_normal_content_not_flagged(self):
        loop = _make_loop()
        assert not loop._has_sensitive_content("The quick brown fox jumped over the lazy dog")

    def test_empty_text_not_flagged(self):
        loop = _make_loop()
        assert not loop._has_sensitive_content("")


# ---------------------------------------------------------------------------
# Importance scoring
# ---------------------------------------------------------------------------


class TestImportanceScoring:
    def test_high_importance_error(self):
        loop = _make_loop()
        assert loop._score_importance("Traceback (most recent call last): Error in module") == "HIGH"

    def test_high_importance_code(self):
        loop = _make_loop()
        assert loop._score_importance("def calculate_total(items): return sum(items)") == "HIGH"

    def test_medium_importance_long_text(self):
        loop = _make_loop()
        text = " ".join(["word"] * 60)  # 60 words
        assert loop._score_importance(text) == "MEDIUM"

    def test_low_importance_short_text(self):
        loop = _make_loop()
        assert loop._score_importance("Hello") == "LOW"

    def test_low_importance_empty(self):
        loop = _make_loop()
        assert loop._score_importance("") == "LOW"


# ---------------------------------------------------------------------------
# Privacy pause
# ---------------------------------------------------------------------------


class TestPrivacyPause:
    def test_privacy_pause_sets_timer(self):
        loop = _make_loop(privacy_pause_minutes=1)
        loop._privacy_pause_until = time.time() + 60
        assert loop.is_privacy_paused

    def test_privacy_pause_expires(self):
        loop = _make_loop()
        loop._privacy_pause_until = time.time() - 1  # Expired
        assert not loop.is_privacy_paused

    def test_manual_override_on(self):
        loop = _make_loop()
        loop._privacy_pause_until = time.time() + 9999  # Would be paused
        loop.set_manual_override(True)  # Force ON
        assert not loop.is_privacy_paused

    def test_manual_override_off(self):
        loop = _make_loop()
        loop._privacy_pause_until = 0  # Would not be paused
        loop.set_manual_override(False)  # Force OFF
        assert loop.is_privacy_paused

    def test_manual_override_auto(self):
        loop = _make_loop()
        loop.set_manual_override(None)  # Back to auto
        assert not loop.is_privacy_paused


# ---------------------------------------------------------------------------
# Storage hygiene
# ---------------------------------------------------------------------------


class TestStorageHygiene:
    def test_prune_old_screenshots(self):
        loop = _make_loop(max_age_days=0)  # prune everything
        obs_dir = loop._observations_dir
        # Create a fake old screenshot
        fake = Path(obs_dir) / "obs_20200101_000000.png"
        fake.write_bytes(b"fake png data")
        # Set mtime to far past
        old_time = time.time() - 86400 * 30
        os.utime(fake, (old_time, old_time))

        loop._max_age_days = 1  # 1 day
        loop._prune_old_screenshots()
        assert not fake.exists()

    def test_enforce_size_limit(self):
        loop = _make_loop(max_size_mb=0)  # basically zero limit
        obs_dir = loop._observations_dir
        # Create fake screenshots
        for i in range(3):
            fake = Path(obs_dir) / f"obs_2020010{i}_000000.png"
            fake.write_bytes(b"x" * 1000)

        loop._max_size_mb = 0  # 0 MB limit — will prune everything
        # Size limit is 0 bytes, but max_bytes check uses > not >=
        # so all files should be pruned since total > 0
        loop._enforce_size_limit()

    def test_prune_disabled_when_zero(self):
        loop = _make_loop(max_age_days=-1)
        # Should not crash
        loop._prune_old_screenshots()


# ---------------------------------------------------------------------------
# Start / Stop
# ---------------------------------------------------------------------------


class TestStartStop:
    def test_start_creates_thread(self):
        loop = _make_loop()
        loop.start()
        assert loop.is_running
        loop.stop()
        assert not loop.is_running

    def test_double_start_is_safe(self):
        loop = _make_loop()
        loop.start()
        loop.start()  # Should not crash
        assert loop.is_running
        loop.stop()
