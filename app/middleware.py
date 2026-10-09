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
import sqlglot
from sqlglot import exp
import redis

from config import settings
from app.redis_client import get_redis


class MiddlewareError(Exception):
    """被中间件拦截时抛出。message 会原样返回给 LLM，让它知道为什么被拒、如何修正。"""


# ---- ① 会话限流（Redis 固定窗口版）----
class RedisRateLimiter:
    """按 session_id 的固定窗口限流，计数器存 Redis（多实例共享 + INCR 原子 + TTL 自动过期）。"""

    def __init__(self, max_queries: int, window_seconds: int, redis_factory):
        self.max_queries = max_queries
        self.window_seconds = window_seconds
        self.redis = redis_factory()

    def _key(self, session_id: str) -> str:
        return f"rate_limit:{session_id}"          # 前缀命名空间，避免和别的 key 撞

    def check(self, session_id: str) -> None:
        key = self._key(session_id)
        try:
            used = self.redis.incr(key)            # 原子自增，返回自增后的值
            if used == 1:
                self.redis.expire(key, self.window_seconds)   # 首次计数才设 TTL
        except redis.RedisError as e:
            # fail-closed：Redis 挂了宁可拒绝，也不能失去限流保护
            raise MiddlewareError(f"限流服务不可用：{e}")
        if used > self.max_queries:
            raise MiddlewareError(
                f"本会话在 {self.window_seconds} 秒内查询已达上限（{self.max_queries} 次），请稍后再试。"
            )


# ---- ② SQL 白名单（AST 版）----
# 只允许 SELECT / UNION / WITH...SELECT 这类只读查询。
# 根节点必须是 Select 或 Union；其余语句（Insert/Update/Drop/Create/...）一律拒绝。
_ALLOWED_STMT = (exp.Select, exp.Union)


def sql_whitelist(query: str) -> str:
    """用 sqlglot 解析成 AST，只放行根节点为 SELECT / UNION 的只读查询。"""
    try:
        statements = sqlglot.parse(query, read="clickhouse")
    except sqlglot.errors.ParseError as e:
        raise MiddlewareError(f"SQL 无法解析：{e}")

    # 过滤掉 None 节点
    statements = [s for s in statements if s is not None]
    if not statements:
        raise MiddlewareError("SQL 为空。")

    for stmt in statements:
        if not isinstance(stmt, _ALLOWED_STMT):
            kind = stmt.key or type(stmt).__name__  # 如 insert / drop / create
            raise MiddlewareError(f"只允许 SELECT 查询，检测到 {kind.upper()} 语句，已拦截。")

    return query


# ---- ③ 表白名单（AST 版）----
def table_whitelist(query: str) -> str:
    """遍历 AST 里所有被引用的表，禁止 ods_/meta_ 前缀和 system 库。"""
    try:
        statement = sqlglot.parse_one(query, read="clickhouse")
    except sqlglot.errors.ParseError as e:
        raise MiddlewareError(f"SQL 无法解析：{e}")

    for table in statement.find_all(exp.Table):
        # 拼出完整引用（如 analytics.ods_orders / system.tables）
        ref = ".".join(p for p in (table.catalog, table.db, table.name) if p)
        segs = ref.lower().split(".")
        if segs[0] == "system" or any(s.startswith(("ods_", "meta_")) for s in segs):
            raise MiddlewareError(f"禁止访问内部表 {ref}，只能查询 dwd_/dws_/ads_ 层。")
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
        self.limiter = RedisRateLimiter(
            settings.max_queries_per_session,
            settings.rate_limit_window_seconds,
            get_redis
        )
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

