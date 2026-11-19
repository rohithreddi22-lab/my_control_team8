
import os
import uuid
from flask import Flask, render_template, request, redirect, session, flash, jsonify
from jinja2 import ChoiceLoader, FileSystemLoader
import mysql.connector
import json
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from config import DB_CONFIG, SECRET_KEY

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Support templates both inside 'templates/' folder and at root directory
app.jinja_loader = ChoiceLoader([
    FileSystemLoader(os.path.join(app.root_path, "templates")),
    FileSystemLoader(app.root_path),
])

# File Upload Configuration for Product Images
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads", "products")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_product_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    if allowed_file(file_storage.filename):
        ext = file_storage.filename.rsplit(".", 1)[1].lower()
        unique_name = f"product_{uuid.uuid4().hex[:12]}.{ext}"
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
        file_storage.save(file_path)
        return f"uploads/products/{unique_name}"
    return None


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def init_db():
    """Ensure all required tables and columns exist in the database."""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
          id INT AUTO_INCREMENT PRIMARY KEY,
          name VARCHAR(100) NOT NULL,
          email VARCHAR(255) NOT NULL UNIQUE,
          password_hash VARCHAR(255) NOT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
          id INT AUTO_INCREMENT PRIMARY KEY,
          user_id INT NOT NULL,
          name VARCHAR(150) NOT NULL,
          category VARCHAR(50),
          brand VARCHAR(100),
          model_number VARCHAR(100),
          purchase_date DATE,
          purchase_price DECIMAL(10,2),
          store VARCHAR(150),
          notes TEXT,
          image_path VARCHAR(255),
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS warranties (
          id INT AUTO_INCREMENT PRIMARY KEY,
          product_id INT NOT NULL,
          warranty_type VARCHAR(50),
          start_date DATE,
          expiry_date DATE NOT NULL,
          provider VARCHAR(150),
          document_path VARCHAR(255),
          FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS maintenance (
          id INT AUTO_INCREMENT PRIMARY KEY,
          product_id INT NOT NULL,
          task VARCHAR(200) NOT NULL,
          last_done_date DATE,
          next_due_date DATE,
          service_provider VARCHAR(150),
          cost DECIMAL(10,2),
          notes TEXT,
          FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
        """)
        
        # Check image_path column specifically
        cursor.execute("SHOW COLUMNS FROM products LIKE 'image_path'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE products ADD COLUMN image_path VARCHAR(255) NULL AFTER notes")
            
        db.commit()
        cursor.close()
        db.close()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Database init notice: {e}")


init_db()


# =========================
# HOME - DASHBOARD
# =========================

@app.route("/")
def home():
    if not session.get("user_id"):
        return redirect("/login")

    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # 1. Get all products for user
        cursor.execute(
            """
            SELECT id, name, category, brand, model_number,
                   purchase_date, purchase_price, store, notes, image_path
            FROM products
            WHERE user_id = %s
            ORDER BY id DESC
            """,
            (user_id,)
        )
        products = cursor.fetchall()
        total_products = len(products)

        # 2. Get upcoming warranties (expiring within next 30 days)
        cursor.execute(
            """
            SELECT w.id, w.expiry_date, w.warranty_type, w.provider,
                   DATEDIFF(w.expiry_date, CURDATE()) AS days_left,
                   p.id AS product_id,
                   p.name AS product_name
            FROM warranties w
            JOIN products p ON w.product_id = p.id
            WHERE p.user_id = %s
            AND w.expiry_date >= CURDATE()
            AND w.expiry_date <= DATE_ADD(CURDATE(), INTERVAL 30 DAY)
            ORDER BY w.expiry_date ASC
            """,
            (user_id,)
        )
        upcoming_warranties = cursor.fetchall()

        # 3. Get expired warranties
        cursor.execute(
            """
            SELECT w.id, w.expiry_date, w.warranty_type, w.provider,
                   DATEDIFF(CURDATE(), w.expiry_date) AS days_ago,
                   p.id AS product_id,
                   p.name AS product_name
            FROM warranties w
            JOIN products p ON w.product_id = p.id
            WHERE p.user_id = %s
            AND w.expiry_date < CURDATE()
            ORDER BY w.expiry_date DESC
            """,
            (user_id,)
        )
        expired_warranties = cursor.fetchall()

        # 4. Count total active warranties (any warranty where expiry_date >= today)
        cursor.execute(
            """
            SELECT COUNT(*) AS active_count
            FROM warranties w
            JOIN products p ON w.product_id = p.id
            WHERE p.user_id = %s
            AND w.expiry_date >= CURDATE()
            """,
            (user_id,)
        )
        active_warranties_count = cursor.fetchone()["active_count"]

        # 5. Get upcoming maintenance (due today or within the next 30 days)
        cursor.execute(
            """
            SELECT m.id, m.task, m.last_done_date, m.next_due_date,
                   m.service_provider, m.cost, m.notes,
                   DATEDIFF(m.next_due_date, CURDATE()) AS days_until_due,
                   p.id AS product_id,
                   p.name AS product_name
            FROM maintenance m
            JOIN products p ON m.product_id = p.id
            WHERE p.user_id = %s
            AND m.next_due_date >= CURDATE()
            AND m.next_due_date <= DATE_ADD(CURDATE(), INTERVAL 30 DAY)
            ORDER BY m.next_due_date ASC
            """,
            (user_id,)
        )
        upcoming_maintenance = cursor.fetchall()

        # 6. Get overdue maintenance (due date before today)
        cursor.execute(
            """
            SELECT m.id, m.task, m.last_done_date, m.next_due_date,
                   m.service_provider, m.cost, m.notes,
                   DATEDIFF(CURDATE(), m.next_due_date) AS days_overdue,
                   p.id AS product_id,
                   p.name AS product_name
            FROM maintenance m
            JOIN products p ON m.product_id = p.id
            WHERE p.user_id = %s
            AND m.next_due_date < CURDATE()
            ORDER BY m.next_due_date ASC
            """,
            (user_id,)
        )
        overdue_maintenance = cursor.fetchall()

        # 7. Total maintenance expenses
        cursor.execute(
            """
            SELECT COALESCE(SUM(m.cost), 0) AS total_maintenance_cost
            FROM maintenance m
            JOIN products p ON m.product_id = p.id
            WHERE p.user_id = %s
            """,
            (user_id,)
        )
        total_maintenance_cost = float(cursor.fetchone()["total_maintenance_cost"] or 0)

        # 8. Total asset purchase valuation
        cursor.execute(
            """
            SELECT COALESCE(SUM(purchase_price), 0) AS total_asset_value
            FROM products
            WHERE user_id = %s
            """,
            (user_id,)
        )
        total_asset_value = float(cursor.fetchone()["total_asset_value"] or 0)

        cursor.close()
        db.close()
    except Exception as e:
        flash(f"Database error while loading dashboard: {e}", "danger")
        products = []
        upcoming_warranties = []
        expired_warranties = []
        upcoming_maintenance = []
        overdue_maintenance = []
        total_products = 0
        active_warranties_count = 0
        total_maintenance_cost = 0.0
        total_asset_value = 0.0

    # Metrics dictionary for clean dashboard access
    stats = {
        "total_products": total_products,
        "active_warranties": active_warranties_count,
        "expired_warranties": len(expired_warranties),
        "upcoming_maintenance": len(upcoming_maintenance),
        "overdue_maintenance": len(overdue_maintenance),
        "total_maintenance_cost": total_maintenance_cost,
        "total_asset_value": total_asset_value,
    }

    return render_template(
        "home.html",
        products=products,
        upcoming_warranties=upcoming_warranties,
        expired_warranties=expired_warranties,
        upcoming_maintenance=upcoming_maintenance,
        overdue_maintenance=overdue_maintenance,
        stats=stats
    )


# =========================
# ADD PRODUCT
# =========================

@app.route("/add_product", methods=["POST"])
def add_product():
    if not session.get("user_id"):
        return redirect("/login")

    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip() or None
    brand = request.form.get("brand", "").strip() or None
    model_number = request.form.get("model_number", "").strip() or None
    purchase_date = request.form.get("purchase_date", "").strip() or None
    purchase_price = request.form.get("purchase_price", "").strip() or None
    store = request.form.get("store", "").strip() or None
    notes = request.form.get("notes", "").strip() or None

    if not name:
        flash("Please enter a product name.")
        return redirect("/")

    if purchase_price:
        try:
            if float(purchase_price) < 0:
                raise ValueError
        except ValueError:
            flash("Please enter a valid purchase price.")
            return redirect("/")

    image_file = request.files.get("image")
    image_path = save_product_image(image_file)

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """
        INSERT INTO products (user_id, name, category, brand, model_number, purchase_date, purchase_price, store, notes, image_path)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (session["user_id"], name, category, brand, model_number, purchase_date, purchase_price, store, notes, image_path)
    )

    db.commit()
    cursor.close()
    db.close()

    flash("Product added successfully!")
    return redirect("/")



# =========================
# EDIT PRODUCT
# =========================

@app.route("/edit_product/<int:product_id>", methods=["GET", "POST"])
def edit_product(product_id):
    if not session.get("user_id"):
        return redirect("/login")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id, name, category, brand, model_number, purchase_date, purchase_price, store, notes, image_path
        FROM products
        WHERE id = %s AND user_id = %s
        """,
        (product_id, session["user_id"])
    )

    product = cursor.fetchone()

    if not product:
        cursor.close()
        db.close()
        flash("Product not found.")
        return redirect("/")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip() or None
        brand = request.form.get("brand", "").strip() or None
        model_number = request.form.get("model_number", "").strip() or None
        purchase_date = request.form.get("purchase_date", "").strip() or None
        purchase_price = request.form.get("purchase_price", "").strip() or None
        store = request.form.get("store", "").strip() or None
        notes = request.form.get("notes", "").strip() or None

        if not name:
            cursor.close()
            db.close()
            flash("Product name cannot be empty.")
            return redirect(f"/edit_product/{product_id}")

        if purchase_price:
            try:
                if float(purchase_price) < 0:
                    raise ValueError
            except ValueError:
                cursor.close()
                db.close()
                flash("Please enter a valid non-negative purchase price.")
                return redirect(f"/edit_product/{product_id}")

        current_image = product.get("image_path")
        remove_image = request.form.get("remove_image") == "1"
        new_image = request.files.get("image")

        if remove_image and current_image:
            old_file = os.path.join(app.root_path, "static", current_image)
            if os.path.exists(old_file):
                try:
                    os.remove(old_file)
                except OSError:
                    pass
            current_image = None

        if new_image and new_image.filename:
            saved = save_product_image(new_image)
            if saved:
                if current_image:
                    old_file = os.path.join(app.root_path, "static", current_image)
                    if os.path.exists(old_file):
                        try:
                            os.remove(old_file)
                        except OSError:
                            pass
                current_image = saved

        cursor.execute(
            """
            UPDATE products
            SET name = %s, category = %s, brand = %s, model_number = %s,
                purchase_date = %s, purchase_price = %s, store = %s, notes = %s, image_path = %s
            WHERE id = %s AND user_id = %s
            """,
            (name, category, brand, model_number, purchase_date, purchase_price, store, notes, current_image, product_id, session["user_id"])
        )

        db.commit()
        cursor.close()
        db.close()

        flash("Product updated successfully!")
        return redirect("/")

    cursor.close()
    db.close()

    return render_template("edit_product.html", product=product)



# =========================
# DELETE PRODUCT
# =========================

@app.route("/delete_product/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    if not session.get("user_id"):
        return redirect("/login")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT image_path FROM products WHERE id = %s AND user_id = %s",
        (product_id, session["user_id"])
    )
    product = cursor.fetchone()

    cursor.execute(
        """
        DELETE FROM products
        WHERE id = %s AND user_id = %s
        """,
        (product_id, session["user_id"])
    )

    db.commit()

    if cursor.rowcount:
        if product and product.get("image_path"):
            img_file = os.path.join(app.root_path, "static", product["image_path"])
            if os.path.exists(img_file):
                try:
                    os.remove(img_file)
                except OSError:
                    pass
        flash("Product deleted successfully!")
    else:
        flash("Product not found.")

    cursor.close()
    db.close()

    return redirect("/")


# =========================
# VIEW PRODUCT WARRANTIES
# =========================

@app.route("/product/<int:product_id>/warranties")
def view_warranties(product_id):
    if not session.get("user_id"):
        return redirect("/login")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id, name
        FROM products
        WHERE id = %s AND user_id = %s
        """,
        (product_id, session["user_id"])
    )

    product = cursor.fetchone()

    if not product:
        cursor.close()
        db.close()
        flash("Product not found.")
        return redirect("/")

    cursor.execute(
        """
        SELECT id, warranty_type, start_date, expiry_date,
               provider, document_path,
               DATEDIFF(expiry_date, CURDATE()) AS days_left
        FROM warranties
        WHERE product_id = %s
        ORDER BY expiry_date ASC
        """,
        (product_id,)
    )

    warranties = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "warranties.html",
        product=product,
        warranties=warranties
    )


