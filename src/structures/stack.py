"""LIFO stack built on singly linked nodes.

Domain use: session report. One stack per student (push on ENTRY, pop on EXIT) tells who is
inside and exposes anomalies (pop on empty = exit without entry, leftover = entry without
exit). A global stack of ENTRY events gives the "last entries" list (top = most recent).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from structures.singly_linked_list import Node


class Stack:
    """Last in, first out. Every operation is O(1)."""

    def __init__(self) -> None:
        self._top: Node | None = None
        self._size = 0

    def push(self, value: Any) -> None:
        self._top = Node(value, self._top)
        self._size += 1

    def pop(self) -> Any:
        """Remove and return the top value. Raises IndexError when empty."""
        if self._top is None:
            raise IndexError("pop from empty stack")
        node = self._top
        self._top = node.next
        self._size -= 1
        return node.value

    def peek(self) -> Any:
        """Return the top value without removing it. Raises IndexError when empty."""
        if self._top is None:
            raise IndexError("peek at empty stack")
        return self._top.value

    def is_empty(self) -> bool:
        return self._top is None

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[Any]:
        """Iterate from the top (newest) to the bottom (oldest)."""
        node = self._top
        while node is not None:
            yield node.value
            node = node.next
