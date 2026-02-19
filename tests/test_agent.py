"""Tests for the Agent class."""

import pytest

from artifice.agent import SimulatedAgent, ToolCall, ToolDef, TOOLS, execute_tool_call
from artifice.agent.tools import get_all_schemas


@pytest.mark.asyncio
async def test_agent_manages_history():
    """Test that agent maintains conversation history."""
    agent = SimulatedAgent(response_delay=0.001)

    await agent.send("First message")
    assert len(agent.messages) == 2  # user + agent
    assert agent.messages[0]["role"] == "user"
    assert agent.messages[1]["role"] == "assistant"

    await agent.send("Second message")
    assert len(agent.messages) == 4  # 2 turns


@pytest.mark.asyncio
async def test_agent_clear():
    """Test that clear() works."""
    agent = SimulatedAgent(response_delay=0.001)

    await agent.send("Hello")
    assert len(agent.messages) > 0

    agent.clear()
    assert len(agent.messages) == 0


@pytest.mark.asyncio
async def test_multiple_agents_independent_history():
    """Test that multiple agents maintain separate history."""
    agent1 = SimulatedAgent(system_prompt="You are helpful")
    agent2 = SimulatedAgent(system_prompt="You are concise")

    agent1.configure_scenarios([{"response": "agent1 reply"}])
    agent2.configure_scenarios([{"response": "agent2 reply"}])

    await agent1.send("Hello")
    await agent2.send("Hello")

    assert len(agent1.messages) == 2
    assert len(agent2.messages) == 2
    assert agent1 is not agent2


@pytest.mark.asyncio
async def test_agent_system_prompt():
    """Test that system prompt is stored."""
    agent = SimulatedAgent(system_prompt="Test system prompt")
    assert agent.system_prompt == "Test system prompt"
    await agent.send("Hello")
    assert len(agent.messages) == 2


@pytest.mark.asyncio
async def test_agent_streaming():
    """Test that streaming callbacks are passed through."""
    agent = SimulatedAgent(response_delay=0.001)
    agent.set_default_response("hello world")

    chunks = []
    thinking_chunks = []

    response = await agent.send(
        "Hello",
        on_chunk=lambda c: chunks.append(c),
        on_thinking_chunk=lambda c: thinking_chunks.append(c),
    )

    assert len(chunks) > 0
    assert "".join(chunks) == response.text


@pytest.mark.asyncio
async def test_agent_error_handling():
    """Test that errors in agent.send are returned as AgentResponse.error."""
    from artifice.agent import AgentResponse

    agent = SimulatedAgent(response_delay=0.001)

    # Patch send to simulate an error

    async def erroring_send(*args, **kwargs):
        return AgentResponse(text="", error="Test error")

    agent.send = erroring_send

    response = await agent.send("Hello")
    assert response.error == "Test error"
    assert response.text == ""


@pytest.mark.asyncio
async def test_agent_empty_prompt():
    """Test that empty prompts are not added to history."""
    agent = SimulatedAgent(response_delay=0.001)
    agent.set_default_response("reply")

    await agent.send("")
    assert all(m["role"] != "user" for m in agent.messages)

    await agent.send("   ")
    assert all(m["content"] != "   " for m in agent.messages)


@pytest.mark.asyncio
async def test_agent_tool_result():
    """Test that add_tool_result appends a tool message."""
    agent = SimulatedAgent()
    agent.add_tool_result("call_123", "output text")
    assert any(
        m.get("role") == "tool" and m.get("tool_call_id") == "call_123"
        for m in agent.messages
    )


# --- Tool registry tests ---


def test_tool_def_to_schema():
    """Test that ToolDef.to_schema() produces valid OpenAI function-call format."""
    tool = ToolDef(
        name="test_tool",
        description="A test tool.",
        parameters={"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}},
        display_language="python",
        display_arg="x",
    )
    schema = tool.to_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "test_tool"
    assert schema["function"]["description"] == "A test tool."
    assert schema["function"]["parameters"]["required"] == ["x"]


def test_registry_contains_expected_tools():
    """Test that TOOLS contains python and shell (and stubs)."""
    assert "python" in TOOLS
    assert "shell" in TOOLS
    assert "read_file" in TOOLS
    assert "write_file" in TOOLS
    assert "web_search" in TOOLS
    assert "web_fetch" in TOOLS
    assert "system_info" in TOOLS


def test_get_all_schemas_returns_valid_list():
    """Test that get_all_schemas() returns a list of valid schemas."""
    schemas = get_all_schemas()
    assert isinstance(schemas, list)
    assert len(schemas) == len(TOOLS)
    for schema in schemas:
        assert schema["type"] == "function"
        assert "name" in schema["function"]
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]


def test_toolcall_display_text_python():
    """Test ToolCall.display_text for python tool."""
    tc = ToolCall(id="1", name="python", args={"code": "print('hi')"})
    assert tc.display_text == "print('hi')"


def test_toolcall_display_text_shell():
    """Test ToolCall.display_text for shell tool."""
    tc = ToolCall(id="2", name="shell", args={"command": "ls -la"})
    assert tc.display_text == "ls -la"


def test_toolcall_display_language():
    """Test ToolCall.display_language for known tools."""
    tc_py = ToolCall(id="1", name="python", args={"code": "x"})
    assert tc_py.display_language == "python"

    tc_sh = ToolCall(id="2", name="shell", args={"command": "ls"})
    assert tc_sh.display_language == "bash"


