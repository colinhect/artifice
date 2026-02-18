"""Tests for StreamingFenceDetector - the code tag parser.

Uses lightweight fakes instead of real Textual widgets to test
the parsing state machine in isolation. We patch the isinstance
targets in the terminal module so the detector recognizes our fakes.
"""

from unittest.mock import patch
import pytest
from artifice.fence_detector import StreamingFenceDetector, _FenceState


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


class FakeAssistantBlock(FakeBlock):
    """Fake AssistantOutputBlock that just accumulates text."""

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


class FakeThinkingBlock(FakeBlock):
    """Fake ThinkingOutputBlock that accumulates thinking text."""

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
        patch("artifice.fence_detector.AssistantOutputBlock", FakeAssistantBlock),
        patch("artifice.fence_detector.CodeInputBlock", FakeCodeBlock),
        patch("artifice.fence_detector.ThinkingOutputBlock", FakeThinkingBlock),
    ):
        yield


def make_detector():
    """Create a detector with fake dependencies."""
    output = FakeOutput()
    detector = StreamingFenceDetector(output)
    detector._make_prose_block = lambda activity: FakeAssistantBlock(activity=activity)
    detector._make_code_block = lambda code, lang: FakeCodeBlock(code, language=lang)
    detector._make_thinking_block = lambda: FakeThinkingBlock(activity=True)
    return detector, output


class TestBasicTagDetection:
    def test_prose_only(self):
        """Plain text without tags produces a single prose block."""
        d, out = make_detector()
        d.start()
        d.feed("Hello world, no code here.")
        d.finish()
        assert len(d.all_blocks) == 1
        assert isinstance(d.all_blocks[0], FakeAssistantBlock)
        assert "Hello world" in d.all_blocks[0]._text

    def test_single_python_block(self):
        """<python> tag creates prose + code + prose blocks."""
        d, out = make_detector()
        d.start()
        d.feed("Here is code:<python>print('hi')</python>Done.")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "print('hi')" in code_blocks[0]._code
        assert code_blocks[0]._language == "python"

    def test_single_shell_block(self):
        """<shell> tag creates a bash code block."""
        d, out = make_detector()
        d.start()
        d.feed("Run this:<shell>ls -la</shell>Done.")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "ls -la" in code_blocks[0]._code
        assert code_blocks[0]._language == "bash"

    def test_multiple_code_blocks(self):
        d, out = make_detector()
        d.start()
        d.feed("First:<python>x = 1</python>Second:<shell>ls -la</shell>End.")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 2
        assert code_blocks[0]._language == "python"
        assert code_blocks[1]._language == "bash"
        assert "x = 1" in code_blocks[0]._code
        assert "ls -la" in code_blocks[1]._code

    def test_code_with_prose_before_and_after(self):
        d, out = make_detector()
        d.start()
        d.feed("Before<python>code</python>After")
        d.finish()

        prose_blocks = [
            b
            for b in d.all_blocks
            if isinstance(b, FakeAssistantBlock) and b._text.strip()
        ]
        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert any("Before" in b._text for b in prose_blocks)
        assert any("After" in b._text for b in prose_blocks)

    def test_multiline_python_block(self):
        """Code tags with newlines in code content."""
        d, out = make_detector()
        d.start()
        d.feed("Code:\n<python>\nx = 1\ny = 2\nprint(x + y)\n</python>\nDone.")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "x = 1" in code_blocks[0]._code
        assert "y = 2" in code_blocks[0]._code
        assert "print(x + y)" in code_blocks[0]._code


class TestStreamingChunks:
    def test_tag_split_across_chunks(self):
        """Tags arriving in separate chunks should still be detected."""
        d, out = make_detector()
        d.start()
        d.feed("Hello<py")
        d.feed("thon>print(1)</py")
        d.feed("thon>Done")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "print(1)" in code_blocks[0]._code

    def test_character_by_character_streaming(self):
        """Feeding one character at a time should work correctly."""
        d, out = make_detector()
        d.start()
        text = "Hi<python>x=1</python>Bye"
        for ch in text:
            d.feed(ch)
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "x=1" in code_blocks[0]._code

    def test_whole_response_at_once(self):
        """Entire response in one feed() call."""
        d, out = make_detector()
        d.start()
        d.feed("Try this:<python>print(42)</python>Done!")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "print(42)" in code_blocks[0]._code


