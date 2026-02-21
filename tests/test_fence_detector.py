"""Tests for StreamingFenceDetector - header-based streaming splitter.

Uses lightweight fakes instead of real Textual widgets to test
that content splits on markdown headers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch
import pytest
from artifice.agent.streaming.detector import StreamingFenceDetector

if TYPE_CHECKING:
    from typing import Protocol

    class FakeBlockProtocol(Protocol):
        """Protocol for fake blocks used in tests."""

        _text: str
        _finished: bool
        _success: bool


def _as_fake(block: Any) -> FakeBlockProtocol:
    """Cast block to fake protocol for type checking."""
    return block  # type: ignore


# --- Fakes to avoid Textual widget dependencies ---


class FakeBlock:
    """Base fake block."""

    def __init__(self):
        self._text = ""
        self._output_str = ""
        self._finished = False
        self._success = False
        self._removed = False

    def remove(self):
        self._removed = True


class FakeAgentBlock(FakeBlock):
    """Fake AgentOutputBlock that just accumulates text."""

    def __init__(self, activity=False):
        super().__init__()
        self._streaming = True

    async def append(self, text):
        """Async append to match the real block's async interface."""
        self._text += text
        self._output_str += text

    def flush(self):
        pass

    def mark_success(self):
        self._success = True

    def mark_failed(self):
        pass

    def finalize_streaming(self):
        if not self._streaming:
            return
        self._streaming = False
        self._finished = True


class FakeOutput:
    """Fake TerminalOutput."""

    def __init__(self):
        self._blocks = []
        self._command_counter = 0

    def append_block(self, block, scroll=True):
        self._blocks.append(block)

    def remove_block(self, block):
        if block in self._blocks:
            self._blocks.remove(block)
        block.remove()

    def scroll_end(self, animate=True):
        pass


@pytest.fixture(autouse=True)
def _patch_block_types():
    """Patch isinstance targets so the detector recognizes our fakes."""
    with patch("artifice.agent.streaming.detector.AgentOutputBlock", FakeAgentBlock):
        yield


def make_detector() -> tuple[StreamingFenceDetector, FakeOutput]:
    """Create a detector with fake dependencies."""
    output = FakeOutput()
    detector = StreamingFenceDetector(output)  # type: ignore[arg-type]
    detector._make_prose_block = lambda activity: FakeAgentBlock(activity=activity)  # type: ignore[assignment]
    return detector, output


class TestSingleBlockStreaming:
    """Tests for the base single-block streaming behavior."""

    @pytest.mark.asyncio
    async def test_prose_only(self):
        """Plain text without headers produces a single prose block."""
        d, out = make_detector()
        d.start()
        await d.feed("Hello world, no headers here.")
        await d.finish()
        assert len(d.all_blocks) == 1
        assert isinstance(d.all_blocks[0], FakeAgentBlock)
        assert "Hello world" in d.all_blocks[0]._text

    @pytest.mark.asyncio
    async def test_text_with_code_fences(self):
        """Code fences are streamed as regular text, not split into blocks."""
        d, out = make_detector()
        d.start()
        await d.feed("Here is code:\n```python\nprint('hello')\n```\nDone")
        await d.finish()

        # Should only have one block with all the text
        assert len(d.all_blocks) == 1
        block = d.all_blocks[0]
        assert isinstance(block, FakeAgentBlock)
        assert "```python" in block._text
        assert "print('hello')" in block._text
        assert "Done" in block._text

    @pytest.mark.asyncio
    async def test_multiple_code_fences(self):
        """Multiple code fences stay in the single block as text."""
        d, out = make_detector()
        d.start()
        await d.feed("First:\n```python\nx = 1\n```\nSecond:\n```bash\nls\n```\nEnd")
        await d.finish()

        # Should still only have one block
        assert len(d.all_blocks) == 1
        block = d.all_blocks[0]
        assert "First:" in block._text
        assert "```python" in block._text
        assert "Second:" in block._text
        assert "```bash" in block._text
        assert "End" in block._text

    @pytest.mark.asyncio
    async def test_angle_bracket_in_prose(self):
        """< and > in prose should remain as prose text."""
        d, out = make_detector()
        d.start()
        await d.feed("x < 5 and y > 3")
        await d.finish()

        assert len(d.all_blocks) == 1
        assert "x < 5" in d.all_blocks[0]._text

    @pytest.mark.asyncio
    async def test_empty_lines_in_text(self):
        """Empty lines in prose should NOT split into multiple blocks."""
        d, out = make_detector()
        d.start()
        await d.feed("Paragraph one.\n\nParagraph two.")
        await d.finish()

        # Should still only have one block
        assert len(d.all_blocks) == 1
        block = d.all_blocks[0]
        assert "Paragraph one." in block._text
        assert "Paragraph two." in block._text

    @pytest.mark.asyncio
    async def test_streaming_multiple_chunks(self):
        """Multiple feed() calls accumulate into single block."""
        d, out = make_detector()
        d.start()
        await d.feed("First chunk")
        await d.feed(" second chunk")
        await d.feed(" third chunk")
        await d.finish()

        assert len(d.all_blocks) == 1
        assert "First chunk second chunk third chunk" in d.all_blocks[0]._text

    @pytest.mark.asyncio
    async def test_block_finalized_on_finish(self):
        """Block is finalized when finish() is called."""
        d, out = make_detector()
        d.start()
        await d.feed("Some text")
        await d.finish()

        block = d.all_blocks[0]
        assert block._finished
        assert block._success


