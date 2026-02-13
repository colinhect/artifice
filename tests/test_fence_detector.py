"""Tests for StreamingFenceDetector - the code fence parser.

Uses lightweight fakes instead of real Textual widgets to test
the parsing state machine in isolation. We patch the isinstance
targets in the terminal module so the detector recognizes our fakes.
"""

from unittest.mock import patch
import pytest
from artifice.terminal import StreamingFenceDetector, _FenceState, _LANG_ALIASES


# --- Fakes to avoid Textual widget dependencies ---

class FakeBlock:
    """Base fake block."""
    def __init__(self):
        self._text = ""
        self._full = ""
        self._finished = False
        self._success = False
        self._removed = False

    def remove(self):
        self._removed = True


class FakeAgentBlock(FakeBlock):
    """Fake AgentOutputBlock that just accumulates text."""
    def __init__(self, activity=False):
        super().__init__()

    def append(self, text):
        self._text += text
        self._full += text

    def flush(self):
        pass

    def mark_success(self):
        self._success = True

    def mark_failed(self):
        pass

    def finalize_streaming(self):
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

    def scroll_end(self, animate=False):
        pass

    def next_command_number(self):
        self._command_counter += 1
        return self._command_counter


@pytest.fixture(autouse=True)
def _patch_block_types():
    """Patch isinstance targets so the detector recognizes our fakes."""
    with patch("artifice.terminal.AgentOutputBlock", FakeAgentBlock), \
         patch("artifice.terminal.CodeInputBlock", FakeCodeBlock):
        yield


def make_detector(save_callback=None):
    """Create a detector with fake dependencies."""
    output = FakeOutput()
    detector = StreamingFenceDetector(output, auto_scroll=True, save_callback=save_callback)
    detector._make_prose_block = lambda activity: FakeAgentBlock(activity=activity)
    detector._make_code_block = lambda code, lang: FakeCodeBlock(code, language=lang)
    return detector, output


class TestBasicFenceDetection:
    def test_prose_only(self):
        """Plain text without fences produces a single prose block."""
        d, out = make_detector()
        d.start()
        d.feed("Hello world, no code here.")
        d.finish()
        assert len(d.all_blocks) == 1
        assert isinstance(d.all_blocks[0], FakeAgentBlock)
        assert "Hello world" in d.all_blocks[0]._text

    def test_single_code_block(self):
        """Standard code fence creates prose + code + prose blocks."""
        d, out = make_detector()
        d.start()
        d.feed("Here is code:\n```python\nprint('hi')\n```\nDone.")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "print('hi')" in code_blocks[0]._code
        assert code_blocks[0]._language == "python"

    def test_multiple_code_blocks(self):
        d, out = make_detector()
        d.start()
        d.feed("First:\n```python\nx = 1\n```\nSecond:\n```bash\nls -la\n```\nEnd.")
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
        d.feed("Before\n```python\ncode\n```\nAfter")
        d.finish()

        prose_blocks = [b for b in d.all_blocks if isinstance(b, FakeAgentBlock) and b._text.strip()]
        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert any("Before" in b._text for b in prose_blocks)
        assert any("After" in b._text for b in prose_blocks)


class TestLanguageAliases:
    def test_py_becomes_python(self):
        d, out = make_detector()
        d.start()
        d.feed("```py\ncode\n```")
        d.finish()
        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert code_blocks[0]._language == "python"

    def test_sh_becomes_bash(self):
        d, out = make_detector()
        d.start()
        d.feed("```sh\necho hi\n```")
        d.finish()
        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert code_blocks[0]._language == "bash"

    def test_shell_becomes_bash(self):
        d, out = make_detector()
        d.start()
        d.feed("```shell\necho hi\n```")
        d.finish()
        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert code_blocks[0]._language == "bash"

    def test_no_language_defaults_to_python(self):
        d, out = make_detector()
        d.start()
        d.feed("```\ncode\n```")
        d.finish()
        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert code_blocks[0]._language == "python"

    def test_unknown_language_preserved(self):
        d, out = make_detector()
        d.start()
        d.feed("```rust\nfn main() {}\n```")
        d.finish()
        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert code_blocks[0]._language == "rust"


