"""Singly linked list.

Domain use: it is the storage behind ``Queue`` (arrival order of students in the session
report) and shares its node type with ``Stack`` (students currently inside the classroom).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


class Node:
    """One element of the list, pointing to the next one."""

    __slots__ = ("value", "next")

    def __init__(self, value: Any, next: Node | None = None) -> None:
        self.value = value
        self.next = next


class SinglyLinkedList:
    """Linked list with head and tail pointers: append and prepend are O(1)."""

    def __init__(self) -> None:
        self._head: Node | None = None
        self._tail: Node | None = None
        self._size = 0

    def append(self, value: Any) -> None:
        """Add a value at the end. O(1) thanks to the tail pointer."""
        node = Node(value)
        if self._tail is None:
            self._head = self._tail = node
        else:
            self._tail.next = node
            self._tail = node
        self._size += 1

    def prepend(self, value: Any) -> None:
        """Add a value at the front. O(1)."""
        node = Node(value, self._head)
        self._head = node
        if self._tail is None:
            self._tail = node
        self._size += 1

    def remove_first(self) -> Any:
        """Remove and return the first value. O(1). Raises IndexError when empty."""
        if self._head is None:
            raise IndexError("remove_first from empty list")
        node = self._head
        self._head = node.next
        if self._head is None:
            self._tail = None
        self._size -= 1
        return node.value

    def first(self) -> Any:
        """Return the first value without removing it. Raises IndexError when empty."""
        if self._head is None:
            raise IndexError("first of empty list")
        return self._head.value

    def __iter__(self) -> Iterator[Any]:
        node = self._head
        while node is not None:
            yield node.value
            node = node.next

    def __len__(self) -> int:
        return self._size