class TestIncompleteBlocks:
    def test_incomplete_opening_tag(self):
        """Incomplete tag at end of stream should be treated as prose."""
        d, out = make_detector()
        d.start()
        d.feed("Hello <pyth")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 0

    def test_unclosed_code_block(self):
        """Code block without closing tag keeps code in block."""
        d, out = make_detector()
        d.start()
        d.feed("<python>print('hello')\n")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "print('hello')" in code_blocks[0]._code

    def test_angle_bracket_not_tag(self):
        """< followed by non-tag text should remain as prose."""
        d, out = make_detector()
        d.start()
        d.feed("x < 5 and y > 3")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 0
        assert "x < 5" in d.all_blocks[0]._text

    def test_backticks_create_code_blocks(self):
        """Markdown code fences should create code blocks like XML tags."""
        d, out = make_detector()
        d.start()
        d.feed("Use ```python\ncode\n```\nfor formatting")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "code" in code_blocks[0]._code
        assert code_blocks[0]._language == "python"

    def test_tags_inside_backtick_spans_ignored(self):
        """Tags inside inline backtick code spans should not trigger detection."""
        d, out = make_detector()
        d.start()
        d.feed("Use `<python>` to write code")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 0
        assert "`<python>`" in d.all_blocks[0]._text

    def test_tags_inside_triple_backtick_spans_ignored(self):
        """Tags inside triple-backtick code spans should not trigger detection."""
        d, out = make_detector()
        d.start()
        d.feed("Example: ```<shell>ls</shell>``` is how you run it")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 0

    def test_tag_after_backtick_span_still_works(self):
        """Real tags after a backtick span should still be detected."""
        d, out = make_detector()
        d.start()
        d.feed("Use `<python>` like this:\n<python>x = 1</python>")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "x = 1" in code_blocks[0]._code

    def test_shell_tag_inside_backtick_ignored(self):
        """<shell> inside backticks should not create a code block."""
        d, out = make_detector()
        d.start()
        d.feed("The `<shell>` tag runs bash commands")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 0

    def test_think_tag_inside_backtick_ignored(self):
        """<think> inside backticks should not create a thinking block."""
        d, out = make_detector()
        d.start()
        d.feed("The `<think>` tag is for reasoning")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 0


class TestWhitespaceStripping:
    def test_newline_after_closing_code_tag_stripped(self):
        """Whitespace after </python> should be stripped from the next prose block."""
        d, _ = make_detector()
        d.start()
        d.feed("<python>x = 1</python>\nNext text")
        d.finish()

        prose_blocks = [
            b
            for b in d.all_blocks
            if isinstance(b, FakeAssistantBlock) and b._text.strip()
        ]
        # The prose after the code block should start with "Next", not "\n"
        after_code = [b for b in prose_blocks if "Next text" in b._text]
        assert len(after_code) == 1
        assert after_code[0]._text.startswith("Next")

    def test_multiple_whitespace_after_closing_tag_stripped(self):
        """Multiple whitespace chars after closing tag should all be stripped."""
        d, _ = make_detector()
        d.start()
        d.feed("<python>code</python>\n\n  After")
        d.finish()

        prose_blocks = [
            b
            for b in d.all_blocks
            if isinstance(b, FakeAssistantBlock) and b._text.strip()
        ]
        after_code = [b for b in prose_blocks if "After" in b._text]
        assert len(after_code) == 1
        assert after_code[0]._text.startswith("After")

    def test_whitespace_after_think_closing_tag_stripped(self):
        """Whitespace after </think> should be stripped."""
        d, _ = make_detector()
        d.start()
        d.feed("<think>thinking</think>\n\nVisible text")
        d.finish()

        prose_blocks = [
            b
            for b in d.all_blocks
            if isinstance(b, FakeAssistantBlock) and b._text.strip()
        ]
        after_think = [b for b in prose_blocks if "Visible text" in b._text]
        assert len(after_think) == 1
        assert after_think[0]._text.startswith("Visible")

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
            if isinstance(b, FakeAssistantBlock) and b._text.strip()
        ]
        assert any("Line one" in b._text for b in prose_blocks)
        assert any("Line two" in b._text for b in prose_blocks)


