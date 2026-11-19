import pytest

from structures.doubly_linked_list import DoublyLinkedList


def make(values):
    items = DoublyLinkedList()
    for value in values:
        items.append(value)
    return items


def test_append_prepend_and_both_iterations():
    items = make([2, 3])
    items.prepend(1)
    assert list(items) == [1, 2, 3]
    assert list(items.iter_backward()) == [3, 2, 1]
    assert len(items) == 3


def test_remove_head_middle_tail():
    items = DoublyLinkedList()
    nodes = [items.append(v) for v in (1, 2, 3, 4)]
    items.remove(nodes[1])
    items.remove(nodes[0])
    items.remove(nodes[3])
    assert list(items) == [3]
    assert list(items.iter_backward()) == [3]
    items.remove(nodes[2])
    assert len(items) == 0
    items.append(9)
    assert list(items) == [9]


def test_find():
    items = make([1, 2, 3])
    assert items.find(lambda v: v == 2).value == 2
    assert items.find(lambda v: v == 7) is None


def test_window_next_from_start_and_cursor():
    items = make(range(1, 8))
    first = items.window(None, "next", 3)
    assert (first.items, first.has_prev, first.has_next) == ([1, 2, 3], False, True)
    second = items.window(3, "next", 3)
    assert (second.items, second.has_prev, second.has_next) == ([4, 5, 6], True, True)
    last = items.window(6, "next", 3)
    assert (last.items, last.has_prev, last.has_next) == ([7], True, False)


def test_window_prev_returns_forward_order():
    items = make(range(1, 8))
    tail = items.window(None, "prev", 3)
    assert (tail.items, tail.has_prev, tail.has_next) == ([5, 6, 7], True, False)
    before = items.window(5, "prev", 3)
    assert (before.items, before.has_prev, before.has_next) == ([2, 3, 4], True, True)
    start = items.window(2, "prev", 3)
    assert (start.items, start.has_prev, start.has_next) == ([1], False, True)


def test_window_with_key_and_errors():
    items = make([{"id": "a"}, {"id": "b"}])
    assert items.window("a", "next", 5, key=lambda v: v["id"]).items == [{"id": "b"}]
    with pytest.raises(KeyError):
        items.window("zzz", "next", 5, key=lambda v: v["id"])
    with pytest.raises(ValueError):
        items.window(None, "sideways", 5)


def test_window_on_empty_list():
    window = DoublyLinkedList().window(None, "next", 5)
    assert (window.items, window.has_prev, window.has_next) == ([], False, False)
