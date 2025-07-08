import os
import random
import re
import requests
import sqlite3
import string
import io
import pandas as pd


from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, make_response, send_file
)
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'static/uploads/'
BANNER_FOLDER = 'static/banners/'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BANNER_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['BANNER_FOLDER'] = BANNER_FOLDER

contacts = {
    '9606888430': {
        'API': '7418954356:AAHWEzyo1lr0jM34r1yi5IcRrnHB2TDHHZ0',
        'ID': '7887307343'  # Replace this with the actual Telegram chat ID
    }
}

def send_otp_to_telegram(phone):
    otp = str(random.randint(100000, 999999))
    session['otp'] = otp

    bot_api = contacts[phone]['API']
    chat_id = contacts[phone]['ID']
    message = f"🔐 Your Admin OTP is: {otp}"

    url = f"https://api.telegram.org/bot{bot_api}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message}

   try:
    response = requests.post(url, data=payload, timeout=10)
    response.raise_for_status()
    return True
except requests.RequestException as e:
    print("Telegram send failed:", e)
    return False


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Generate a random filename with a given extension (e.g., jpg, png)
def generate_random_filename(extension: str, length: int = 10) -> str:
    random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=length))
    return f"{random_str}.{extension.lower()}"

# Check if the uploaded file has an allowed extension
def allowed_file(filename: str) -> bool:
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[-1].lower() in allowed_extensions

# Generate a unique filename that does not already exist in the upload folder
def generate_unique_filename(extension: str, upload_folder: str, length: int = 30) -> str:
    while True:
        random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=length))
        filename = f"{random_str}.{extension.lower()}"
        full_path = os.path.join(upload_folder, filename)
        if not os.path.exists(full_path):
            return filename

