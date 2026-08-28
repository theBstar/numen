"""Tests for the event bus."""

import pytest

from src.events.bus import EventBus


class DummyEvent:
    pass


class OtherEvent:
    pass


@pytest.mark.asyncio
async def test_emit_calls_handler():
    bus = EventBus()
    called = []

    async def handler(event):
        called.append(event)

    bus.subscribe(DummyEvent, handler)
    event = DummyEvent()
    await bus.emit(event)

    assert len(called) == 1
    assert called[0] is event


@pytest.mark.asyncio
async def test_emit_returns_results():
    bus = EventBus()

    async def handler(event):
        pass

    bus.subscribe(DummyEvent, handler, name="test_handler")
    results = await bus.emit(DummyEvent())

    assert len(results) == 1
    assert results[0] == ("test_handler", None)


@pytest.mark.asyncio
async def test_handlers_run_in_priority_order():
    bus = EventBus()
    order = []

    async def first(event):
        order.append("first")

    async def second(event):
        order.append("second")

    async def third(event):
        order.append("third")

    bus.subscribe(DummyEvent, third, priority=30)
    bus.subscribe(DummyEvent, first, priority=10)
    bus.subscribe(DummyEvent, second, priority=20)

    await bus.emit(DummyEvent())
    assert order == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_failing_handler_does_not_block_others():
    bus = EventBus()
    called = []

    async def failing(event):
        raise ValueError("boom")

    async def succeeding(event):
        called.append("ok")

    bus.subscribe(DummyEvent, failing, priority=10, name="fails")
    bus.subscribe(DummyEvent, succeeding, priority=20, name="succeeds")

    results = await bus.emit(DummyEvent())

    assert len(results) == 2
    assert results[0][0] == "fails"
    assert isinstance(results[0][1], ValueError)
    assert results[1] == ("succeeds", None)
    assert called == ["ok"]


@pytest.mark.asyncio
async def test_no_handlers_returns_empty():
    bus = EventBus()
    results = await bus.emit(DummyEvent())
    assert results == []


@pytest.mark.asyncio
async def test_different_event_types_are_isolated():
    bus = EventBus()
    called = []

    async def dummy_handler(event):
        called.append("dummy")

    async def other_handler(event):
        called.append("other")

    bus.subscribe(DummyEvent, dummy_handler)
    bus.subscribe(OtherEvent, other_handler)

    await bus.emit(DummyEvent())
    assert called == ["dummy"]


@pytest.mark.asyncio
async def test_multiple_handlers_same_event():
    bus = EventBus()
    called = []

    async def h1(event):
        called.append("h1")

    async def h2(event):
        called.append("h2")

    bus.subscribe(DummyEvent, h1, priority=100)
    bus.subscribe(DummyEvent, h2, priority=100)

    await bus.emit(DummyEvent())
    assert len(called) == 2


@pytest.mark.asyncio
async def test_subscribe_uses_qualname_as_default_name():
    bus = EventBus()

    async def my_handler(event):
        pass

    bus.subscribe(DummyEvent, my_handler)
    results = await bus.emit(DummyEvent())

    assert "my_handler" in results[0][0]
