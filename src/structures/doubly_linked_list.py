"""Doubly linked list with cursor-based windows.

Domain use: session report timeline. Events are appended in chronological order and the
client pages forwards and backwards by passing the id of the last event it saw.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, NamedTuple


class DNode:
    """One element of the list, linked to its neighbours in both directions."""

    __slots__ = ("value", "prev", "next")

    def __init__(self, value: Any) -> None:
        self.value = value
        self.prev: DNode | None = None
        self.next: DNode | None = None


class Window(NamedTuple):
    """A page of values (always in forward order) plus whether more exist on each side."""

    items: list[Any]
    has_prev: bool
    has_next: bool


class DoublyLinkedList:
    def __init__(self) -> None:
        self._head: DNode | None = None
        self._tail: DNode | None = None
        self._size = 0

    def append(self, value: Any) -> DNode:
        """Add at the end. O(1)."""
        node = DNode(value)
        node.prev = self._tail
        if self._tail is None:
            self._head = node
        else:
            self._tail.next = node
        self._tail = node
        self._size += 1
        return node

    def prepend(self, value: Any) -> DNode:
        """Add at the front. O(1)."""
        node = DNode(value)
        node.next = self._head
        if self._head is None:
            self._tail = node
        else:
            self._head.prev = node
        self._head = node
        self._size += 1
        return node

    def remove(self, node: DNode) -> None:
        """Unlink a node that belongs to this list. O(1)."""
        if node.prev is None:
            self._head = node.next
        else:
            node.prev.next = node.next
        if node.next is None:
            self._tail = node.prev
        else:
            node.next.prev = node.prev
        node.prev = node.next = None
        self._size -= 1

    def find(self, predicate: Callable[[Any], bool]) -> DNode | None:
        """Return the first node whose value satisfies the predicate. O(n)."""
        node = self._head
        while node is not None:
            if predicate(node.value):
                return node
            node = node.next
        return None

    def __iter__(self) -> Iterator[Any]:
        node = self._head
        while node is not None:
            yield node.value
            node = node.next

    def iter_backward(self) -> Iterator[Any]:
        node = self._tail
        while node is not None:
            yield node.value
            node = node.prev

    def __len__(self) -> int:
        return self._size

    def window(
        self,
        cursor: Any,
        direction: str,
        limit: int,
        key: Callable[[Any], Any] = lambda value: value,
    ) -> Window:
        """Return up to ``limit`` values after ("next") or before ("prev") the cursor.

        ``cursor`` is the ``key(value)`` of a known element, or None to start at the
        beginning ("next") or the end ("prev"). The cursor element itself is excluded.
        Raises KeyError when the cursor is not in the list and ValueError for a bad
        direction. O(n) to locate the cursor plus O(limit).
        """
        if direction not in ("next", "prev"):
            raise ValueError("direction must be 'next' or 'prev'")
        anchor: DNode | None = None
        if cursor is not None:
            anchor = self.find(lambda value: key(value) == cursor)
            if anchor is None:
                raise KeyError(cursor)

        items: list[Any] = []
        if direction == "next":
            node = self._head if anchor is None else anchor.next
            while node is not None and len(items) < limit:
                items.append(node.value)
                last = node
                node = node.next
            has_prev = (last.prev is not None) if items else (anchor is not None)
            return Window(items, has_prev, node is not None)

        node = self._tail if anchor is None else anchor.prev
        while node is not None and len(items) < limit:
            items.append(node.value)
            first = node
            node = node.prev
        items.reverse()
        has_next = (first.next is not None) if items else (anchor is not None)
        return Window(items, node is not None, has_next)
