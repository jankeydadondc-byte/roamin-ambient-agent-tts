"""Tests for path validation — allowlist-based file operation safety."""

from __future__ import annotations

import os
from pathlib import Path

from agent.core.validators import SAFE_READ_ROOTS, SAFE_WRITE_ROOTS, validate_path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestValidatePath:
    """Path validation against allowlist roots."""

    def test_project_root_read_accepted(self):
        """Read inside project root should pass."""
        path = str(_PROJECT_ROOT / "agent" / "core" / "tools.py")
        assert validate_path(path, mode="read") is None

    def test_project_root_write_accepted(self):
        """Write inside project root should pass."""
        path = str(_PROJECT_ROOT / "tests" / "output.txt")
        assert validate_path(path, mode="write") is None

    def test_user_home_read_accepted(self):
        """Read inside user home should pass."""
        home = os.path.expanduser("~")
        path = os.path.join(home, "Documents", "test.txt")
        assert validate_path(path, mode="read") is None

    def test_user_home_write_rejected(self):
        """Write to user home (outside project root) should be rejected."""
        home = os.path.expanduser("~")
        path = os.path.join(home, "Documents", "test.txt")
        result = validate_path(path, mode="write")
        # Should be rejected UNLESS user home is under a safe write root
        # (which it's not — only project root and temp are write-safe)
        if not any(Path(path).resolve().is_relative_to(r.resolve()) for r in SAFE_WRITE_ROOTS):
            assert result is not None
            assert result["success"] is False

    def test_system_dir_rejected(self):
        """Write to system directory should be rejected."""
        result = validate_path(r"C:\Windows\System32\test.txt", mode="write")
        assert result is not None
        assert result["success"] is False
        assert "outside allowed" in result["error"] or "permission" in result.get("category", "")

    def test_system_dir_read_rejected(self):
        """Read from system directory should be rejected."""
        result = validate_path(r"C:\Windows\System32\drivers\etc\hosts", mode="read")
        assert result is not None
        assert result["success"] is False

    def test_empty_path_rejected(self):
        """Empty path should be rejected."""
        result = validate_path("", mode="read")
        assert result is not None
        assert result["success"] is False

    def test_null_bytes_rejected(self):
        """Path with null bytes should be rejected."""
        result = validate_path("file\x00.txt", mode="read")
        assert result is not None
        assert "null bytes" in result["error"]

    def test_unc_path_rejected(self):
        """UNC paths (\\\\server\\share) should be rejected."""
        result = validate_path(r"\\server\share\secret.txt", mode="read")
        assert result is not None
        assert result["success"] is False

    def test_temp_dir_write_accepted(self):
        """Write to temp directory should pass."""
        temp = os.environ.get("TEMP", os.environ.get("TMP", "/tmp"))
        path = os.path.join(temp, "roamin_test_output.txt")
        assert validate_path(path, mode="write") is None

    def test_relative_path_resolved(self):
        """Relative path should be resolved and validated correctly."""
        # A relative path starting with "agent/core/tools.py" resolves
        # relative to CWD. If CWD is project root, this should be accepted.
        original_cwd = os.getcwd()
        try:
            os.chdir(str(_PROJECT_ROOT))
            result = validate_path("agent/core/tools.py", mode="read")
            assert result is None
        finally:
            os.chdir(original_cwd)

    def test_mode_read_allows_more_roots(self):
        """Read mode should have more allowed roots than write mode."""
        assert len(SAFE_READ_ROOTS) >= len(SAFE_WRITE_ROOTS)

    def test_ssh_dir_read_rejected(self):
        """~/.ssh must be outside SAFE_READ_ROOTS — credential leak prevention."""
        path = str(Path.home() / ".ssh" / "id_rsa")
        result = validate_path(path, mode="read")
        assert result is not None
        assert result["success"] is False

    def test_aws_credentials_read_rejected(self):
        """~/.aws/credentials must be outside SAFE_READ_ROOTS."""
        path = str(Path.home() / ".aws" / "credentials")
        result = validate_path(path, mode="read")
        assert result is not None
        assert result["success"] is False

    def test_documents_subdir_read_accepted(self):
        """~/Documents subtree is explicitly in SAFE_READ_ROOTS and must be readable."""
        path = str(Path.home() / "Documents" / "notes.txt")
        assert validate_path(path, mode="read") is None

    def test_downloads_subdir_read_accepted(self):
        """~/Downloads subtree is explicitly in SAFE_READ_ROOTS and must be readable."""
        path = str(Path.home() / "Downloads" / "file.pdf")
        assert validate_path(path, mode="read") is None

    def test_plugin_dir_write_rejected(self):
        """Writes to agent/plugins/ must be blocked — code injection prevention."""
        path = str(_PROJECT_ROOT / "agent" / "plugins" / "evil.py")
        result = validate_path(path, mode="write")
        assert result is not None
        assert result["success"] is False
        assert result["category"] == "permission"

    def test_plugin_dir_read_accepted(self):
        """Reads from agent/plugins/ are still allowed (plugins load themselves)."""
        path = str(_PROJECT_ROOT / "agent" / "plugins" / "__init__.py")
        assert validate_path(path, mode="read") is None

    def test_core_dir_write_rejected(self):
        """Writes to agent/core/ must be blocked — core module protection."""
        path = str(_PROJECT_ROOT / "agent" / "core" / "tools.py")
        result = validate_path(path, mode="write")
        assert result is not None
        assert result["success"] is False

    def test_workspace_write_accepted(self):
        """Writes to workspace/ are still allowed (normal agent output area)."""
        path = str(_PROJECT_ROOT / "workspace" / "output.txt")
        assert validate_path(path, mode="write") is None

    def test_path_traversal_read_rejected(self):
        """POSIX-style path traversal must be rejected on read (#110)."""
        result = validate_path("../../etc/passwd", mode="read")
        # validate_path returns None (allowed) or dict (blocked) — traversal must be blocked
        assert result is not None
        assert result["success"] is False

    def test_path_traversal_write_rejected(self):
        """Path traversal on write must be rejected (#110)."""
        result = validate_path("../../etc/shadow", mode="write")
        assert result is not None
        assert result["success"] is False

    def test_windows_traversal_write_rejected(self):
        """Windows-style traversal into System32 must be rejected (#110)."""
        path = str(_PROJECT_ROOT / ".." / ".." / "Windows" / "System32" / "drivers" / "etc" / "hosts")
        result = validate_path(path, mode="write")
        assert result is not None
        assert result["success"] is False
