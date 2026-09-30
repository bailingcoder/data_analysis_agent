"""填充元数据表：驱动 get_schema / 权限控制 / PII 脱敏。"""
import logging

from etl.connections import get_clickhouse

logger = logging.getLogger("data_analysis_agent.etl.metadata")

# (table_name, layer, business_name, description, update_freq)
META_TABLES = [
    ("dwd_order_detail", "dwd", "订单明细宽表", "订单+客户+商品 join 后的明细，一行=一条订单明细", "daily"),
    ("dws_city_daily_sales", "dws", "城市日销售汇总", "按城市×日期聚合的销售额/订单数/销量", "daily"),
    ("ads_category_sales", "ads", "品类销售指标", "按品类聚合的销售指标，含去重客户数", "daily"),
]

# (table_name, column_name, data_type, business_name, description, is_pii, is_dimension)
META_COLUMNS = [
    ("dwd_order_detail", "order_id", "UInt64", "订单ID", "订单唯一标识", 0, 0),
    ("dwd_order_detail", "order_date", "Date", "下单日期", "订单创建日期", 0, 1),
    ("dwd_order_detail", "order_status", "String", "订单状态", "pending/completed/cancelled", 0, 1),
    ("dwd_order_detail", "customer_id", "UInt64", "客户ID", "客户唯一标识", 0, 0),
    ("dwd_order_detail", "customer_name", "String", "客户姓名", "客户姓名", 0, 0),
    ("dwd_order_detail", "email", "String", "邮箱", "客户邮箱（敏感）", 1, 0),
    ("dwd_order_detail", "phone", "String", "手机号", "客户手机号（敏感）", 1, 0),
    ("dwd_order_detail", "city", "String", "城市", "客户所在城市", 0, 1),
    ("dwd_order_detail", "product_id", "UInt64", "商品ID", "商品唯一标识", 0, 0),
    ("dwd_order_detail", "product_name", "String", "商品名称", "商品名称", 0, 0),
    ("dwd_order_detail", "category", "String", "品类", "商品品类", 0, 1),
    ("dwd_order_detail", "quantity", "UInt32", "数量", "购买数量", 0, 0),
    ("dwd_order_detail", "unit_price", "Decimal(10,2)", "单价", "商品单价", 0, 0),
    ("dwd_order_detail", "line_amount", "Decimal(12,2)", "行金额", "数量×单价", 0, 0),

    ("dws_city_daily_sales", "city", "String", "城市", "客户所在城市", 0, 1),
    ("dws_city_daily_sales", "order_date", "Date", "下单日期", "订单创建日期", 0, 1),
    ("dws_city_daily_sales", "order_count", "UInt64", "订单数", "去重订单数", 0, 0),
    ("dws_city_daily_sales", "total_amount", "Decimal(18,2)", "销售额", "销售额合计", 0, 0),
    ("dws_city_daily_sales", "total_quantity", "UInt64", "销量", "销量合计", 0, 0),

    ("ads_category_sales", "category", "String", "品类", "商品品类", 0, 1),
    ("ads_category_sales", "order_count", "UInt64", "订单数", "去重订单数", 0, 0),
    ("ads_category_sales", "total_amount", "Decimal(18,2)", "销售额", "销售额合计", 0, 0),
    ("ads_category_sales", "total_quantity", "UInt64", "销量", "销量合计", 0, 0),
    ("ads_category_sales", "distinct_customers", "UInt64", "去重客户数", "下单的独立客户数", 0, 0),
]


def load_metadata() -> None:
    ch = get_clickhouse()
    try:
        ch.command("TRUNCATE TABLE analytics.meta_tables")
        ch.command("TRUNCATE TABLE analytics.meta_columns")
        ch.insert("analytics.meta_tables", META_TABLES,
                  column_names=["table_name", "layer", "business_name", "description", "update_freq"])
        ch.insert("analytics.meta_columns", META_COLUMNS,
                  column_names=["table_name", "column_name", "data_type", "business_name",
                                "description", "is_pii", "is_dimension"])
        logger.info("填充元数据: %d 张表 / %d 个字段", len(META_TABLES), len(META_COLUMNS))
    finally:
        ch.close()