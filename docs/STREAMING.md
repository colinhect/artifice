# Streaming Architecture

**Version:** 0.1.0
**Last Updated:** 2026-02-12

## Overview

Artifice's streaming architecture enables real-time processing of AI agent responses, parsing code fences as they arrive and creating UI blocks incrementally. This document details the streaming pipeline, fence detection algorithm, and critical threading constraints.

---

## Why Streaming?

### User Experience Benefits
1. **Immediate Feedback**: User sees response as it's generated
2. **Progress Indication**: Loading indicators show activity
3. **Faster Perceived Latency**: UX feels responsive even with slow APIs
4. **Interruption Support**: User can cancel mid-stream

### Technical Benefits
1. **Memory Efficiency**: Process data incrementally vs buffering
2. **Parallelism**: UI updates while API streams
3. **Testability**: Simulate various streaming scenarios

### Challenges Addressed
1. **Threading Complexity**: API callbacks run in background threads
2. **Partial Data**: Parse incomplete fence markers correctly
3. **Rendering Performance**: Avoid re-rendering on every character
4. **Widget Creation Constraints**: Textual widgets can't mount in threads

---

## Streaming Pipeline

### High-Level Flow

```
╔══════════════════════════════════════════════════════════════╗
║  Background Thread (API Call)                                ║
╠══════════════════════════════════════════════════════════════╣
║  1. Agent.send_prompt()                                      ║
║  2. Stream text chunks from API                              ║
║  3. Call on_chunk() for each chunk                           ║
║  4. Call on_thinking_chunk() for thinking (if supported)     ║
╚═══════════════════════╦══════════════════════════════════════╝
                        │
                        ▼ (Post messages via call_soon_threadsafe)
╔══════════════════════════════════════════════════════════════╗
║  Main Event Loop (Textual)                                   ║
╠══════════════════════════════════════════════════════════════╣
║  5. Receive StreamChunk / StreamThinkingChunk messages       ║
║  6. Buffer chunks                                            ║
║  7. Schedule batch processing (once per event loop tick)     ║
║  8. Process buffered chunks:                                 ║
║     - Feed to StreamingFenceDetector                         ║
║     - Detector updates existing blocks                       ║
║     - Detector creates new blocks as needed                  ║
║  9. Finalize blocks when streaming complete                  ║
╚══════════════════════════════════════════════════════════════╝
```

### Detailed Steps

#### 1. Initiate Streaming

```python
async def _stream_agent_response(agent, prompt):
    # Create detector (deferred start)
    self._current_detector = StreamingFenceDetector(
        self.output,
        self.output.auto_scroll,
        save_callback=self._save_block_to_session
    )
    self._detector_started = False

    # Create loading block (shows activity before first chunk)
    self._loading_block = AgentOutputBlock(activity=True)
    self.output.append_block(self._loading_block)

    # Define callbacks for background thread
    def on_chunk(text):
        self.post_message(StreamChunk(text))

    def on_thinking_chunk(text):
        self.post_message(StreamThinkingChunk(text))

    # Stream from agent (runs in thread pool)
    response = await agent.send_prompt(prompt, on_chunk, on_thinking_chunk)
```

**Why deferred start?** Thinking blocks must appear before text blocks. We start the detector when the first **text** chunk arrives, after any thinking blocks are created.

#### 2. Background Thread Callbacks

```python
# Inside thread pool executor
with client.messages.stream(...) as stream:
    for event in stream:
        if event.type == "thinking_delta":
            loop.call_soon_threadsafe(on_thinking_chunk, event.delta.thinking)
        elif event.type == "text_delta":
            loop.call_soon_threadsafe(on_chunk, event.delta.text)
```

**Thread Safety:** `call_soon_threadsafe()` schedules callback on main event loop.

#### 3. Message Handling (Main Thread)

```python
def on_stream_chunk(self, event: StreamChunk):
    if not self._detector_started:
        # First text chunk: remove loading block, start detector
        self._loading_block.remove()
        self._detector_started = True
        self._current_detector.start()

    # Buffer chunk
    self._chunk_buffer += event.text

    # Schedule batch processing
    if not self._chunk_processing_scheduled:
        self._chunk_processing_scheduled = True
        self.call_later(self._process_chunk_buffer)
```

**Batching:** Multiple chunks arriving in quick succession are batched into a single `_process_chunk_buffer()` call.

#### 4. Batch Processing

```python
def _process_chunk_buffer(self):
    if self._current_detector and self._chunk_buffer:
        text = self._chunk_buffer
        self._chunk_buffer = ""

        with self.app.batch_update():
            self._current_detector.feed(text, auto_scroll=False)

        # Scroll after layout refresh (Markdown height recalculated)
        self.call_after_refresh(lambda: self.output.scroll_end(animate=False))

    self._chunk_processing_scheduled = False
```

