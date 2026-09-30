-- ============================================================
-- ClickHouse 数据仓库分层建表
-- 数据库: analytics   分层: ODS -> DWD -> DWS -> ADS
-- ============================================================
CREATE DATABASE IF NOT EXISTS analytics;

-- ============================================================
-- ODS 贴源层：与 MySQL 结构对齐，加 _etl_loaded_at 抽取时间戳
-- ReplacingMergeTree(version) 按时间戳保留最新行 → 重跑 ETL 幂等
-- ============================================================
CREATE TABLE analytics.ods_customers (
    id             UInt64,
    name           String,
    email          String,
    phone          String,
    city           String,
    register_date  Date,
    _etl_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_etl_loaded_at)
ORDER BY id;

CREATE TABLE analytics.ods_products (
    id             UInt64,
    name           String,
    category       String,
    price          Decimal(10, 2),
    _etl_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_etl_loaded_at)
ORDER BY id;

CREATE TABLE analytics.ods_orders (
    id             UInt64,
    customer_id    UInt64,
    order_date     Date,
    status         String,
    total_amount   Decimal(12, 2),
    _etl_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_etl_loaded_at)
PARTITION BY toYYYYMM(order_date)
ORDER BY id;

CREATE TABLE analytics.ods_order_items (
    id             UInt64,
    order_id       UInt64,
    product_id     UInt64,
    quantity       UInt32,
    unit_price     Decimal(10, 2),
    _etl_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_etl_loaded_at)
ORDER BY id;

-- ============================================================
-- DWD 明细宽表：订单 + 客户 + 商品 join 成一行（清洗、标准化）
-- 排序键按最常过滤/分组的字段：order_date -> category -> city
-- ============================================================
CREATE TABLE analytics.dwd_order_detail (
    order_id      UInt64,
    order_date    Date,
    order_status  String,
    customer_id   UInt64,
    customer_name String,
    email         String,          -- 原始 PII，仅内部分析用
    phone         String,          -- 原始 PII，仅内部分析用
    city          String,
    product_id    UInt64,
    product_name  String,
    category      String,
    quantity      UInt32,
    unit_price    Decimal(10, 2),
    line_amount   Decimal(12, 2)   -- quantity * unit_price
) ENGINE = MergeTree
PARTITION BY toYYYYMM(order_date)
ORDER BY (order_date, category, city);

-- ============================================================
-- DWS 汇总层：城市 × 日期 预聚合
-- SummingMergeTree：相同 (city, order_date) 的数值列自动求和
-- ============================================================
CREATE TABLE analytics.dws_city_daily_sales (
    city           String,
    order_date     Date,
    order_count    UInt64,          -- 订单数
    total_amount   Decimal(18, 2),  -- 销售额
    total_quantity UInt64           -- 销量
) ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(order_date)
ORDER BY (city, order_date);

-- ============================================================
-- ADS 应用层：面向分析 Agent 的品类指标（最终口径）
-- 去重客户数这类 Summing 无法处理的指标放这里，ETL 算好写入
-- ============================================================
CREATE TABLE analytics.ads_category_sales (
    category           String,
    order_count        UInt64,
    total_amount       Decimal(18, 2),
    total_quantity     UInt64,
    distinct_customers UInt64        -- 去重客户数
) ENGINE = MergeTree
ORDER BY category;

-- ============================================================
-- 元数据表：驱动 get_schema / 权限控制 / PII 脱敏
-- ============================================================
CREATE TABLE analytics.meta_tables (
    table_name    String,
    layer         String,     -- ods / dwd / dws / ads / meta
    business_name String,
    description   String,
    update_freq   String      -- daily / hourly
) ENGINE = MergeTree
ORDER BY (layer, table_name);

CREATE TABLE analytics.meta_columns (
    table_name    String,
    column_name   String,
    data_type     String,
    business_name String,
    description   String,
    is_pii        UInt8,      -- 1 = 敏感字段，需脱敏
    is_dimension  UInt8       -- 1 = 维度字段，可用于 GROUP BY
) ENGINE = MergeTree
ORDER BY (table_name, column_name);