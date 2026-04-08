"""Tests for centralized secrets loader."""

from __future__ import annotations

import os
from unittest.mock import patch

from agent.core.secrets import check_secrets, get_secret, load_secrets


class TestGetSecret:
    """get_secret() reads from environment."""

    def test_returns_env_var(self):
        """Should return the env var value when set."""
        with patch.dict(os.environ, {"TEST_SECRET_XYZ": "hunter2"}):
            assert get_secret("TEST_SECRET_XYZ") == "hunter2"

    def test_returns_none_when_missing(self):
        """Should return None for missing optional secret."""
        key = "DEFINITELY_NOT_SET_ABC123"
        os.environ.pop(key, None)
        assert get_secret(key) is None

    def test_required_raises_on_missing(self):
        """Should raise RuntimeError for missing required secret."""
        key = "DEFINITELY_NOT_SET_ABC123"
        os.environ.pop(key, None)
        try:
            get_secret(key, required=True)
            raise AssertionError("Should have raised RuntimeError")
        except RuntimeError as e:
            assert key in str(e)

    def test_required_returns_value_when_set(self):
        """Should return value without raising when required and present."""
        with patch.dict(os.environ, {"TEST_REQUIRED_KEY": "val"}):
            assert get_secret("TEST_REQUIRED_KEY", required=True) == "val"


class TestLoadSecrets:
    """load_secrets() parses .env files."""

    def test_loads_from_env_file(self, tmp_path):
        """Should load KEY=VALUE pairs from .env file."""
        import agent.core.secrets as mod

        env_file = tmp_path / ".env"
        env_file.write_text("MY_TEST_KEY=my_test_value\n# comment line\nANOTHER=123\n")

        # Reset the _LOADED flag so load_secrets actually runs
        mod._LOADED = False
        # Remove keys if they exist
        os.environ.pop("MY_TEST_KEY", None)
        os.environ.pop("ANOTHER", None)

        try:
            load_secrets(env_path=env_file)
            assert os.environ.get("MY_TEST_KEY") == "my_test_value"
            assert os.environ.get("ANOTHER") == "123"
        finally:
            os.environ.pop("MY_TEST_KEY", None)
            os.environ.pop("ANOTHER", None)
            mod._LOADED = False

    def test_env_var_takes_precedence(self, tmp_path):
        """Existing env vars should NOT be overwritten by .env file."""
        import agent.core.secrets as mod

        env_file = tmp_path / ".env"
        env_file.write_text("PREC_TEST=from_file\n")

        mod._LOADED = False
        os.environ["PREC_TEST"] = "from_env"

        try:
            load_secrets(env_path=env_file)
            assert os.environ.get("PREC_TEST") == "from_env"
        finally:
            os.environ.pop("PREC_TEST", None)
            mod._LOADED = False

    def test_missing_env_file_no_error(self, tmp_path):
        """Missing .env file should not raise."""
        import agent.core.secrets as mod

        mod._LOADED = False
        load_secrets(env_path=tmp_path / "nonexistent.env")
        # No exception raised
        mod._LOADED = False


class TestCheckSecrets:
    """check_secrets() validates at startup."""

    def test_required_missing_raises(self):
        """Should raise if a required secret is missing."""
        key = "CHECK_REQUIRED_MISSING_XYZ"
        os.environ.pop(key, None)
        try:
            check_secrets(required=[key])
            raise AssertionError("Should have raised RuntimeError")
        except RuntimeError as e:
            assert key in str(e)

    def test_required_present_ok(self):
        """Should not raise if required secret is present."""
        with patch.dict(os.environ, {"CHECK_PRESENT": "yes"}):
            check_secrets(required=["CHECK_PRESENT"])

    def test_optional_missing_no_error(self):
        """Missing optional secrets should not raise (only logs)."""
        key = "OPTIONAL_MISSING_XYZ"
        os.environ.pop(key, None)
        check_secrets(optional=[key])  # No exception
