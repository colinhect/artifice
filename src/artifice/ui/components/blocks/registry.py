"""BlockRenderer protocol and registry for extensible block creation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from artifice.ui.components.blocks.blocks import BaseBlock


class BlockRenderer(Protocol):
    """Protocol for renderable output blocks.

    Implementations can register with BlockRegistry to handle specific
    content types. This enables open/closed principle for adding new
    block types without modifying existing code.
    """

    def can_render(self, content_type: str) -> bool:
        """Check if this renderer can handle the given content type.

        Args:
            content_type: The type of content to render (e.g., "code", "agent", "tool")

        Returns:
            True if this renderer can create blocks for this content type
        """
        ...  # pylint: disable=unnecessary-ellipsis

    def create_block(self, content: str, **kwargs) -> BaseBlock:
        """Create a block widget for the given content.

        Args:
            content: The content to render in the block
            **kwargs: Additional arguments specific to the block type

        Returns:
            A configured BaseBlock instance ready to be mounted
        """
        ...  # pylint: disable=unnecessary-ellipsis


class BlockRegistry:
    """Register and lookup block renderers.

    Maintains a registry of BlockRenderer implementations that can create
    blocks for different content types. New block types can be added by
    registering additional renderers without modifying existing code.

    Example:
        registry = BlockRegistry()
        registry.register(CodeBlockRenderer())
        registry.register(AgentBlockRenderer())

        # Later, create a block for code content
        block = registry.create_block("code", "print('hello')", language="python")
    """

    def __init__(self) -> None:
        """Initialize an empty block registry."""
        self._renderers: list[BlockRenderer] = []

    def register(self, renderer: BlockRenderer) -> None:
        """Register a block renderer.

        Renderers are checked in registration order - first match wins.

        Args:
            renderer: A BlockRenderer implementation to add to the registry
        """
        self._renderers.append(renderer)

    def create_block(self, content_type: str, content: str, **kwargs) -> BaseBlock:
        """Create a block for the given content type.

        Iterates through registered renderers and uses the first one
        that can handle the content type.

        Args:
            content_type: The type of content (e.g., "code", "agent")
            content: The content to render
            **kwargs: Additional arguments passed to the renderer

        Returns:
            A configured block widget

        Raises:
            ValueError: If no renderer can handle the content type
        """
        for renderer in self._renderers:
            if renderer.can_render(content_type):
                return renderer.create_block(content, **kwargs)
        raise ValueError(f"No renderer registered for content type: {content_type}")

    def can_render(self, content_type: str) -> bool:
        """Check if any registered renderer can handle the content type.

        Args:
            content_type: The type of content to check

        Returns:
            True if a renderer is available for this content type
        """
        return any(r.can_render(content_type) for r in self._renderers)