class TestHeaderSplitting:
    """Tests for header-based block splitting."""

    @pytest.mark.asyncio
    async def test_single_header_creates_new_block(self):
        """A markdown header splits content into two blocks."""
        d, out = make_detector()
        d.start()
        await d.feed("Intro text\n# Section Header\nMore content")
        await d.finish()

        assert len(d.all_blocks) == 2
        # First block should have intro text
        assert "Intro text" in d.all_blocks[0]._text
        assert "# Section Header" not in d.all_blocks[0]._text
        # Second block should start with the header
        assert d.all_blocks[1]._text.startswith("# Section Header")
        assert "More content" in d.all_blocks[1]._text

    @pytest.mark.asyncio
    async def test_header_at_start_no_split(self):
        """If text starts with a header, it's in the first block."""
        d, out = make_detector()
        d.start()
        await d.feed("# First Header\nSome content")
        await d.finish()

        # Should only have one block
        assert len(d.all_blocks) == 1
        assert d.all_blocks[0]._text.startswith("# First Header")
        assert "Some content" in d.all_blocks[0]._text

    @pytest.mark.asyncio
    async def test_multiple_headers_create_multiple_blocks(self):
        """Multiple headers create multiple blocks."""
        d, out = make_detector()
        d.start()
        await d.feed(
            "Intro\n# Header 1\nContent 1\n## Header 2\nContent 2\n### Header 3\nContent 3"
        )
        await d.finish()

        assert len(d.all_blocks) == 4  # Intro + 3 headers
        assert "Intro" in d.all_blocks[0]._text
        assert d.all_blocks[1]._text.startswith("# Header 1")
        assert "Content 1" in d.all_blocks[1]._text
        assert d.all_blocks[2]._text.startswith("## Header 2")
        assert "Content 2" in d.all_blocks[2]._text
        assert d.all_blocks[3]._text.startswith("### Header 3")
        assert "Content 3" in d.all_blocks[3]._text

    @pytest.mark.asyncio
    async def test_different_header_levels(self):
        """All markdown header levels (H1-H6) trigger splitting."""
        d, out = make_detector()
        d.start()
        await d.feed(
            "Intro\n# H1\nA\n## H2\nB\n### H3\nC\n#### H4\nD\n##### H5\nE\n###### H6\nF"
        )
        await d.finish()

        assert len(d.all_blocks) == 7  # Intro + 6 headers
        assert d.all_blocks[1]._text.startswith("# H1")
        assert d.all_blocks[2]._text.startswith("## H2")
        assert d.all_blocks[3]._text.startswith("### H3")
        assert d.all_blocks[4]._text.startswith("#### H4")
        assert d.all_blocks[5]._text.startswith("##### H5")
        assert d.all_blocks[6]._text.startswith("###### H6")

    @pytest.mark.asyncio
    async def test_seven_hashes_not_header(self):
        """Seven # characters is not a valid header."""
        d, out = make_detector()
        d.start()
        await d.feed("Intro\n####### Not a header\nMore")
        await d.finish()

        # Should remain in one block
        assert len(d.all_blocks) == 1
        assert "####### Not a header" in d.all_blocks[0]._text

    @pytest.mark.asyncio
    async def test_header_at_end_of_line_is_detected(self):
        """A header at the end of a line (before newline) should split."""
        d, out = make_detector()
        d.start()
        await d.feed("Intro text")
        await d.feed("\n# Header\n")
        await d.feed("More content")
        await d.finish()

        assert len(d.all_blocks) == 2
        assert "Intro text" in d.all_blocks[0]._text
        assert d.all_blocks[1]._text.startswith("# Header")

    @pytest.mark.asyncio
    async def test_header_without_space_not_header(self):
        """###text is not a header (needs space after #)."""
        d, out = make_detector()
        d.start()
        await d.feed("Intro\n###text not header\nMore")
        await d.finish()

        # Should remain in one block
        assert len(d.all_blocks) == 1
        assert "###text not header" in d.all_blocks[0]._text

    @pytest.mark.asyncio
    async def test_header_at_stream_end(self):
        """Header at the very end of stream (no trailing newline)."""
        d, out = make_detector()
        d.start()
        await d.feed("Intro text\n")
        await d.feed("# Final Header")
        await d.finish()

        assert len(d.all_blocks) == 2
        assert "Intro text" in d.all_blocks[0]._text
        assert d.all_blocks[1]._text.startswith("# Final Header")


