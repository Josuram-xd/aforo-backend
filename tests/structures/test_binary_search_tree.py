import random

from structures.binary_search_tree import BinarySearchTree

WORDS = ["maria", "ana", "andres", "ana", "pedro", "anibal", "zoe", "mario", "b", "a"]


def build(words):
    tree = BinarySearchTree()
    for word in words:
        tree.insert(word, word)
    return tree


def test_in_order_is_sorted_and_keeps_duplicates():
    tree = build(WORDS)
    assert list(tree.in_order()) == sorted(WORDS)
    assert len(tree) == len(WORDS)


def test_search():
    tree = build(WORDS)
    assert tree.search("pedro") == "pedro"
    assert tree.search("nobody") is None


def test_prefix_range_matches_linear_filter():
    tree = build(WORDS)
    assert list(tree.prefix_range("an")) == ["ana", "ana", "andres", "anibal"]
    assert list(tree.prefix_range("ma")) == ["maria", "mario"]
    assert list(tree.prefix_range("x")) == []
    assert list(tree.prefix_range("")) == sorted(WORDS)


def test_prefix_range_randomised_against_filter():
    rng = random.Random(7)
    words = ["".join(rng.choice("abc") for _ in range(rng.randint(1, 5))) for _ in range(200)]
    tree = build(words)
    for prefix in ("a", "ab", "abc", "ca", "cc", "b"):
        assert list(tree.prefix_range(prefix)) == sorted(w for w in words if w.startswith(prefix))


def test_height():
    assert BinarySearchTree().height() == 0
    assert build(["b"]).height() == 1
    assert build(["b", "a", "c"]).height() == 2
    assert build(["a", "b", "c", "d"]).height() == 4  # degenerate, sorted input


def test_deep_tree_does_not_hit_recursion_limit():
    tree = build([f"{i:05d}" for i in range(3000)])
    assert tree.height() == 3000
    assert len(list(tree.in_order())) == 3000
