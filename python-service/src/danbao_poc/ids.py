from __future__ import annotations

import time
import uuid


def new_id() -> int:
    now_ms = int(time.time() * 1000)
    rand = uuid.uuid4().int & ((1 << 20) - 1)
    return (now_ms << 20) | rand

