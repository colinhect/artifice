"""Tests for StreamingFenceDetector - the markdown fence parser.

Uses lightweight fakes instead of real Textual widgets to test
the parsing state machine in isolation. We patch the isinstance
targets in the terminal module so the detector recognizes our fakes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch
import pytest
from artifice.fence_detector import StreamingFenceDetector, _FenceState

if TYPE_CHECKING:
    from typing import Protocol

    class HasText(Protocol):
        _text: str

    class HasRemoved(Protocol):
        _removed: bool

    class HasOutputStr(Protocol):
        _output_str: str


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

    def append(self, text):
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


class FakeCodeBlock(FakeBlock):
    """Fake CodeInputBlock that just stores code."""

    def __init__(self, code="", language="python"):
        super().__init__()
        self._code = code
        self._language = language
        self._command_number = 0

    def get_code(self):
        return self._code

    def update_code(self, code):
        self._code = code

    def finish_streaming(self):
        self._finished = True


class FakeOutput:
    """Fake TerminalOutput."""

    def __init__(self):
        self._blocks = []
        self._command_counter = 0

    def append_block(self, block):
        self._blocks.append(block)

    def remove_block(self, block):
        if block in self._blocks:
            self._blocks.remove(block)
        block.remove()

    def scroll_end(self, animate=False):
        pass


@pytest.fixture(autouse=True)
def _patch_block_types():
    """Patch isinstance targets so the detector recognizes our fakes."""
    with (
        patch("artifice.fence_detector.AgentOutputBlock", FakeAgentBlock),
        patch("artifice.fence_detector.CodeInputBlock", FakeCodeBlock),
    ):
        yield


def make_detector():
    """Create a detector with fake dependencies."""
    output = FakeOutput()
    detector = StreamingFenceDetector(output)  # type: ignore
    detector._make_prose_block = lambda activity: FakeAgentBlock(activity=activity)  # type: ignore
    detector._make_code_block = lambda code, lang: FakeCodeBlock(code, language=lang)  # type: ignore
    return detector, output


class TestProseOnly:
    def test_prose_only(self):
        """Plain text without fences produces a single prose block."""
        d, out = make_detector()
        d.start()
        d.feed("Hello world, no code here.")
        d.finish()
        assert len(d.all_blocks) == 1
        assert isinstance(d.all_blocks[0], FakeAgentBlock)
        assert "Hello world" in d.all_blocks[0]._text

    def test_angle_bracket_in_prose(self):
        """< and > in prose should remain as prose text."""
        d, out = make_detector()
        d.start()
        d.feed("x < 5 and y > 3")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 0
        assert "x < 5" in d.all_blocks[0]._text  # type: ignore


class TestMarkdownFences:
    """Tests for markdown code fence support (```language)."""

    def test_simple_python_fence(self):
        """```python fence creates a python code block."""
        d, out = make_detector()
        d.start()
        d.feed("Here is code:\n```python\nprint('hello')\n```\nDone")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "print('hello')" in code_blocks[0]._code
        assert code_blocks[0]._language == "python"

    def test_simple_bash_fence(self):
        """```bash fence creates a bash code block."""
        d, out = make_detector()
        d.start()
        d.feed("Run this:\n```bash\nls -la\n```\nDone")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "ls -la" in code_blocks[0]._code
        assert code_blocks[0]._language == "bash"

    def test_shell_fence_maps_to_bash(self):
        """```shell fence should create a bash code block."""
        d, out = make_detector()
        d.start()
        d.feed("```shell\necho hi\n```")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert code_blocks[0]._language == "bash"

    def test_fence_without_language(self):
        """``` without language should default to bash."""
        d, out = make_detector()
        d.start()
        d.feed("```\nsome command\n```")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert code_blocks[0]._language == "bash"

    def test_empty_lines_in_fence_dont_split(self):
        """Empty lines inside a fence should NOT split into multiple blocks."""
        d, out = make_detector()
        d.start()
        d.feed("```python\ndef foo():\n    pass\n\ndef bar():\n    pass\n```")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "def foo():" in code_blocks[0]._code
        assert "def bar():" in code_blocks[0]._code

    def test_multiple_fences(self):
        """Multiple fences in one response."""
        d, out = make_detector()
        d.start()
        d.feed("First:\n```python\nx = 1\n```\nSecond:\n```bash\nls\n```\nEnd")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 2
        assert code_blocks[0]._language == "python"
        assert code_blocks[1]._language == "bash"
        assert "x = 1" in code_blocks[0]._code
        assert "ls" in code_blocks[1]._code

    def test_fence_with_prose_before_and_after(self):
        """Fences create separate blocks from surrounding prose."""
        d, out = make_detector()
        d.start()
        d.feed("Before\n```python\ncode\n```\nAfter")
        d.finish()

        prose_blocks = [
            b
            for b in d.all_blocks
            if isinstance(b, FakeAgentBlock) and b._text.strip()  # type: ignore
        ]
        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert any("Before" in b._text for b in prose_blocks)  # type: ignore
        assert any("After" in b._text for b in prose_blocks)  # type: ignore

    def test_fence_split_across_chunks(self):
        """Fence split across feed() calls should work."""
        d, out = make_detector()
        d.start()
        d.feed("Text\n```py")
        d.feed("thon\nco")
        d.feed("de\n```")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "code" in code_blocks[0]._code

    def test_backticks_create_code_blocks(self):
        """Markdown code fences should create code blocks."""
        d, out = make_detector()
        d.start()
        d.feed("Use ```python\ncode\n```\nfor formatting")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "code" in code_blocks[0]._code
        assert code_blocks[0]._language == "python"


class TestBackticksInCodeBlocks:
    """Test that backticks in strings/comments within code don't close fences."""

    def test_triple_backticks_in_string(self):
        """Triple backticks in a string literal should not close the fence."""
        d, out = make_detector()
        d.start()
        d.feed(
            'Here is code:\n```python\ntext = "Use ```python for code blocks"\nprint(text)\n```\nDone'
        )
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert 'text = "Use ```python' in code_blocks[0]._code
        assert "print(text)" in code_blocks[0]._code

    def test_triple_backticks_in_comment(self):
        """Triple backticks in a comment should not close the fence."""
        d, out = make_detector()
        d.start()
        d.feed(
            '```python\n# Use ```python to start a code block\nprint("hello")\n```\nDone'
        )
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "# Use ```python" in code_blocks[0]._code
        assert 'print("hello")' in code_blocks[0]._code

    def test_triple_backticks_in_multiline_string(self):
        """Triple backticks in a multiline string should not close the fence."""
        d, out = make_detector()
        d.start()
        d.feed('```python\nhelp_text = """\nUse ```python\nfor code\n"""\n```\nDone')
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "```python" in code_blocks[0]._code
        assert "help_text" in code_blocks[0]._code


class TestWhitespaceStripping:
    def test_whitespace_after_closing_fence_stripped(self):
        """Whitespace after closing ``` should be stripped from the next prose block."""
        d, _ = make_detector()
        d.start()
        d.feed("```bash\nx = 1\n```\nNext text")
        d.finish()

        prose_blocks = [
            b
            for b in d.all_blocks
            if isinstance(b, FakeAgentBlock) and b._text.strip()  # type: ignore
        ]
        after_code = [b for b in prose_blocks if "Next text" in b._text]  # type: ignore
        assert len(after_code) == 1
        assert after_code[0]._text.startswith("Next")  # type: ignore

    def test_no_stripping_within_prose(self):
        """Normal whitespace within prose should not be affected."""
        d, _ = make_detector()
        d.start()
        d.feed("Line one\n\nLine two")
        d.finish()

        # Should have split into multiple blocks on the empty line, as normal
        prose_blocks = [
            b
            for b in d.all_blocks
            if isinstance(b, FakeAgentBlock) and b._text.strip()  # type: ignore
        ]
        assert any("Line one" in b._text for b in prose_blocks)  # type: ignore
        assert any("Line two" in b._text for b in prose_blocks)  # type: ignore


class TestRealTimeBlockFinalization:
    def test_empty_line_finalizes_block_immediately(self):
        """Block completed by empty line is finalized (not just marked success) mid-stream."""
        d, _ = make_detector()
        d.start()
        d.feed("Paragraph one.\n\n")
        prose_blocks = [b for b in d.all_blocks if isinstance(b, FakeAgentBlock)]
        assert len(prose_blocks) >= 1
        first_block = prose_blocks[0]
        assert first_block._finished, (
            "Block split by empty line should be finalized immediately"
        )
        assert first_block._success

    def test_second_block_still_streaming_after_split(self):
        """After an empty-line split, the new block is still streaming."""
        d, _ = make_detector()
        d.start()
        d.feed("Para one.\n\nPara two.")
        prose_blocks = [b for b in d.all_blocks if isinstance(b, FakeAgentBlock)]
        assert len(prose_blocks) >= 2
        second_block = prose_blocks[-1]
        assert not second_block._finished, (
            "Current streaming block should not be finalized yet"
        )

    def test_finalize_streaming_idempotent(self):
        """Calling finalize_streaming() twice on the same block is safe."""
        d, _ = make_detector()
        d.start()
        d.feed("Para one.\n\nPara two.")
        d.finish()
        prose_blocks = [b for b in d.all_blocks if isinstance(b, FakeAgentBlock)]
        assert all(b._finished for b in prose_blocks)

    def test_multiple_empty_lines_finalize_each_block(self):
        """Each paragraph split creates a new finalized block in real-time."""
        d, _ = make_detector()
        d.start()
        d.feed("Para one.\n\nPara two.\n\nPara three.")
        prose_blocks = [b for b in d.all_blocks if isinstance(b, FakeAgentBlock)]
        finalized = [b for b in prose_blocks if b._finished]
        assert len(finalized) == 2
        assert "Para one." in finalized[0]._text
        assert "Para two." in finalized[1]._text


class TestEmptyBlocks:
    def test_empty_prose_before_code_is_removed(self):
        """If the response starts immediately with a fence, the empty prose is removed."""
        d, out = make_detector()
        d.start()
        d.feed("```python\nx = 1\n```")
        d.finish()

        assert d.first_agent_block is None  # Was removed since it was empty

    def test_empty_trailing_prose_removed(self):
        """Empty prose block after last code fence should be removed."""
        d, out = make_detector()
        d.start()
        d.feed("```python\nx = 1\n```")
        d.finish()

        non_removed = [b for b in d.all_blocks if not b._removed]  # type: ignore
        for b in non_removed:
            if isinstance(b, FakeAgentBlock):
                assert b._text.strip()  # type: ignore


    def test_consecutive_blank_lines_no_empty_blocks(self):
        """Multiple consecutive blank lines should not leave empty blocks after finish."""
        d, out = make_detector()
        d.start()
        d.feed("Hello.\n\n\n\nWorld.")
        d.finish()

        non_removed = [b for b in d.all_blocks if not b._removed]
        for b in non_removed:
            if isinstance(b, FakeAgentBlock):
                assert b._text.strip(), f"Empty AgentOutputBlock left in output: {b._text!r}"

    def test_empty_first_agent_block_removed_in_finish(self):
        """first_agent_block should be set to None if it's empty at finish()."""
        d, out = make_detector()
        d.start()
        assert d.first_agent_block is not None
        # Don't feed any text, just finish
        d.finish()
        assert d.first_agent_block is None


class TestStateTransitions:
    def test_state_starts_as_prose(self):
        d, _ = make_detector()
        assert d._state == _FenceState.PROSE

    def test_fence_transitions_to_code(self):
        d, _ = make_detector()
        d.start()
        d.feed("```python\n")
        assert d._state == _FenceState.CODE

    def test_closing_fence_transitions_to_prose(self):
        d, _ = make_detector()
        d.start()
        d.feed("```python\ncode\n```")
        assert d._state == _FenceState.PROSE


class TestPauseAfterCodeBlock:
    def make_pausing_detector(self):
        """Create a detector with pause_after_code enabled."""
        output = FakeOutput()
        detector = StreamingFenceDetector(output, pause_after_code=True)  # type: ignore
        detector._make_prose_block = lambda activity: FakeAgentBlock(  # type: ignore
            activity=activity
        )
        detector._make_code_block = lambda code, lang: FakeCodeBlock(  # type: ignore
            code, language=lang
        )
        return detector, output

    def test_pauses_after_code_block(self):
        """Detector pauses after a code fence closes."""
        d, out = self.make_pausing_detector()
        d.start()
        d.feed("Hello\n```python\nx=1\n```\nAfter code")
        assert d.is_paused
        assert d._remainder == "After code"

    def test_last_code_block_set(self):
        """last_code_block is set to the block that triggered the pause."""
        d, out = self.make_pausing_detector()
        d.start()
        d.feed("Hello\n```python\nx=1\n```\nrest")
        assert d.last_code_block is not None
        assert isinstance(d.last_code_block, FakeCodeBlock)
        assert "x=1" in d.last_code_block._code

    def test_resume_feeds_remainder(self):
        """resume() processes the saved remainder text."""
        d, out = self.make_pausing_detector()
        d.start()
        d.feed("Hello\n```python\nx=1\n```\nAfter text")
        assert d.is_paused

        d.resume()
        assert not d.is_paused
        prose_blocks = [b for b in d.all_blocks if isinstance(b, FakeAgentBlock)]
        combined = "".join(b._text for b in prose_blocks)  # type: ignore
        assert "After text" in combined

    def test_resume_with_second_code_block(self):
        """resume() pauses again if remainder contains another code block."""
        d, out = self.make_pausing_detector()
        d.start()
        d.feed("Hello\n```python\nfirst\n```\nMiddle\n```bash\nls\n```\nEnd")
        assert d.is_paused

        d.resume()
        # Should pause again on second code block
        assert d.is_paused

    def test_no_pause_without_flag(self):
        """Default detector (no pause_after_code) does not pause."""
        d, out = make_detector()
        d.start()
        d.feed("Hello\n```python\nx=1\n```\nAfter")
        assert not d.is_paused

    def test_pause_after_fence(self):
        """Pause after code block works with markdown fences."""
        d, out = self.make_pausing_detector()
        d.start()
        d.feed("Hello\n```python\nx=1\n```\nAfter")
        assert d.is_paused
        assert "After" in d._remainder
