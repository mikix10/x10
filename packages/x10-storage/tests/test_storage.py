from __future__ import annotations

import pytest

from x10_storage import StorageAdapter, StorageRecord


class _MemoryAdapter(StorageAdapter):
    def __init__(self) -> None:
        self._records: dict[str, StorageRecord] = {}

    def save(self, record: StorageRecord) -> None:
        self._records[record.key] = record

    def load(self, key: str) -> StorageRecord | None:
        return self._records.get(key)


def test_base_adapter_requires_implementations():
    adapter = StorageAdapter()
    with pytest.raises(NotImplementedError):
        adapter.save(StorageRecord(key="k"))
    with pytest.raises(NotImplementedError):
        adapter.load("k")


def test_memory_adapter_roundtrip():
    adapter = _MemoryAdapter()
    record = StorageRecord(key="ifs/2t/2026-01-01", payload={"unit": "K"})
    adapter.save(record)
    assert adapter.load("ifs/2t/2026-01-01") == record


def test_loading_an_unknown_key_returns_none():
    assert _MemoryAdapter().load("absent") is None


def test_payload_defaults_are_not_shared_between_instances():
    first = StorageRecord(key="a")
    second = StorageRecord(key="b")
    first.payload["x"] = 1
    assert second.payload == {}
