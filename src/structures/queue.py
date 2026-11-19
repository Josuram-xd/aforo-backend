"""FIFO queue built on ``SinglyLinkedList``.

Domain use: session report. Students are enqueued by their first ENTRY event, so iterating
the queue gives the real arrival order of the class.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from structures.singly_linked_list import SinglyLinkedList


class Queue:
    """First in, first out. Every operation is O(1)."""

    def __init__(self) -> None:
        self._items = SinglyLinkedList()

    def enqueue(self, value: Any) -> None:
        self._items.append(value)

    def dequeue(self) -> Any:
        """Remove and return the oldest value. Raises IndexError when empty."""
        if self.is_empty():
            raise IndexError("dequeue from empty queue")
        return self._items.remove_first()

    def peek(self) -> Any:
        """Return the oldest value without removing it. Raises IndexError when empty."""
        if self.is_empty():
            raise IndexError("peek at empty queue")
        return self._items.first()

    def is_empty(self) -> bool:
        return len(self._items) == 0

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Any]:
        """Iterate from oldest to newest without consuming the queue."""
        return iter(self._items)