# =========================
# ADD WARRANTY
# =========================

@app.route(
    "/product/<int:product_id>/add_warranty",
    methods=["GET", "POST"]
)
def add_warranty(product_id):
    if not session.get("user_id"):
        return redirect("/login")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id, name
        FROM products
        WHERE id = %s AND user_id = %s
        """,
        (product_id, session["user_id"])
    )

    product = cursor.fetchone()

    if not product:
        cursor.close()
        db.close()
        flash("Product not found.")
        return redirect("/")

    if request.method == "POST":
        warranty_type = request.form.get(
            "warranty_type", ""
        ).strip()

        start_date = request.form.get("start_date", "").strip()
        expiry_date = request.form.get("expiry_date", "").strip()
        provider = request.form.get("provider", "").strip() or None

        if not warranty_type or not start_date or not expiry_date:
            flash("Please fill in all required warranty details.")
            cursor.close()
            db.close()
            return redirect(f"/product/{product_id}/add_warranty")

        if expiry_date < start_date:
            flash("Expiry date cannot be before start date.")
            cursor.close()
            db.close()
            return redirect(f"/product/{product_id}/add_warranty")

        cursor.execute(
            """
            INSERT INTO warranties
            (product_id, warranty_type, start_date, expiry_date, provider)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                product_id,
                warranty_type,
                start_date,
                expiry_date,
                provider
            )
        )

        db.commit()
        cursor.close()
        db.close()

        flash("Warranty added successfully!")
        return redirect(f"/product/{product_id}/warranties")

    cursor.close()
    db.close()

    return render_template(
        "add_warranty.html",
        product=product
    )