class TestRealTimeBlockFinalization:
    def test_empty_line_finalizes_block_immediately(self):
        """Block completed by empty line is finalized (not just marked success) mid-stream."""
        d, _ = make_detector()
        d.start()
        # Feed first paragraph plus empty line - this should finalize block 1 mid-stream
        d.feed("Paragraph one.\n\n")
        # At this point, the first block should be finalized before finish() is called
        prose_blocks = [b for b in d.all_blocks if isinstance(b, FakeAssistantBlock)]
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
        # Second block should not be finalized yet (stream not done)
        prose_blocks = [b for b in d.all_blocks if isinstance(b, FakeAssistantBlock)]
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
        # After finish(), all blocks should be finalized exactly once
        prose_blocks = [b for b in d.all_blocks if isinstance(b, FakeAssistantBlock)]
        assert all(b._finished for b in prose_blocks)

    def test_multiple_empty_lines_finalize_each_block(self):
        """Each paragraph split creates a new finalized block in real-time."""
        d, _ = make_detector()
        d.start()
        d.feed("Para one.\n\nPara two.\n\nPara three.")
        prose_blocks = [b for b in d.all_blocks if isinstance(b, FakeAssistantBlock)]
        # First two should be finalized, last one still streaming
        finalized = [b for b in prose_blocks if b._finished]
        assert len(finalized) == 2
        assert "Para one." in finalized[0]._text
        assert "Para two." in finalized[1]._text

    def test_tag_immediately_after_closing_tag(self):
        """A new tag immediately after a closing tag (no whitespace) works."""
        d, _ = make_detector()
        d.start()
        d.feed("<python>first</python><python>second</python>")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 2
        assert "first" in code_blocks[0]._code
        assert "second" in code_blocks[1]._code


class TestEmptyBlocks:
    def test_empty_prose_before_code_is_removed(self):
        """If the response starts immediately with a tag, the empty prose is removed."""
        d, out = make_detector()
        d.start()
        d.feed("<python>x = 1</python>")
        d.finish()

        # Initial empty prose should have been removed from all_blocks
        assert d.first_assistant_block is None  # Was removed since it was empty

    def test_empty_trailing_prose_removed(self):
        """Empty prose block after last code tag should be removed."""
        d, out = make_detector()
        d.start()
        d.feed("<python>x = 1</python>")
        d.finish()

        non_removed = [b for b in d.all_blocks if not b._removed]
        # All remaining assistant blocks should have content
        for b in non_removed:
            if isinstance(b, FakeAssistantBlock):
                assert b._text.strip()


class TestStateTransitions:
    def test_state_starts_as_prose(self):
        d, _ = make_detector()
        assert d._state == _FenceState.PROSE

    def test_python_tag_transitions_to_code(self):
        d, _ = make_detector()
        d.start()
        d.feed("<python>")
        assert d._state == _FenceState.CODE

    def test_shell_tag_transitions_to_code(self):
        d, _ = make_detector()
        d.start()
        d.feed("<shell>")
        assert d._state == _FenceState.CODE

    def test_closing_tag_transitions_to_prose(self):
        d, _ = make_detector()
        d.start()
        d.feed("<python>code</python>")
        assert d._state == _FenceState.PROSE


