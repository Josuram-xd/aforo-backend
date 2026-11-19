import pytest

from structures.queue import Queue


def test_fifo_order():
    queue = Queue()
    for value in "abc":
        queue.enqueue(value)
    assert queue.peek() == "a"
    assert [queue.dequeue(), queue.dequeue(), queue.dequeue()] == ["a", "b", "c"]
    assert queue.is_empty()


def test_iteration_does_not_consume():
    queue = Queue()
    queue.enqueue(1)
    queue.enqueue(2)
    assert list(queue) == [1, 2]
    assert len(queue) == 2


def test_empty_queue_raises():
    queue = Queue()
    with pytest.raises(IndexError):
        queue.dequeue()
    with pytest.raises(IndexError):
        queue.peek()
