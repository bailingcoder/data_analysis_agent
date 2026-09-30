"""抽取：MySQL 业务库 -> ClickHouse ODS 贴源层（全量刷新）。"""
import logging
from datetime import datetime

from etl.connections import get_mysql, get_clickhouse

logger = logging.getLogger("data_analysis_agent.etl.extract")

# 源表 -> 目标 ODS 表
TABLES = {
    "customers": "ods_customers",
    "products": "ods_products",
    "orders": "ods_orders",
    "order_items": "ods_order_items",
}

# 每张源表抽取的列（排除 created_at，ODS 用 _etl_loaded_at 替代）
COLUMNS = {
    "customers": ["id", "name", "email", "phone", "city", "register_date"],
    "products": ["id", "name", "category", "price"],
    "orders": ["id", "customer_id", "order_date", "status", "total_amount"],
    "order_items": ["id", "order_id", "product_id", "quantity", "unit_price"],
}


def extract_mysql_to_ods() -> None:
    mysql = get_mysql()
    ch = get_clickhouse()
    # 同一批数据用同一个时间戳，ReplacingMergeTree 靠它去重（增量时才有意义）
    batch_ts = datetime.now()

    try:
        for src, dst in TABLES.items():
            cols = COLUMNS[src]
            with mysql.cursor() as cur:
                cur.execute(f"SELECT {', '.join(cols)} FROM `{src}`")
                rows = cur.fetchall()

            ch.command(f"TRUNCATE TABLE {dst}")   # 全量刷新：先清空

            if rows:
                data = [tuple(r[c] for c in cols) + (batch_ts,) for r in rows]
                ch.insert(dst, data, column_names=cols + ["_etl_loaded_at"])

            logger.info("抽取 %s -> %s: %d 行", src, dst, len(rows))
    finally:
        mysql.close()
        ch.close()
