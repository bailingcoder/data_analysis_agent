import uuid

import pytest

from app.middleware import MiddlewareError, RedisRateLimiter
from app.redis_client import get_redis

pytestmark = pytest.mark.integration


def test_blocks_after_max():
    sid = f"test_{uuid.uuid4().hex}"
    limiter = RedisRateLimiter(max_queries=2, window_seconds=60, redis_factory=get_redis)
    limiter.check(sid)
    limiter.check(sid)
    with pytest.raises(MiddlewareError):
        limiter.check(sid)             # 第 3 次超限
    get_redis().delete(limiter._key(sid))   # 清理测试 key