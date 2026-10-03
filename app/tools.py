"""工具层：get_schema / execute_sql / execute_python。

这三个函数用 @tool 装饰后，docstring 会变成 LLM 的「函数说明」——
LLM 就是靠读这段中文说明，决定什么时候该调哪个工具、传什么参数。
所以 docstring 写得越清楚，Agent 用得越准。
"""
import subprocess
import sys

from langchain_core.tools import tool

from config import settings, session_id_var
from app.db import get_clickhouse
from app.middleware import MiddlewareError, SQLMiddleware


_middleware = SQLMiddleware(get_clickhouse)

@tool
def get_schema(table_name: str = "") -> str:
    """获取数据仓库的表结构（业务字典）。

    不传 table_name 时，返回所有可用表清单（表名/分层/中文名/说明）。
    传入 table_name 时，返回该表的字段详情（字段名/类型/中文名/说明/是否敏感/是否维度）。
    写 SQL 之前必须先调它，搞清楚有哪些表和字段、字段的中文含义。
    """
    ch = get_clickhouse()
    try:
        if not table_name:
            rows = ch.query(
                "SELECT table_name, layer, business_name, description "
                "FROM analytics.meta_tables ORDER BY table_name"
            ).result_rows
            lines = ["可用表："]
            for name, layer, biz, desc in rows:
                lines.append(f"- {name} [{layer}] {biz}：{desc}")
            return "\n".join(lines)

        rows = ch.query(
            "SELECT column_name, data_type, business_name, description, is_pii, is_dimension "
            "FROM analytics.meta_columns WHERE table_name = %(t)s ORDER BY column_name",
            parameters={"t": table_name},
        ).result_rows
        if not rows:
            return f"未找到表 {table_name}。先调用 get_schema() 看可用表清单。"
        lines = [f"表 {table_name} 的字段："]
        for col, dtype, biz, desc, pii, dim in rows:
            tags = []
            if pii:
                tags.append("敏感")
            if dim:
                tags.append("维度")
            tag = f" [{'/'.join(tags)}]" if tags else ""
            lines.append(f"- {col} {dtype} {biz}：{desc}{tag}")
        return "\n".join(lines)
    finally:
        ch.close()


@tool
def execute_sql(query: str) -> str:
    """对 ClickHouse 数据仓库执行只读 SQL 查询，返回结果集。

    query 是一条 SELECT 语句。返回制表符分隔的表格文本。
    结果超过 max_result_rows 行时会被截断。
    """
    try:
        columns,rows = _middleware.run(session_id_var.get(),query)
    except MiddlewareError as e:
        return f"[已拦截] {e}"
    lines = ["\t".join(columns)]
    lines += ["\t".join(str(v) for v in row) for row in rows]
    return "\n".join(lines)



