"""Tests for session transcript saving."""

from unittest.mock import MagicMock
from artifice.config import ArtificeConfig
from artifice.session import SessionTranscript


def make_config(**kwargs):
    c = ArtificeConfig()
    c.provider = kwargs.get("provider", "simulated")
    c.model = kwargs.get("model", "test-model")
    c.system_prompt = kwargs.get("system_prompt", "Be helpful")
    return c


def make_fake_block(block_type, **kwargs):
    """Create a minimal fake block for testing session serialization."""
    block = MagicMock()
    block.__class__.__name__ = block_type

    # Set up isinstance checks by patching the module imports
    if block_type == "AgentInputBlock":
        block.get_prompt.return_value = kwargs.get("prompt", "test prompt")
    elif block_type == "AgentOutputBlock":
        block._full = kwargs.get("text", "agent response")
    elif block_type == "CodeInputBlock":
        block.get_code.return_value = kwargs.get("code", "print('hello')")
        block._language = kwargs.get("language", "python")
        block._command_number = kwargs.get("command_number", 1)
    elif block_type == "CodeOutputBlock":
        block._full = kwargs.get("output", "hello\n")
        block._has_error = kwargs.get("has_error", False)

    return block


class TestSessionTranscript:
    def test_creates_session_file(self, tmp_sessions_dir):
        config = make_config()
        s = SessionTranscript(tmp_sessions_dir, config)
        assert s.session_file.parent == tmp_sessions_dir
        assert s.session_file.name.startswith("session_")
        assert s.session_file.name.endswith(".md")

    def test_header_written_once(self, tmp_sessions_dir):
        config = make_config()
        s = SessionTranscript(tmp_sessions_dir, config)
        s._ensure_header()
        s._ensure_header()  # Second call should be no-op
        content = s.session_file.read_text()
        assert content.count("# Artifice Session") == 1

    def test_header_contains_metadata(self, tmp_sessions_dir):
        config = make_config(provider="claude", model="opus")
        s = SessionTranscript(tmp_sessions_dir, config)
        s._ensure_header()
        content = s.session_file.read_text()
        assert "claude" in content
        assert "opus" in content

    def test_finalize_adds_footer(self, tmp_sessions_dir):
        config = make_config()
        s = SessionTranscript(tmp_sessions_dir, config)
        s._ensure_header()
        s.finalize()
        content = s.session_file.read_text()
        assert "Ended:" in content

    def test_finalize_noop_without_header(self, tmp_sessions_dir):
        config = make_config()
        s = SessionTranscript(tmp_sessions_dir, config)
        s.finalize()  # Should not create file
        assert not s.session_file.exists()


class TestBlockToMarkdown:
    """Test the _block_to_markdown conversion for each block type."""

    def _convert(self, tmp_sessions_dir, block_type, **kwargs):
        """Helper to create session and convert a fake block."""
        from artifice.terminal_output import (
            CodeInputBlock, CodeOutputBlock,
            AgentInputBlock, AgentOutputBlock
        )
        config = make_config()
        s = SessionTranscript(tmp_sessions_dir, config)

        type_map = {
            "AgentInputBlock": AgentInputBlock,
            "AgentOutputBlock": AgentOutputBlock,
            "CodeInputBlock": CodeInputBlock,
            "CodeOutputBlock": CodeOutputBlock,
        }

        # We can't easily construct real Textual widgets without an app,
        # so we test the logic path by using isinstance-compatible mocks
        block = MagicMock(spec=type_map[block_type])

        if block_type == "AgentInputBlock":
            block.get_prompt.return_value = kwargs.get("prompt", "test")
        elif block_type == "AgentOutputBlock":
            block._full = kwargs.get("text", "response")
        elif block_type == "CodeInputBlock":
            block.get_code.return_value = kwargs.get("code", "x = 1")
            block._language = kwargs.get("language", "python")
            block._command_number = kwargs.get("command_number", 1)
        elif block_type == "CodeOutputBlock":
            block._full = kwargs.get("output", "result")
            block._has_error = kwargs.get("has_error", False)

        return s._block_to_markdown(block)

    def test_agent_input(self, tmp_sessions_dir):
        md = self._convert(tmp_sessions_dir, "AgentInputBlock", prompt="What is 2+2?")
        assert "## User" in md
        assert "What is 2+2?" in md

    def test_agent_output(self, tmp_sessions_dir):
        md = self._convert(tmp_sessions_dir, "AgentOutputBlock", text="The answer is 4")
        assert "## Agent" in md
        assert "The answer is 4" in md

    def test_agent_output_empty(self, tmp_sessions_dir):
        md = self._convert(tmp_sessions_dir, "AgentOutputBlock", text="   ")
        assert md == ""

    def test_code_input(self, tmp_sessions_dir):
        md = self._convert(tmp_sessions_dir, "CodeInputBlock", code="print(42)", language="python", command_number=1)
        assert "```python" in md
        assert "print(42)" in md

    def test_code_output(self, tmp_sessions_dir):
        md = self._convert(tmp_sessions_dir, "CodeOutputBlock", output="42\n")
        assert "### Output" in md
        assert "42" in md

    def test_code_output_error(self, tmp_sessions_dir):
        md = self._convert(tmp_sessions_dir, "CodeOutputBlock", output="NameError: x", has_error=True)
        assert "error" in md.lower()
        assert "NameError" in md

    def test_code_output_empty(self, tmp_sessions_dir):
        md = self._convert(tmp_sessions_dir, "CodeOutputBlock", output="   ")
        assert md == ""
