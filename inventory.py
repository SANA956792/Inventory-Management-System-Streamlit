
import mysql.connector
from dataclasses import dataclass
from typing import Optional, List, Tuple
import streamlit as st
import pandas as pd
from datetime import datetime

# ----------------------- Models -----------------------
@dataclass
class Product:
    id: Optional[int]
    name: str
    category: str
    price: float
    stock: int
    added_date: Optional[str] = None

# ----------------------- MySQL DB Wrapper -----------------------
class InventoryDBMySQL:
    def __init__(self):
        self.conn = None
        self.connect()
        self.ensure_tables()

    def connect(self):
        # EDIT YOUR PASSWORD HERE
        self.conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="root",
            database="inventory_db"
        )

    def ensure_tables(self):
        create_products = """
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            category VARCHAR(255),
            price DOUBLE NOT NULL DEFAULT 0,
            stock INT NOT NULL DEFAULT 0,
            added_date DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """

        create_sales = """
        CREATE TABLE IF NOT EXISTS sales (
            sale_id INT AUTO_INCREMENT PRIMARY KEY,
            product_id INT NOT NULL,
            quantity INT NOT NULL,
            total_price DOUBLE NOT NULL,
            sale_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        );
        """

        cur = self.conn.cursor()
        cur.execute(create_products)
        cur.execute(create_sales)
        self.conn.commit()
        cur.close()

    # ------------------ PRODUCT CRUD ------------------

    def add_product(self, p: Product) -> int:
        sql = "INSERT INTO products (name, category, price, stock) VALUES (%s, %s, %s, %s)"
        cur = self.conn.cursor()
        cur.execute(sql, (p.name, p.category, p.price, p.stock))
        self.conn.commit()
        new_id = cur.lastrowid
        cur.close()
        return new_id

    def get_products(self) -> List[Product]:
        sql = "SELECT id, name, category, price, stock, added_date FROM products ORDER BY id"
        cur = self.conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        return [Product(id=r[0], name=r[1], category=r[2] or "", price=float(r[3]), stock=int(r[4]), added_date=str(r[5])) for r in rows]

    def get_product_by_id(self, pid: int) -> Optional[Product]:
        sql = "SELECT id, name, category, price, stock, added_date FROM products WHERE id=%s"
        cur = self.conn.cursor()
        cur.execute(sql, (pid,))
        r = cur.fetchone()
        cur.close()
        if r:
            return Product(id=r[0], name=r[1], category=r[2], price=float(r[3]), stock=int(r[4]), added_date=str(r[5]))
        return None

    def update_stock(self, pid: int, add_qty: int) -> bool:
        sql = "UPDATE products SET stock = stock + %s WHERE id=%s"
        cur = self.conn.cursor()
        cur.execute(sql, (add_qty, pid))
        self.conn.commit()
        ok = cur.rowcount > 0
        cur.close()
        return ok

    def set_stock(self, pid: int, new_stock: int) -> bool:
        sql = "UPDATE products SET stock = %s WHERE id=%s"
        cur = self.conn.cursor()
        cur.execute(sql, (new_stock, pid))
        self.conn.commit()
        ok = cur.rowcount > 0
        cur.close()
        return ok

    def delete_product(self, pid: int) -> bool:
        sql = "DELETE FROM products WHERE id=%s"
        cur = self.conn.cursor()
        cur.execute(sql, (pid,))
        self.conn.commit()
        ok = cur.rowcount > 0
        cur.close()
        return ok

    def low_stock(self, threshold: int = 10) -> List[Product]:
        sql = "SELECT id, name, category, price, stock, added_date FROM products WHERE stock < %s ORDER BY stock"
        cur = self.conn.cursor()
        cur.execute(sql, (threshold,))
        rows = cur.fetchall()
        cur.close()
        return [Product(id=r[0], name=r[1], category=r[2], price=float(r[3]), stock=int(r[4]), added_date=str(r[5])) for r in rows]

    # ------------------ Sales ------------------

    def record_sale(self, pid: int, qty: int):
        cur = self.conn.cursor()

        try:
            cur.execute("SELECT price, stock FROM products WHERE id=%s", (pid,))
            row = cur.fetchone()
            if not row:
                return False, None, "Product not found"

            price, stock = float(row[0]), int(row[1])

            if stock < qty:
                return False, None, f"Not enough stock (available: {stock})"

            total_price = price * qty

            cur.execute(
                "INSERT INTO sales (product_id, quantity, total_price) VALUES (%s, %s, %s)",
                (pid, qty, total_price)
            )

            cur.execute(
                "UPDATE products SET stock = stock - %s WHERE id=%s",
                (qty, pid)
            )

            self.conn.commit()
            return True, total_price, "Sale recorded"

        except Exception as e:
            self.conn.rollback()
            return False, None, str(e)

        finally:
            cur.close()

    def get_sales_report(self):
        sql = """
        SELECT DATE(sale_date), SUM(total_price)
        FROM sales
        GROUP BY DATE(sale_date)
        ORDER BY DATE(sale_date)
        """
        cur = self.conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        return [(str(r[0]), float(r[1])) for r in rows]

    def get_total_inventory_value(self):
        sql = "SELECT SUM(price * stock) FROM products"
        cur = self.conn.cursor()
        cur.execute(sql)
        r = cur.fetchone()
        cur.close()
        return float(r[0]) if r and r[0] else 0.0