def test_toolcall_display_text_read_file():
    """Test ToolCall.display_text for stub tools."""
    tc = ToolCall(id="3", name="read_file", args={"path": "/tmp/foo.txt"})
    assert tc.display_text == "/tmp/foo.txt"
    assert tc.display_language == "text"


def test_toolcall_unknown_tool():
    """Test ToolCall behavior for an unregistered tool name."""
    tc = ToolCall(id="99", name="unknown_tool", args={"foo": "bar"})
    assert tc.display_text == str({"foo": "bar"})
    assert tc.display_language == "text"


def test_registry_contains_file_search():
    """Test that file_search tool is registered."""
    assert "file_search" in TOOLS
    assert TOOLS["file_search"].display_arg == "pattern"


def test_tools_with_executors():
    """Test that non-code tools have executors, code tools do not."""
    assert TOOLS["python"].executor is None
    assert TOOLS["shell"].executor is None
    assert TOOLS["read_file"].executor is not None
    assert TOOLS["write_file"].executor is not None
    assert TOOLS["file_search"].executor is not None
    assert TOOLS["web_search"].executor is not None
    assert TOOLS["web_fetch"].executor is not None
    assert TOOLS["system_info"].executor is not None


# --- Tool executor tests ---


@pytest.mark.asyncio
async def test_execute_read_file(tmp_path):
    """Test read_file executor reads file contents with line numbers."""
    f = tmp_path / "test.txt"
    f.write_text("line1\nline2\nline3\n")

    tc = ToolCall(id="1", name="read_file", args={"path": str(f)})
    result = await execute_tool_call(tc)

    assert result is not None
    assert "line1" in result
    assert "line2" in result
    assert "   1 |" in result  # line numbers


@pytest.mark.asyncio
async def test_execute_read_file_with_offset_and_limit(tmp_path):
    """Test read_file executor respects offset and limit."""
    f = tmp_path / "test.txt"
    f.write_text("a\nb\nc\nd\ne\n")

    tc = ToolCall(id="1", name="read_file", args={"path": str(f), "offset": 1, "limit": 2})
    result = await execute_tool_call(tc)

    assert result is not None
    assert "b" in result
    assert "c" in result
    assert "a" not in result
    assert "d" not in result


@pytest.mark.asyncio
async def test_execute_read_file_not_found():
    """Test read_file executor handles missing files."""
    tc = ToolCall(id="1", name="read_file", args={"path": "/nonexistent/file.txt"})
    result = await execute_tool_call(tc)

    assert result is not None
    assert "Error" in result


@pytest.mark.asyncio
async def test_execute_write_file(tmp_path):
    """Test write_file executor creates files."""
    f = tmp_path / "output.txt"

    tc = ToolCall(id="1", name="write_file", args={"path": str(f), "content": "hello world"})
    result = await execute_tool_call(tc)

    assert result is not None
    assert "Wrote" in result
    assert f.read_text() == "hello world"


@pytest.mark.asyncio
async def test_execute_write_file_creates_dirs(tmp_path):
    """Test write_file executor creates parent directories."""
    f = tmp_path / "sub" / "dir" / "file.txt"

    tc = ToolCall(id="1", name="write_file", args={"path": str(f), "content": "nested"})
    result = await execute_tool_call(tc)

    assert result is not None
    assert f.read_text() == "nested"


@pytest.mark.asyncio
async def test_execute_file_search(tmp_path):
    """Test file_search executor finds files by glob pattern."""
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")
    (tmp_path / "c.txt").write_text("")

    tc = ToolCall(id="1", name="file_search", args={"pattern": "*.py", "path": str(tmp_path)})
    result = await execute_tool_call(tc)

    assert result is not None
    assert "a.py" in result
    assert "b.py" in result
    assert "c.txt" not in result


@pytest.mark.asyncio
async def test_execute_file_search_no_matches(tmp_path):
    """Test file_search executor when no files match."""
    tc = ToolCall(id="1", name="file_search", args={"pattern": "*.xyz", "path": str(tmp_path)})
    result = await execute_tool_call(tc)

    assert result is not None
    assert "No files matching" in result


@pytest.mark.asyncio
async def test_execute_system_info():
    """Test system_info executor returns OS and cwd info."""
    tc = ToolCall(id="1", name="system_info", args={"categories": ["os", "cwd"]})
    result = await execute_tool_call(tc)

    assert result is not None
    assert "OS:" in result
    assert "Working directory:" in result


@pytest.mark.asyncio
async def test_execute_tool_call_returns_none_for_code_tools():
    """Test that execute_tool_call returns None for python/shell (no executor)."""
    tc = ToolCall(id="1", name="python", args={"code": "print('hi')"})
    result = await execute_tool_call(tc)
    assert result is None

    tc2 = ToolCall(id="2", name="shell", args={"command": "ls"})
    result2 = await execute_tool_call(tc2)
    assert result2 is None


@pytest.mark.asyncio
async def test_execute_tool_call_returns_none_for_unknown():
    """Test that execute_tool_call returns None for unknown tools."""
    tc = ToolCall(id="1", name="nonexistent_tool", args={})
    result = await execute_tool_call(tc)
    assert result is None