class TestThinkTagDetection:
    def test_simple_think_tag(self):
        """Basic <think>...</think> detection creates a thinking block."""
        d, out = make_detector()
        d.start()
        d.feed("Before<think>thinking content</think>After")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 1
        assert "thinking content" in thinking_blocks[0]._text

    def test_think_tag_with_newlines(self):
        """Think tags can span multiple lines."""
        d, out = make_detector()
        d.start()
        d.feed("Before\n<think>\nline 1\nline 2\n</think>\nAfter")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 1
        assert "line 1" in thinking_blocks[0]._text
        assert "line 2" in thinking_blocks[0]._text

    def test_multiple_think_blocks(self):
        """Multiple think tags create separate thinking blocks."""
        d, out = make_detector()
        d.start()
        d.feed("<think>first</think>prose<think>second</think>")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 2
        assert "first" in thinking_blocks[0]._text
        assert "second" in thinking_blocks[1]._text

    def test_think_tag_split_across_chunks(self):
        """Think tags split across feed() calls should still be detected."""
        d, out = make_detector()
        d.start()
        d.feed("Text<th")
        d.feed("ink>thinking")
        d.feed("</th")
        d.feed("ink>")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 1
        assert "thinking" in thinking_blocks[0]._text

    def test_unclosed_think_tag(self):
        """Unclosed think tag keeps content in thinking block."""
        d, out = make_detector()
        d.start()
        d.feed("Before<think>thinking without close")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 1
        assert "thinking without close" in thinking_blocks[0]._text

    def test_think_and_code_blocks_together(self):
        """Think tags and code tags can coexist."""
        d, out = make_detector()
        d.start()
        d.feed("<think>planning</think>\n<python>code</python>Done")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(thinking_blocks) == 1
        assert len(code_blocks) == 1
        assert "planning" in thinking_blocks[0]._text
        assert "code" in code_blocks[0]._code

    def test_think_tag_with_prose_before_and_after(self):
        """Think tags create separate blocks from surrounding prose."""
        d, out = make_detector()
        d.start()
        d.feed("Before text<think>thinking</think>After text")
        d.finish()

        prose_blocks = [
            b
            for b in d.all_blocks
            if isinstance(b, FakeAssistantBlock) and b._text.strip()
        ]
        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]

        assert len(thinking_blocks) == 1
        assert any("Before" in b._text for b in prose_blocks)
        assert any("After" in b._text for b in prose_blocks)

    def test_state_transitions_with_think(self):
        """State machine transitions correctly with think tags."""
        d, _ = make_detector()
        d.start()
        assert d._state == _FenceState.PROSE

        d.feed("<think>")
        assert d._state == _FenceState.THINKING

        d.feed("content</think>")
        assert d._state == _FenceState.PROSE

    def test_incomplete_think_tag(self):
        """Incomplete <think at end should be treated as prose."""
        d, out = make_detector()
        d.start()
        d.feed("Hello <thi")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 0
        # Should be in prose block
        assert "<thi" in d.all_blocks[0]._text

    def test_thinking_split_on_empty_lines(self):
        """Empty lines within <think> tags should split into multiple thinking blocks."""
        d, out = make_detector()
        d.start()
        d.feed(
            "<think>\nFirst paragraph\n\nSecond paragraph\n\nThird paragraph\n</think>"
        )
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 3, (
            f"Expected 3 thinking blocks, got {len(thinking_blocks)}"
        )

        # Check content of each thinking block
        assert "First paragraph" in thinking_blocks[0]._text
        assert "Second paragraph" in thinking_blocks[1]._text
        assert "Third paragraph" in thinking_blocks[2]._text

        # Verify all are marked as successful
        assert all(b._success for b in thinking_blocks)


