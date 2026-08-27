from __future__ import annotations

import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Iterator


_lock = threading.Lock()
_counters: dict[str, int] = defaultdict(int)
_durations: dict[str, list[float]] = defaultdict(list)


def inc(name: str, amount: int = 1) -> None:
    with _lock:
        _counters[name] += amount


def observe(name: str, seconds: float) -> None:
    with _lock:
        rows = _durations[name]
        rows.append(max(0.0, seconds))
        if len(rows) > 1000:
            del rows[: len(rows) - 1000]


@contextmanager
def timer(name: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        observe(name, time.perf_counter() - start)


def render_prometheus() -> str:
    lines: list[str] = []
    with _lock:
        for name, value in sorted(_counters.items()):
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {value}")
        for name, rows in sorted(_durations.items()):
            if not rows:
                continue
            ordered = sorted(rows)
            p50 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.50))]
            p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
            p99 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))]
            lines.append(f"# TYPE {name}_seconds summary")
            lines.append(f'{name}_seconds{{quantile="0.50"}} {p50:.6f}')
            lines.append(f'{name}_seconds{{quantile="0.95"}} {p95:.6f}')
            lines.append(f'{name}_seconds{{quantile="0.99"}} {p99:.6f}')
            lines.append(f"{name}_seconds_count {len(rows)}")
            lines.append(f"{name}_seconds_sum {sum(rows):.6f}")
    return "\n".join(lines) + "\n"
