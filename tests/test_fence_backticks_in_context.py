"""Tests for backtick fence detection in various contexts.

Ensures that triple backticks don't trigger false positives when they appear:
- Inside <thinking> blocks
- In strings within code blocks
- In comments within code blocks
"""

import pytest
from unittest.mock import patch
from tests.test_fence_detector import make_detector, FakeCodeBlock, FakeThinkingBlock, FakeAssistantBlock


@pytest.fixture(autouse=True)
def _patch_block_types():
    """Patch isinstance targets so the detector recognizes our fakes."""
    with (
        patch("artifice.fence_detector.AssistantOutputBlock", FakeAssistantBlock),
        patch("artifice.fence_detector.CodeInputBlock", FakeCodeBlock),
        patch("artifice.fence_detector.ThinkingOutputBlock", FakeThinkingBlock),
    ):
        yield


class TestBackticksInThinking:
    """Test that backticks in thinking blocks don't create code blocks."""

    def test_triple_backticks_in_thinking(self):
        """Triple backticks inside <think> should not create code blocks."""
        d, out = make_detector()
        d.start()
        d.feed("<think>The user can use ```python to format code</think>After")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 0, "Backticks in thinking should not create code blocks"

        thinking_blocks = [b for b in d.all_blocks if isinstance(b, FakeThinkingBlock)]
        assert len(thinking_blocks) == 1
        assert "```python" in thinking_blocks[0]._text

    def test_multiline_thinking_with_fences(self):
        """Thinking block with code examples using fences should not split."""
        d, out = make_detector()
        d.start()
        d.feed("<think>I should tell them to use:\n```python\ncode\n```\nin their response</think>Done")
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 0, "Fences in thinking should not create code blocks"


class TestBackticksInCodeBlocks:
    """Test that backticks in strings/comments within code don't close fences."""

    def test_triple_backticks_in_string(self):
        """Triple backticks in a string literal should not close the fence."""
        d, out = make_detector()
        d.start()
        d.feed('Here is code:\n```python\ntext = "Use ```python for code blocks"\nprint(text)\n```\nDone')
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1, "Should create exactly one code block"
        # The entire code including the string should be in one block
        assert 'text = "Use ```python' in code_blocks[0]._code
        assert 'print(text)' in code_blocks[0]._code

    def test_triple_backticks_in_comment(self):
        """Triple backticks in a comment should not close the fence."""
        d, out = make_detector()
        d.start()
        d.feed('```python\n# Use ```python to start a code block\nprint("hello")\n```\nDone')
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert '# Use ```python' in code_blocks[0]._code
        assert 'print("hello")' in code_blocks[0]._code

    def test_triple_backticks_in_multiline_string(self):
        """Triple backticks in a multiline string should not close the fence."""
        d, out = make_detector()
        d.start()
        d.feed('```python\nhelp_text = """\nUse ```python\nfor code\n"""\n```\nDone')
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert '```python' in code_blocks[0]._code
        assert 'help_text' in code_blocks[0]._code

    def test_xml_code_block_with_backticks(self):
        """Triple backticks in XML-style code tags should be treated as code content."""
        d, out = make_detector()
        d.start()
        d.feed('<python>text = "```python"\nprint(text)</python>After')
        d.finish()

        code_blocks = [b for b in d.all_blocks if isinstance(b, FakeCodeBlock)]
        assert len(code_blocks) == 1
        assert '```python' in code_blocks[0]._code
        assert 'print(text)' in code_blocks[0]._code