class TestStreamingChunks:
    def test_fence_split_across_chunks(self):
        """Backticks arriving in separate chunks should still detect fence."""
        d, out = make_detector()
        d.start()
        d.feed("Hello\n`")
        d.feed("`")
        d.feed("`python\nprint(1)\n`")
        d.feed("``")
        d.feed("\nDone")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "print(1)" in code_blocks[0]._code

    def test_character_by_character_streaming(self):
        """Feeding one character at a time should work correctly."""
        d, out = make_detector()
        d.start()
        text = "Hi\n```python\nx=1\n```\nBye"
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
        d.feed("Try this:\n```python\nprint(42)\n```\nDone!")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "print(42)" in code_blocks[0]._code


class TestIncompleteFences:
    def test_incomplete_opening_fence(self):
        """Incomplete fence at end of stream should be treated as prose."""
        d, out = make_detector()
        d.start()
        d.feed("Hello ```python")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 0

    def test_unclosed_code_block(self):
        """Code block without closing fence keeps code in block."""
        d, out = make_detector()
        d.start()
        d.feed("```python\nprint('hello')\n")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert "print('hello')" in code_blocks[0]._code

    def test_trailing_backticks_not_fence(self):
        """1-2 backticks in prose should remain as text, not start a fence."""
        d, out = make_detector()
        d.start()
        d.feed("Use `inline code` here")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 0
        assert "`inline code`" in d.all_blocks[0]._text

    def test_two_backticks_not_fence(self):
        d, out = make_detector()
        d.start()
        d.feed("``not a fence``")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 0


class TestStringAwareness:
    def test_backticks_in_double_quoted_string(self):
        """Backticks inside double-quoted string literals should not close the fence."""
        d, out = make_detector()
        d.start()
        d.feed('```python\nx = "```"\nprint(x)\n```\nDone')
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert 'print(x)' in code_blocks[0]._code

    def test_backticks_in_single_quoted_string(self):
        d, out = make_detector()
        d.start()
        d.feed("```python\nx = '```'\nprint(x)\n```\nDone")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert 'print(x)' in code_blocks[0]._code


class TestEmptyBlocks:
    def test_empty_prose_before_code_is_removed(self):
        """If the response starts immediately with a fence, the empty prose is removed."""
        d, out = make_detector()
        d.start()
        d.feed("```python\nx = 1\n```")
        d.finish()

        # Initial empty prose should have been removed from all_blocks
        assert d.first_agent_block is None  # Was removed since it was empty

    def test_empty_trailing_prose_removed(self):
        """Empty prose block after last code fence should be removed."""
        d, out = make_detector()
        d.start()
        d.feed("```python\nx = 1\n```")
        d.finish()

        non_removed = [b for b in d.all_blocks if not b._removed]
        # All remaining agent blocks should have content
        for b in non_removed:
            if isinstance(b, FakeAgentBlock):
                assert b._text.strip()


class TestStateTransitions:
    def test_state_starts_as_prose(self):
        d, _ = make_detector()
        assert d._state == _FenceState.PROSE

    def test_opening_fence_transitions_to_lang_line(self):
        d, _ = make_detector()
        d.start()
        d.feed("```")
        assert d._state == _FenceState.LANG_LINE

    def test_newline_after_lang_transitions_to_code(self):
        d, _ = make_detector()
        d.start()
        d.feed("```python\n")
        assert d._state == _FenceState.CODE

    def test_closing_fence_transitions_to_prose(self):
        d, _ = make_detector()
        d.start()
        d.feed("```python\ncode\n```")
        assert d._state == _FenceState.PROSE


class TestSaveCallback:
    def test_save_callback_called_on_finish(self):
        saved = []
        d, _ = make_detector(save_callback=lambda b: saved.append(b))
        d.start()
        d.feed("Hi\n```python\nx=1\n```\nBye")
        d.finish()
        assert len(saved) > 0

    def test_save_callback_gets_all_block_types(self):
        saved = []
        d, _ = make_detector(save_callback=lambda b: saved.append(b))
        d.start()
        d.feed("Prose\n```python\ncode\n```\nMore prose")
        d.finish()
        types = {type(b) for b in saved}
        assert FakeAgentBlock in types
        assert FakeCodeBlock in types
