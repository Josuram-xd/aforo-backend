import pytest

from structures.singly_linked_list import SinglyLinkedList


def test_append_and_prepend_keep_order():
    items = SinglyLinkedList()
    items.append(2)
    items.append(3)
    items.prepend(1)
    assert list(items) == [1, 2, 3]
    assert len(items) == 3


def test_remove_first_returns_head_and_resets_tail_when_empty():
    items = SinglyLinkedList()
    items.append("a")
    items.append("b")
    assert items.remove_first() == "a"
    assert items.remove_first() == "b"
    items.append("c")  # tail must have been reset
    assert list(items) == ["c"]


def test_empty_list_raises():
    items = SinglyLinkedList()
    with pytest.raises(IndexError):
        items.remove_first()
    with pytest.raises(IndexError):
        items.first()


def test_first_does_not_remove():
    items = SinglyLinkedList()
    items.append(1)
    assert items.first() == 1
    assert len(items) == 1
