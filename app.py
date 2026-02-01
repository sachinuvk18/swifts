# app.py
import os
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import psycopg2, psycopg2.extras

# Flask-SocketIO for real-time
from flask_socketio import SocketIO, emit, join_room, leave_room

# ====== DB CONFIG (PGAdmin) ======
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_NAME = os.environ.get('DB_NAME', 'swiftserve')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASS = os.environ.get('DB_PASS', 'Sachin@14')
DB_PORT = os.environ.get('DB_PORT', '5432')

# Video source mode: 'online' or 'local'
VIDEO_SOURCE_MODE = os.environ.get('VIDEO_SOURCE_MODE', 'local').lower()

def get_conn():
    return psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS, port=DB_PORT)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'swiftserve_secret')

# SocketIO init
socketio = SocketIO(app, cors_allowed_origins="*")

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ========= Helpers =========
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash('Access denied.')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return wrapped
    return decorator

def init_cart():
    if 'cart' not in session:
        session['cart'] = []
    return session['cart']

def add_row_to_cart(row):
    cart = init_cart()
    # single-restaurant cart
    if cart and cart[0]['restaurant_id'] != row['restaurant_id']:
        cart.clear()
    for it in cart:
        if it['item_id'] == row['id']:
            it['qty'] += 1
            session.modified = True
            return
    cart.append({
        'item_id': row['id'],
        'name': row['name'],
        'price': float(row['price']),
        'qty': 1,
        'restaurant_id': row['restaurant_id'],
        'image_path': row.get('image_path')
    })
    session.modified = True

def clear_cart():
    session.pop('cart', None)

# Small util to broadcast order updates
def broadcast_order_update(order_id, status, extra=None):
    payload = {"order_id": order_id, "status": status}
    if extra:
        payload.update(extra)
    # Emit to all connected clients. In future you can target rooms (per-order or per-user).
    socketio.emit('order_update', payload)

# ========= Public / Customer =========
@app.route('/')
def index():
    conn = get_conn(); cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT id,name,cuisine,address,image_path FROM restaurants ORDER BY id DESC")
    restaurants = cur.fetchall()
    cur.close(); conn.close()
    return render_template('index.html', restaurants=restaurants)

@app.route('/customer/dashboard')
@login_required()
def customer_dashboard():
    return redirect(url_for('index'))

