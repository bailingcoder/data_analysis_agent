"""转换：ODS -> DWD 宽表 -> DWS 汇总 -> ADS 指标（都在 ClickHouse 内 INSERT SELECT）。"""
import logging

from .connections import get_clickhouse

logger = logging.getLogger("data_analysis_agent.etl.transform")

DWD_SQL = """
INSERT INTO analytics.dwd_order_detail
SELECT
    o.id AS order_id,
    o.order_date,
    o.status AS order_status,
    o.customer_id,
    c.name AS customer_name,
    c.email,
    c.phone,
    c.city,
    p.id AS product_id,
    p.name AS product_name,
    p.category,
    oi.quantity,
    oi.unit_price,
    oi.quantity * oi.unit_price AS line_amount
FROM analytics.ods_orders AS o
JOIN analytics.ods_order_items AS oi ON o.id = oi.order_id
JOIN analytics.ods_customers AS c ON o.customer_id = c.id
JOIN analytics.ods_products AS p ON oi.product_id = p.id
"""

DWS_SQL = """
INSERT INTO analytics.dws_city_daily_sales
SELECT
    city,
    order_date,
    countDistinct(order_id) AS order_count,
    sum(line_amount) AS total_amount,
    sum(quantity) AS total_quantity
FROM analytics.dwd_order_detail
GROUP BY city, order_date
"""

ADS_SQL = """
INSERT INTO analytics.ads_category_sales
SELECT
    category,
    countDistinct(order_id) AS order_count,
    sum(line_amount) AS total_amount,
    sum(quantity) AS total_quantity,
    countDistinct(customer_id) AS distinct_customers
FROM analytics.dwd_order_detail
GROUP BY category
"""


def _count(ch, table: str) -> int:
    return ch.query(f"SELECT count() FROM {table}").result_rows[0][0]


def build_dwd() -> None:
    ch = get_clickhouse()
    try:
        ch.command("TRUNCATE TABLE analytics.dwd_order_detail")
        ch.command(DWD_SQL)
        logger.info("构建 DWD 宽表: %d 行", _count(ch, "analytics.dwd_order_detail"))
    finally:
        ch.close()


def build_dws() -> None:
    ch = get_clickhouse()
    try:
        ch.command("TRUNCATE TABLE analytics.dws_city_daily_sales")
        ch.command(DWS_SQL)
        logger.info("构建 DWS 汇总: %d 行", _count(ch, "analytics.dws_city_daily_sales"))
    finally:
        ch.close()


def build_ads() -> None:
    ch = get_clickhouse()
    try:
        ch.command("TRUNCATE TABLE analytics.ads_category_sales")
        ch.command(ADS_SQL)
        logger.info("构建 ADS 指标: %d 行", _count(ch, "analytics.ads_category_sales"))
    finally:
        ch.close()