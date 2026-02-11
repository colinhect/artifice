"""Tests for StreamingFenceDetector."""

from unittest.mock import Mock, MagicMock


class FakeBlock:
    """Mock block for testing."""

    def __init__(self, block_type, **kwargs):
        self.block_type = block_type
        self._code = kwargs.get("code", "")
        self._full = ""
        self.language = kwargs.get("language", "python")
        self.finished = False

    def update_code(self, code):
        self._code = code

    def get_code(self):
        return self._code

    def append(self, text):
        self._full += text

    def mark_success(self):
        pass

    def finish_streaming(self):
        self.finished = True

    def finalize_streaming(self):
        pass

    def remove(self):
        pass


class FakeMockOutput:
    """Mock TerminalOutput for testing."""

    def __init__(self):
        self._blocks = []

    def append_block(self, block):
        self._blocks.append(block)

    def scroll_end(self, animate=False):
        pass


def create_test_detector():
    """Create a StreamingFenceDetector with mock block factories."""
    from artifice.terminal import StreamingFenceDetector
    
    output = FakeMockOutput()
    detector = StreamingFenceDetector(output, auto_scroll=lambda: None)
    
    # Override factory methods to create FakeBlocks instead of real Textual widgets
    detector._make_prose_block = lambda activity: FakeBlock("prose")
    detector._make_code_block = lambda code, lang: FakeBlock("code", code=code, language=lang)
    
    return detector, output


def test_code_fence_in_string_literal():
    """Test that code fences inside string literals are ignored."""
    detector, output = create_test_detector()
    detector.start()

    # Feed a code block with a fence inside a string
    text = '''```python
markdown_text = """
Some text with a code fence:
```python
print("hello")
```
More text
"""
```'''

    detector.feed(text, auto_scroll=False)
    detector.finish()

    # Should create 2 blocks: initial prose (empty) and one code block
    # The fence inside the triple-quoted string should be ignored
    blocks = [b for b in detector.all_blocks if not (b.block_type == "prose" and not b._full.strip())]
    
    assert len(blocks) == 1, f"Expected 1 code block, got {len(blocks)} blocks"
    assert blocks[0].block_type == "code", "Expected a code block"
    
    # The code should contain the entire content including the nested fence
    code = blocks[0].get_code()
    assert 'markdown_text = """' in code
    assert '```python' in code  # The nested fence should be in the code
    assert 'print("hello")' in code


def test_code_fence_in_single_quote_string():
    """Test that code fences in single-quoted strings are ignored."""
    detector, output = create_test_detector()
    detector.start()

    # Feed a code block with a fence inside a single-quoted string
    text = """```python
text = '```'
print(text)
```"""

    detector.feed(text, auto_scroll=False)
    detector.finish()

    # Should create one code block with the fence inside the string
    blocks = [b for b in detector.all_blocks if not (b.block_type == "prose" and not b._full.strip())]
    
    assert len(blocks) == 1, f"Expected 1 code block, got {len(blocks)} blocks"
    assert blocks[0].block_type == "code"
    
    code = blocks[0].get_code()
    assert "text = '```'" in code
    assert 'print(text)' in code


def test_code_fence_in_double_quote_string():
    """Test that code fences in double-quoted strings are ignored."""
    detector, output = create_test_detector()
    detector.start()

    # Feed a code block with a fence inside a double-quoted string
    text = '''```python
text = "```"
print(text)
```'''

    detector.feed(text, auto_scroll=False)
    detector.finish()

    # Should create one code block with the fence inside the string
    blocks = [b for b in detector.all_blocks if not (b.block_type == "prose" and not b._full.strip())]
    
    assert len(blocks) == 1, f"Expected 1 code block, got {len(blocks)} blocks"
    assert blocks[0].block_type == "code"
    
    code = blocks[0].get_code()
    assert 'text = "```"' in code
    assert 'print(text)' in code


def test_escaped_quotes_in_string():
    """Test that escaped quotes are handled correctly."""
    detector, output = create_test_detector()
    detector.start()

    # Feed a code block with escaped quotes
    text = r'''```python
text = "He said \"```\" to me"
print(text)
```'''

    detector.feed(text, auto_scroll=False)
    detector.finish()

    # Should create one code block
    blocks = [b for b in detector.all_blocks if not (b.block_type == "prose" and not b._full.strip())]
    
    assert len(blocks) == 1
    assert blocks[0].block_type == "code"
    
    code = blocks[0].get_code()
    assert r'He said \"```\" to me' in code
    assert 'print(text)' in code


def test_real_fence_after_string_with_fence():
    """Test that a real fence is detected after a string containing a fence."""
    detector, output = create_test_detector()
    detector.start()

    # Feed a code block with a fence in a string, then a real closing fence
    text = '''```python
text = "```"
print(text)
```
More prose text'''

    detector.feed(text, auto_scroll=False)
    detector.finish()

    # Should create 2 blocks: code block and prose block
    blocks = [b for b in detector.all_blocks if not (b.block_type == "prose" and not b._full.strip())]
    
    assert len(blocks) == 2, f"Expected 2 blocks, got {len(blocks)}"
    assert blocks[0].block_type == "code", "First block should be code"
    assert blocks[1].block_type == "prose", "Second block should be prose"
    
    code = blocks[0].get_code()
    assert 'text = "```"' in code
    assert 'print(text)' in code
    
    prose = blocks[1]._full
    assert "More prose text" in prose


def test_multiple_blocks_with_nested_fences():
    """Test multiple code blocks where some contain nested fences."""
    detector, output = create_test_detector()
    detector.start()

    # Feed multiple code blocks
    text = '''Here is some code:
```python
x = "```"
```
And more code:
```python
y = 2
```'''

    detector.feed(text, auto_scroll=False)
    detector.finish()

    # Should create: initial prose, code block 1, prose, code block 2
    blocks = [b for b in detector.all_blocks if not (b.block_type == "prose" and not b._full.strip())]
    
    # We should have at least 2 code blocks
    code_blocks = [b for b in blocks if b.block_type == "code"]
    assert len(code_blocks) == 2, f"Expected 2 code blocks, got {len(code_blocks)}"
    
    # First code block should contain the nested fence
    code1 = code_blocks[0].get_code()
    assert 'x = "```"' in code1
    
    # Second code block should be normal
    code2 = code_blocks[1].get_code()
    assert 'y = 2' in code2


def test_normal_fence_detection_still_works():
    """Test that normal fence detection (without strings) still works correctly."""
    detector, output = create_test_detector()
    detector.start()

    # Feed simple code blocks without string complications
    text = '''Here is code:
```python
print("hello")
```
Done!'''

    detector.feed(text, auto_scroll=False)
    detector.finish()

    # Should create: prose, code, prose
    blocks = detector.all_blocks
    code_blocks = [b for b in blocks if b.block_type == "code"]
    
    assert len(code_blocks) == 1
    code = code_blocks[0].get_code()
    assert 'print("hello")' in code