@app.route('/customer/orders')
@login_required()
def customer_orders():
    uid = session['user_id']
    conn = get_conn(); cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT o.id, o.total_amount, o.status, o.created_at, r.name AS restaurant
        FROM orders o JOIN restaurants r ON r.id=o.restaurant_id
        WHERE o.user_id=%s ORDER BY o.created_at DESC
    """, (uid,))
    orders = cur.fetchall()
    cur.close(); conn.close()
    return render_template('customer_orders.html', orders=orders)

# ========= Auth (register/login include agent role) =========
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        gmail = request.form.get('gmail','').strip()
        password = request.form.get('password','')
        role = request.form.get('role', 'customer')
        phone = request.form.get('phone', None) if role == 'agent' else None

        if not username or not gmail or not password:
            flash('Please fill all fields.'); return redirect(url_for('register'))

        pw = generate_password_hash(password)
        conn = get_conn(); cur = conn.cursor()
        # Try insert including phone if DB supports it, otherwise fallback without phone.
        try:
            cur.execute("""
                INSERT INTO users (username, gmail, password_hash, role, phone)
                VALUES (%s, %s, %s, %s, %s)
            """, (username, gmail, pw, role, phone))
            conn.commit()
        except Exception as e:
            conn.rollback()
            # fallback: try without phone column (in case schema older)
            try:
                cur.execute("""
                    INSERT INTO users (username, gmail, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                """, (username, gmail, pw, role))
                conn.commit()
            except Exception as e2:
                conn.rollback()
                flash('Email already exists or invalid input.')
                cur.close(); conn.close(); return redirect(url_for('register'))

        cur.close(); conn.close()
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        gmail = request.form.get('gmail','').strip()
        password = request.form.get('password','')
        conn = get_conn(); cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT * FROM users WHERE gmail=%s', (gmail,)); user = cur.fetchone()
        cur.close(); conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['gmail'] = user['gmail']
            session['role'] = user['role']
            # redirect based on role
            if user['role'] == 'restaurant':
                return redirect(url_for('restaurant_dashboard'))
            if user['role'] == 'agent':
                return redirect(url_for('agent_dashboard'))
            return redirect(url_for('index'))
        flash('Invalid email or password.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); flash('Logged out.'); return redirect(url_for('index'))

# ========= Profile =========
@app.route('/profile', methods=['GET', 'POST'])
@login_required()
def edit_profile():
    uid = session['user_id']
    role = session.get('role')

    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM users WHERE id=%s', (uid,))
    user = cur.fetchone()

    if not user:
        flash('User not found.')
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        gmail = request.form['gmail']
        pw = request.form.get('password', '').strip()

        # For agents only
        phone = request.form.get('phone') if role == 'agent' else None

        if pw:
            if role == 'agent':
                cur.execute(
                    'UPDATE users SET username=%s, gmail=%s, phone=%s, password_hash=%s WHERE id=%s',
                    (username, gmail, phone, generate_password_hash(pw), uid)
                )
            else:
                cur.execute(
                    'UPDATE users SET username=%s, gmail=%s, password_hash=%s WHERE id=%s',
                    (username, gmail, generate_password_hash(pw), uid)
                )
        else:
            if role == 'agent':
                cur.execute(
                    'UPDATE users SET username=%s, gmail=%s, phone=%s WHERE id=%s',
                    (username, gmail, phone, uid)
                )
            else:
                cur.execute(
                    'UPDATE users SET username=%s, gmail=%s WHERE id=%s',
                    (username, gmail, uid)
                )

        conn.commit()
        session['username'] = username
        session['gmail'] = gmail
        flash('Profile updated successfully.')

        cur.close()
        conn.close()

        # Redirect based on role
        if role == 'restaurant':
            return redirect(url_for('restaurant_dashboard'))
        elif role == 'agent':
            return redirect(url_for('agent_dashboard'))
        else:
            return redirect(url_for('index'))

    cur.close()
    conn.close()

    # Render the correct page based on role
    if role == 'agent':
        return render_template('agent_profile.html', user=user)
    else:
        return render_template('edit_profile.html', user=user)


# ========= Restaurant Owner =========
@app.route('/restaurant/dashboard')
@login_required(role='restaurant')
def restaurant_dashboard():
    owner_id = session['user_id']
    conn = get_conn(); cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM restaurants WHERE owner_id=%s', (owner_id,))
    restaurant = cur.fetchone()
    items = []
    if restaurant:
        cur.execute('SELECT * FROM menu_items WHERE restaurant_id=%s ORDER BY id DESC', (restaurant['id'],))
        items = cur.fetchall()
    cur.close(); conn.close()
    return render_template('restaurant_dashboard.html', restaurant=restaurant, items=items, VIDEO_SOURCE_MODE=VIDEO_SOURCE_MODE)

@app.route('/restaurant/manage-menu')
@login_required(role='restaurant')
def restaurant_manage_menu():
    owner_id = session['user_id']
    conn = get_conn(); cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM restaurants WHERE owner_id = %s', (owner_id,))
    restaurant = cur.fetchone()
    items = []
    if restaurant:
        cur.execute('SELECT * FROM menu_items WHERE restaurant_id = %s ORDER BY id DESC', (restaurant['id'],))
        items = cur.fetchall()
    cur.close(); conn.close()
    return render_template('restaurant_manage_menu.html', restaurant=restaurant, items=items, VIDEO_SOURCE_MODE=VIDEO_SOURCE_MODE)

@app.route('/restaurant/create', methods=['GET','POST'])
@login_required(role='restaurant')
def create_restaurant():
    if request.method == 'POST':
        name=request.form.get('name'); address=request.form.get('address'); cuisine=request.form.get('cuisine')
        image_path=None
        if 'image' in request.files:
            f=request.files['image']
            if f and f.filename:
                fname=secure_filename(f.filename); f.save(os.path.join(UPLOAD_FOLDER, fname)); image_path=f'uploads/{fname}'
        conn=get_conn(); cur=conn.cursor()
        cur.execute('INSERT INTO restaurants (owner_id,name,address,cuisine,image_path) VALUES (%s,%s,%s,%s,%s)',
                    (session['user_id'],name,address,cuisine,image_path))
        conn.commit(); cur.close(); conn.close(); flash('Restaurant created.');
        return redirect(url_for('restaurant_dashboard'))
    return render_template('create_restaurant.html')

@app.route('/restaurant/edit', methods=['GET','POST'])
@login_required(role='restaurant')
def edit_restaurant():
    owner_id=session['user_id']
    conn=get_conn(); cur=conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM restaurants WHERE owner_id=%s',(owner_id,)); r=cur.fetchone()
    if not r: cur.close(); conn.close(); flash('Create your restaurant first.'); return redirect(url_for('restaurant_dashboard'))
    if request.method=='POST':
        name=request.form.get('name'); address=request.form.get('address'); cuisine=request.form.get('cuisine')
        image_path=r['image_path']
        if 'image' in request.files:
            f=request.files['image']
            if f and f.filename:
                fname=secure_filename(f.filename); f.save(os.path.join(UPLOAD_FOLDER,fname)); image_path=f'uploads/{fname}'
        cur.execute('UPDATE restaurants SET name=%s,address=%s,cuisine=%s,image_path=%s WHERE id=%s',
                    (name,address,cuisine,image_path,r['id'])); conn.commit(); cur.close(); conn.close()
        flash('Restaurant updated.'); return redirect(url_for('restaurant_dashboard'))
    cur.close(); conn.close(); return render_template('edit_restaurant.html', restaurant=r)

# ========= Menu & Items =========
@app.route('/restaurant/<int:rid>/menu')
def view_restaurant_menu(rid):
    conn=get_conn(); cur=conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM restaurants WHERE id=%s', (rid,)); restaurant=cur.fetchone()
    cur.execute('SELECT * FROM menu_items WHERE restaurant_id=%s ORDER BY id', (rid,)); items=cur.fetchall()
    cur.close(); conn.close()
    return render_template('restaurant_menu.html', restaurant=restaurant, items=items, VIDEO_SOURCE_MODE=VIDEO_SOURCE_MODE)

@app.route('/restaurant/orders/<int:oid>')
@login_required(role='restaurant')
def restaurant_order_details(oid):
    owner_id = session['user_id']
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Verify the restaurant belongs to this owner
    cur.execute('SELECT id FROM restaurants WHERE owner_id=%s', (owner_id,))
    r = cur.fetchone()
    if not r:
        cur.close(); conn.close(); flash('No restaurant found.'); return redirect(url_for('restaurant_orders'))

    rid = r['id']
    cur.execute('SELECT * FROM orders WHERE id=%s AND restaurant_id=%s', (oid, rid))
    order = cur.fetchone()
    if not order:
        cur.close(); conn.close(); flash('Order not found.'); return redirect(url_for('restaurant_orders'))

    # Get order items
    cur.execute('SELECT name, price, qty FROM order_items WHERE order_id=%s', (oid,))
    items = cur.fetchall()
    cur.close(); conn.close()
    return render_template('restaurant_order_details.html', order=order, items=items)

@app.route('/restaurant/<int:rid>/menu/create', methods=['GET','POST'])
@login_required(role='restaurant')
def create_menu_item(rid):
    owner_id=session['user_id']
    conn=get_conn(); cur=conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM restaurants WHERE id=%s', (rid,)); r=cur.fetchone()
    if not r or r['owner_id']!=owner_id:
        cur.close(); conn.close(); flash('Not authorized.'); return redirect(url_for('index'))
    if request.method=='POST':
        name=request.form.get('name'); price=request.form.get('price'); description=request.form.get('description')
        image_path=None; video_path=None; video_url=request.form.get('video_url') or None
        if 'image' in request.files:
            f=request.files['image']
            if f and f.filename:
                fname=secure_filename(f.filename); f.save(os.path.join(UPLOAD_FOLDER,fname)); image_path=f'uploads/{fname}'
        if 'video' in request.files:
            v=request.files['video']
            if v and v.filename:
                vname=secure_filename(v.filename); v.save(os.path.join(UPLOAD_FOLDER,vname)); video_path=f'uploads/{vname}'
        cur.execute('INSERT INTO menu_items (restaurant_id,name,description,price,image_path,video_path,video_url) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                    (rid,name,description,price,image_path,video_path,video_url))
        conn.commit(); cur.close(); conn.close(); flash('Item added.'); return redirect(url_for('view_restaurant_menu', rid=rid))
    cur.close(); conn.close(); return render_template('create_menu_item.html', restaurant=r)

@app.route('/restaurant/<int:rid>/menu/<int:item_id>/edit', methods=['GET','POST'])
@login_required(role='restaurant')
def edit_menu_item(rid, item_id):
    owner_id=session['user_id']
    conn=get_conn(); cur=conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM restaurants WHERE id=%s', (rid,)); r=cur.fetchone()
    cur.execute('SELECT * FROM menu_items WHERE id=%s AND restaurant_id=%s', (item_id,rid)); item=cur.fetchone()
    if not r or r['owner_id']!=owner_id or not item:
        cur.close(); conn.close(); flash('Not authorized.'); return redirect(url_for('index'))
    if request.method=='POST':
        name=request.form.get('name'); price=request.form.get('price'); description=request.form.get('description')
        image_path=item['image_path']; video_path=item['video_path']; video_url=request.form.get('video_url') or item['video_url']
        if 'image' in request.files:
            f=request.files['image']
            if f and f.filename:
                fname=secure_filename(f.filename); f.save(os.path.join(UPLOAD_FOLDER,fname)); image_path=f'uploads/{fname}'
        if 'video' in request.files:
            v=request.files['video']
            if v and v.filename:
                vname=secure_filename(v.filename); v.save(os.path.join(UPLOAD_FOLDER,vname)); video_path=f'uploads/{vname}'
        cur.execute('UPDATE menu_items SET name=%s,description=%s,price=%s,image_path=%s,video_path=%s,video_url=%s WHERE id=%s',
                    (name,description,price,image_path,video_path,video_url,item_id))
        conn.commit(); cur.close(); conn.close(); flash('Item updated.'); return redirect(url_for('view_restaurant_menu', rid=rid))
    cur.close(); conn.close(); return render_template('edit_menu_item.html', restaurant=r, item=item)

@app.route('/restaurant/<int:rid>/menu/<int:item_id>/delete', methods=['POST'])
@login_required(role='restaurant')
def delete_menu_item(rid, item_id):
    owner_id=session['user_id']
    conn=get_conn(); cur=conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT owner_id FROM restaurants WHERE id=%s',(rid,)); r=cur.fetchone()
    if not r or r['owner_id']!=owner_id:
        cur.close(); conn.close(); flash('Not authorized.'); return redirect(url_for('index'))
    cur.execute('DELETE FROM menu_items WHERE id=%s', (item_id,)); conn.commit(); cur.close(); conn.close()
    flash('Deleted.'); return redirect(url_for('view_restaurant_menu', rid=rid))

# ========= Cart / Checkout / Orders =========
@app.route('/cart/add', methods=['POST'])
def cart_add():
    item_id = int(request.form.get('item_id'))
    conn=get_conn(); cur=conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT id,name,price,restaurant_id,image_path FROM menu_items WHERE id=%s',(item_id,))
    row=cur.fetchone(); cur.close(); conn.close()
    if not row: return jsonify({'ok':False}),404
    add_row_to_cart(row);
    return jsonify({'ok':True,'count':sum(i['qty'] for i in session['cart'])})

@app.route('/cart')
@login_required()
def cart_view():
    if session.get('role') == 'restaurant':
        flash('Cart is not available for restaurant accounts.'); return redirect(url_for('restaurant_dashboard'))
    cart = init_cart()
    subtotal = sum(i['price']*i['qty'] for i in cart)
    return render_template('cart.html', cart=cart, subtotal=subtotal)

@app.route('/cart/update', methods=['POST'])
def cart_update():
    cart = init_cart(); item_id = int(request.form.get('item_id')); qty = int(request.form.get('qty'))
    for it in cart:
        if it['item_id']==item_id: it['qty']=max(1,qty)
    session.modified=True; return redirect(url_for('cart_view'))

@app.route('/cart/remove', methods=['POST'])
def cart_remove():
    cart = init_cart(); item_id = int(request.form.get('item_id'))
    session['cart']=[i for i in cart if i['item_id']!=item_id]; session.modified=True
    return redirect(url_for('cart_view'))

@app.route('/checkout', methods=['GET','POST'])
@login_required()
def checkout():
    if session.get('role') == 'restaurant':
        flash('Checkout is for customers only.'); return redirect(url_for('restaurant_dashboard'))
    cart = init_cart()
    if not cart: flash('Your cart is empty.'); return redirect(url_for('index'))
    subtotal = sum(i['price']*i['qty'] for i in cart)
    if request.method=='POST':
        rid = cart[0]['restaurant_id']
        if any(i['restaurant_id']!=rid for i in cart):
            flash('Please order from a single restaurant at a time.'); return redirect(url_for('cart_view'))
        name=request.form.get('name'); phone=request.form.get('phone'); address=request.form.get('address')
        conn=get_conn(); cur=conn.cursor()
        cur.execute("""INSERT INTO orders (user_id,restaurant_id,total_amount,status,delivery_name,delivery_phone,delivery_address,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (session['user_id'],rid,subtotal,'Placed',name,phone,address,datetime.now()))
        oid=cur.fetchone()[0]
        for it in cart:
            cur.execute('INSERT INTO order_items (order_id,item_id,name,price,qty) VALUES (%s,%s,%s,%s,%s)',
                        (oid,it['item_id'],it['name'],it['price'],it['qty']))
        conn.commit(); cur.close(); conn.close()
        clear_cart(); flash(f'Order #{oid} placed!')

        # Broadcast that a new order was placed (restaurant & agents)
        broadcast_order_update(oid, 'Placed')
        return redirect(url_for('order_details', order_id=oid))
    return render_template('checkout.html', subtotal=subtotal, cart=cart)

@app.route('/orders/<int:order_id>')
@login_required()
def order_details(order_id):
    uid=session['user_id']
    conn=get_conn(); cur=conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    # fetch order owned by this user (or if restaurant/agent they may view differently in their dashboards)
    cur.execute('SELECT o.*, u.username AS customer_name, a.username AS agent_name, a.phone AS agent_phone FROM orders o LEFT JOIN users u ON u.id=o.user_id LEFT JOIN users a ON a.id=o.agent_id WHERE o.id=%s AND o.user_id=%s', (order_id, uid))
    order = cur.fetchone()
    # if not found for this user, show message
    if not order:
        cur.close(); conn.close(); flash('Order not found.'); return redirect(url_for('customer_orders'))
    cur.execute('SELECT name,price,qty FROM order_items WHERE order_id=%s', (order_id,)); items=cur.fetchall()
    cur.close(); conn.close()
    return render_template('order_details.html', order=order, items=items)

# ========= Restaurant Orders (list + status update) =========
@app.route('/restaurant/orders')
@login_required(role='restaurant')
def restaurant_orders():
    owner_id = session['user_id']
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute('SELECT id FROM restaurants WHERE owner_id=%s', (owner_id,))
    r = cur.fetchone()
    if not r:
        flash('Create your restaurant first.'); return redirect(url_for('restaurant_dashboard'))
    rid = r['id']

    cur.execute("""
        SELECT o.*, u.username AS customer
        FROM orders o
        JOIN users u ON u.id = o.user_id
        WHERE o.restaurant_id = %s
        ORDER BY o.created_at DESC
    """, (rid,))
    orders = cur.fetchall(); cur.close(); conn.close()
    return render_template('restaurant_orders.html', orders=orders)

@app.route('/restaurant/orders/<int:oid>/action', methods=['POST'])
@login_required(role='restaurant')
def restaurant_order_action(oid):
    action = request.form.get('action')
    conn = get_conn(); cur = conn.cursor()
    new_status = None

    if action == 'accept':
        new_status = 'Preparing'
    elif action == 'reject':
        new_status = 'Rejected'
    elif action == 'ready':
        new_status = 'Ready'

    if new_status:
        cur.execute('UPDATE orders SET status=%s WHERE id=%s', (new_status, oid))
        conn.commit()
        broadcast_order_update(oid, new_status)

    cur.close(); conn.close()
    return redirect(url_for('restaurant_orders'))

# Legacy/compat route kept but not necessary - remove if redundant
@app.route('/restaurant/orders/<int:oid>/status', methods=['POST'])
@login_required(role='restaurant')
def update_order_status(oid):
    status=request.form.get('status')
    conn=get_conn(); cur=conn.cursor()
    cur.execute('UPDATE orders SET status=%s WHERE id=%s', (status, oid))
    conn.commit(); cur.close(); conn.close()
    broadcast_order_update(oid, status)
    return redirect(url_for('restaurant_orders'))

@app.route('/agent/dashboard')
@login_required(role='agent')
def agent_dashboard():
    """Show available deliveries (Ready orders) and active deliveries (assigned but not delivered)."""
    agent_id = session['user_id']
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Available (unassigned) orders
    cur.execute("""
        SELECT o.id, o.delivery_name, o.delivery_phone, o.delivery_address,
               o.total_amount, o.status, r.name AS restaurant_name
        FROM orders o
        JOIN restaurants r ON r.id = o.restaurant_id
        WHERE o.status = 'Ready' AND (o.agent_id IS NULL)
        ORDER BY o.created_at ASC
    """)
    available_orders = cur.fetchall()

    # Active orders for this agent (not yet delivered)
    cur.execute("""
        SELECT o.*, u.username AS customer_name, r.name AS restaurant_name
        FROM orders o
        JOIN users u ON u.id = o.user_id
        JOIN restaurants r ON r.id = o.restaurant_id
        WHERE o.agent_id = %s AND o.status != 'Delivered'
        ORDER BY o.created_at DESC
    """, (agent_id,))
    active_orders = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        'agent_dashboard.html',
        available_orders=available_orders,
        active_orders=active_orders
    )


