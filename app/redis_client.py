"""Redis 连接（限流器共用）。"""
import redis
from config import settings

_pool = redis.ConnectionPool(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password,
    db=settings.redis_db,
    decode_responses=True
)

def get_redis():
    return redis.Redis(connection_pool=_pool)