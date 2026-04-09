"""Unit tests for agent.core.resource_monitor."""

from __future__ import annotations

from unittest.mock import patch

from agent.core.resource_monitor import (
    get_cpu_percent,
    get_ram_usage_mb,
    get_throttle_status,
    get_vram_usage_mb,
    is_resource_exhausted,
)


def test_cpu_percent_returns_valid_value():
    """get_cpu_percent returns a float between 0 and 100."""
    cpu = get_cpu_percent(interval=0.1)
    assert isinstance(cpu, float)
    assert 0.0 <= cpu <= 100.0


def test_ram_usage_returns_positive_mb():
    """get_ram_usage_mb returns a positive integer."""
    ram = get_ram_usage_mb()
    assert isinstance(ram, int)
    assert ram > 0


def test_vram_returns_none_or_positive():
    """get_vram_usage_mb returns None (no GPU) or a positive int."""
    vram = get_vram_usage_mb()
    assert vram is None or (isinstance(vram, int) and vram >= 0)


def test_is_resource_exhausted_not_exhausted():
    """is_resource_exhausted returns False under normal load (very high thresholds)."""
    result = is_resource_exhausted(threshold_cpu=100.0, threshold_ram_mb=999_999, threshold_vram_mb=None)
    assert result is False


def test_is_resource_exhausted_cpu_threshold():
    """is_resource_exhausted returns True when CPU exceeds threshold."""
    with patch("agent.core.resource_monitor.get_cpu_percent", return_value=95.0):
        assert is_resource_exhausted(threshold_cpu=90.0) is True


def test_is_resource_exhausted_ram_threshold():
    """is_resource_exhausted returns True when RAM exceeds threshold."""
    with patch("agent.core.resource_monitor.get_cpu_percent", return_value=5.0):
        with patch("agent.core.resource_monitor.get_ram_usage_mb", return_value=20_000):
            assert is_resource_exhausted(threshold_cpu=90.0, threshold_ram_mb=16_000) is True


def test_is_resource_exhausted_vram_threshold():
    """is_resource_exhausted returns True when VRAM exceeds threshold."""
    with patch("agent.core.resource_monitor.get_cpu_percent", return_value=5.0):
        with patch("agent.core.resource_monitor.get_ram_usage_mb", return_value=4_000):
            with patch("agent.core.resource_monitor.get_vram_usage_mb", return_value=22_000):
                assert is_resource_exhausted(threshold_vram_mb=20_000) is True


def test_is_resource_exhausted_skips_vram_when_none():
    """is_resource_exhausted skips VRAM check when threshold_vram_mb=None."""
    with patch("agent.core.resource_monitor.get_cpu_percent", return_value=5.0):
        with patch("agent.core.resource_monitor.get_ram_usage_mb", return_value=4_000):
            with patch("agent.core.resource_monitor.get_vram_usage_mb", return_value=999_999):
                assert is_resource_exhausted(threshold_vram_mb=None) is False


def test_get_throttle_status_keys():
    """get_throttle_status returns dict with required keys."""
    status = get_throttle_status()
    assert "cpu_percent" in status
    assert "ram_mb" in status
    assert "vram_mb" in status
    assert "throttled" in status
    assert isinstance(status["throttled"], bool)
