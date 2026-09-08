"""Deterministic, trusted write path. Never imported by SQL execution."""
import random
import sqlite3
from contextlib import closing
from pathlib import Path

DESCRIPTIONS = {
    "customers": "Customers, buyers, names, email, country. 客户 顾客 国家 Canada 加拿大",
    "categories": "Product categories and departments. 商品 分类",
    "suppliers": "Product suppliers, vendors and their countries. 供应商",
    "products": "Products with category, supplier, current catalog price and inventory stock. 商品 产品 库存 价格",
    "orders": "Customer orders, order dates and status: completed, pending, refunded. 订单 日期 年 退款",
    "order_items": "Order line items: quantity and historical unit_price. Revenue or spending = quantity * unit_price. 购买金额 销售额 收入 消费 数量",
    "payments": "Payments per order, amount, date and method. Multiple payments possible. 付款 支付",
}

DDL = """
CREATE TABLE customers(customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL,
 email TEXT UNIQUE NOT NULL, country TEXT NOT NULL, created_at DATE NOT NULL);
CREATE TABLE categories(category_id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE suppliers(supplier_id INTEGER PRIMARY KEY, name TEXT NOT NULL, country TEXT NOT NULL);
CREATE TABLE products(product_id INTEGER PRIMARY KEY, name TEXT NOT NULL,
 category_id INTEGER NOT NULL REFERENCES categories(category_id),
 supplier_id INTEGER NOT NULL REFERENCES suppliers(supplier_id),
 price DECIMAL(12,2) NOT NULL CHECK(price>=0), stock INTEGER NOT NULL CHECK(stock>=0));
CREATE TABLE orders(order_id INTEGER PRIMARY KEY,
 customer_id INTEGER NOT NULL REFERENCES customers(customer_id), order_date DATE NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('completed','pending','refunded')));
CREATE TABLE order_items(order_item_id INTEGER PRIMARY KEY,
 order_id INTEGER NOT NULL REFERENCES orders(order_id),
 product_id INTEGER NOT NULL REFERENCES products(product_id),
 quantity INTEGER NOT NULL CHECK(quantity>0), unit_price DECIMAL(12,2) NOT NULL CHECK(unit_price>=0));
CREATE TABLE payments(payment_id INTEGER PRIMARY KEY,
 order_id INTEGER NOT NULL REFERENCES orders(order_id), amount DECIMAL(12,2) NOT NULL,
 payment_date DATE NOT NULL, method TEXT NOT NULL CHECK(method IN ('card','paypal','bank')));
CREATE INDEX idx_orders_customer_date ON orders(customer_id, order_date);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);
CREATE INDEX idx_payments_order ON payments(order_id);
"""


def seed_database(path: Path, seed: int = 42) -> dict[str, int]:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental replacement of an existing database.
    with path.open("xb"):
        pass
    rng = random.Random(seed)
    countries = ["Canada", "USA", "Germany", "Japan", "France"]
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(DDL)
        conn.executemany("INSERT INTO categories VALUES (?,?)", enumerate(
            ["Electronics", "Books", "Home", "Sports", "Clothing"], 1))
        conn.executemany("INSERT INTO suppliers VALUES (?,?,?)",
                         [(i, f"Supplier {i}", countries[i % 5]) for i in range(1, 9)])
        conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", [
            (i, f"Customer {i:03d}", f"customer{i}@example.test", countries[i % 5],
             f"2024-{i % 12 + 1:02d}-01") for i in range(1, 61)])
        prices = {i: rng.randint(500, 50000) / 100 for i in range(1, 81)}
        conn.executemany("INSERT INTO products VALUES (?,?,?,?,?,?)", [
            (i, f"Product {i:03d}", i % 5 + 1, i % 8 + 1, prices[i], rng.randint(0, 120))
            for i in prices])
        item_id = payment_id = 0
        for oid in range(1, 361):
            date = f"{2024 + oid % 3}-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}"
            status = rng.choices(["completed", "pending", "refunded"], [8, 1, 1])[0]
            conn.execute("INSERT INTO orders VALUES (?,?,?,?)", (oid, rng.randint(1, 55), date, status))
            cents = 0
            for pid in rng.sample(range(1, 76), rng.randint(1, 5)):
                item_id += 1
                qty = rng.randint(1, 5)
                price = round(prices[pid] * rng.choice([0.8, 0.9, 1.0]), 2)
                cents += qty * round(price * 100)
                conn.execute("INSERT INTO order_items VALUES (?,?,?,?,?)", (item_id, oid, pid, qty, price))
            if status != "pending":
                if status == 'completed' and oid % 37 == 0:
                    cents -= 50  # Deliberate reconciliation discrepancies for evaluation.
                parts = [cents // 2, cents - cents // 2] if oid % 7 == 0 else [cents]
                for amount in parts:
                    payment_id += 1
                    conn.execute("INSERT INTO payments VALUES (?,?,?,?,?)",
                                 (payment_id, oid, amount / 100, date, rng.choice(["card", "paypal", "bank"])))
        return {name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                for name in DESCRIPTIONS}
