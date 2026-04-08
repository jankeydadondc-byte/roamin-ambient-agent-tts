"""Tests for JSONL audit log — append, query, and pruning."""

from __future__ import annotations

import json
from unittest.mock import patch

from agent.core import audit_log


class TestAuditAppend:
    """audit_log.append() writes JSONL entries."""

    def test_append_creates_valid_json_line(self, tmp_path):
        """Each append should write exactly one valid JSON line."""
        log_file = tmp_path / "audit.jsonl"
        with patch.object(audit_log, "_LOG_PATH", log_file):
            audit_log.append(tool="read_file", params={"path": "/test"}, success=True, duration_ms=12.5)

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["tool"] == "read_file"
        assert entry["success"] is True
        assert entry["duration_ms"] == 12.5
        assert "ts" in entry

    def test_append_multiple_entries(self, tmp_path):
        """Multiple appends should create multiple lines."""
        log_file = tmp_path / "audit.jsonl"
        with patch.object(audit_log, "_LOG_PATH", log_file):
            audit_log.append(tool="tool_a", params={}, success=True)
            audit_log.append(tool="tool_b", params={}, success=False, result_summary="error msg")
            audit_log.append(tool="tool_c", params={}, success=True)

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_append_truncates_large_result(self, tmp_path):
        """Result summary should be truncated to 500 chars."""
        log_file = tmp_path / "audit.jsonl"
        big_result = "x" * 1000
        with patch.object(audit_log, "_LOG_PATH", log_file):
            audit_log.append(tool="test", params={}, success=True, result_summary=big_result)

        entry = json.loads(log_file.read_text().strip())
        assert len(entry["result"]) <= 500

    def test_append_sanitizes_large_params(self, tmp_path):
        """Large param values should be truncated in the log."""
        log_file = tmp_path / "audit.jsonl"
        with patch.object(audit_log, "_LOG_PATH", log_file):
            audit_log.append(tool="test", params={"code": "x" * 500}, success=True)

        entry = json.loads(log_file.read_text().strip())
        assert "[truncated]" in entry["params"]["code"]

    def test_append_failure_does_not_raise(self, tmp_path):
        """Audit write failure should be silently swallowed."""
        bad_path = tmp_path / "nonexistent_dir" / "deep" / "audit.jsonl"
        # Make it fail by pointing to a file where parent can't be created
        with patch.object(audit_log, "_LOG_PATH", bad_path):
            with patch.object(audit_log, "_LOG_PATH") as mock_path:
                mock_path.parent.mkdir.side_effect = PermissionError("denied")
                # This should NOT raise
                audit_log.append(tool="test", params={}, success=True)


class TestAuditQuery:
    """audit_log.query() reads and filters entries."""

    def _populate(self, log_file, entries):
        """Write test entries to a JSONL file."""
        with open(log_file, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def test_query_returns_reverse_chronological(self, tmp_path):
        """Entries should be returned newest-first."""
        log_file = tmp_path / "audit.jsonl"
        self._populate(
            log_file,
            [
                {"ts": "2026-04-07T10:00:00Z", "tool": "a", "success": True},
                {"ts": "2026-04-07T11:00:00Z", "tool": "b", "success": True},
                {"ts": "2026-04-07T12:00:00Z", "tool": "c", "success": True},
            ],
        )
        with patch.object(audit_log, "_LOG_PATH", log_file):
            results = audit_log.query(limit=10)
        assert results[0]["tool"] == "c"
        assert results[-1]["tool"] == "a"

    def test_query_with_tool_filter(self, tmp_path):
        """tool_filter should return only matching entries."""
        log_file = tmp_path / "audit.jsonl"
        self._populate(
            log_file,
            [
                {"ts": "2026-04-07T10:00:00Z", "tool": "read_file", "success": True},
                {"ts": "2026-04-07T11:00:00Z", "tool": "write_file", "success": True},
                {"ts": "2026-04-07T12:00:00Z", "tool": "read_file", "success": False},
            ],
        )
        with patch.object(audit_log, "_LOG_PATH", log_file):
            results = audit_log.query(tool_filter="read_file")
        assert len(results) == 2
        assert all(r["tool"] == "read_file" for r in results)

    def test_query_with_since_filter(self, tmp_path):
        """since filter should exclude earlier entries."""
        log_file = tmp_path / "audit.jsonl"
        self._populate(
            log_file,
            [
                {"ts": "2026-04-06T10:00:00Z", "tool": "old", "success": True},
                {"ts": "2026-04-07T10:00:00Z", "tool": "new", "success": True},
            ],
        )
        with patch.object(audit_log, "_LOG_PATH", log_file):
            results = audit_log.query(since="2026-04-07")
        assert len(results) == 1
        assert results[0]["tool"] == "new"

    def test_query_respects_limit(self, tmp_path):
        """Should return at most `limit` entries."""
        log_file = tmp_path / "audit.jsonl"
        self._populate(
            log_file, [{"ts": f"2026-04-07T{i:02d}:00:00Z", "tool": f"t{i}", "success": True} for i in range(20)]
        )
        with patch.object(audit_log, "_LOG_PATH", log_file):
            results = audit_log.query(limit=5)
        assert len(results) == 5

    def test_query_empty_log(self, tmp_path):
        """Should return empty list for nonexistent log."""
        with patch.object(audit_log, "_LOG_PATH", tmp_path / "does_not_exist.jsonl"):
            results = audit_log.query()
        assert results == []


class TestAuditPrune:
    """Auto-prune keeps log file size manageable."""

    def test_prune_triggers_on_large_file(self, tmp_path):
        """File exceeding max size should be pruned."""
        log_file = tmp_path / "audit.jsonl"
        # Write enough data to exceed 100KB
        with open(log_file, "w", encoding="utf-8") as f:
            for i in range(2000):
                f.write(json.dumps({"ts": f"T{i}", "tool": "t", "data": "x" * 50}) + "\n")

        original_lines = len(log_file.read_text().splitlines())
        with patch.object(audit_log, "_LOG_PATH", log_file):
            audit_log._prune_if_needed()

        pruned_lines = len(log_file.read_text().splitlines())
        assert pruned_lines < original_lines
