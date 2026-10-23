"""工具层测试：get_schema / execute_sql，全部用 mock 替代数据库。"""

from app import tools
from app.middleware import MiddlewareError


# ---------- get_schema ----------
class TestGetSchema:
    def test_list_tables(self, monkeypatch, fake_ch):
        fake_ch.query.return_value.result_rows = [
            ("dwd_order_detail", "dwd", "订单明细宽表", "订单+客户+商品 join"),
            ("ads_category_sales", "ads", "品类销售指标", "按品类聚合"),
        ]
        monkeypatch.setattr(tools, "get_clickhouse", lambda: fake_ch)

        result = tools.get_schema.invoke({})

        assert "dwd_order_detail" in result
        assert "订单明细宽表" in result
        fake_ch.close.assert_called_once()            # finally 里关连接

    def test_list_tables_query_text(self, monkeypatch, fake_ch):
        fake_ch.query.return_value.result_rows = []
        monkeypatch.setattr(tools, "get_clickhouse", lambda: fake_ch)

        tools.get_schema.invoke({})

        sql = fake_ch.query.call_args.args[0]         # 校验发给 CH 的 SQL
        assert "meta_tables" in sql
        assert "ORDER BY table_name" in sql

    def test_one_table_passes_parameter(self, monkeypatch, fake_ch):
        fake_ch.query.return_value.result_rows = [
            ("email", "String", "邮箱", "客户邮箱（敏感）", 1, 0),
            ("city", "String", "城市", "客户所在城市", 0, 1),
        ]
        monkeypatch.setattr(tools, "get_clickhouse", lambda: fake_ch)

        result = tools.get_schema.invoke({"table_name": "dwd_order_detail"})

        assert "email" in result
        assert "敏感" in result
        # 关键：参数化查询，table_name 通过 parameters 传入（不是字符串拼接）
        assert fake_ch.query.call_args.kwargs["parameters"] == {"t": "dwd_order_detail"}

    def test_unknown_table(self, monkeypatch, fake_ch):
        fake_ch.query.return_value.result_rows = []
        monkeypatch.setattr(tools, "get_clickhouse", lambda: fake_ch)

        result = tools.get_schema.invoke({"table_name": "nope"})

        assert "未找到表 nope" in result


# ---------- execute_sql ----------
class TestExecuteSql:
    def test_returns_tab_separated(self, monkeypatch):
        monkeypatch.setattr(
            tools._middleware, "run",
            lambda session_id, query: (["city", "total"], [("北京", 100), ("上海", 200)]),
        )

        result = tools.execute_sql.invoke({"query": "SELECT city, total FROM t"})

        assert "city\ttotal" in result
        assert "北京\t100" in result
        assert "上海\t200" in result

    def test_intercepted(self, monkeypatch):
        def boom(session_id, query):
            raise MiddlewareError("只允许 SELECT")
        monkeypatch.setattr(tools._middleware, "run", boom)

        result = tools.execute_sql.invoke({"query": "DROP TABLE x"})

        assert result.startswith("[已拦截]")
        assert "只允许 SELECT" in result

    def test_passes_session_id(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            tools._middleware, "run",
            lambda sid, q: (captured.setdefault("sid", sid), [] ) or ([], []),
        )

        tools.execute_sql.invoke({"query": "SELECT 1"})

        assert captured["sid"] == "pytest_session"   # 由 isolated_session fixture 注入