import pytest

from app.tools import get_schema, execute_sql
from unittest.mock import MagicMock

pytestmark = pytest.mark.integration


def test_get_schema_list():
    # 1) 造一个假连接，让它"查 meta_tables"时返回一行假数据
    fake_ch = MagicMock()
    fake_ch.query.return_value.result_rows = [
        ("dwd_order_detail", "dwd", "订单明细宽表", "订单+客户+商品 join"),
    ]

    # 2) 把 get_clickhouse 换成"返回假连接"的函数
    monkeypatch.setattr("app.tools.get_clickhouse", lambda: fake_ch)

    # 3) 正常调用被测函数，它拿到的其实是假连接
    result = get_schema.invoke({})

    assert "dwd_order_detail" in result
    assert "订单明细宽表" in result

def test_get_schema_table():
    result = get_schema.invoke({"table_name": "dwd_order_detail"})
    assert "email" in result


def test_execute_sql(isolated_session):
    result = execute_sql.invoke(
        {"query": "SELECT * FROM analytics.ads_category_sales ORDER BY total_amount DESC"}
    )
    assert "category" in result        # 表头


def test_execute_sql_pii_masked(isolated_session):
    result = execute_sql.invoke(
        {"query": "SELECT email, phone FROM dwd_order_detail LIMIT 3"}
    )
    assert "@" in result               # 仍是邮箱格式
    assert "***" in result             # 但已脱敏