def init_db():
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()

        # Admin Table
        c.execute('''
            CREATE TABLE IF NOT EXISTS admin (
                username TEXT,
                password TEXT
            )
        ''')

        # Products Table: Full schema verification
        c.execute("PRAGMA table_info(products)")
        existing_columns = {col[1] for col in c.fetchall()}

        required_columns = {
            'id', 'product_id', 'name', 'images', 'description', 'price',
            'know_more', 'product_type', 'sub_category', 'tags',
            'brand_name', 'rating'
        }

        if not required_columns.issubset(existing_columns):
            print("🔄 Dropping and recreating 'products' table with full schema...")
            c.execute("DROP TABLE IF EXISTS products")
            c.execute('''
                CREATE TABLE products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT,
                    name TEXT,
                    images TEXT,
                    description TEXT,
                    price TEXT,
                    know_more TEXT,
                    product_type TEXT,
                    sub_category TEXT,
                    tags TEXT,
                    brand_name TEXT,
                    rating REAL  -- ✅ float-compatible
                )
            ''')

        # Visitors Table
        c.execute('''
            CREATE TABLE IF NOT EXISTS visitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                email TEXT,
                mobile TEXT,
                visit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Banners Table
        c.execute('''
            CREATE TABLE IF NOT EXISTS banners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT
            )
        ''')

        # ✅ Ensure 'link' column exists in banners table
        c.execute("PRAGMA table_info(banners)")
        banner_columns = {col[1] for col in c.fetchall()}
        if 'link' not in banner_columns:
            c.execute("ALTER TABLE banners ADD COLUMN link TEXT")

        # Insert default admin user if none exists
        c.execute("SELECT * FROM admin")
        if not c.fetchone():
            c.execute("INSERT INTO admin (username, password) VALUES (?, ?)", ("Admin", "Admin@2025"))

        conn.commit()

# ✅ Run DB initialization
init_db()

@app.route('/upload-banner', methods=['POST'])
@login_required
def upload_banner():
    file = request.files.get('banner')
    link = request.form.get('link', '').strip()

    # ✅ Optional: Basic URL validation (optional but recommended)
    if link and not re.match(r'^https?://', link):
        flash("Invalid banner link URL (must start with http/https)", "danger")
        return redirect(url_for('dashboard'))

    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        random_filename = generate_random_filename(ext)
        filepath = os.path.join(app.config['BANNER_FOLDER'], random_filename)
        file.save(filepath)

        # ✅ Save to DB with banner link
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute("INSERT INTO banners (filename, link) VALUES (?, ?)", (random_filename, link))
            conn.commit()

        flash("Banner uploaded successfully", "success")
    else:
        flash("Invalid file or no banner selected", "warning")

    return redirect(url_for('dashboard'))


@app.route('/delete-banner/<int:banner_id>', methods=['POST'])
@login_required
def delete_banner(banner_id):
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()

        # ✅ Fetch the filename before deleting
        c.execute("SELECT filename FROM banners WHERE id=?", (banner_id,))
        row = c.fetchone()

        if row:
            image_path = os.path.join(app.config['BANNER_FOLDER'], row[0])
            if os.path.exists(image_path):
                os.remove(image_path)

            # ✅ Delete from DB
            c.execute("DELETE FROM banners WHERE id=?", (banner_id,))
            conn.commit()
            flash("Banner deleted successfully", "success")
        else:
            flash("Banner not found", "danger")

    return redirect(url_for('dashboard'))


@app.route('/banners')
def get_banners():
    with sqlite3.connect('database.db') as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # ✅ Return all banners with their filenames and links
        c.execute("SELECT * FROM banners ORDER BY id DESC")
        banners = c.fetchall()

    response = make_response(jsonify([dict(b) for b in banners]))
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response



@app.route('/')
def index():
    raw_query = request.args.get('search', '').strip()
    selected_category = request.args.get('category', '').lower()

    with sqlite3.connect('database.db') as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Fetch categories
        c.execute("SELECT DISTINCT product_type FROM products")
        categories = [row['product_type'] for row in c.fetchall()]

        query_sql = "SELECT * FROM products"
        filters = []
        values = []
        raw_lower = raw_query.lower()

        # Price filters
        match = re.search(r'(under|below|less than)\s+(\d+)', raw_lower)
        if match:
            amount = int(match.group(2))
            filters.append("CAST(price AS INTEGER) <= ?")
            values.append(amount)

        match = re.search(r'(above|over|more than)\s+(\d+)', raw_lower)
        if match:
            amount = int(match.group(2))
            filters.append("CAST(price AS INTEGER) >= ?")
            values.append(amount)

        match = re.search(r'between\s+(\d+)\s+and\s+(\d+)', raw_lower)
        if match:
            low, high = int(match.group(1)), int(match.group(2))
            filters.append("CAST(price AS INTEGER) BETWEEN ? AND ?")
            values.extend([low, high])

        if raw_query:
            terms = re.findall(r'\w+', raw_lower)
            term_clauses = []
            for term in terms:
                if term in ['under', 'below', 'less', 'than', 'above', 'over', 'more', 'between', 'and']:
                    continue
                clause = """
                (LOWER(name) LIKE ? OR LOWER(description) LIKE ? OR LOWER(tags) LIKE ?
                 OR LOWER(brand_name) LIKE ? OR LOWER(product_type) LIKE ?
                 OR LOWER(sub_category) LIKE ? OR LOWER(product_id) LIKE ?)
                """
                term_clauses.append(clause)
                values.extend(['%' + term + '%'] * 7)
            if term_clauses:
                filters.append('(' + ' OR '.join(term_clauses) + ')')

        if selected_category:
            filters.append("LOWER(product_type) = ?")
            values.append(selected_category)

        if filters:
            query_sql += " WHERE " + " AND ".join(filters)
        query_sql += " ORDER BY id DESC"

        c.execute(query_sql, values)
        products = c.fetchall()

        # ✅ Refresh page if no product found
        if raw_query and not products:
            return redirect(url_for('index'))

        c.execute("SELECT * FROM banners ORDER BY id DESC LIMIT 10")
        banners = c.fetchall()

    return render_template(
        'index.html',
        products=products,
        categories=categories,
        search=raw_query,
        category=selected_category,
        banners=banners
    )



@app.route('/record-visitor', methods=['POST'])
def record_visitor():
    name = request.form.get('name')
    email = request.form.get('email')
    mobile = request.form.get('mobile')

    if not all([name, email, mobile]):
        flash("Please fill all visitor fields", "warning")
        return redirect(url_for('index'))

    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO visitors (name, email, mobile) VALUES (?, ?, ?)",
            (name, email, mobile)
        )
        conn.commit()

    flash("Visitor details submitted successfully!", "success")
    return redirect(url_for('index'))


@app.route('/log-visitor', methods=['POST'])
def log_visitor():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    mobile = data.get('mobile')

    if not all([name, email, mobile]):
        return jsonify({'error': 'Missing fields'}), 400

    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO visitors (name, email, mobile) VALUES (?, ?, ?)",
            (name, email, mobile)
        )
        conn.commit()

    return jsonify({'message': 'Visitor logged successfully'}), 200


@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash("Please enter both username and password", "warning")
            return redirect(url_for('admin_login'))

        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute(
                "SELECT * FROM admin WHERE username=? AND password=?",
                (username, password)
            )
            admin = c.fetchone()

        if admin:
            session['temp_admin'] = username
            send_otp_to_telegram('9606888430')  # You can make this dynamic later
            flash("OTP sent to admin Telegram", "info")
            return redirect(url_for('verify_otp'))
        else:
            flash("Invalid credentials", "danger")
            return redirect(url_for('admin_login'))

    return render_template('admin_login.html')


@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if 'temp_admin' not in session:
        flash("Unauthorized access", "warning")
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        entered_otp = request.form.get('otp', '').strip()
        if entered_otp == session.get('otp'):
            session['admin'] = True
            session.pop('temp_admin', None)
            session.pop('otp', None)
            flash("OTP verified successfully", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid OTP", "danger")
            return redirect(url_for('verify_otp'))

    return render_template('verify_otp.html')


@app.route('/dashboard')
@login_required
def dashboard():
    with sqlite3.connect('database.db') as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Fetch all products
        c.execute("SELECT * FROM products ORDER BY id DESC")
        all_products = c.fetchall()

        # Group products by category
        categorized_products = {}
        for product in all_products:
            category = product['product_type']
            categorized_products.setdefault(category, []).append(product)

        # Fetch recent visitors
        c.execute("SELECT name, email, mobile, visit_time FROM visitors ORDER BY id DESC LIMIT 50")
        visitors = c.fetchall()

        # Fetch banners
        c.execute("SELECT * FROM banners ORDER BY id DESC")
        banners = c.fetchall()

    return render_template(
        'dashboard.html',
        categorized_products=categorized_products,
        visitors=visitors,
        banners=banners
    )


@app.route('/add-product', methods=['POST'])
@login_required
def add_product():
    files = request.files.getlist('images')
    if not files or all(file.filename == '' for file in files):
        flash("No images selected", "warning")
        return redirect(url_for('dashboard'))

    image_filenames = []
    for file in files:
        if file and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[-1].lower()
            new_filename = generate_unique_filename(ext)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
            file.save(filepath)
            image_filenames.append(new_filename)

    image_string = ','.join(image_filenames)

    # ✅ Get form values including new fields
    product_id = request.form.get('product_id')
    name = request.form.get('name')
    description = request.form.get('description')
    price = request.form.get('price')
    know_more = request.form.get('know_more')
    product_type = request.form.get('product_type')
    sub_category = request.form.get('sub_category')
    tags = request.form.get('tags')
    brand_name = request.form.get('brand_name')
    rating = request.form.get('rating', 0)

    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO products (
                product_id, name, images, description, price, know_more,
                product_type, sub_category, tags, brand_name, rating
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            product_id, name, image_string, description, price, know_more,
            product_type, sub_category, tags, brand_name, float(rating)
        ))
        conn.commit()

    flash("Product added successfully", "success")
    return redirect(url_for('dashboard'))


@app.route('/edit-product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    with sqlite3.connect('database.db') as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        if request.method == 'POST':
            # Fetch form data
            product_id_val = request.form.get('product_id')
            name = request.form.get('name')
            description = request.form.get('description')
            price = request.form.get('price')
            know_more = request.form.get('know_more')
            product_type = request.form.get('product_type')
            sub_category = request.form.get('sub_category')
            tags = request.form.get('tags')
            brand_name = request.form.get('brand_name')
            rating = request.form.get('rating', 0)
            files = request.files.getlist('images')

            # Handle image replacement if new images provided
            if files and any(file.filename != '' for file in files):
                c.execute("SELECT images FROM products WHERE id=?", (product_id,))
                old_images = c.fetchone()
                if old_images:
                    for old_img in old_images['images'].split(','):
                        old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_img)
                        if os.path.exists(old_path):
                            os.remove(old_path)

                new_filenames = []
                for file in files:
                    if file and allowed_file(file.filename):
                        ext = file.filename.rsplit('.', 1)[-1].lower()
                        new_filename = generate_unique_filename(ext)
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                        file.save(filepath)
                        new_filenames.append(new_filename)

                image_string = ','.join(new_filenames)
                c.execute("""
                    UPDATE products SET 
                        product_id=?, name=?, images=?, description=?, price=?, 
                        know_more=?, product_type=?, sub_category=?, tags=?, 
                        brand_name=?, rating=?
                    WHERE id=?
                """, (
                    product_id_val, name, image_string, description, price,
                    know_more, product_type, sub_category, tags, brand_name,
                    float (rating), product_id
                ))
            else:
                # Update without modifying images
                c.execute("""
                    UPDATE products SET 
                        product_id=?, name=?, description=?, price=?, know_more=?, 
                        product_type=?, sub_category=?, tags=?, brand_name=?, rating=? 
                    WHERE id=?
                """, (
                    product_id_val, name, description, price, know_more,
                    product_type, sub_category, tags, brand_name,
                    float(rating), product_id
                ))

            conn.commit()
            flash("Product updated successfully", "success")
            return redirect(url_for('dashboard'))

        c.execute("SELECT * FROM products WHERE id=?", (product_id,))
        product = c.fetchone()

    return render_template('edit_product.html', product=product)


@app.route('/delete-product/<int:product_id>')
@login_required
def delete_product(product_id):
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()

        # Delete images from disk
        c.execute("SELECT images FROM products WHERE id=?", (product_id,))
        row = c.fetchone()
        if row:
            for img in row[0].split(','):
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], img)
                if os.path.exists(image_path):
                    os.remove(image_path)

        # Delete product from database
        c.execute("DELETE FROM products WHERE id=?", (product_id,))
        conn.commit()

    flash("Product deleted successfully", "success")
    return redirect(url_for('dashboard'))



@app.route('/download-visitors')
@login_required
def download_visitors():
    with sqlite3.connect('database.db') as conn:
        df = pd.read_sql_query("SELECT name, email, mobile, visit_time FROM visitors ORDER BY id DESC", conn)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Visitors')

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name='visitors_data.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash("Logged out successfully", "info")
    return redirect(url_for('index'))


@app.route('/faq')
def faq():
    return render_template('faq.html')


@app.route('/privacy-policy')
def privacy():
    return render_template('privacy.html')


@app.route('/refund-policy')
def refund():
    return render_template('refund.html')


@app.route('/terms-of-service')
def terms():
    return render_template('terms.html')


@app.route('/shipping-policy')
def shipping():
    return render_template('shipping.html')


if __name__ == '__main__':
    app.run(debug=True)
