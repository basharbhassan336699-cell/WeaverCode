"""اختبارات وضع الخلفية: ناقل الأحداث والحالة والطابور."""

import asyncio
from background.events import EventBus, WeaverEvent, EventType
from background import status as st


def test_event_serialization():
    ev = WeaverEvent(EventType.FILE_CREATE, "ينشئ x", "x.py", diff_added=3)
    d = ev.to_dict()
    assert d["type"] == "file_create"
    assert d["message"] == "ينشئ x" and d["detail"] == "x.py"
    assert d["diff_added"] == 3
    import json
    assert json.loads(ev.to_json())["type"] == "file_create"


def test_event_bus_singleton_and_emit():
    bus = EventBus()
    assert EventBus() is bus  # singleton
    got = []

    async def sub(ev):
        got.append(ev.message)

    unsub = bus.subscribe(sub)
    asyncio.run(bus.emit(WeaverEvent(EventType.THINKING, "hi")))
    assert got == ["hi"]
    assert bus.history[-1].message == "hi"
    unsub()
    asyncio.run(bus.emit(WeaverEvent(EventType.THINKING, "bye")))
    assert got == ["hi"]  # unsubscribed → no new delivery


def test_event_history_capped():
    bus = EventBus()
    bus.history.clear()
    for i in range(250):
        asyncio.run(bus.emit(WeaverEvent(EventType.STATUS, str(i))))
    assert len(bus.history) <= 200


def test_status_and_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(st, "QUEUE_FILE", tmp_path / "queue.json")
    st.save_status("working", "مهمة", pid=123)
    s = st.read_status()
    assert s["state"] == "working" and s["task"] == "مهمة"
    assert st.queue_task("مهمة1") == 1
    assert st.queue_task("مهمة2") == 2
    t = st.pop_task()
    assert t["prompt"] == "مهمة1"
    assert len(st.read_queue()) == 1
