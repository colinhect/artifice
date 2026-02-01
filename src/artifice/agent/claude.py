from __future__ import annotations

import asyncio
import os
from typing import Optional, Any, Callable

from .common import AgentBase, AgentResponse, ToolCall

class ClaudeAgent(AgentBase):
    """Agent for connecting to Claude via Anthropic API with tool support.

    This agent provides streaming responses and supports agentic tool calling loops.
    The agent will automatically iterate through multiple tool calls until Claude
    stops requesting tools, up to a maximum of 10 iterations.

    API Key: Reads from ANTHROPIC_API_KEY environment variable.

    Thread Safety: The agent uses lazy client initialization and runs API calls
    in a thread pool executor to avoid blocking the async event loop.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        tools: list[dict[str, Any]] | None = None,
        tool_handler: Callable[[str, dict[str, Any]], Any] | None = None,
        system_prompt: str | None = None,
    ):
        """Initialize Claude agent.

        Args:
            model: Model identifier to use. Defaults to Claude Sonnet 4.5.
            tools: List of tool definitions in Anthropic API format.
            tool_handler: Async callback to handle tool calls.
                         Takes (tool_name: str, tool_input: dict) and returns result string.
            system_prompt: Optional system prompt to guide the agent's behavior.
        """
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.tools = tools or []
        self.tool_handler = tool_handler
        self.system_prompt = system_prompt
        self._client = None
        self.messages = []  # Persistent conversation history

    def _get_client(self):
        """Lazy import and create Anthropic client."""
        if self._client is None:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "anthropic package not installed. Install with: pip install anthropic"
                )
        return self._client

    def clear_conversation(self):
        """Clear the conversation history.

        This resets the agent's memory of previous interactions,
        starting fresh with the next prompt.
        """
        self.messages = []

    async def send_prompt(
        self, prompt: str, on_chunk: Optional[Callable] = None
    ) -> AgentResponse:
        """Send a prompt to Claude with tool support.

        Args:
            prompt: The prompt text.
            on_chunk: Optional callback for streaming text chunks.

        Returns:
            AgentResponse with the complete response and tool calls.
        """
        if not self.api_key:
            return AgentResponse(
                text="",
                error="No API key found. Set ANTHROPIC_API_KEY environment variable.",
            )

        try:
            client = self._get_client()
            loop = asyncio.get_running_loop()

            # Add new user message to conversation history (only if non-empty)
            if prompt.strip():
                self.messages.append({"role": "user", "content": prompt})
            all_text_chunks = []
            final_stop_reason = None

            # Agentic loop: continue until Claude stops requesting tools
            max_iterations = 10  # Prevent infinite loops
            for _ in range(max_iterations):
                def sync_stream():
                    """Synchronously stream from Claude."""
                    chunks = []
                    stop_reason = None
                    tool_uses = []

                    # Build API call parameters
                    api_params = {
                        "model": self.model,
                        "max_tokens": 4096,
                        "messages": self.messages,
                    }
                    
                    # Add system prompt if available
                    if self.system_prompt:
                        api_params["system"] = self.system_prompt
                    
                    # Add tools if available
                    if self.tools:
                        api_params["tools"] = self.tools

                    with client.messages.stream(**api_params) as stream:
                        for text in stream.text_stream:
                            chunks.append(text)
                            if on_chunk:
                                loop.call_soon_threadsafe(on_chunk, text)
                        
                        # Get final message
                        message = stream.get_final_message()
                        stop_reason = message.stop_reason
                        
                        # Extract tool uses from content blocks
                        for block in message.content:
                            if block.type == "tool_use":
                                tool_uses.append({
                                    "id": block.id,
                                    "name": block.name,
                                    "input": block.input,
                                })

                    return "".join(chunks), stop_reason, tool_uses, message.content

                # Execute streaming in thread pool
                text, stop_reason, tool_uses, content_blocks = await loop.run_in_executor(
                    None, sync_stream
                )
                
                all_text_chunks.append(text)
                final_stop_reason = stop_reason

                # Add assistant's response to conversation (convert content blocks to dicts)
                serialized_content = []
                for block in content_blocks:
                    if block.type == "text":
                        # Only add text blocks with non-empty text
                        if block.text:
                            serialized_content.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        serialized_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })

                # Only add assistant message if it has content
                if serialized_content:
                    self.messages.append({
                        "role": "assistant",
                        "content": serialized_content,
                    })

                # If no tool uses, we're done
                if not tool_uses or stop_reason != "tool_use":
                    break

                # Process tool calls
                tool_results = []
                for tool_use in tool_uses:
                    tool_call = ToolCall(
                        id=tool_use["id"],
                        name=tool_use["name"],
                        input=tool_use["input"],
                    )

                    # Execute the tool
                    if self.tool_handler:
                        try:
                            result = await self.tool_handler(tool_use["name"], tool_use["input"])
                            tool_call.output = str(result)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_use["id"],
                                "content": str(result),
                            })
                        except Exception as e:
                            tool_call.error = str(e)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_use["id"],
                                "content": f"Error: {e}",
                                "is_error": True,
                            })
                    else:
                        tool_call.error = "No tool handler configured"
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use["id"],
                            "content": "Error: No tool handler configured",
                            "is_error": True,
                        })

                # Add tool results to conversation (only if we have results)
                if tool_results:
                    self.messages.append({
                        "role": "user",
                        "content": tool_results,
                    })

            return AgentResponse(
                text="\n".join(all_text_chunks),
                stop_reason=final_stop_reason,
            )

        except ImportError as e:
            return AgentResponse(text="", error=str(e))
        except Exception as e:
            error_msg = f"Error communicating with Claude: {e}"
            # Add debug info about messages structure
            if "empty content" in str(e).lower():
                error_msg += f"\n\nMessage count: {len(self.messages)}"
                for i, msg in enumerate(self.messages):
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        error_msg += f"\n  Message {i} ({msg['role']}): {len(content)} content blocks"
                    else:
                        error_msg += f"\n  Message {i} ({msg['role']}): {len(str(content))} chars"
            return AgentResponse(text="", error=error_msg)