@app.route('/agent/orders')
@login_required(role='agent')
def agent_orders():
    """Show delivered orders (history)."""
    agent_id = session['user_id']
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Delivered (completed) orders
    cur.execute("""
        SELECT o.*, u.username AS customer_name, r.name AS restaurant_name
        FROM orders o
        JOIN users u ON u.id = o.user_id
        JOIN restaurants r ON r.id = o.restaurant_id
        WHERE o.agent_id = %s AND o.status = 'Delivered'
        ORDER BY o.created_at DESC
    """, (agent_id,))
    delivered_orders = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('agent_orders.html', delivered_orders=delivered_orders)



@app.route('/agent/accept/<int:oid>', methods=['POST'])
@login_required(role='agent')
def agent_accept(oid):
    agent_id = session['user_id']
    conn=get_conn(); cur=conn.cursor()
    # atomically assign only if still Ready and unassigned
    cur.execute("""
        UPDATE orders
        SET agent_id=%s, status='Out for Delivery'
        WHERE id=%s AND status='Ready' AND (agent_id IS NULL)
        RETURNING id
    """, (agent_id, oid))
    row = cur.fetchone()
    if row:
        conn.commit()
        # broadcast assignment (agent_id included)
        broadcast_order_update(oid, 'Out for Delivery', {'agent_id': agent_id})
    else:
        conn.rollback()
    cur.close(); conn.close()
    return redirect(url_for('agent_dashboard'))

