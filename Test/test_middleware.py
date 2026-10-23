import pytest
import redis
from unittest.mock import MagicMock

from app.middleware import RedisRateLimiter, SQLMiddleware, MiddlewareError


class TestRedisRateLimiter:
    """限流器：用 redis_factory 注入假 Redis，验证计数/过期/超限/fail-closed。"""

    def _make(self, max_queries=2):
        fake_redis = MagicMock()
        limiter = RedisRateLimiter(max_queries, 60, lambda: fake_redis)
        return limiter, fake_redis

    def test_first_call_sets_ttl(self):
        limiter, fake = self._make()
        fake.incr.return_value = 1
        limiter.check("s1")
        fake.expire.assert_called_once_with("rate_limit:s1", 60)

    def test_later_calls_do_not_reset_ttl(self):
        limiter, fake = self._make()
        fake.incr.return_value = 2
        limiter.check("s1")
        fake.expire.assert_not_called()

    def test_blocks_over_limit(self):
        limiter, fake = self._make()
        fake.incr.return_value = 3
        with pytest.raises(MiddlewareError, match="已达上限"):
            limiter.check("s1")

    def test_fail_closed_on_redis_error(self):
        limiter, fake = self._make()
        fake.incr.side_effect = redis.RedisError("down")
        with pytest.raises(MiddlewareError, match="限流服务不可用"):
            limiter.check("s1")

    def test_key_format(self):
        limiter, _ = self._make()
        assert limiter._key("abc") == "rate_limit:abc"


class TestSQLMiddleware:
    """责任链整体：验证 run() 把「限流→白名单→LIMIT→只读→脱敏」串起来。"""

    def _make(self, pii_columns=("email", "phone")):
        fake_ch = MagicMock()
        # __init__ 里的 _load_pii_columns 会查 meta_columns，返回 PII 列名
        fake_ch.query.return_value.result_rows = [(c,) for c in pii_columns]
        mw = SQLMiddleware(lambda: fake_ch)
        mw.limiter = MagicMock()          # 换掉真实限流器，单测不碰 Redis
        fake_ch.query.reset_mock()        # 清掉 __init__ 那次查询的调用记录
        return mw, fake_ch

    def test_run_masks_pii_and_pushes_limit(self):
        mw, fake_ch = self._make()
        fake_ch.query.return_value.column_names = ["city", "email"]
        fake_ch.query.return_value.result_rows = [("北京", "a@b.com")]

        cols, rows = mw.run("s1", "SELECT city, email FROM dwd_order_detail")

        assert cols == ["city", "email"]
        assert rows[0] == ("北京", "a***@b.com")      # email 被脱敏
        # 只读设置 + LIMIT 下推都生效
        fake_ch.query.assert_called_once_with(
            "SELECT city, email FROM dwd_order_detail LIMIT 100",
            settings={"readonly": 1},
        )

    def test_run_blocks_bad_table(self):
        mw, fake_ch = self._make()
        with pytest.raises(MiddlewareError, match="ods"):
            mw.run("s1", "SELECT * FROM ods_orders")
        fake_ch.query.assert_not_called()             # 拦截后根本不执行查询