# =========================
# VIEW PRODUCT MAINTENANCE
# =========================

@app.route("/product/<int:product_id>/maintenance")
def view_maintenance(product_id):
    if not session.get("user_id"):
        return redirect("/login")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Check product ownership
    cursor.execute(
        """
        SELECT id, name
        FROM products
        WHERE id = %s AND user_id = %s
        """,
        (product_id, session["user_id"])
    )

    product = cursor.fetchone()

    if not product:
        cursor.close()
        db.close()
        flash("Product not found.")
        return redirect("/")

    # Get maintenance records
    cursor.execute(
        """
        SELECT id, task, last_done_date, next_due_date,
               service_provider, cost, notes,
               DATEDIFF(next_due_date, CURDATE()) AS days_until_due
        FROM maintenance
        WHERE product_id = %s
        ORDER BY next_due_date ASC
        """,
        (product_id,)
    )

    maintenance_records = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "maintenance.html",
        product=product,
        maintenance_records=maintenance_records
    )


# =========================
# ADD MAINTENANCE
# =========================

@app.route(
    "/product/<int:product_id>/add_maintenance",
    methods=["GET", "POST"]
)
def add_maintenance(product_id):
    if not session.get("user_id"):
        return redirect("/login")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Check product ownership
    cursor.execute(
        """
        SELECT id, name
        FROM products
        WHERE id = %s AND user_id = %s
        """,
        (product_id, session["user_id"])
    )

    product = cursor.fetchone()

    if not product:
        cursor.close()
        db.close()
        flash("Product not found.")
        return redirect("/")

    if request.method == "POST":
        task = request.form.get("task", "").strip()
        last_done_date = request.form.get("last_done_date", "").strip() or None
        next_due_date = request.form.get("next_due_date", "").strip() or None
        service_provider = request.form.get("service_provider", "").strip() or None
        cost = request.form.get("cost", "").strip() or None
        notes = request.form.get("notes", "").strip() or None

        if not task:
            flash("Please enter a maintenance task.")
            cursor.close()
            db.close()
            return redirect(
                f"/product/{product_id}/add_maintenance"
            )

        if cost:
            try:
                if float(cost) < 0:
                    raise ValueError
            except ValueError:
                flash("Please enter a valid non-negative maintenance cost.")
                cursor.close()
                db.close()
                return redirect(
                    f"/product/{product_id}/add_maintenance"
                )

        if last_done_date and next_due_date:
            if next_due_date < last_done_date:
                flash("Next due date cannot be before the last service date.")
                cursor.close()
                db.close()
                return redirect(
                    f"/product/{product_id}/add_maintenance"
                )

        cursor.execute(
            """
            INSERT INTO maintenance
            (product_id, task, last_done_date, next_due_date,
             service_provider, cost, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                product_id,
                task,
                last_done_date,
                next_due_date,
                service_provider,
                cost,
                notes
            )
        )

        db.commit()
        cursor.close()
        db.close()

        flash("Maintenance record added successfully!")
        return redirect(
            f"/product/{product_id}/maintenance"
        )

    cursor.close()
    db.close()

    return render_template(
        "add_maintenance.html",
        product=product
    )


# =========================
# USER REGISTRATION
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        try:
            db = get_db()
            cursor = db.cursor()

            cursor.execute(
                "SELECT id FROM users WHERE email = %s",
                (email,)
            )

            if cursor.fetchone():
                cursor.close()
                db.close()
                flash("That email is already registered.", "warning")
                return redirect("/register")

            cursor.execute(
                """
                INSERT INTO users (name, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (name, email, generate_password_hash(password))
            )

            db.commit()
            cursor.close()
            db.close()

            flash("Account created. Please log in.", "success")
            return redirect("/login")
        except Exception as e:
            flash(f"Database error: {e}. Check MySQL connection or credentials.", "danger")
            return redirect("/register")

    return render_template("register.html")


# =========================
# USER LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)

            cursor.execute(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )

            user = cursor.fetchone()
            cursor.close()
            db.close()
        except Exception as e:
            flash(f"Database connection error: {e}. Check MySQL server and credentials.", "danger")
            return redirect("/login")

        if user and check_password_hash(
            user["password_hash"], password
        ):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect("/")

        flash("Wrong email or password.", "danger")
        return redirect("/login")

    return render_template("login.html")


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# =========================
# ALL WARRANTIES HUB
# =========================

@app.route("/warranties")
def all_warranties():
    if not session.get("user_id"):
        return redirect("/login")

    status_filter = request.args.get("status", "all").lower()
    user_id = session["user_id"]

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT w.id, w.warranty_type, w.start_date, w.expiry_date,
               w.provider, w.document_path,
               DATEDIFF(w.expiry_date, CURDATE()) AS days_left,
               p.id AS product_id,
               p.name AS product_name,
               p.category, p.brand
        FROM warranties w
        JOIN products p ON w.product_id = p.id
        WHERE p.user_id = %s
        ORDER BY w.expiry_date ASC
        """,
        (user_id,)
    )
    all_records = cursor.fetchall()

    cursor.close()
    db.close()

    # Categorize
    active_list = [w for w in all_records if w["days_left"] is not None and w["days_left"] > 30]
    expiring_list = [w for w in all_records if w["days_left"] is not None and 0 <= w["days_left"] <= 30]
    expired_list = [w for w in all_records if w["days_left"] is not None and w["days_left"] < 0]

    if status_filter == "active":
        filtered_warranties = active_list
    elif status_filter == "expiring":
        filtered_warranties = expiring_list
    elif status_filter == "expired":
        filtered_warranties = expired_list
    else:
        filtered_warranties = all_records

    counts = {
        "all": len(all_records),
        "active": len(active_list),
        "expiring": len(expiring_list),
        "expired": len(expired_list)
    }

    return render_template(
        "all_warranties.html",
        warranties=filtered_warranties,
        counts=counts,
        active_status=status_filter
    )


# =========================
# ALL MAINTENANCE HUB
# =========================

@app.route("/maintenance")
def all_maintenance():
    if not session.get("user_id"):
        return redirect("/login")

    status_filter = request.args.get("status", "all").lower()
    user_id = session["user_id"]

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT m.id, m.task, m.last_done_date, m.next_due_date,
               m.service_provider, m.cost, m.notes,
               DATEDIFF(m.next_due_date, CURDATE()) AS days_until_due,
               p.id AS product_id,
               p.name AS product_name,
               p.category, p.brand
        FROM maintenance m
        JOIN products p ON m.product_id = p.id
        WHERE p.user_id = %s
        ORDER BY m.next_due_date ASC
        """,
        (user_id,)
    )
    all_records = cursor.fetchall()

    cursor.close()
    db.close()

    # Categorize
    overdue_list = [m for m in all_records if m["days_until_due"] is not None and m["days_until_due"] < 0]
    due_today_list = [m for m in all_records if m["days_until_due"] is not None and m["days_until_due"] == 0]
    upcoming_list = [m for m in all_records if m["days_until_due"] is not None and 0 <= m["days_until_due"] <= 30]
    scheduled_list = [m for m in all_records if m["days_until_due"] is not None and m["days_until_due"] > 30]

    if status_filter == "overdue":
        filtered_maintenance = overdue_list
    elif status_filter == "upcoming":
        filtered_maintenance = upcoming_list
    elif status_filter == "scheduled":
        filtered_maintenance = scheduled_list
    else:
        filtered_maintenance = all_records

    counts = {
        "all": len(all_records),
        "overdue": len(overdue_list),
        "due_today": len(due_today_list),
        "upcoming": len(upcoming_list),
        "scheduled": len(scheduled_list)
    }

    return render_template(
        "all_maintenance.html",
        records=filtered_maintenance,
        counts=counts,
        active_status=status_filter
    )


