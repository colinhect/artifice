"""Tests for terminal output blocks."""

from artifice.terminal_output import CodeInputBlock, AgentOutputBlock


class TestCodeInputBlock:
    """Tests for CodeInputBlock."""

    def test_streaming_code_block_initialization(self):
        """Test that code blocks are initialized correctly during streaming."""
        code = "print('hello')"
        block = CodeInputBlock(code, language="python", show_loading=True)

        # Should be in streaming mode
        assert block._streaming is True
        assert block._original_code == code
        assert block._language == "python"

        # Code widget should exist
        assert block._code is not None

    def test_update_code_stores_original(self):
        """Test that update_code() stores the original code correctly."""
        block = CodeInputBlock("x = 1", language="python", show_loading=True)

        # Update with new code
        new_code = "y = 2\nprint(y)"
        block.update_code(new_code)

        # Should store the new code
        assert block._original_code == new_code
        assert block.get_code() == new_code

    def test_finish_streaming_shows_status(self):
        """Test that finish_streaming() shows the status indicator."""
        block = CodeInputBlock("x = 1", language="python", show_loading=True)

        # Initially status indicator should be hidden
        assert block._status_indicator.styles.display == "none"

        # After finish_streaming, should be visible
        block.finish_streaming()
        assert block._status_indicator.styles.display == "block"
        assert block._streaming is False


class TestAgentOutputBlock:
    """Tests for AgentOutputBlock."""

    def test_streaming_uses_markdown_when_enabled(self):
        """Test that agent output uses Markdown during streaming when render_markdown=True."""
        block = AgentOutputBlock("Initial text", activity=True, render_markdown=True)

        # During streaming with markdown enabled, should use Markdown
        assert block._streaming is True
        assert block._markdown is not None
        assert block._output is None

    def test_streaming_uses_plain_text_when_markdown_disabled(self):
        """Test that agent output uses plain text when render_markdown=False."""
        block = AgentOutputBlock("Initial text", activity=True, render_markdown=False)

        # Should use plain Static when markdown is disabled
        assert block._streaming is True
        assert block._output is not None
        assert block._markdown is None

    def test_finalize_streaming_updates_flag(self):
        """Test that finalize_streaming() updates the streaming flag."""
        block = AgentOutputBlock("Test output", activity=True, render_markdown=True)

        # Should start in streaming mode
        assert block._streaming is True

        # After finalization, streaming flag should be False
        block.finalize_streaming()
        assert block._streaming is False

    def test_append_accumulates_text(self):
        """Test that append() accumulates text correctly."""
        block = AgentOutputBlock("Initial", activity=True, render_markdown=False)

        # Append more text (use plain text mode to avoid Markdown context requirement)
        block.append(" text")

        # Full text should be accumulated
        assert block._full == "Initial text"
