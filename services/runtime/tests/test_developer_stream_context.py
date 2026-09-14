import asyncio

from app.developer_stream import bind_developer_sink, emit_developer_event


def test_developer_event_sink_is_task_local():
    async def worker(name: str):
        seen = []
        bind_developer_sink(seen.append)
        await asyncio.sleep(0)
        emit_developer_event({"event_type": name})
        return seen

    left, right = asyncio.run(asyncio.gather(worker("left"), worker("right")))
    assert left == [{"event_type": "left"}]
    assert right == [{"event_type": "right"}]


def test_developer_sink_failure_is_ignored():
    def broken(event):
        raise RuntimeError("observability store unavailable")

    bind_developer_sink(broken)
    try:
        emit_developer_event({"event_type": "developer_message"})
    finally:
        bind_developer_sink(None)
