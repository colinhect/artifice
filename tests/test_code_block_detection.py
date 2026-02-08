"""Tests for parse_response_segments."""

from artifice.terminal import parse_response_segments


class TestParseResponseSegments:
    def test_trailing_python_block(self):
        text = "Here's some code:\n\n```python\nprint('hello')\n```"
        segments = parse_response_segments(text)
        assert segments == [
            ('text', "Here's some code:"),
            ('code', 'python', "print('hello')\n"),
        ]

    def test_trailing_bash_block(self):
        text = "Run this:\n\n```bash\nls -la\n```"
        segments = parse_response_segments(text)
        assert segments == [
            ('text', 'Run this:'),
            ('code', 'bash', "ls -la\n"),
        ]

    def test_no_code_block(self):
        text = "Just a plain text response with no code."
        segments = parse_response_segments(text)
        assert segments == [('text', text)]

    def test_code_block_in_middle(self):
        text = "Here's code:\n\n```python\nprint('hello')\n```\n\nAnd some text after."
        segments = parse_response_segments(text)
        assert segments == [
            ('text', "Here's code:"),
            ('code', 'python', "print('hello')\n"),
            ('text', 'And some text after.'),
        ]

    def test_non_python_bash_block_ignored(self):
        text = "Here's some JSON:\n\n```json\n{\"key\": \"value\"}\n```"
        segments = parse_response_segments(text)
        assert segments == [('text', text)]

    def test_multiline_python_code(self):
        text = "Here:\n\n```python\ndef foo():\n    return 42\n\nprint(foo())\n```"
        segments = parse_response_segments(text)
        assert segments == [
            ('text', 'Here:'),
            ('code', 'python', "def foo():\n    return 42\n\nprint(foo())\n"),
        ]

    def test_multiple_code_blocks(self):
        text = "First:\n\n```python\nx = 1\n```\n\nThen:\n\n```bash\necho hi\n```"
        segments = parse_response_segments(text)
        assert segments == [
            ('text', 'First:'),
            ('code', 'python', "x = 1\n"),
            ('text', 'Then:'),
            ('code', 'bash', "echo hi\n"),
        ]

    def test_code_block_only(self):
        text = "```python\nprint('hello')\n```"
        segments = parse_response_segments(text)
        assert segments == [
            ('code', 'python', "print('hello')\n"),
        ]

    def test_empty_code_block(self):
        text = "Empty:\n\n```python\n```"
        segments = parse_response_segments(text)
        assert segments == [
            ('text', 'Empty:'),
            ('code', 'python', ''),
        ]

    def test_text_after_code_block(self):
        text = "```python\nx = 1\n```\n\nThis came after the code."
        segments = parse_response_segments(text)
        assert segments == [
            ('code', 'python', "x = 1\n"),
            ('text', 'This came after the code.'),
        ]
