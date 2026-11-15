import pytest

from craftpipe.signal import container_signal


@pytest.mark.parametrize("slots,stacks,want", [
    (27, [], 0),
    (27, [(1, 64)], 1),
    (27, [(64, 64)] * 27, 15),
    (27, [(64, 64)] * 13 + [(32, 64)], 8),
    (5, [(16, 16)], 3),
    (27, [(0, 64)], 0),
    (3, [(64, 64)], 5),
    (9, [(1, 1)] * 9, 15),
    (54, [(64, 64)] * 27, 8),
])
def test_container_signal(slots, stacks, want):
    assert container_signal(slots, stacks) == want


def test_signal_is_monotone_in_item_count():
    last = 0
    for items in range(0, 27 * 64 + 1):
        full, rest = divmod(items, 64)
        stacks = [(64, 64)] * full + ([(rest, 64)] if rest else [])
        now = container_signal(27, stacks)
        assert now >= last
        last = now
    assert last == 15


def test_overfull_stack_is_capped():
    assert container_signal(1, [(99, 64)]) == 15
