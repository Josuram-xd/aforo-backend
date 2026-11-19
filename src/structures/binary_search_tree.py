"""Binary search tree keyed by string.

Domain use: course roster. Students are inserted with a normalised name as key, so the
in-order traversal is the alphabetical roster and ``prefix_range`` answers "name starts
with ..." searches without scanning every student.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


class _TreeNode:
    __slots__ = ("key", "value", "left", "right")

    def __init__(self, key: str, value: Any) -> None:
        self.key = key
        self.value = value
        self.left: _TreeNode | None = None
        self.right: _TreeNode | None = None


class BinarySearchTree:
    """Unbalanced BST. Equal keys are allowed and go to the right subtree.

    shortcut: no self-balancing, so sorted input degrades to O(n) height; fine for a
    course roster (tens of students) read in arbitrary order, upgrade to AVL/red-black
    if rosters grow large. All traversals are iterative to avoid recursion limits.
    """

    def __init__(self) -> None:
        self._root: _TreeNode | None = None
        self._size = 0

    def insert(self, key: str, value: Any) -> None:
        """Insert a key/value pair. O(h)."""
        node = _TreeNode(key, value)
        self._size += 1
        if self._root is None:
            self._root = node
            return
        current = self._root
        while True:
            if key < current.key:
                if current.left is None:
                    current.left = node
                    return
                current = current.left
            else:
                if current.right is None:
                    current.right = node
                    return
                current = current.right

    def search(self, key: str) -> Any | None:
        """Return the value of the first node found with this key, or None. O(h)."""
        current = self._root
        while current is not None:
            if key == current.key:
                return current.value
            current = current.left if key < current.key else current.right
        return None

    def in_order(self) -> Iterator[Any]:
        """Yield every value sorted by key. O(n)."""
        stack: list[_TreeNode] = []
        current = self._root
        while stack or current is not None:
            while current is not None:
                stack.append(current)
                current = current.left
            current = stack.pop()
            yield current.value
            current = current.right

    def prefix_range(self, prefix: str) -> Iterator[Any]:
        """Yield, sorted, the values whose key starts with ``prefix``.

        Prunes subtrees that cannot contain matches: O(h + k) for k results.
        """
        stack: list[_TreeNode] = []
        current = self._root
        while stack or current is not None:
            while current is not None:
                stack.append(current)
                # Left keys are < current.key: skip them when current.key is already < prefix.
                current = current.left if current.key >= prefix else None
            current = stack.pop()
            if current.key.startswith(prefix):
                yield current.value
            # Right keys are >= current.key: stop once past the whole prefix block.
            current = None if current.key[: len(prefix)] > prefix else current.right

    def height(self) -> int:
        """Number of levels (0 for an empty tree). O(n)."""
        best = 0
        pending = [(self._root, 1)] if self._root else []
        while pending:
            node, depth = pending.pop()
            best = max(best, depth)
            for child in (node.left, node.right):
                if child is not None:
                    pending.append((child, depth + 1))
        return best

    def __len__(self) -> int:
        return self._size