class TestEdgeCases:
    """Edge case tests for streaming behavior."""

    @pytest.mark.asyncio
    async def test_empty_stream(self):
        """Empty stream should still create a block."""
        d, out = make_detector()
        d.start()
        await d.finish()

        # Should have one empty block that was finalized
        assert len(d.all_blocks) == 1
        assert d.all_blocks[0]._finished

    @pytest.mark.asyncio
    async def test_only_whitespace(self):
        """Whitespace-only stream."""
        d, out = make_detector()
        d.start()
        await d.feed("   \n\n   ")
        await d.finish()

        assert len(d.all_blocks) == 1
        assert "   \n\n   " in d.all_blocks[0]._text

    @pytest.mark.asyncio
    async def test_very_long_text(self):
        """Long text streams into single block."""
        d, out = make_detector()
        d.start()

        long_text = "x" * 10000
        await d.feed(long_text)
        await d.finish()

        assert len(d.all_blocks) == 1
        assert long_text in d.all_blocks[0]._text

    @pytest.mark.asyncio
    async def test_special_characters(self):
        """Special markdown characters are preserved."""
        d, out = make_detector()
        d.start()

        special = "# Header\n## Subheader\n- List item\n**bold**\n_italic_\n`code`"
        await d.feed(special)
        await d.finish()

        # Should have 2 blocks (header and subheader)
        assert len(d.all_blocks) == 2
        assert "# Header" in d.all_blocks[0]._text
        assert d.all_blocks[1]._text.startswith("## Subheader")
        assert "- List item" in d.all_blocks[1]._text
        assert "**bold**" in d.all_blocks[1]._text
        assert "`code`" in d.all_blocks[1]._text

    @pytest.mark.asyncio
    async def test_unicode_text(self):
        """Unicode text is preserved."""
        d, out = make_detector()
        d.start()

        unicode_text = "Hello 世界 🌍 ñ"
        await d.feed(unicode_text)
        await d.finish()

        assert unicode_text in d.all_blocks[0]._text

    @pytest.mark.asyncio
    async def test_header_with_only_hashes(self):
        """Just # or ## is a valid header."""
        d, out = make_detector()
        d.start()
        await d.feed("Intro\n#\nMore content")
        await d.finish()

        assert len(d.all_blocks) == 2
        assert "Intro" in d.all_blocks[0]._text
        assert d.all_blocks[1]._text.startswith("#")

    @pytest.mark.asyncio
    async def test_last_code_block_none(self):
        """last_code_block always returns None."""
        d, out = make_detector()
        d.start()
        await d.feed("Some text with code fences")

        assert d.last_code_block is None

        await d.finish()
        assert d.last_code_block is None

    @pytest.mark.asyncio
    async def test_resume_is_noop(self):
        """resume() does nothing in simplified version."""
        d, out = make_detector()
        d.start()
        await d.feed("Some text\n")  # Add newline so text is flushed immediately

        # Should not raise or cause issues
        d.resume()

        # Text should still be there
        assert "Some text" in d.all_blocks[0]._text