class TestDetailTagDetection:
    def test_simple_detail_tag(self):
        """Basic <detail>...</detail> detection creates a thinking block."""
        d, out = make_detector()
        d.start()
        d.feed("Before<detail>detail content</detail>After")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 1
        assert "detail content" in thinking_blocks[0]._text

    def test_detail_tag_with_newlines(self):
        """Detail tags can span multiple lines."""
        d, out = make_detector()
        d.start()
        d.feed("Before\n<detail>\nline 1\nline 2\n</detail>\nAfter")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 1
        assert "line 1" in thinking_blocks[0]._text
        assert "line 2" in thinking_blocks[0]._text

    def test_detail_tag_split_across_chunks(self):
        """Detail tags split across feed() calls should still be detected."""
        d, out = make_detector()
        d.start()
        d.feed("Text<det")
        d.feed("ail>thinking")
        d.feed("</det")
        d.feed("ail>")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 1
        assert "thinking" in thinking_blocks[0]._text

    def test_detail_does_not_close_with_think(self):
        """</think> should NOT close a <detail> block."""
        d, out = make_detector()
        d.start()
        d.feed("<detail>content</think>still detail</detail>After")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) >= 1
        # The </think> text should be inside the thinking block, not closing it
        combined = "".join(b._text for b in thinking_blocks)
        assert "</think>" in combined
        assert "still detail" in combined

    def test_think_does_not_close_with_detail(self):
        """</detail> should NOT close a <think> block."""
        d, out = make_detector()
        d.start()
        d.feed("<think>content</detail>still thinking</think>After")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) >= 1
        combined = "".join(b._text for b in thinking_blocks)
        assert "</detail>" in combined
        assert "still thinking" in combined

    def test_detail_inside_backtick_ignored(self):
        """<detail> inside backticks should not create a thinking block."""
        d, out = make_detector()
        d.start()
        d.feed("The `<detail>` tag is for details")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 0

    def test_detail_and_code_together(self):
        """<detail> and code tags can coexist."""
        d, out = make_detector()
        d.start()
        d.feed("<detail>reasoning</detail>\n<python>code</python>Done")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(thinking_blocks) == 1
        assert len(code_blocks) == 1
        assert "reasoning" in thinking_blocks[0]._text
        assert "code" in code_blocks[0]._code

    def test_state_transitions_with_detail(self):
        """State machine transitions correctly with detail tags."""
        d, _ = make_detector()
        d.start()
        assert d._state == _FenceState.PROSE

        d.feed("<detail>")
        assert d._state == _FenceState.THINKING

        d.feed("content</detail>")
        assert d._state == _FenceState.PROSE


class TestPauseAfterCodeBlock:
    def make_pausing_detector(self):
        """Create a detector with pause_after_code enabled."""
        output = FakeOutput()
        detector = StreamingFenceDetector(output, pause_after_code=True)
        detector._make_prose_block = lambda activity: FakeAssistantBlock(
            activity=activity
        )
        detector._make_code_block = lambda code, lang: FakeCodeBlock(
            code, language=lang
        )
        detector._make_thinking_block = lambda: FakeThinkingBlock(activity=True)
        return detector, output

    def test_pauses_after_code_block(self):
        """Detector pauses after a code block closes."""
        d, out = self.make_pausing_detector()
        d.start()
        d.feed("Hello<python>x=1</python>trailing junk\nAfter code")
        assert d.is_paused
        # Trailing chars on the same line as closing tag are stripped
        assert d._remainder == "After code"

    def test_pauses_strips_trailing_no_newline(self):
        """Trailing chars with no newline are fully discarded."""
        d, out = self.make_pausing_detector()
        d.start()
        d.feed("Hello<python>x=1</python>junk")
        assert d.is_paused
        assert d._remainder == ""

    def test_last_code_block_set(self):
        """last_code_block is set to the block that triggered the pause."""
        d, out = self.make_pausing_detector()
        d.start()
        d.feed("Hello<python>x=1</python>rest")
        assert d.last_code_block is not None
        assert isinstance(d.last_code_block, FakeCodeBlock)
        assert "x=1" in d.last_code_block._code

    def test_resume_feeds_remainder(self):
        """resume() processes the saved remainder text."""
        d, out = self.make_pausing_detector()
        d.start()
        d.feed("Hello<python>x=1</python>junk\nAfter text")
        assert d.is_paused

        d.resume()
        # After resume, paused should be False (no more code blocks in remainder)
        assert not d.is_paused
        # The "After text" should now be in a prose block (trailing "junk" is stripped)
        prose_blocks = [b for b in d.all_blocks if isinstance(b, FakeAssistantBlock)]
        combined = "".join(b._text for b in prose_blocks)
        assert "After text" in combined
        assert "junk" not in combined

    def test_resume_with_second_code_block(self):
        """resume() pauses again if remainder contains another code block."""
        d, out = self.make_pausing_detector()
        d.start()
        d.feed("Hello<python>first</python>\nMiddle<shell>ls</shell>\nEnd")
        assert d.is_paused
        assert "Middle<shell>ls</shell>\nEnd" == d._remainder

        d.resume()
        # Should pause again on second code block
        assert d.is_paused
        assert "End" == d._remainder

    def test_no_pause_without_flag(self):
        """Default detector (no pause_after_code) does not pause."""
        d, out = make_detector()
        d.start()
        d.feed("Hello<python>x=1</python>After")
        assert not d.is_paused

    def test_pause_with_split_tag(self):
        """Pause works correctly when closing tag is split across chunks."""
        d, out = self.make_pausing_detector()
        d.start()
        d.feed("Hello<python>x=1</py")
        assert not d.is_paused  # Tag not complete yet
        d.feed("thon>\nAfter")
        assert d.is_paused
        assert d._remainder == "After"


