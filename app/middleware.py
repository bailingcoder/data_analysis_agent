"""中间件拦截链：套在 execute_sql 外面，让「能力」与「安全」解耦。

责任链上每一节单一职责，按序执行：
  执行前（改 SQL 文本 / 拦截）：
    ① 会话限流   ② SQL 白名单（只准 SELECT）  ③ 表白名单（禁内部表）  ④ LIMIT 下推
  执行时（数据库级硬保证）：
    ⑤ readonly=1（写操作被 ClickHouse 直接拒绝）
  执行后（改结果）：
    ⑥ PII 脱敏
"""
import re

from config import settings


class MiddlewareError(Exception):
    """被中间件拦截时抛出。message 会原样返回给 LLM，让它知道为什么被拒、如何修正。"""


# ---- ① 会话限流 ----
class SessionRateLimiter:
    """按 session_id 计数，超过上限就拒绝（防死循环 / 无限烧 token）。"""

    def __init__(self, max_queries: int):
        self.max_queries = max_queries
        self._counters: dict[str, int] = {}

    def check(self, session_id: str) -> None:
        used = self._counters.get(session_id, 0)
        if used >= self.max_queries:
            raise MiddlewareError(
                f"本会话查询已达上限（{self.max_queries} 次），请精简问题或开新会话。"
            )
        self._counters[session_id] = used + 1


# ---- ② SQL 白名单 ----
DANGEROUS_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|RENAME|GRANT|REVOKE|ATTACH|DETACH|KILL|OPTIMIZE|SYSTEM)\b",
    re.IGNORECASE,
)
# re.IGNORECASE的作用：**大小写不敏感匹配**

def _strip_comments(query: str) -> str:
    """去掉注释，防止「SELECT 1 -- 换行 DROP」这类藏在注释里的写操作。"""
    query = re.sub(r"/\*.*?\*/", " ", query, flags=re.DOTALL)   # 块注释
    query = re.sub(r"--[^\n]*", " ", query)                      # 行注释
    return query


def sql_whitelist(query: str) -> str:
    """只允许 SELECT / WITH 开头的单条只读查询。"""
    q = _strip_comments(query).strip().rstrip(";").strip()
    if not q:
        raise MiddlewareError("SQL 为空。")

    first = q.split()[0].upper()
    if first not in {"SELECT", "WITH"}:
        raise MiddlewareError(f"只允许 SELECT 查询，收到以 {first} 开头的语句。")

    m = DANGEROUS_RE.search(q)
    if m:
        raise MiddlewareError(f"检测到危险关键字 {m.group(1).upper()}，已拦截。")
    return q


# ---- ③ 表白名单 ----
FORBIDDEN_TABLE_RE = re.compile(
    r"\b(ods_\w+|meta_tables|meta_columns|system\.\w+)\b",
    re.IGNORECASE,
)


def table_whitelist(query: str) -> str:
    """只允许访问 dwd_/dws_/ads_ 层，禁止 ODS 贴源层和内部元数据表。"""
    m = FORBIDDEN_TABLE_RE.search(query)
    if m:
        raise MiddlewareError(
            f"禁止访问内部表 {m.group(1)}，只能查询 dwd_/dws_/ads_ 层。"
        )
    return query


# ---- ④ LIMIT 下推 ----
def limit_pushdown(query: str) -> str:
    """没有 LIMIT 时自动补上，防止大结果集打爆内存。"""
    if not re.search(r"\bLIMIT\s+\d+", query, re.IGNORECASE):
        query = f"{query} LIMIT {settings.max_result_rows}"
    return query


# ---- ⑥ PII 脱敏 ----
def mask_value(value):
    """遮住敏感值：邮箱保留前缀 + 域名，其余保留前 N 位。"""
    if value is None:
        return None
    s = str(value)
    keep = settings.mask_keep_prefix
    if "@" in s:
        user, _, domain = s.partition("@")
        return f"{user[:keep]}***@{domain}"
    if len(s) <= keep:
        return "*" * len(s)
    return s[:keep] + "*" * (len(s) - keep)


def mask_pii(columns, rows, pii_columns):
    """把结果里命中 is_pii 的列整列脱敏。"""
    if not pii_columns:
        return columns, rows
    idx = [i for i, c in enumerate(columns) if c.lower() in pii_columns]
    if not idx:
        return columns, rows
    masked = []
    for row in rows:
        row = list(row)
        for i in idx:
            row[i] = mask_value(row[i])
        masked.append(tuple(row))
    return columns, masked


# ---- 责任链编排 ----
class SQLMiddleware:
    """把上面各节串成一条链：持有一个连接，缓存 PII 列名，暴露 run()。"""

    def __init__(self, ch_factory):
        self.ch = ch_factory()
        self.limiter = SessionRateLimiter(settings.max_queries_per_session)
        self.pii_columns = self._load_pii_columns()

    def _load_pii_columns(self) -> set[str]:
        rows = self.ch.query(
            "SELECT column_name FROM analytics.meta_columns WHERE is_pii = 1"
        ).result_rows
        return {r[0].lower() for r in rows}

    def run(self, session_id: str, query: str) -> tuple[list, list]:
        # 执行前：限流 + 逐节改写 SQL
        self.limiter.check(session_id)
        query = sql_whitelist(query)
        query = table_whitelist(query)
        query = limit_pushdown(query)

        # 执行时：readonly=1，数据库级只读硬保证（写操作在这里被 ClickHouse 拒绝）
        result = self.ch.query(query, settings={"readonly": 1})

        # 执行后：结果脱敏
        return mask_pii(result.column_names, result.result_rows, self.pii_columns)

