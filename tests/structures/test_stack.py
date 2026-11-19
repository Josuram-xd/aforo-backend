import pytest

from structures.stack import Stack


def test_lifo_order():
    stack = Stack()
    for value in (1, 2, 3):
        stack.push(value)
    assert stack.peek() == 3
    assert len(stack) == 3
    assert [stack.pop(), stack.pop(), stack.pop()] == [3, 2, 1]
    assert stack.is_empty()


def test_iteration_goes_top_to_bottom():
    stack = Stack()
    stack.push("a")
    stack.push("b")
    assert list(stack) == ["b", "a"]


def test_empty_stack_raises():
    stack = Stack()
    with pytest.raises(IndexError):
        stack.pop()
    with pytest.raises(IndexError):
        stack.peek()
