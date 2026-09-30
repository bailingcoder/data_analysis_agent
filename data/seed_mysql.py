"""生成示例电商业务数据（MySQL 业务库）。

四张表（OLTP 规范化设计）：
- customers   客户（含 email / phone，用于演示 PII 脱敏）
- products    商品
- orders      订单
- order_items 订单明细

用法：
  1. 确保 MySQL 已启动，.env 中 MYSQL_PASSWORD 已填
  2. 运行：python data/seed_mysql.py
"""
from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import settings

random.seed(42)

FIRST_NAMES = ["伟", "芳", "娜", "敏", "静", "磊", "军", "洋", "勇", "艳", "杰", "娟", "涛", "明", "超"]
LAST_NAMES = ["王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙", "马", "朱", "胡"]
CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "西安", "南京", "苏州"]

PRODUCTS = [
    ("iPhone 15", "手机数码", 5999.0),
    ("小米 14", "手机数码", 3999.0),
    ("华为 Mate 60", "手机数码", 5499.0),
    ("MacBook Air", "电脑办公", 7999.0),
    ("联想小新 Pro", "电脑办公", 4999.0),
    ("戴尔显示器", "电脑办公", 1299.0),
    ("索尼耳机", "影音娱乐", 1999.0),
    ("Bose 音箱", "影音娱乐", 2499.0),
    ("罗技鼠标", "电脑办公", 199.0),
    ("机械键盘", "电脑办公", 499.0),
    ("保温杯", "家居生活", 99.0),
    ("电动牙刷", "家居生活", 299.0),
    ("吹风机", "家居生活", 399.0),
    ("空气净化器", "家居生活", 1299.0),
    ("跑步机", "运动健康", 2999.0),
    ("瑜伽垫", "运动健康", 89.0),
    ("篮球", "运动健康", 199.0),
    ("智能手表", "手机数码", 1599.0),
    ("平板电脑", "电脑办公", 3299.0),
    ("投影仪", "影音娱乐", 3999.0),
]

STATUSES = [("completed", 0.75), ("pending", 0.15), ("cancelled", 0.10)]


def _pick_status() -> str:
    r = random.random()
    acc = 0.0
    for status, p in STATUSES:
        acc += p
        if r <= acc:
            return status
    return "completed"


def _random_date(start: date, end: date) -> str:
    span = (end - start).days
    return (start + timedelta(days=random.randint(0, span))).isoformat()


def _random_email(name: str) -> str:
    return f"{name.lower()}@example.com"


def _random_phone() -> str:
    return "1" + "".join(random.choice("0123456789") for _ in range(10))


def get_connection(with_db: bool = True):
    kwargs = dict(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        charset="utf8mb4",
        autocommit=False,
    )
    if with_db:
        kwargs["database"] = settings.mysql_database
    return pymysql.connect(**kwargs)


def build(conn) -> None:
    cur = conn.cursor()

    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    for t in ("order_items", "orders", "products", "customers"):
        cur.execute(f"DROP TABLE IF EXISTS `{t}`")
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")

    cur.execute(
        """
        CREATE TABLE customers (
            id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            name          VARCHAR(64)  NOT NULL,
            email         VARCHAR(128) NOT NULL,
            phone         VARCHAR(20)  NOT NULL,
            city          VARCHAR(32)  NOT NULL,
            register_date DATE         NOT NULL,
            created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
            KEY idx_city (city),
            KEY idx_register_date (register_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cur.execute(
        """
        CREATE TABLE products (
            id       BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            name     VARCHAR(128)   NOT NULL,
            category VARCHAR(32)    NOT NULL,
            price    DECIMAL(10, 2) NOT NULL,
            KEY idx_category (category)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cur.execute(
        """
        CREATE TABLE orders (
            id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            customer_id  BIGINT UNSIGNED NOT NULL,
            order_date   DATE            NOT NULL,
            status       ENUM('pending', 'completed', 'cancelled') NOT NULL DEFAULT 'pending',
            total_amount DECIMAL(12, 2)  NOT NULL,
            created_at   TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
            KEY idx_customer (customer_id),
            KEY idx_order_date (order_date),
            KEY idx_status (status),
            CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) REFERENCES customers(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cur.execute(
        """
        CREATE TABLE order_items (
            id         BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            order_id   BIGINT UNSIGNED NOT NULL,
            product_id BIGINT UNSIGNED NOT NULL,
            quantity   INT UNSIGNED    NOT NULL,
            unit_price DECIMAL(10, 2)  NOT NULL,
            KEY idx_order (order_id),
            KEY idx_product (product_id),
            CONSTRAINT fk_items_order FOREIGN KEY (order_id) REFERENCES orders(id),
            CONSTRAINT fk_items_product FOREIGN KEY (product_id) REFERENCES products(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    # 客户
    customers = []
    for i in range(1, 201):
        last = random.choice(LAST_NAMES)
        first = random.choice(FIRST_NAMES)
        name = last + first
        customers.append(
            (
                i,
                name,
                _random_email(name),
                _random_phone(),
                random.choice(CITIES),
                _random_date(date(2023, 1, 1), date(2024, 12, 31)),
            )
        )
    cur.executemany(
        "INSERT INTO customers (id, name, email, phone, city, register_date) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        customers,
    )

    # 商品
    for i, (name, category, price) in enumerate(PRODUCTS, start=1):
        cur.execute(
            "INSERT INTO products (id, name, category, price) VALUES (%s, %s, %s, %s)",
            (i, name, category, price),
        )

    # 订单 + 明细
    order_id = 1
    item_id = 1
    for _ in range(600):
        customer_id = random.randint(1, 200)
        order_date = _random_date(date(2024, 1, 1), date(2024, 12, 31))
        status = _pick_status()

        n_items = random.randint(1, 4)
        product_ids = random.sample(range(1, len(PRODUCTS) + 1), n_items)
        total = 0.0
        items = []
        for pid in product_ids:
            price = PRODUCTS[pid - 1][2]
            qty = random.randint(1, 3)
            items.append((item_id, order_id, pid, qty, price))
            total += price * qty
            item_id += 1

        cur.execute(
            "INSERT INTO orders (id, customer_id, order_date, status, total_amount) "
            "VALUES (%s, %s, %s, %s, %s)",
            (order_id, customer_id, order_date, status, round(total, 2)),
        )
        cur.executemany(
            "INSERT INTO order_items (id, order_id, product_id, quantity, unit_price) "
            "VALUES (%s, %s, %s, %s, %s)",
            items,
        )
        order_id += 1

    conn.commit()


def main() -> None:
    # 1) 建库
    conn = get_connection(with_db=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_database}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()

    # 2) 建表 + 造数
    conn = get_connection(with_db=True)
    try:
        build(conn)
    finally:
        conn.close()

    # 3) 概览
    conn = get_connection(with_db=True)
    try:
        with conn.cursor() as cur:
            for table in ("customers", "products", "orders", "order_items"):
                cur.execute(f"SELECT COUNT(*) FROM `{table}`")
                print(f"{table}: {cur.fetchone()[0]} rows")
    finally:
        conn.close()
    print(f"\nMySQL 业务库 `{settings.mysql_database}` 造数完成")


if __name__ == "__main__":
    main()