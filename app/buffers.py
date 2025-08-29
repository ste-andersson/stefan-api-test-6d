from collections import deque
from typing import Any, Deque, Dict, List
import time


class RingLog:
    '''Minimal in-memory ring buffer for observability endpoints.'''
    def __init__(self, capacity: int = 200):
        self.capacity = capacity
        self._dq: Deque[Dict[str, Any]] = deque(maxlen=capacity)

    def add(self, item: Dict[str, Any]) -> None:
        self._dq.append(item)

    def latest(self, limit: int = 50) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        return list(self._dq)[-limit:]

    def __len__(self) -> int:
        return len(self._dq)


def now_s() -> float:
    return time.time()
