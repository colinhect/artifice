"""Tests for configuration loading and sandboxing."""

from pathlib import Path
from artifice.config import ArtificeConfig, load_config, get_sessions_dir


class TestArtificeConfig:
    def test_defaults(self):
        c = ArtificeConfig()
        assert c.provider is None
        assert c.model is None
        assert c.agent_markdown is True
        assert c.python_markdown is False
        assert c.save_sessions is True
        assert c.thinking_budget is None

    def test_thinking_budget_set_via_config(self, monkeypatch, tmp_path):
        init_file = tmp_path / "init.py"
        init_file.write_text("config.thinking_budget = 10000\n")
        monkeypatch.setattr("artifice.config.get_init_script_path", lambda: init_file)
        config, error = load_config()
        assert error is None
        assert config.thinking_budget == 10000

    def test_custom_settings(self):
        c = ArtificeConfig()
        c.set("my_key", "my_value")
        assert c.get("my_key") == "my_value"
        assert c.get("missing", "default") == "default"


class TestLoadConfig:
    def test_no_config_file(self, monkeypatch, tmp_path):
        """When no init.py exists, should return defaults with no error."""
        monkeypatch.setattr("artifice.config.get_init_script_path", lambda: tmp_path / "init.py")
        config, error = load_config()
        assert error is None
        assert config.provider is None

    def test_valid_config(self, monkeypatch, tmp_path):
        init_file = tmp_path / "init.py"
        init_file.write_text(
            'config.provider = "anthropic"\n'
            'config.model = "claude-sonnet-4-5"\n'
            'config.agent_markdown = False\n'
        )
        monkeypatch.setattr("artifice.config.get_init_script_path", lambda: init_file)
        config, error = load_config()
        assert error is None
        assert config.provider == "anthropic"
        assert config.model == "claude-sonnet-4-5"
        assert config.agent_markdown is False

    def test_sandbox_blocks_import(self, monkeypatch, tmp_path):
        """The sandbox should prevent __import__ calls."""
        init_file = tmp_path / "init.py"
        init_file.write_text("import os\n")
        monkeypatch.setattr("artifice.config.get_init_script_path", lambda: init_file)
        _, error = load_config()
        assert error is not None
        assert "Error" in error

    def test_sandbox_blocks_open(self, monkeypatch, tmp_path):
        init_file = tmp_path / "init.py"
        init_file.write_text("f = open('/etc/passwd')\n")
        monkeypatch.setattr("artifice.config.get_init_script_path", lambda: init_file)
        _, error = load_config()
        assert error is not None

    def test_sandbox_blocks_eval(self, monkeypatch, tmp_path):
        init_file = tmp_path / "init.py"
        init_file.write_text("eval('1+1')\n")
        monkeypatch.setattr("artifice.config.get_init_script_path", lambda: init_file)
        _, error = load_config()
        assert error is not None

    def test_sandbox_allows_basic_types(self, monkeypatch, tmp_path):
        """Basic Python types should work in the sandbox."""
        init_file = tmp_path / "init.py"
        init_file.write_text(
            'x = str(42)\n'
            'y = list(range(3))\n'
            'config.set("x", x)\n'
            'config.set("y", y)\n'
        )
        monkeypatch.setattr("artifice.config.get_init_script_path", lambda: init_file)
        config, error = load_config()
        assert error is None
        assert config.get("x") == "42"
        assert config.get("y") == [0, 1, 2]

    def test_syntax_error_in_config(self, monkeypatch, tmp_path):
        init_file = tmp_path / "init.py"
        init_file.write_text("def f(:\n")
        monkeypatch.setattr("artifice.config.get_init_script_path", lambda: init_file)
        _, error = load_config()
        assert error is not None
        assert "SyntaxError" in error


class TestGetSessionsDir:
    def test_default_path(self):
        c = ArtificeConfig()
        result = get_sessions_dir(c)
        assert result == Path.home() / ".artifice" / "sessions"

    def test_custom_path(self):
        c = ArtificeConfig()
        c.sessions_dir = "/tmp/my_sessions"
        result = get_sessions_dir(c)
        assert result == Path("/tmp/my_sessions")

    def test_tilde_expansion(self):
        c = ArtificeConfig()
        c.sessions_dir = "~/my_sessions"
        result = get_sessions_dir(c)
        assert str(result).startswith(str(Path.home()))
        assert "my_sessions" in str(result)
