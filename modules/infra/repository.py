"""In-memory Repository (implements the Repository contract)."""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar('T')


class InMemoryRepository(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    def get(self, id: str) -> T | None:
        return self._items.get(id)

    def save(self, id: str, entity: T) -> T:
        self._items[id] = entity
        return entity

    def list(self) -> list[T]:
        return list(self._items.values())