class TestLiberalTagParsing:
    """Tests for liberal tag syntax: tool_call aliases, namespace prefixes, whitespace."""

    def test_tool_call_tag_as_shell(self):
        """<tool_call> should be treated as <shell>."""
        d, out = make_detector()
        d.start()
        d.feed("Run:<tool_call>ls -la</tool_call>Done.")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "ls -la" in code_blocks[0]._code
        assert code_blocks[0]._language == "bash"

    def test_namespaced_tool_call(self):
        """<minimax:tool_call> should be treated as <shell>."""
        d, out = make_detector()
        d.start()
        d.feed("Run:<minimax:tool_call>echo hi</minimax:tool_call>Done.")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "echo hi" in code_blocks[0]._code
        assert code_blocks[0]._language == "bash"

    def test_arbitrary_namespace_prefix(self):
        """<anything:shell> should work with any prefix."""
        d, out = make_detector()
        d.start()
        d.feed("Run:<foo:shell>pwd</foo:shell>Done.")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "pwd" in code_blocks[0]._code

    def test_namespaced_python_tag(self):
        """<ns:python> should be treated as <python>."""
        d, out = make_detector()
        d.start()
        d.feed("Code:<ns:python>x = 1</ns:python>Done.")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "x = 1" in code_blocks[0]._code
        assert code_blocks[0]._language == "python"

    def test_whitespace_in_opening_tag(self):
        """< shell > with spaces should be treated as <shell>."""
        d, out = make_detector()
        d.start()
        d.feed("Run:< shell >ls< /shell >Done.")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "ls" in code_blocks[0]._code
        assert code_blocks[0]._language == "bash"

    def test_whitespace_in_python_tag(self):
        """< python > with spaces should work."""
        d, out = make_detector()
        d.start()
        d.feed("Code:< python >x = 1< /python >Done.")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "x = 1" in code_blocks[0]._code

    def test_whitespace_in_think_tag(self):
        """< think > with spaces should work."""
        d, out = make_detector()
        d.start()
        d.feed("Before< think >thinking< /think >After")
        d.finish()

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 1
        assert "thinking" in thinking_blocks[0]._text

    def test_whitespace_and_namespace_combined(self):
        """< minimax : tool_call > with spaces and namespace should work."""
        d, out = make_detector()
        d.start()
        d.feed("Run:< minimax:tool_call >echo hi< /minimax:tool_call >Done.")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "echo hi" in code_blocks[0]._code

    def test_tool_call_split_across_chunks(self):
        """<tool_call> split across feed() calls should work."""
        d, out = make_detector()
        d.start()
        d.feed("Run:<tool_")
        d.feed("call>echo hi</tool_")
        d.feed("call>Done.")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "echo hi" in code_blocks[0]._code

    def test_tool_call_char_by_char(self):
        """<tool_call> fed character by character should work."""
        d, out = make_detector()
        d.start()
        for ch in "Hi<tool_call>x=1</tool_call>Bye":
            d.feed(ch)
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "x=1" in code_blocks[0]._code

    def test_tool_call_state_transitions(self):
        """<tool_call> should transition to CODE state like <shell>."""
        d, _ = make_detector()
        d.start()
        d.feed("<tool_call>")
        assert d._state == _FenceState.CODE

        d.feed("code</tool_call>")
        assert d._state == _FenceState.PROSE

    def test_mixed_open_close_tags(self):
        """Opening with <tool_call> and closing with </shell> should work."""
        d, out = make_detector()
        d.start()
        d.feed("Run:<tool_call>echo hi</shell>Done.")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "echo hi" in code_blocks[0]._code

    def test_second_angle_bracket_resets(self):
        """A second < should flush the first and start a new tag."""
        d, out = make_detector()
        d.start()
        d.feed("x < 5 <python>code</python>Done")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        # The "x < 5 " should appear as prose
        prose_blocks = [
            b
            for b in d.all_blocks
            if isinstance(b, FakeAssistantBlock) and b._text.strip()
        ]
        assert any("x < 5" in b._text for b in prose_blocks)

    def test_newline_in_tag_aborts(self):
        """A newline inside a potential tag should abort tag detection."""
        d, out = make_detector()
        d.start()
        d.feed("x <\npython>code")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 0

    def test_pause_with_tool_call(self):
        """Pause after code block works with <tool_call> tags."""
        output = FakeOutput()
        d = StreamingFenceDetector(output, pause_after_code=True)
        d._make_prose_block = lambda activity: FakeAssistantBlock(activity=activity)
        d._make_code_block = lambda code, lang: FakeCodeBlock(code, language=lang)
        d._make_thinking_block = lambda: FakeThinkingBlock(activity=True)
        d.start()
        d.feed("Hello<tool_call>ls</tool_call>\nAfter")
        assert d.is_paused
        assert d._remainder == "After"

    def test_unrecognized_tag_is_prose(self):
        """<unknown_tag> should be treated as prose."""
        d, out = make_detector()
        d.start()
        d.feed("Hello <unknown>world</unknown> end")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 0
        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 0


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
            if isinstance(b, FakeAssistantBlock) and b._text.strip()
        ]
        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert any("Before" in b._text for b in prose_blocks)
        assert any("After" in b._text for b in prose_blocks)

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

    def test_xml_tags_and_fences_together(self):
        """XML tags and markdown fences can coexist."""
        d, out = make_detector()
        d.start()
        d.feed("<python>x = 1</python>\nThen:\n```bash\nls\n```")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 2
        assert "x = 1" in code_blocks[0]._code
        assert "ls" in code_blocks[1]._code

    def test_backticks_inside_xml_tags_ignored(self):
        """``` inside <python> tags should be treated as code content."""
        d, out = make_detector()
        d.start()
        d.feed("<python>s = '''multi\nline\nstring'''\n</python>")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "'''" in code_blocks[0]._code

    def test_pause_after_fence(self):
        """Pause after code block works with markdown fences."""
        output = FakeOutput()
        d = StreamingFenceDetector(output, pause_after_code=True)
        d._make_prose_block = lambda activity: FakeAssistantBlock(activity=activity)
        d._make_code_block = lambda code, lang: FakeCodeBlock(code, language=lang)
        d._make_thinking_block = lambda: FakeThinkingBlock(activity=True)
        d.start()
        d.feed("Hello\n```python\nx=1\n```\nAfter")
        assert d.is_paused
        assert "After" in d._remainder
