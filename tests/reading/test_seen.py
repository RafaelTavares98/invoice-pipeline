"""Knowing a document was seen must not get slower as the store grows.

The store remembered every hash in a list, so each check walked the whole
list. Ten thousand documents made each check ten thousand comparisons.
"""

import time

from reading import intake


def test_seen_hashes_are_checked_in_constant_time(tmp_path):
    store = intake.Store(tmp_path)
    for n in range(50_000):
        store._remember(f'{n:064x}')

    began = time.perf_counter()
    for _ in range(2_000):
        f'{49_999:064x}' in store.seen
    took = time.perf_counter() - began

    assert isinstance(store.seen, set)
    assert took < 0.05


def test_the_seen_hashes_survive_a_save(tmp_path):
    store = intake.Store(tmp_path)
    store._remember('a' * 64)
    store.save()

    assert 'a' * 64 in intake.Store(tmp_path).seen
