"""Tests for session transcript management."""

import tempfile
from pathlib import Path
import pytest

from artifice.session import SessionTranscript
from artifice.terminal_output import (
    CodeInputBlock,
    CodeOutputBlock,
    AgentInputBlock,
    AgentOutputBlock,
)


def test_session_transcript_initialization(tmp_path):
    """Test creating a session transcript."""
    transcript = SessionTranscript(tmp_path)
    
    assert transcript.sessions_dir == tmp_path
    assert transcript.session_file.parent == tmp_path
    assert transcript.session_file.name.startswith("session_")
    assert transcript.session_file.name.endswith(".md")


def test_session_transcript_creates_directory(tmp_path):
    """Test that session transcript creates the directory if it doesn't exist."""
    sessions_dir = tmp_path / "new_sessions"
    assert not sessions_dir.exists()
    
    transcript = SessionTranscript(sessions_dir)
    
    assert sessions_dir.exists()
    assert sessions_dir.is_dir()


def test_append_agent_input_block(tmp_path):
    """Test saving an agent input block."""
    transcript = SessionTranscript(tmp_path)
    block = AgentInputBlock("What is 2+2?")
    
    transcript.append_block(block)
    
    content = transcript.session_file.read_text()
    assert "## User" in content
    assert "What is 2+2?" in content


def test_append_agent_output_block(tmp_path):
    """Test saving an agent output block."""
    transcript = SessionTranscript(tmp_path)
    block = AgentOutputBlock("The answer is 4", activity=False)
    
    transcript.append_block(block)
    
    content = transcript.session_file.read_text()
    assert "## Agent" in content
    assert "The answer is 4" in content


def test_append_code_input_block(tmp_path):
    """Test saving a code input block."""
    transcript = SessionTranscript(tmp_path)
    block = CodeInputBlock("print('hello')", language="python", show_loading=False)
    
    transcript.append_block(block)
    
    content = transcript.session_file.read_text()
    assert "### Code (python)" in content
    assert "```python" in content
    assert "print('hello')" in content


def test_append_code_output_block(tmp_path):
    """Test saving a code output block."""
    transcript = SessionTranscript(tmp_path)
    block = CodeOutputBlock("hello\n", render_markdown=False)
    block.flush()
    
    transcript.append_block(block)
    
    content = transcript.session_file.read_text()
    assert "### Output" in content
    assert "hello" in content


def test_append_code_output_block_with_error(tmp_path):
    """Test saving a code output block with errors."""
    transcript = SessionTranscript(tmp_path)
    block = CodeOutputBlock(render_markdown=False)
    block.append_error("Error: something went wrong\n")
    block.flush()
    
    transcript.append_block(block)
    
    content = transcript.session_file.read_text()
    assert "### Output (error)" in content
    assert "Error: something went wrong" in content


def test_append_empty_block_skipped(tmp_path):
    """Test that empty blocks are not saved."""
    transcript = SessionTranscript(tmp_path)
    block = AgentOutputBlock("", activity=False)
    
    transcript.append_block(block)
    
    content = transcript.session_file.read_text()
    # Should only have header, not the empty agent output
    assert "## Agent" not in content


def test_multiple_blocks(tmp_path):
    """Test saving multiple blocks in sequence."""
    transcript = SessionTranscript(tmp_path)
    
    # User asks a question
    transcript.append_block(AgentInputBlock("Calculate 5+3"))
    
    # Agent responds
    transcript.append_block(AgentOutputBlock("I'll calculate that for you.", activity=False))
    
    # Agent sends code
    transcript.append_block(CodeInputBlock("result = 5 + 3\nprint(result)", language="python", show_loading=False))
    
    # Code output
    output_block = CodeOutputBlock("8\n", render_markdown=False)
    output_block.flush()
    transcript.append_block(output_block)
    
    content = transcript.session_file.read_text()
    
    # Check all blocks are present
    assert "## User" in content
    assert "Calculate 5+3" in content
    assert "## Agent" in content
    assert "I'll calculate that for you." in content
    assert "### Code (python)" in content
    assert "result = 5 + 3" in content
    assert "### Output" in content
    assert "8" in content


def test_session_header_and_footer(tmp_path):
    """Test that session has proper header and footer."""
    transcript = SessionTranscript(tmp_path)
    
    # Add a block to trigger header creation
    transcript.append_block(AgentInputBlock("test"))
    
    # Finalize session
    transcript.finalize()
    
    content = transcript.session_file.read_text()
    
    # Check header
    assert "# Artifice Session" in content
    assert "**Started:**" in content
    
    # Check footer
    assert "**Ended:**" in content


def test_bash_code_block(tmp_path):
    """Test saving a bash code block."""
    transcript = SessionTranscript(tmp_path)
    block = CodeInputBlock("ls -la", language="bash", show_loading=False)
    
    transcript.append_block(block)
    
    content = transcript.session_file.read_text()
    assert "### Code (bash)" in content
    assert "```bash" in content
    assert "ls -la" in content