**Performance Optimizations:**
- `batch_update()`: Consolidates multiple DOM changes into single render
- `call_after_refresh()`: Ensures scroll happens after layout recalculation

#### 5. Finalization

```python
# After streaming completes
if self._chunk_buffer:
    self._process_chunk_buffer()  # Flush remaining

self._current_detector.finish()
```

---

## Fence Detection Algorithm

### State Machine

The detector is a 3-state finite state machine:

```
┌─────────┐                          ┌──────────────┐
│  PROSE  │ ──────(```)─────────────>│  LANG_LINE   │
└────┬────┘                          └──────┬───────┘
     │                                      │
     │                                      │(newline)
     │                                      │
     │                                      ▼
     │                               ┌──────────────┐
     └──────────(```)────────────────│     CODE     │
                                     └──────────────┘
```

**States:**
1. **PROSE**: Processing prose text (Markdown, plain text)
2. **LANG_LINE**: Processing language identifier (e.g., `python`, `bash`)
3. **CODE**: Processing code content

### Character-by-Character Processing

```python
def feed(self, text: str):
    for ch in text:
        if self._state == _FenceState.PROSE:
            self._feed_prose(ch)
        elif self._state == _FenceState.LANG_LINE:
            self._feed_lang_line(ch)
        elif self._state == _FenceState.CODE:
            self._feed_code(ch)

    # Update current block with accumulated chunk
    if self._chunk_buffer and self._current_block:
        self._update_current_block_with_chunk()
```

### PROSE State

```python
def _feed_prose(self, ch):
    if ch == '`':
        self._backtick_count += 1
        if self._backtick_count == 3:
            # Opening fence detected
            self._flush_pending_to_chunk()
            self._state = _FenceState.LANG_LINE
            self._backtick_count = 0
            self._lang_buffer = ""
    else:
        # Not a fence, flush backticks and continue
        self._flush_backticks_to_pending()
        self._pending_buffer += ch
```

**Backtick Accumulation:** Count backticks to detect `\`\`\``. If non-backtick character appears, flush accumulated backticks as prose text.

### LANG_LINE State

```python
def _feed_lang_line(self, ch):
    if ch == '\n':
        # Language line complete
        lang = self._lang_buffer.strip() or "python"
        lang = _LANG_ALIASES.get(lang, lang)  # Normalize aliases

        # Finalize current prose block
        self._flush_and_update_chunk()
        if current_is_empty:
            self._remove_block(self._current_block)
        else:
            self._current_block.mark_success()

        # Create new code block
        self._current_block = self._make_code_block("", lang)
        self.output.append_block(self._current_block)
        self.all_blocks.append(self._current_block)

        self._state = _FenceState.CODE
    else:
        self._lang_buffer += ch
```

**Block Transition:** Create `CodeInputBlock` and transition to CODE state.

**Empty Block Removal:** If prose block is empty, remove it (no point showing empty blocks).

### CODE State

```python
def _feed_code(self, ch):
    # Track string literals to avoid false fence detection
    self._string_tracker.track(ch)

    if not self._string_tracker.in_string and ch == '`':
        self._backtick_count += 1
        if self._backtick_count == 3:
            # Closing fence detected
            self._flush_pending_to_chunk()
            self._flush_and_update_chunk()

            # Finalize code block
            if isinstance(self._current_block, CodeInputBlock):
                self._current_block.finish_streaming()

            # Create new prose block
            self._current_block = self._make_prose_block(activity=True)
            self.output.append_block(self._current_block)
            self.all_blocks.append(self._current_block)

            self._state = _FenceState.PROSE
            self._backtick_count = 0
            self._string_tracker.reset()
    else:
        self._flush_backticks_to_pending()
        self._pending_buffer += ch
```

**String Tracking:** Critical to avoid false positives:
```python
code = "```python"  # Not a closing fence!
```

---

## String Tracking

### Why Needed

Code can contain backticks inside string literals:

```python
# Agent response:
code = '''
```python
print("hello")
```
'''
```

Without string tracking, the inner `` ``` `` would be interpreted as a fence, breaking the parse.

### StringTracker Implementation

```python
class StringTracker:
    def __init__(self):
        self._in_string = None      # None, "'", '"', "'''", or '"""'
        self._escape_next = False
        self._quote_buffer = ""

    def track(self, ch):
        # Handle escape sequences
        if self._escape_next:
            self._escape_next = False
            return

        if ch == '\\':
            self._escape_next = True
            return

        # Detect quote boundaries
        if ch in ('"', "'"):
            # Build quote buffer for triple-quote detection
            if self._quote_buffer and self._quote_buffer[0] == ch:
                self._quote_buffer += ch
            else:
                self._quote_buffer = ch

            # Check if opening/closing string
            if self._in_string and self._in_string == self._quote_buffer:
                self._in_string = None  # Closing
            elif not self._in_string and len(self._quote_buffer) in (1, 3):
                self._in_string = self._quote_buffer  # Opening
        else:
            # Non-quote: resolve pending quotes
            if self._quote_buffer and not self._in_string:
                if len(self._quote_buffer) <= 2:
                    self._in_string = self._quote_buffer[0]
            self._quote_buffer = ""
```

**Supported String Types:**
- Single quotes: `'...'`
- Double quotes: `"..."`
- Triple single quotes: `'''...'''`
- Triple double quotes: `"""..."""`

**Edge Cases:**
- Escaped quotes: `"He said \"hello\""`
- Mixed quotes: `"It's working"`
- Unclosed strings: Newline ends single-line strings

---

## Block Updates

### Buffering Strategy

Three-level buffering for performance:

1. **Pending Buffer**: Accumulates characters for current state
2. **Chunk Buffer**: Accumulated text for current chunk (flushed to block)
3. **Block Buffer**: Text accumulated in block (flushed to widget)

```python
_pending_buffer = ""  # Characters for current processing
_chunk_buffer = ""    # Text to add to block this chunk
_full = ""            # Block's accumulated content (in block itself)
```

### Update Flow

```python
# 1. Accumulate in pending
self._pending_buffer += ch

# 2. Flush pending to chunk buffer
self._flush_pending_to_chunk()

# 3. Update block with chunk buffer
self._update_current_block_with_chunk()

# 4. Block flushes to widget (throttled)
block.flush()
```

### Block-Specific Updates

#### CodeInputBlock
```python
def update_code(self, code):
    self._original_code = code
    self._code.update(highlight.highlight(code, language=self._language))
```

**Always highlighted:** Syntax highlighting applied during streaming (see critical lesson in MEMORY.md).

#### AgentOutputBlock
```python
def append(self, text):
    self._full += text
    self._dirty = True

def flush(self):
    if not self._dirty:
        return

    # Throttle during streaming
    if self._streaming and elapsed < self._FLUSH_INTERVAL:
        self._schedule_deferred_flush()
        return

    self._markdown.update(self._full.strip())
    self._dirty = False
```

**Throttling:** Markdown re-renders limited to 100ms intervals during streaming.

---

## Threading Constraints

### Critical Rule: No Widget Mount in Callbacks

**Problem:**
```python
def on_chunk(text):
    # ❌ WRONG: This causes NoActiveAppError
    widget.mount(new_block)
```

**Why?**
- Callbacks run in background thread
- Textual's `active_app` ContextVar not set in thread context
- `mount()` triggers `_compose()` which requires `active_app`

**Solution:**
```python
def on_chunk(text):
    # ✅ CORRECT: Post message to main loop
    loop.call_soon_threadsafe(lambda: self.post_message(StreamChunk(text)))

# In main loop message handler:
def on_stream_chunk(self, event):
    # Safe to mount here (on main event loop)
    self.mount(new_block)
```

### Message-Based Communication

```python
class StreamChunk(Message):
    def __init__(self, text: str):
        super().__init__()
        self.text = text

# Background thread:
def on_chunk(text):
    self.post_message(StreamChunk(text))

# Main loop:
def on_stream_chunk(self, event: StreamChunk):
    self._process_chunk(event.text)
```

**Benefits:**
- Thread-safe by design
- Decouples producer/consumer
- Batching opportunities
- Testable (can post fake messages)

---

## Rendering Performance

### Problem: Rapid Updates

Agent streams ~100 chars/sec. Naive rendering = 100 renders/sec → UI lag.

### Solution 1: Batching

```python
# Buffer chunks
self._chunk_buffer += event.text

# Process once per event loop tick
if not self._chunk_processing_scheduled:
    self._chunk_processing_scheduled = True
    self.call_later(self._process_chunk_buffer)
```

**Result:** ~60 renders/sec (one per frame) instead of 100+.

### Solution 2: Throttled Markdown

```python
_FLUSH_INTERVAL = 0.1  # 100ms

def flush(self):
    if elapsed < self._FLUSH_INTERVAL:
        # Schedule deferred flush
        self.set_timer(self._FLUSH_INTERVAL - elapsed, self._deferred_flush)
        return

    self._do_flush()
```

**Result:** Markdown re-renders max 10 times/sec during streaming.

### Solution 3: Batch DOM Updates

```python
with self.app.batch_update():
    # Multiple DOM changes here
    detector.feed(text)
    block.update_code(code)
```

**Result:** Single layout + render cycle for multiple changes.

### Solution 4: Deferred Scrolling

```python
# ❌ WRONG: Scrolls before layout recalculated
detector.feed(text)
output.scroll_end()

# ✅ CORRECT: Scrolls after layout updated
detector.feed(text)
self.call_after_refresh(lambda: output.scroll_end())
```

**Why?** Markdown widget height changes after re-render. Scrolling before refresh uses stale height.

---

## Finalization

### Incomplete Fence Handling

```python
def finish(self):
    # Handle incomplete fence at end of stream
    if self._state == _FenceState.LANG_LINE:
        # Never reached CODE state, treat as prose
        self._pending_buffer = '```' + self._lang_buffer
        self._state = _FenceState.PROSE

    # Flush trailing backticks
    if self._backtick_count > 0:
        self._pending_buffer += '`' * self._backtick_count

    # Flush remaining content
    if self._pending_buffer:
        self._flush_pending_to_chunk()
        self._update_current_block_with_chunk()
```

**Edge Cases:**
- Stream ends mid-fence: `` This is prose ``` ``
- Stream ends with backticks: `` Code here`` ``

### Block Finalization

```python
# Mark last block complete
if isinstance(self._current_block, AgentOutputBlock):
    self._current_block.flush()
    self._current_block.mark_success()

# Switch from streaming to final rendering
for block in self.all_blocks:
    if isinstance(block, CodeInputBlock):
        block.finish_streaming()
    elif isinstance(block, AgentOutputBlock):
        block.finalize_streaming()
```

**CodeInputBlock:** Hide loading indicator, lock content
**AgentOutputBlock:** Disable throttling, force final flush

### Empty Block Cleanup

```python
# Remove empty prose blocks (except first, for status indicator)
for block in self.all_blocks:
    if isinstance(block, AgentOutputBlock) and \
       block is not self.first_agent_block and \
       not block._full.strip():
        self._remove_block(block)
```

**Why?** Agent may stream: `` prose ``` code ``` `` with no prose after code.

### Session Saving

```python
if self._save_callback:
    for block in self.all_blocks:
        self._save_callback(block)
```

Save all blocks to session transcript **after** finalization (ensures complete content).

---

## Testing Strategies

### Simulated Streaming

```python
class SimulatedAgent(AgentBase):
    async def send_prompt(self, prompt, on_chunk=None, ...):
        text = "Here is some code:\n```python\nprint('hello')\n```"

        for ch in text:
            if on_chunk:
                on_chunk(ch)
            await asyncio.sleep(self.response_delay)

        return AgentResponse(text=text)
```

**Benefits:**
- No API calls required
- Deterministic behavior
- Fast execution
- Edge case simulation

### Unit Testing Fence Detector

```python
def test_fence_detection():
    detector = StreamingFenceDetector(...)

    detector.start()
    detector.feed("Here is code:\n```python\nprint('hello')\n```\nDone")
    detector.finish()

    assert len(detector.all_blocks) == 3  # prose, code, prose
    assert isinstance(detector.all_blocks[1], CodeInputBlock)
```

### Mock Block Factories

```python
detector._make_prose_block = lambda activity: MockAgentOutputBlock()
detector._make_code_block = lambda code, lang: MockCodeInputBlock()
```

**Benefits:**
- Test logic without UI
- Verify block creation sequence
- Assert on block content

---

## Known Limitations

### 1. Nested Fences

```python
# Agent output:
```python
code = '''
```python
nested
```
'''
```
```

**Current Behavior:** Inner fence closes outer fence.
**Mitigation:** String tracking prevents most cases, but complex nesting may fail.

### 2. Language Alias Coverage

Only common aliases mapped:
```python
_LANG_ALIASES = {"py": "python", "shell": "bash", "sh": "bash"}
```

**Mitigation:** Defaults to "python" for unknown languages.

### 3. Mid-Fence Cancellation

If user cancels mid-fence, partial fence may remain.

**Mitigation:** Finalization handles incomplete fences gracefully.

### 4. Unicode Edge Cases

Multi-byte characters may break if chunk boundary splits character.

**Current Status:** Streaming APIs typically chunk on character boundaries, so rare.

---

## Future Enhancements

### 1. Nested Fence Support
Track fence depth to handle nested code blocks.

### 2. Custom Fence Markers
Support `~~~` as alternative fence marker.

### 3. Fence Attributes
Parse attributes like `python {filename="test.py"}`.

### 4. Streaming Resume
Save streaming state to resume after app restart.

### 5. Adaptive Throttling
Adjust flush interval based on content size and render time.
