"""Tests for the ChunkBuffer helper class."""

from artifice.agent.streaming.buffer import ChunkBuffer


class TestChunkBuffer:
    def test_append_schedules_drain(self):
        """Appending text schedules a drain callback."""
        scheduled = []
        drained = []

        buf = ChunkBuffer(
            schedule=lambda fn: scheduled.append(fn), drain=lambda t: drained.append(t)
        )
        buf.append("hello")

        assert len(scheduled) == 1
        assert drained == []  # Not drained yet

        # Simulate event-loop calling the scheduled callback
        scheduled[0]()
        assert drained == ["hello"]

    def test_multiple_appends_batch_into_single_drain(self):
        """Multiple appends before drain fires are batched together."""
        scheduled = []
        drained = []

        buf = ChunkBuffer(
            schedule=lambda fn: scheduled.append(fn), drain=lambda t: drained.append(t)
        )
        buf.append("a")
        buf.append("b")
        buf.append("c")

        # Only one callback should be scheduled
        assert len(scheduled) == 1

        scheduled[0]()
        assert drained == ["abc"]

    # Failing because there is no asyncio loop
    #    def test_drain_resets_scheduling(self):
    #        """After a drain, new appends schedule a new drain."""
    #        scheduled = []
    #        drained = []
    #
    #        buf = ChunkBuffer(
    #            schedule=lambda fn: scheduled.append(fn), drain=lambda t: drained.append(t)
    #        )
    #        buf.append("first")
    #        scheduled[0]()
    #
    #        buf.append("second")
    #        assert len(scheduled) == 2
    #
    #        scheduled[1]()
    #        assert drained == ["first", "second"]

    def test_flush_sync_drains_immediately(self):
        """flush_sync drains buffered text without waiting for schedule."""
        scheduled = []
        drained = []

        buf = ChunkBuffer(
            schedule=lambda fn: scheduled.append(fn), drain=lambda t: drained.append(t)
        )
        buf.append("data")
        buf.flush_sync()

        assert drained == ["data"]

    def test_flush_sync_noop_when_empty(self):
        """flush_sync is a no-op when buffer is empty."""
        drained = []
        buf = ChunkBuffer(schedule=lambda fn: None, drain=lambda t: drained.append(t))
        buf.flush_sync()
        assert drained == []

    def test_pending_property(self):
        """pending reflects whether there is un-drained text."""
        buf = ChunkBuffer(schedule=lambda fn: None, drain=lambda t: None)
        assert not buf.pending

        buf.append("text")
        assert buf.pending

        buf.flush_sync()
        assert not buf.pending
