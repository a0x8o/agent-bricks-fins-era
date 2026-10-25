"""In-process TTL cache keyed by (identity, endpoint, params).

OBO results are never shared across users — the identity is part of the key.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

_MAX = 512
_store: OrderedDict[tuple, tuple[float, Any]] = OrderedDict()


def get(key: tuple, ttl: int) -> tuple[bool, Any]:
    item = _store.get(key)
    if item is None:
        return False, None
    ts, val = item
    if time.monotonic() - ts > ttl:
        _store.pop(key, None)
        return False, None
    _store.move_to_end(key)
    return True, val


def put(key: tuple, val: Any) -> None:
    _store[key] = (time.monotonic(), val)
    _store.move_to_end(key)
    while len(_store) > _MAX:
        _store.popitem(last=False)


def clear() -> None:
    _store.clear()
