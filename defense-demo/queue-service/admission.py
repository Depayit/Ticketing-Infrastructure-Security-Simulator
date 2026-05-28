import time
from shared.config import ADMISSION_RATE
from shared.redis_client import r


def _window_key() -> str:
    return f"defense:admission:{int(time.time())}"


def try_admit() -> bool:
    key = _window_key()
    count = r.incr(key)
    if count == 1:
        r.expire(key, 2)
    return count <= ADMISSION_RATE