@app.route('/agent/update/<int:oid>', methods=['POST'])
@login_required(role='agent')
def agent_update_status(oid):
    agent_id = session['user_id']
    new_status = request.form.get('status')
    conn=get_conn(); cur=conn.cursor()
    # verify ownership
    cur.execute('SELECT agent_id FROM orders WHERE id=%s', (oid,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close(); return redirect(url_for('agent_dashboard'))
    # row[0] may be None or an id
    if row[0] != agent_id:
        cur.close(); conn.close(); return redirect(url_for('agent_dashboard'))

    if new_status in ['Out for Delivery', 'Delivered']:
        cur.execute('UPDATE orders SET status=%s WHERE id=%s', (new_status, oid))
        conn.commit()
        broadcast_order_update(oid, new_status, {'agent_id': agent_id})
    cur.close(); conn.close()
    return redirect(url_for('agent_dashboard'))

@app.route("/dashboard")
def restaurant_dashboard():
    restaurant = get_restaurant_for_current_user()
    items = get_menu_items(restaurant.id) if restaurant else []
    return render_template(
        "restaurant_dashboard.html",
        restaurant=restaurant,
        items=items,
        VIDEO_SOURCE_MODE="local"  # or "remote" if using URLs
    )


# ========= Agent API helper (AJAX) =========
@app.route('/agent/available-json')
@login_required(role='agent')
def agent_available_json():
    conn=get_conn(); cur=conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""SELECT o.id, o.total_amount, o.status, o.created_at, r.name AS restaurant, r.address
                   FROM orders o JOIN restaurants r ON r.id=o.restaurant_id
                   WHERE o.status='Ready' AND (o.agent_id IS NULL) ORDER BY o.created_at ASC""")
    rows = cur.fetchall(); cur.close(); conn.close()
    # convert to plain list of dicts
    return jsonify([dict(r) for r in rows])

# ========= SocketIO events (basic) =========
@socketio.on('connect')
def on_connect():
    sid = request.sid
    # optional: log or use join_room based on session info (not available directly here)
    emit('server_ack', {'msg': 'connected'})

@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    # optional cleanup

# join per-order room if client requests (useful for targeted updates)
@socketio.on('join_order_room')
def handle_join(data):
    order_id = data.get('order_id')
    if order_id:
        room = f'order_{order_id}'
        join_room(room)
        emit('joined', {'room': room})

# Optionally: emit to order room in broadcast helper (not used by default)
def emit_to_order_room(order_id, event, payload):
    room = f'order_{order_id}'
    socketio.emit(event, payload, room=room)

# ========= Run Server =========
if __name__ == '__main__':
    # Use socketio.run to enable websocket server
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
