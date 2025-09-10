from __future__ import annotations
from collections import OrderedDict
from typing import Generic, TypeVar

K = TypeVar('K')
V = TypeVar('V')

class LRUCache(Generic[K, V]):
    def __init__(self, maxsize: int = 128):
        self.maxsize = maxsize
        self._store: OrderedDict[K, V] = OrderedDict()

    def get(self, key: K) -> V | None:
        if key not in self._store:
            return None
        val = self._store.pop(key)
        self._store[key] = val
        return val

    def set(self, key: K, value: V) -> None:
        if key in self._store:
            self._store.pop(key)
        elif len(self._store) >= self.maxsize:
            self._store.popitem(last=False)
        self._store[key] = value

    def __len__(self):  # pragma: no cover
        return len(self._store)
