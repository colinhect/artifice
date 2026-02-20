"""Backward compatibility re-export for chunk_buffer module (now in agent.streaming)."""

from __future__ import annotations

from artifice.agent.streaming.buffer import ChunkBuffer

__all__ = ["ChunkBuffer"]