# =========================
# EXPENSES & COST TRACKER
# =========================

@app.route("/expenses")
def expenses():
    if not session.get("user_id"):
        return redirect("/login")

    user_id = session["user_id"]
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # 1. Total Maintenance Cost
    cursor.execute(
        """
        SELECT COALESCE(SUM(m.cost), 0) AS total_maintenance
        FROM maintenance m
        JOIN products p ON m.product_id = p.id
        WHERE p.user_id = %s
        """,
        (user_id,)
    )
    total_maintenance = float(cursor.fetchone()["total_maintenance"] or 0)

    # 2. Total Asset Purchase Cost
    cursor.execute(
        """
        SELECT COALESCE(SUM(purchase_price), 0) AS total_purchase
        FROM products
        WHERE user_id = %s
        """,
        (user_id,)
    )
    total_purchase = float(cursor.fetchone()["total_purchase"] or 0)

    # 3. All Maintenance Expenses
    cursor.execute(
        """
        SELECT m.id, m.task, m.last_done_date, m.cost, m.service_provider,
               p.id AS product_id, p.name AS product_name, p.category
        FROM maintenance m
        JOIN products p ON m.product_id = p.id
        WHERE p.user_id = %s AND m.cost IS NOT NULL AND m.cost > 0
        ORDER BY m.last_done_date DESC, m.id DESC
        """,
        (user_id,)
    )
    maintenance_expenses = cursor.fetchall()

    # 4. Product Purchase Expenses
    cursor.execute(
        """
        SELECT id, name, category, brand, purchase_date, purchase_price, store
        FROM products
        WHERE user_id = %s AND purchase_price IS NOT NULL AND purchase_price > 0
        ORDER BY purchase_date DESC, id DESC
        """,
        (user_id,)
    )
    product_expenses = cursor.fetchall()

    # 5. Category-wise Spending Breakdown (For Chart.js Analytics)
    cursor.execute(
        """
        SELECT COALESCE(NULLIF(category, ''), 'Other') AS cat_name,
               COALESCE(SUM(purchase_price), 0) AS total_spent
        FROM products
        WHERE user_id = %s
        GROUP BY cat_name
        ORDER BY total_spent DESC
        """,
        (user_id,)
    )
    category_summary = cursor.fetchall()

    cat_labels = [c["cat_name"] for c in category_summary]
    cat_values = [float(c["total_spent"]) for c in category_summary]

    # 6. Top Maintenance Cost per Asset (For Chart.js Analytics)
    cursor.execute(
        """
        SELECT p.name AS product_name,
               COALESCE(SUM(m.cost), 0) AS total_cost
        FROM maintenance m
        JOIN products p ON m.product_id = p.id
        WHERE p.user_id = %s AND m.cost IS NOT NULL AND m.cost > 0
        GROUP BY p.id, p.name
        ORDER BY total_cost DESC
        LIMIT 6
        """,
        (user_id,)
    )
    maintenance_product_summary = cursor.fetchall()

    maint_labels = [m["product_name"] for m in maintenance_product_summary]
    maint_values = [float(m["total_cost"]) for m in maintenance_product_summary]

    cursor.close()
    db.close()

    total_combined = total_maintenance + total_purchase

    return render_template(
        "expenses.html",
        total_maintenance=total_maintenance,
        total_purchase=total_purchase,
        total_combined=total_combined,
        maintenance_expenses=maintenance_expenses,
        product_expenses=product_expenses,
        cat_labels_json=json.dumps(cat_labels),
        cat_values_json=json.dumps(cat_values),
        maint_labels_json=json.dumps(maint_labels),
        maint_values_json=json.dumps(maint_values)
    )