# ----------------------- Streamlit UI -----------------------
DB = InventoryDBMySQL()

st.set_page_config(page_title="Inventory (MySQL)", layout="wide")
st.title("🛒 Inventory Management (MySQL Version)")

menu = ["Dashboard", "Add Product", "Update Stock", "Record Sale", "Products", "Sales Report", "Delete Product"]
choice = st.sidebar.selectbox("Menu", menu)

# Dashboard
if choice == "Dashboard":
    st.header("📊 Dashboard")
    products = DB.get_products()
    df = pd.DataFrame([p.__dict__ for p in products])

    if df.empty:
        st.info("No products available.")
    else:
        st.dataframe(df)
        st.metric("Total Products", len(df))
        st.metric("Inventory Value (₹)", f"{DB.get_total_inventory_value():,.2f}")

# Add Product
elif choice == "Add Product":
    st.header("➕ Add Product")
    with st.form("add_form"):
        n = st.text_input("Name")
        c = st.text_input("Category")
        p = st.number_input("Price", min_value=0.0)
        s = st.number_input("Stock", min_value=0, step=1)
        submit = st.form_submit_button("Add")

        if submit:
            prod = Product(None, n, c, p, s)
            pid = DB.add_product(prod)
            st.success(f"Product added (ID {pid})")

# Update Stock
elif choice == "Update Stock":
    st.header("📦 Update Stock")
    products = DB.get_products()
    if not products:
        st.info("No products found.")
    else:
        names = [p.name for p in products]
        chosen = st.selectbox("Product", names)
        prod = next(p for p in products if p.name == chosen)
        st.write(f"Current stock: {prod.stock}")

        add = st.number_input("Add Quantity", min_value=0)
        set_val = st.number_input("Set Stock To", min_value=0, value=prod.stock)

        if st.button("Update"):
            if add > 0:
                DB.update_stock(prod.id, add)
                st.success("Stock increased.")
            else:
                DB.set_stock(prod.id, set_val)
                st.success("Stock updated.")

# Record Sale
elif choice == "Record Sale":
    st.header("💰 Record Sale")
    products = DB.get_products()
    if not products:
        st.info("No products.")
    else:
        names = [p.name for p in products]
        chosen = st.selectbox("Product", names)
        prod = next(p for p in products if p.name == chosen)
        qty = st.number_input("Quantity", min_value=1, max_value=prod.stock)

        if st.button("Sell"):
            ok, total, msg = DB.record_sale(prod.id, qty)
            if ok:
                st.success(f"Sale OK! Total ₹{total:.2f}")
            else:
                st.error(msg)

# Products
elif choice == "Products":
    st.header("📚 Product List")
    df = pd.DataFrame([p.__dict__ for p in DB.get_products()])
    st.dataframe(df)

# Sales Report
elif choice == "Sales Report":
    st.header("📈 Sales Report")
    rows = DB.get_sales_report()
    if rows:
        df = pd.DataFrame(rows, columns=["Date", "Total"])
        st.line_chart(df.set_index("Date"))
        st.dataframe(df)
    else:
        st.info("No sales recorded.")

# Delete Product
elif choice == "Delete Product":
    st.header("🗑 Delete Product")
    products = DB.get_products()
    if not products:
        st.info("No products.")
    else:
        names = [p.name for p in products]
        chosen = st.selectbox("Select", names)
        prod = next(p for p in products if p.name == chosen)

        if st.button("Delete"):
            DB.delete_product(prod.id)
            st.success("Deleted.")
