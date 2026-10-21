import pytest

from app.middleware import (
    MiddlewareError,
    sql_whitelist,
    table_whitelist,
    limit_pushdown,
    mask_value,
    mask_pii,
)


class TestSqlWhitelist:
    def test_select_passes(self):
        assert sql_whitelist("SELECT * FROM dwd_order_detail")

    def test_with_passes(self):
        assert sql_whitelist("WITH t AS (SELECT 1) SELECT * FROM t")

    def test_clickhouse_syntax_passes(self):
        # 验证 read="clickhouse" 生效（countDistinct 是 CH 专有函数）
        assert sql_whitelist("SELECT countDistinct(order_id) FROM dws_city_daily_sales")

    def test_literal_drop_not_blocked(self):
        # 字符串里的 DROP 是字面量，不应误杀
        assert sql_whitelist("SELECT 'DROP TABLE' AS msg")

    def test_insert_blocked(self):
        with pytest.raises(MiddlewareError,match="INSERT"):
            sql_whitelist("INSERT INTO t VALUES (1)")

    def test_multi_statement_blocked(self):
        with pytest.raises(MiddlewareError,match="DROP"):
            sql_whitelist("SELECT 1; DROP TABLE x")

    def test_empty_blocked(self):
        with pytest.raises(MiddlewareError,match="SQL 为空"):
            sql_whitelist("   ")


class TestTableWhitelist:
    def test_ods_blocked(self):
        with pytest.raises(MiddlewareError,match="ods"):
            table_whitelist("SELECT * FROM ods_orders")

    def test_system_blocked(self):
        with pytest.raises(MiddlewareError,match="system"):
            table_whitelist("SELECT * FROM system.tables")

    def test_dwd_passes(self):
        assert table_whitelist("SELECT * FROM dwd_order_detail")

    def test_literal_not_blocked(self):
        # 字符串字面量里的表名不应误杀
        assert table_whitelist("SELECT * FROM dwd_order_detail WHERE note = 'ods_orders'")


class TestLimitPushdown:
    def test_adds_limit(self):
        assert limit_pushdown("SELECT * FROM t") == "SELECT * FROM t LIMIT 100"

    def test_keeps_existing_limit(self):
        assert limit_pushdown("SELECT * FROM t LIMIT 10") == "SELECT * FROM t LIMIT 10"


class TestMaskValue:
    def test_email_masked(self):
        assert mask_value("zhangsan@example.com") == "zh***@example.com"

    def test_none(self):
        assert mask_value(None) is None

    def test_short_value_fully_masked(self):
        assert mask_value("ab") == "**"

    def test_phone_masked(self):
        assert mask_value("13812345678") == "13*********"


class TestMaskPii:
    def test_masks_only_pii_column(self):
        cols = ["city", "email"]
        rows = [("北京", "a@b.com")]
        _, new_rows = mask_pii(cols, rows, {"email"})
        assert new_rows[0][0] == "北京"          # city 不动
        assert new_rows[0][1] != "a@b.com"       # email 被脱敏