# =========================
# CALENDAR & TIMELINE
# =========================

@app.route("/calendar")
def calendar():
    if not session.get("user_id"):
        return redirect("/login")

    user_id = session["user_id"]
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # 1. Fetch all warranties
    cursor.execute(
        """
        SELECT w.id, w.warranty_type, w.expiry_date, w.provider,
               DATEDIFF(w.expiry_date, CURDATE()) AS days_left,
               p.id AS product_id, p.name AS product_name
        FROM warranties w
        JOIN products p ON w.product_id = p.id
        WHERE p.user_id = %s AND w.expiry_date IS NOT NULL
        ORDER BY w.expiry_date ASC
        """,
        (user_id,)
    )
    warranty_records = cursor.fetchall()

    # 2. Fetch all maintenance schedules
    cursor.execute(
        """
        SELECT m.id, m.task, m.next_due_date, m.cost, m.service_provider,
               DATEDIFF(m.next_due_date, CURDATE()) AS days_until_due,
               p.id AS product_id, p.name AS product_name
        FROM maintenance m
        JOIN products p ON m.product_id = p.id
        WHERE p.user_id = %s AND m.next_due_date IS NOT NULL
        ORDER BY m.next_due_date ASC
        """,
        (user_id,)
    )
    maintenance_records = cursor.fetchall()

    cursor.close()
    db.close()

    events = []

    for w in warranty_records:
        expiry_str = w["expiry_date"].strftime("%Y-%m-%d") if hasattr(w["expiry_date"], "strftime") else str(w["expiry_date"])
        is_expired = w["days_left"] is not None and w["days_left"] < 0
        events.append({
            "id": f"w_{w['id']}",
            "title": f"Warranty: {w['product_name']}",
            "type": "warranty",
            "date": expiry_str,
            "product_id": w["product_id"],
            "product_name": w["product_name"],
            "sub_text": w["warranty_type"],
            "is_expired": is_expired,
            "badge_color": "#EF4444" if is_expired else "#F59E0B",
            "link": f"/product/{w['product_id']}/warranties"
        })

    for m in maintenance_records:
        due_str = m["next_due_date"].strftime("%Y-%m-%d") if hasattr(m["next_due_date"], "strftime") else str(m["next_due_date"])
        is_overdue = m["days_until_due"] is not None and m["days_until_due"] < 0
        events.append({
            "id": f"m_{m['id']}",
            "title": f"Service: {m['product_name']}",
            "type": "maintenance",
            "date": due_str,
            "product_id": m["product_id"],
            "product_name": m["product_name"],
            "sub_text": m["task"],
            "is_overdue": is_overdue,
            "badge_color": "#EF4444" if is_overdue else "#10B981",
            "link": f"/product/{m['product_id']}/maintenance"
        })

    return render_template(
        "calendar.html",
        events_json=json.dumps(events),
        events=events
    )


# =========================
# RUN APPLICATION
# =========================

if __name__ == "__main__":
    app.run(debug=True)


