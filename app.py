import os
import json
import stripe
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from models import db, Reservation, Table, MenuItem, Order, OrderItem
from datetime import datetime, timedelta
from sqlalchemy import or_
# Import moved to avoid circular import

load_dotenv()

# Create Flask app without static folder
app = Flask(__name__, static_folder=None)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(os.getcwd(), "instance", "restaurant.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'devsecret')

# Stripe configuration (using test keys for development)
# For production, set these environment variables with your live keys
stripe.api_key = os.getenv('STRIPE_API_KEY', 'sk_test_51234567890abcdef')  # Replace with your test secret key
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', 'pk_test_51234567890abcdef')  # Replace with your test publishable key

# Configure static files
app.config['STATIC_FOLDER'] = os.path.join(app.root_path, 'static')

# Add MIME type configuration
app.config['MIME_TYPES'] = {
    '.js': 'application/javascript',
    '.css': 'text/css',
    '.html': 'text/html',
    '.txt': 'text/plain',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon'
}

db.init_app(app)
auth = HTTPBasicAuth()

# Custom Jinja2 filter for 12-hour time format
@app.template_filter('time12')
def time12_filter(time_str):
    """Convert 24-hour time format (HH:MM) to 12-hour format (H:MM AM/PM)"""
    try:
        # Parse the time string
        time_obj = datetime.strptime(time_str, '%H:%M').time()
        # Format as 12-hour time
        return time_obj.strftime('%I:%M %p').lstrip('0')
    except (ValueError, AttributeError):
        return time_str  # Return original if parsing fails

# Custom Jinja2 filter for time ago calculation
@app.template_filter('time_ago')
def time_ago_filter(dt):
    """Calculate how many minutes ago a datetime was"""
    try:
        now = datetime.now()
        if dt.tzinfo is None:
            # If datetime is naive, assume it's in the same timezone as now
            diff = now - dt
        else:
            # If datetime is timezone-aware, convert now to the same timezone
            diff = now.replace(tzinfo=dt.tzinfo) - dt
        
        minutes = int(diff.total_seconds() / 60)
        
        if minutes < 1:
            return "Just now"
        elif minutes < 60:
            return f"{minutes} min ago"
        else:
            hours = minutes // 60
            remaining_minutes = minutes % 60
            if remaining_minutes == 0:
                return f"{hours}h ago"
            else:
                return f"{hours}h {remaining_minutes}m ago"
    except (AttributeError, TypeError):
        return "Unknown"

# Custom Jinja2 filter for person/people pluralization
@app.template_filter('person_plural')
def person_plural_filter(count):
    """Return 'person' for 1, 'people' for any other number"""
    try:
        count = int(count)
        return "person" if count == 1 else "people"
    except (ValueError, TypeError):
        return "people"

# User credentials for API auth (optional)
users = {
    os.getenv('HTTP_USERNAME', 'admin'): generate_password_hash(os.getenv('HTTP_PASSWORD', 'admin'))
}

# Add error handler for 401 errors
@auth.error_handler
def auth_error(status):
    return jsonify({'error': 'Authentication required'}), status

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username

# Use this block instead
with app.app_context():
    # Ensure instance directory exists
    import os
    os.makedirs('instance', exist_ok=True)
    
    try:
        db.create_all()
        print("✅ Database tables created/verified")
        
        # Database migration: Add missing payment columns to orders table
        def migrate_orders_table():
            """Add payment columns to orders table if they don't exist"""
            try:
                import sqlite3
                from sqlalchemy import text
                
                # Use direct SQLite connection for more reliable migration
                db_path = 'instance/restaurant.db'
                
                # Check if database file exists
                if not os.path.exists(db_path):
                    print("⚠️ Database file doesn't exist, creating new one")
                    return
                
                # Direct SQLite connection for migration
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Check if orders table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
                if not cursor.fetchone():
                    print("⚠️ Orders table doesn't exist yet, skipping migration")
                    conn.close()
                    return
                
                # Check current columns
                cursor.execute("PRAGMA table_info(orders)")
                columns_info = cursor.fetchall()
                columns = [col[1] for col in columns_info]
                print(f"📋 Current orders table columns: {columns}")
                
                # Define payment columns to add
                payment_columns = [
                    ('payment_status', "VARCHAR(20) DEFAULT 'unpaid'"),
                    ('payment_intent_id', "VARCHAR(100)"),
                    ('payment_amount', "FLOAT"),
                    ('payment_date', "DATETIME")
                ]
                
                migration_needed = False
                for col_name, col_def in payment_columns:
                    if col_name not in columns:
                        print(f"🔧 Adding missing column: {col_name}")
                        cursor.execute(f"ALTER TABLE orders ADD COLUMN {col_name} {col_def}")
                        migration_needed = True
                
                if migration_needed:
                    # Update existing orders to have 'unpaid' status
                    cursor.execute("UPDATE orders SET payment_status = 'unpaid' WHERE payment_status IS NULL")
                    conn.commit()
                    print("✅ Orders table migration completed")
                    
                    # Verify the migration
                    cursor.execute("PRAGMA table_info(orders)")
                    updated_columns = [col[1] for col in cursor.fetchall()]
                    print(f"📋 Updated orders table columns: {updated_columns}")
                else:
                    print("✅ Orders table already has all payment columns")
                
                conn.close()
                
            except Exception as e:
                print(f"⚠️ Orders table migration error: {e}")
                import traceback
                traceback.print_exc()
        
        # Run migration
        migrate_orders_table()
        
    except Exception as e:
        print(f"⚠️ Database initialization error: {e}")
        import traceback
        traceback.print_exc()
    
    # Initialize menu items if they don't exist
    if not MenuItem.query.first():
        menu_items = [
            # Appetizers
            MenuItem(
                name='Bruschetta',
                description='Grilled bread rubbed with garlic, topped with diced tomatoes, fresh basil, and olive oil',
                price=8.99,
                category='appetizers'
            ),
            MenuItem(
                name='Buffalo Wings',
                description='Crispy chicken wings tossed in spicy buffalo sauce, served with celery and blue cheese',
                price=12.99,
                category='appetizers'
            ),
            MenuItem(
                name='Spinach Artichoke Dip',
                description='Creamy blend of spinach, artichokes, and cheese served hot with tortilla chips',
                price=10.99,
                category='appetizers'
            ),
            
            # Breakfast
            MenuItem(
                name='Classic Eggs Benedict',
                description='Poached eggs on English muffins with Canadian bacon and hollandaise sauce',
                price=14.99,
                category='breakfast'
            ),
            MenuItem(
                name='Blueberry Pancakes',
                description='Fluffy pancakes loaded with fresh blueberries, served with maple syrup and butter',
                price=11.99,
                category='breakfast'
            ),
            MenuItem(
                name='Avocado Toast',
                description='Multigrain toast topped with smashed avocado, cherry tomatoes, and everything seasoning',
                price=9.99,
                category='breakfast'
            ),
            
            # Main Courses / Dinner
            MenuItem(
                name='Grilled Salmon',
                description='Fresh Atlantic salmon fillet, grilled and served with seasonal vegetables',
                price=24.99,
                category='main-courses'
            ),
            MenuItem(
                name='Ribeye Steak',
                description='12oz prime ribeye steak grilled to perfection, served with garlic mashed potatoes',
                price=32.99,
                category='main-courses'
            ),
            MenuItem(
                name='Chicken Parmesan',
                description='Breaded chicken breast topped with marinara sauce and mozzarella, served with pasta',
                price=19.99,
                category='main-courses'
            ),
            
            # Desserts
            MenuItem(
                name='Chocolate Lava Cake',
                description='Warm chocolate cake with a molten center, served with vanilla ice cream',
                price=8.99,
                category='desserts'
            ),
            MenuItem(
                name='New York Cheesecake',
                description='Classic creamy cheesecake with graham cracker crust and berry compote',
                price=7.99,
                category='desserts'
            ),
            MenuItem(
                name='Tiramisu',
                description='Traditional Italian dessert with coffee-soaked ladyfingers and mascarpone cream',
                price=9.99,
                category='desserts'
            ),
            
            # Drinks
            MenuItem(
                name='Signature Cocktail',
                description='House-made infusion with fresh fruits and premium spirits',
                price=12.99,
                category='drinks'
            ),
            MenuItem(
                name='Craft Beer Selection',
                description='Rotating selection of local craft beers on tap',
                price=6.99,
                category='drinks'
            ),
            MenuItem(
                name='House Wine',
                description='Carefully selected red or white wine by the glass',
                price=8.99,
                category='drinks'
            ),
            MenuItem(
                name='Coca-Cola',
                description='Classic Coca-Cola soft drink',
                price=2.99,
                category='drinks'
            ),
            MenuItem(
                name='Pepsi',
                description='Classic Pepsi cola soft drink',
                price=2.99,
                category='drinks'
            ),
            MenuItem(
                name='Diet Pepsi',
                description='Zero-calorie Pepsi cola',
                price=2.99,
                category='drinks'
            ),
            MenuItem(
                name='Mountain Dew',
                description='Citrus-flavored Pepsi product',
                price=2.99,
                category='drinks'
            ),
            MenuItem(
                name='Sierra Mist',
                description='Lemon-lime soda by Pepsi',
                price=2.99,
                category='drinks'
            ),
            MenuItem(
                name='Iced Tea',
                description='Freshly brewed iced tea with lemon',
                price=2.99,
                category='drinks'
            ),
            MenuItem(
                name='Coffee',
                description='Freshly brewed premium coffee',
                price=3.49,
                category='drinks'
            ),
            MenuItem(
                name='Sparkling Water',
                description='Premium sparkling water with lime',
                price=2.49,
                category='drinks'
            ),
            MenuItem(
                name='Fresh Lemonade',
                description='House-made lemonade with fresh lemons',
                price=3.99,
                category='drinks'
            ),
            MenuItem(
                name='Hot Tea',
                description='Selection of premium teas',
                price=2.99,
                category='drinks'
            )
        ]
        for item in menu_items:
            db.session.add(item)
        db.session.commit()

# Web routes
@app.route('/')
def index():
    search_query = request.args.get('search', '').strip()
    
    if search_query:
        # Search by name, phone number, or reservation number
        reservations = Reservation.query.filter(
            or_(
                Reservation.name.ilike(f'%{search_query}%'),
                Reservation.phone_number.ilike(f'%{search_query}%'),
                Reservation.reservation_number.ilike(f'%{search_query}%')
            )
        ).order_by(Reservation.date, Reservation.time).all()
    else:
        reservations = Reservation.query.order_by(Reservation.date, Reservation.time).all()
    
    return render_template('index.html', reservations=reservations)

@app.route('/reservation/new', methods=['GET', 'POST'])
def new_reservation():
    if request.method == 'POST':
        name = request.form['name']
        party_size = request.form['party_size']
        date = request.form['date']
        time = request.form['time']
        phone_number = request.form['phone_number']
        # Generate a unique 6-digit reservation number
        import random
        while True:
            reservation_number = f"{random.randint(100000, 999999)}"
            # Check if this number already exists
            existing = Reservation.query.filter_by(reservation_number=reservation_number).first()
            if not existing:
                break
        
        reservation = Reservation(
            reservation_number=reservation_number,
            name=name, 
            party_size=party_size, 
            date=date, 
            time=time, 
            phone_number=phone_number
        )
        db.session.add(reservation)
        db.session.flush()  # Get reservation.id
        
        # Send SMS confirmation using the receptionist agent's SMS functionality
        if receptionist_agent and phone_number:
            try:
                # Prepare reservation data for SMS
                reservation_data = {
                    'id': reservation.id,
                    'reservation_number': reservation.reservation_number,
                    'name': reservation.name,
                    'date': str(reservation.date),
                    'time': str(reservation.time),
                    'party_size': reservation.party_size,
                    'special_requests': reservation.special_requests or ''
                }
                
                # Send SMS confirmation
                sms_result = receptionist_agent.send_reservation_sms(reservation_data, phone_number)
                
                # Console logging for SMS status
                print(f"📱 WEB FORM SMS Status for reservation {reservation.id}:")
                print(f"   Phone: {phone_number}")
                print(f"   Success: {sms_result.get('success', False)}")
                print(f"   SMS Sent: {sms_result.get('sms_sent', False)}")
                if not sms_result.get('success'):
                    print(f"   Error: {sms_result.get('error', 'Unknown error')}")
                else:
                    print(f"   Result: {sms_result.get('sms_result', 'SMS sent')}")
                
                if sms_result.get('success'):
                    flash('Reservation created and SMS confirmation sent!', 'success')
                else:
                    flash('Reservation created! (SMS confirmation could not be sent)', 'warning')
                    
            except Exception as e:
                print(f"📱 WEB FORM SMS Exception for reservation {reservation.id}: {e}")
                flash('Reservation created! (SMS confirmation could not be sent)', 'warning')
        else:
            flash('Reservation created!', 'success')
        
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('reservation_form.html', action='Create')

# Edit reservation route removed - now handled by modal and API endpoint

@app.route('/reservation/<int:res_id>/delete', methods=['POST'])
def delete_reservation(res_id):
    reservation = Reservation.query.get_or_404(res_id)
    db.session.delete(reservation)
    db.session.commit()
    flash('Reservation deleted!', 'info')
    return redirect(url_for('index'))

@app.route('/calendar')
def calendar():
    try:
        # Get today's date in YYYY-MM-DD format
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Get today's reservations ordered by time
        todays_reservations = Reservation.query.filter_by(date=today).order_by(Reservation.time).all()
        
        # Ensure we always return a list, even if empty
        if todays_reservations is None:
            todays_reservations = []
            
        return render_template('calendar.html', todays_reservations=todays_reservations)
    except Exception as e:
        # Log the error and return an empty list
        print(f"Error in calendar route: {str(e)}")
        return render_template('calendar.html', todays_reservations=[])

@app.route('/api/reservations/calendar')
def get_calendar_events():
    try:
        reservations = Reservation.query.all()
        events = []
        
        for reservation in reservations:
            try:
                # Parse the date and time strings
                date_str = reservation.date
                time_str = reservation.time
                
                # Create datetime object
                dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                
                # Use proper pluralization for party size
                party_text = "person" if reservation.party_size == 1 else "people"
                
                # Create event object
                event = {
                    'id': reservation.id,
                    'title': f"{reservation.name} ({reservation.party_size} {party_text})",
                    'start': dt.isoformat(),
                    'end': (dt + timedelta(hours=2)).isoformat(),  # Assuming 2-hour reservations
                    'extendedProps': {
                        'partySize': reservation.party_size,
                        'phoneNumber': reservation.phone_number,
                        'status': reservation.status,
                        'specialRequests': reservation.special_requests or ''
                    }
                }
                events.append(event)
            except (ValueError, AttributeError) as e:
                # Log individual reservation errors but continue processing others
                print(f"Error processing reservation {reservation.id}: {str(e)}")
                continue
        
        return jsonify(events)
    except Exception as e:
        # Log the error and return an empty list
        print(f"Error in calendar events API: {str(e)}")
        return jsonify([]), 500

# REST API endpoints
@app.route('/api/reservations', methods=['GET'])
@auth.login_required
def api_list_reservations():
    reservations = Reservation.query.all()
    return jsonify([r.to_dict() for r in reservations])

@app.route('/api/menu_items')
def api_menu_items():
    items = MenuItem.query.filter_by(is_available=True).all()
    return jsonify([
        {
            'id': item.id,
            'name': item.name,
            'description': item.description,
            'price': item.price,
            'category': item.category
        } for item in items
    ])

@app.route('/api/reservations', methods=['POST'])
def api_create_reservation():
    name = request.form.get('name')
    party_size = request.form.get('party_size')
    date = request.form.get('date')
    time = request.form.get('time')
    phone_number = request.form.get('phone_number')
    special_requests = request.form.get('special_requests')
    party_orders_json = request.form.get('party_orders')
    try:
        # Generate a unique 6-digit reservation number
        import random
        while True:
            reservation_number = f"{random.randint(100000, 999999)}"
            # Check if this number already exists
            existing = Reservation.query.filter_by(reservation_number=reservation_number).first()
            if not existing:
                break
        
        reservation = Reservation(
            reservation_number=reservation_number,
            name=name,
            party_size=int(party_size),
            date=date,
            time=time,
            phone_number=phone_number,
            status='confirmed',
            special_requests=special_requests
        )
        db.session.add(reservation)
        db.session.flush()  # Get reservation.id
        party_orders = json.loads(party_orders_json) if party_orders_json else []
        total_reservation_amount = 0.0
        for person in party_orders:
            person_name = person.get('name', '')
            items = person.get('items', [])
            if not items:
                continue
            order = Order(
                order_number=generate_order_number(),
                reservation_id=reservation.id,
                table_id=None,  # Table assignment logic can be added
                person_name=person_name,
                status='pending',
                total_amount=0.0
            )
            db.session.add(order)
            total = 0.0
            for oi in items:
                menu_item = MenuItem.query.get(int(oi['menu_item_id']))
                qty = int(oi['quantity'])
                if menu_item and qty > 0:
                    total += menu_item.price * qty
                    db.session.add(OrderItem(
                        order=order,
                        menu_item=menu_item,
                        quantity=qty,
                        price_at_time=menu_item.price
                    ))
            order.total_amount = total
            total_reservation_amount += total
        
        # Send SMS confirmation using the receptionist agent's SMS functionality
        receptionist_agent = get_receptionist_agent()
        if receptionist_agent and phone_number:
            try:
                # Prepare reservation data for SMS
                reservation_data = {
                    'id': reservation.id,
                    'reservation_number': reservation.reservation_number,
                    'name': reservation.name,
                    'date': str(reservation.date),
                    'time': str(reservation.time),
                    'party_size': reservation.party_size,
                    'special_requests': reservation.special_requests or ''
                }
                
                # Send SMS confirmation
                sms_result = receptionist_agent.send_reservation_sms(reservation_data, phone_number)
                
                # Console logging for SMS status
                print(f"📱 WEB API SMS Status for reservation {reservation.id}:")
                print(f"   Phone: {phone_number}")
                print(f"   Success: {sms_result.get('success', False)}")
                print(f"   SMS Sent: {sms_result.get('sms_sent', False)}")
                if not sms_result.get('success'):
                    print(f"   Error: {sms_result.get('error', 'Unknown error')}")
                else:
                    print(f"   Result: {sms_result.get('sms_result', 'SMS sent')}")
                
            except Exception as e:
                print(f"📱 WEB API SMS Exception for reservation {reservation.id}: {e}")
                # Don't fail the reservation if SMS fails
                sms_result = {'success': False, 'error': str(e)}
        
        db.session.commit()
        return jsonify({'success': True, 'total_reservation_amount': total_reservation_amount})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/reservations/<int:res_id>', methods=['GET'])
def api_get_reservation(res_id):
    reservation = Reservation.query.get_or_404(res_id)
    return jsonify(reservation.to_dict())

@app.route('/api/reservations/<int:res_id>', methods=['PUT'])
def api_update_reservation(res_id):
    try:
        reservation = Reservation.query.get_or_404(res_id)
        data = request.json
        print(f"DEBUG: Received data for reservation {res_id}: {data}")
        
        # Update basic reservation fields
        reservation.name = data.get('name', reservation.name)
        reservation.party_size = data.get('party_size', reservation.party_size)
        reservation.date = data.get('date', reservation.date)
        reservation.time = data.get('time', reservation.time)
        reservation.phone_number = data.get('phone_number', reservation.phone_number)
        reservation.special_requests = data.get('special_requests', reservation.special_requests)
        
        # Handle party orders if provided
        if 'party_orders' in data and data['party_orders']:
            try:
                # Delete existing orders for this reservation
                existing_orders = Order.query.filter_by(reservation_id=reservation.id).all()
                for order in existing_orders:
                    # Delete order items first
                    OrderItem.query.filter_by(order_id=order.id).delete()
                    db.session.delete(order)
                
                # Create new orders from party_orders data
                party_orders_data = data['party_orders']
                if isinstance(party_orders_data, str):
                    party_orders = json.loads(party_orders_data)
                else:
                    party_orders = party_orders_data
                
                print(f"DEBUG: Processing party orders: {party_orders}")
                
                # Handle both formats: array of {name, items} or dict with person names as keys
                if isinstance(party_orders, list):
                    # New format: array of {name, items}
                    for person_order in party_orders:
                        person_name = person_order.get('name', '') or f"Person {party_orders.index(person_order) + 1}"
                        items = person_order.get('items', [])
                        
                        if items and len(items) > 0:  # Only create order if there are items
                            order = Order(
                                order_number=generate_order_number(),
                                reservation_id=reservation.id,
                                person_name=person_name,
                                status='pending'
                            )
                            db.session.add(order)
                            db.session.flush()  # Get order ID
                            
                            total_amount = 0
                            for oi in items:
                                try:
                                    menu_item = MenuItem.query.get(int(oi['menu_item_id']))
                                    if menu_item:
                                        order_item = OrderItem(
                                            order_id=order.id,
                                            menu_item_id=menu_item.id,
                                            quantity=int(oi['quantity']),
                                            price_at_time=menu_item.price
                                        )
                                        db.session.add(order_item)
                                        total_amount += menu_item.price * int(oi['quantity'])
                                except (ValueError, KeyError) as e:
                                    print(f"Error processing order item: {e}")
                                    continue
                            
                            order.total_amount = total_amount
                            print(f"DEBUG: Created order for {person_name} with {len(items)} items, total: ${total_amount}")
                else:
                    # Old format: dict with person names as keys
                    for person_name, orders in party_orders.items():
                        if orders and len(orders) > 0:  # Only create order if there are items
                            order = Order(
                                order_number=generate_order_number(),
                                reservation_id=reservation.id,
                                person_name=person_name,
                                status='pending'
                            )
                            db.session.add(order)
                            db.session.flush()  # Get order ID
                            
                            total_amount = 0
                            for oi in orders:
                                try:
                                    menu_item = MenuItem.query.get(int(oi['menu_item_id']))
                                    if menu_item:
                                        order_item = OrderItem(
                                            order_id=order.id,
                                            menu_item_id=menu_item.id,
                                            quantity=int(oi['quantity']),
                                            price_at_time=menu_item.price
                                        )
                                        db.session.add(order_item)
                                        total_amount += menu_item.price * int(oi['quantity'])
                                except (ValueError, KeyError) as e:
                                    print(f"Error processing order item: {e}")
                                    continue
                            
                            order.total_amount = total_amount
            except Exception as e:
                print(f"Error handling party orders: {e}")
                # Continue without party orders if there's an error
        
        db.session.commit()
        return jsonify({'success': True, 'reservation': reservation.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/reservations/<int:res_id>', methods=['DELETE'])
def api_delete_reservation(res_id):
    reservation = Reservation.query.get_or_404(res_id)
    db.session.delete(reservation)
    db.session.commit()
    return '', 204

@app.route('/api/menu', methods=['GET'])
def get_menu():
    menu_items = MenuItem.query.all()
    return jsonify([item.to_dict() for item in menu_items])

def generate_order_number():
    """Generate a unique 6-digit order number"""
    import random
    while True:
        # Generate a 6-digit number (100000 to 999999)
        number = str(random.randint(100000, 999999))
        
        # Check if this number already exists
        existing = Order.query.filter_by(order_number=number).first()
        if not existing:
            return number

@app.route('/api/order', methods=['POST'])
def place_order():
    data = request.json
    reservation_id = data.get('reservation_id')
    items = data.get('items')  # List of {menu_item_id, quantity}

    if not reservation_id or not items:
        return jsonify({'error': 'Invalid data'}), 400

    order = Order(
        order_number=generate_order_number(),
        reservation_id=reservation_id, 
        status='pending'
    )
    db.session.add(order)
    db.session.flush()  # Get the order ID

    total_amount = 0
    for item in items:
        menu_item = MenuItem.query.get(item['menu_item_id'])
        if not menu_item or not menu_item.is_available:
            continue
        order_item = OrderItem(
            order_id=order.id,
            menu_item_id=menu_item.id,
            quantity=item['quantity'],
            price_at_time=menu_item.price
        )
        db.session.add(order_item)
        total_amount += menu_item.price * item['quantity']

    order.total_amount = total_amount
    db.session.commit()

    return jsonify(order.to_dict()), 201

@app.route('/api/orders', methods=['POST'])
def create_standalone_order():
    """Create a standalone order (pickup/delivery) without reservation"""
    try:
        data = request.get_json()
        
        # Extract order data
        items = data.get('items', [])
        order_type = data.get('orderType', 'pickup')
        order_date = data.get('orderDate')
        order_time = data.get('orderTime')
        customer_name = data.get('customerName')
        customer_phone = data.get('customerPhone')
        customer_address = data.get('customerAddress')
        special_instructions = data.get('specialInstructions', '')
        
        if not items or not customer_name or not customer_phone or not order_date or not order_time:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Create order
        order = Order(
            order_number=generate_order_number(),
            person_name=customer_name,
            status='pending',
            target_date=order_date,
            target_time=order_time,
            order_type=order_type,
            customer_phone=customer_phone,
            customer_address=customer_address,
            special_instructions=special_instructions
        )
        db.session.add(order)
        db.session.flush()  # Get order.id
        
        total_amount = 0
        
        # Add order items
        for item_data in items:
            # Find menu item by name (since we're using generated IDs)
            menu_item = MenuItem.query.filter_by(name=item_data['name']).first()
            if menu_item:
                order_item = OrderItem(
                    order_id=order.id,
                    menu_item_id=menu_item.id,
                    quantity=item_data['quantity'],
                    price_at_time=item_data['price'],
                    notes=f"Order Type: {order_type.title()}\nPhone: {customer_phone}\n{f'Address: {customer_address}' if customer_address else ''}\n{f'Instructions: {special_instructions}' if special_instructions else ''}".strip()
                )
                db.session.add(order_item)
                total_amount += item_data['price'] * item_data['quantity']
        
        order.total_amount = total_amount
        db.session.commit()
        
        # Calculate estimated time (15-30 minutes for pickup, 30-45 for delivery)
        estimated_time = 25 if order_type == 'pickup' else 40
        
        return jsonify({
            'success': True, 
            'orderId': order.id,
            'estimatedTime': estimated_time,
            'message': f'Order placed successfully! Estimated {order_type} time: {estimated_time} minutes.'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/kitchen')
def kitchen_orders():
    """Kitchen dashboard to view and manage orders"""
    from datetime import datetime, timedelta
    
    # Get filter parameters
    filter_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    start_time = request.args.get('start_time', '00:00')
    end_time = request.args.get('end_time', '23:59')
    
    # Parse datetime filters
    try:
        start_datetime = datetime.strptime(f"{filter_date} {start_time}", '%Y-%m-%d %H:%M')
        end_datetime = datetime.strptime(f"{filter_date} {end_time}", '%Y-%m-%d %H:%M')
    except ValueError:
        # Default to today if parsing fails
        start_datetime = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_datetime = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Query orders with target date/time filters
    base_query = Order.query.filter(
        Order.target_date == filter_date,
        Order.target_time >= start_time,
        Order.target_time <= end_time
    )
    
    pending_orders = base_query.filter_by(status='pending').order_by(Order.target_time).all()
    preparing_orders = base_query.filter_by(status='preparing').order_by(Order.target_time).all()
    ready_orders = base_query.filter_by(status='ready').order_by(Order.target_time).all()
    
    return render_template('kitchen.html', 
                         pending_orders=pending_orders,
                         preparing_orders=preparing_orders, 
                         ready_orders=ready_orders,
                         filter_date=filter_date,
                         start_time=start_time,
                         end_time=end_time)

@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    """Update order status for kitchen management"""
    try:
        order = Order.query.get_or_404(order_id)
        data = request.get_json()
        new_status = data.get('status')
        
        if new_status not in ['pending', 'preparing', 'ready', 'completed', 'cancelled']:
            return jsonify({'success': False, 'error': 'Invalid status'}), 400
        
        order.status = new_status
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'Order status updated to {new_status}'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/orders/<int:order_id>/payment', methods=['PUT'])
def update_order_payment(order_id):
    """Update order payment status"""
    try:
        order = Order.query.get_or_404(order_id)
        data = request.get_json()
        payment_status = data.get('payment_status')
        payment_intent_id = data.get('payment_intent_id')
        payment_amount = data.get('payment_amount')
        sms_number = data.get('sms_number')  # Optional SMS number for receipt
        
        if payment_status not in ['unpaid', 'paid', 'refunded']:
            return jsonify({'success': False, 'error': 'Invalid payment status'}), 400
        
        order.payment_status = payment_status
        if payment_intent_id:
            order.payment_intent_id = payment_intent_id
        if payment_amount:
            order.payment_amount = payment_amount
        if payment_status == 'paid':
            order.payment_date = datetime.utcnow()
        
        db.session.commit()
        
        # Send SMS receipt if payment was successful
        sms_result = None
        if payment_status == 'paid' and payment_amount:
            # Use provided SMS number or fall back to order customer phone
            receipt_phone = sms_number if sms_number else order.customer_phone
            sms_result = send_order_payment_receipt_sms(order, payment_amount, receipt_phone)
        
        return jsonify({
            'success': True, 
            'message': f'Order payment status updated to {payment_status}',
            'sms_result': sms_result
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/menu')
def menu():
    # Get menu items from database and organize by category
    menu_items = MenuItem.query.filter_by(is_available=True).all()
    menu_data = {}
    
    for item in menu_items:
        if item.category not in menu_data:
            menu_data[item.category] = []
        
        # Convert database item to template format
        menu_item = {
            'id': str(item.id),
            'name': item.name,
            'description': item.description,
            'price': item.price
        }
        menu_data[item.category].append(menu_item)
    
    # If no items in database, use static data
    if not menu_data:
        menu_data = {
            'appetizers': [
                {
                    'id': 'app1',
                    'name': 'Bruschetta',
                    'description': 'Grilled bread rubbed with garlic, topped with diced tomatoes, fresh basil, and olive oil',
                    'price': 8.99,
                    'dietary': ['vegetarian'],
                    'spicy_level': 0
                },
                {
                    'id': 'app2',
                    'name': 'Buffalo Wings',
                    'description': 'Crispy chicken wings tossed in spicy buffalo sauce, served with celery and blue cheese',
                    'price': 12.99,
                    'spicy_level': 2
                },
                {
                    'id': 'app3',
                    'name': 'Spinach Artichoke Dip',
                    'description': 'Creamy blend of spinach, artichokes, and melted cheeses, served with tortilla chips',
                    'price': 10.99,
                    'dietary': ['vegetarian', 'gluten-free']
                }
            ],
            'main-courses': [
                {
                    'id': 'main1',
                    'name': 'Grilled Salmon',
                    'description': 'Fresh Atlantic salmon fillet, grilled and served with seasonal vegetables',
                    'price': 24.99,
                    'dietary': ['gluten-free']
                },
                {
                    'id': 'main2',
                    'name': 'Spicy Chicken Curry',
                    'description': 'Tender chicken in a rich, aromatic curry sauce with basmati rice',
                    'price': 18.99,
                    'spicy_level': 3
                },
                {
                    'id': 'main3',
                    'name': 'Vegan Buddha Bowl',
                    'description': 'Quinoa, roasted vegetables, avocado, and tahini dressing',
                    'price': 16.99,
                    'dietary': ['vegan', 'gluten-free']
                }
            ],
            'desserts': [
                {
                    'id': 'des1',
                    'name': 'Chocolate Lava Cake',
                    'description': 'Warm chocolate cake with a molten center, served with vanilla ice cream',
                    'price': 8.99,
                    'dietary': ['vegetarian']
                },
                {
                    'id': 'des2',
                    'name': 'Vegan Apple Crumble',
                    'description': 'Warm spiced apples topped with oat crumble, served with vegan ice cream',
                    'price': 7.99,
                    'dietary': ['vegan', 'gluten-free']
                }
            ],
            'drinks': [
                {
                    'id': 'drink1',
                    'name': 'Signature Cocktail',
                    'description': 'House-made infusion with fresh fruits and premium spirits',
                    'price': 12.99
                },
                {
                    'id': 'drink2',
                    'name': 'Craft Beer Selection',
                    'description': 'Rotating selection of local craft beers',
                    'price': 6.99
                },
                {
                    'id': 'drink3',
                    'name': 'Fresh Fruit Smoothie',
                    'description': 'Blend of seasonal fruits and berries',
                    'price': 5.99,
                    'dietary': ['vegan', 'gluten-free']
                }
            ]
        }
    
    return render_template('menu.html', menu=menu_data)

# Serve static files with correct MIME types
@app.route('/static/<path:filename>')
def serve_static(filename):
    mimetype = None
    for ext, mime in app.config['MIME_TYPES'].items():
        if filename.lower().endswith(ext):
            mimetype = mime
            break
    if not mimetype and filename.lower().endswith(('.js', '.mjs')):
        mimetype = 'application/javascript'
    return send_from_directory(app.config['STATIC_FOLDER'], filename, mimetype=mimetype)

# Global conversation memory to track function calls per AI session
conversation_memory = {}

def get_conversation_memory(ai_session_id):
    """Get or create conversation memory for an AI session"""
    if ai_session_id not in conversation_memory:
        conversation_memory[ai_session_id] = {
            'function_calls': [],
            'menu_data': None,
            'last_function_time': {}
        }
    return conversation_memory[ai_session_id]

def should_block_function_call(ai_session_id, function_name):
    """Check if a function call should be blocked due to recent repetition"""
    memory = get_conversation_memory(ai_session_id)
    
    # Block if the same function was called in the last 30 seconds
    import time
    current_time = time.time()
    
    if function_name in memory['last_function_time']:
        time_since_last = current_time - memory['last_function_time'][function_name]
        
        # Special handling for create_reservation - be more intelligent about blocking
        if function_name == 'create_reservation':
            # Only block if it was called very recently (less than 5 seconds)
            # This allows for natural conversation flow where customer confirms details
            if time_since_last < 5:
                return True, f"Function {function_name} was called {time_since_last:.1f} seconds ago. Please use the previous response."
        
        # Special handling for create_order - allow if it's likely a finalization
        elif function_name == 'create_order':
            # Allow create_order if it was called more than 10 seconds ago
            # This gives time for the conversation flow to continue
            if time_since_last < 10:
                return True, f"Function {function_name} was called {time_since_last:.1f} seconds ago. Please use the previous response."
        
        # For get_reservation, allow more frequent calls as customers might be looking up different reservations
        elif function_name == 'get_reservation':
            # Only block if called within 10 seconds
            if time_since_last < 10:
                return True, f"Function {function_name} was called {time_since_last:.1f} seconds ago. Please use the previous response."
        
        # For payment functions, allow progression through payment steps
        elif function_name in ['get_card_details', 'pay_reservation']:
            # Only block if called within 5 seconds to allow payment flow progression
            if time_since_last < 5:
                return True, f"Function {function_name} was called {time_since_last:.1f} seconds ago. Please use the previous response."
        
        else:
            # Standard 30 second cooldown for other functions
            if time_since_last < 30:
                return True, f"Function {function_name} was called {time_since_last:.1f} seconds ago. Please use the previous response."
    
    # Special rules for specific functions
    if function_name == 'get_menu':
        # Block if menu was already retrieved recently (within 60 seconds)
        if memory['menu_data'] is not None and function_name in memory['last_function_time']:
            time_since_menu = current_time - memory['last_function_time'][function_name]
            if time_since_menu < 60:
                return True, "Menu data already available from previous call. Use existing menu information."
    
    return False, None

def record_function_call(ai_session_id, function_name, result=None):
    """Record a function call in conversation memory"""
    memory = get_conversation_memory(ai_session_id)
    import time
    current_time = time.time()
    
    memory['function_calls'].append({
        'function': function_name,
        'timestamp': current_time
    })
    memory['last_function_time'][function_name] = current_time
    
    # Store menu data for reuse
    if function_name == 'get_menu' and result:
        memory['menu_data'] = result
    
    print(f"📝 Recorded function call: {function_name} for session {ai_session_id}")
    print(f"   Total calls in session: {len(memory['function_calls'])}")
    print(f"   Functions called: {list(memory['last_function_time'].keys())}")

# Global agent instance
_agent_instance = None

def get_receptionist_agent():
    """Get or create the receptionist agent instance"""
    global _agent_instance
    if _agent_instance is None:
        try:
            # Import here to avoid circular import
            from swaig_agents import FullRestaurantReceptionistAgent
            _agent_instance = FullRestaurantReceptionistAgent()
            print("✅ SignalWire agent initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize SignalWire agent: {e}")
            return None
    return _agent_instance

# Add SWAIG routes to Flask app
@app.route('/receptionist', methods=['POST'])
def swaig_receptionist():
    """Handle SWAIG requests for the receptionist agent"""
    try:
        print(f"🔍 SWAIG POST request received from {request.remote_addr}")
        print(f"   Content-Type: {request.content_type}")
        print(f"   Content-Length: {request.content_length}")
        print(f"   User-Agent: {request.headers.get('User-Agent', 'None')}")
        
        agent = get_receptionist_agent()
        if not agent:
            print("❌ Agent not available")
            return jsonify({'error': 'Agent not available'}), 503
        
        # Enhanced raw data logging
        raw_data = request.get_data(as_text=True)
        print(f"   Raw request data: {raw_data[:500]}...")  # Truncate for readability
        
        # Better error handling for JSON parsing
        try:
            data = request.get_json()
            if data:
                import json as json_module
                print(f"   Parsed JSON data: {json_module.dumps(data, indent=2)[:500]}...")
            else:
                print("   Parsed JSON data: None")
        except Exception as json_error:
            print(f"❌ JSON parsing error: {json_error}")
            print(f"   Raw data type: {type(raw_data)}")
            print(f"   Raw data length: {len(raw_data) if raw_data else 0}")
            return jsonify({'error': f'Invalid JSON: {str(json_error)}'}), 400
        
        # Validate required SWAIG fields
        if not data:
            print("❌ No JSON data received")
            # Try to get form data as fallback
            form_data = request.form.to_dict()
            print(f"   Form data: {form_data}")
            if form_data:
                data = form_data
            else:
                return jsonify({'error': 'No JSON data received'}), 400
        

        
        # Check if this is a signature request
        action = data.get('action')
        if action == 'get_signature':
            print("📋 Handling signature request")
            
            # Get the functions array from the request
            requested_functions = data.get('functions', [])
            print(f"   Requested functions: {requested_functions}")
            
            # If functions array is empty, return list of available function names
            if not requested_functions:
                print("📋 Returning available function names")
                
                # Get function names dynamically from the agent's registered SWAIG functions
                available_functions = [
                    'create_reservation',
                    'get_reservation', 
                    'update_reservation',
                    'cancel_reservation',
                    'get_menu',
                    'create_order',
                    'get_order_status',
                    'update_order_status',
                    'get_card_details',
                    'pay_reservation',
                    'pay_order',
                    'transfer_to_manager',
                    'schedule_callback'
                ]
                
                print(f"   Returning {len(available_functions)} available functions: {available_functions}")
                return jsonify({"functions": available_functions})
            
            # If specific functions are requested, return their signatures
            print(f"📋 Returning signatures for specific functions: {requested_functions}")
            
            # Define all available function signatures
            all_signatures = {
                'create_reservation': {
                    'function': 'create_reservation',
                    'purpose': ('Create a new restaurant reservation with optional food pre-ordering. '
                               'ALWAYS ask customers if they want to pre-order from the menu when making reservations. '
                               'For parties larger than one, ask for each person\'s name and food preferences. '
                               'Extract any food items mentioned during the reservation request and include them in party_orders.'),
                    'argument': {
                        'type': 'object',
                        'properties': {
                            'name': {'type': 'string', 'description': 'Customer full name (extract from conversation if mentioned)'},
                            'party_size': {'type': 'integer', 'description': 'Number of people (extract from conversation)'},
                            'date': {'type': 'string', 'description': 'Reservation date in YYYY-MM-DD format (extract from conversation - today, tomorrow, specific dates)'},
                            'time': {'type': 'string', 'description': 'Reservation time in 24-hour HH:MM format (extract from conversation - convert PM/AM to 24-hour)'},
                            'phone_number': {'type': 'string', 'description': 'Customer phone number with country code (extract from conversation or use caller ID)'},
                            'special_requests': {'type': 'string', 'description': 'Optional special requests or dietary restrictions (extract from conversation)'},
                            'old_school': {'type': 'boolean', 'description': 'True for old school reservation (no pre-ordering)'},
                            'party_orders': {
                                'type': 'array',
                                'description': 'Optional pre-orders for each person in the dining party. Use when customers want to order food in advance for their reservation.',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'person_name': {'type': 'string', 'description': 'Name of person ordering (optional, can be "Person 1", "Person 2", etc.)'},
                                        'items': {
                                            'type': 'array',
                                            'description': 'Menu items ordered by this person',
                                            'items': {
                                                'type': 'object',
                                                'properties': {
                                                    'menu_item_id': {'type': 'integer', 'description': 'ID of the menu item'},
                                                    'quantity': {'type': 'integer', 'description': 'Quantity ordered'}
                                                },
                                                'required': ['menu_item_id', 'quantity']
                                            }
                                        }
                                    },
                                    'required': ['items']
                                }
                            },
                            'pre_order': {
                                'type': 'array',
                                'description': 'Alternative format for pre-orders - simpler format using menu item names instead of IDs',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'name': {'type': 'string', 'description': 'Menu item name (e.g., "Kraft Lemonade", "Buffalo Wings")'},
                                        'quantity': {'type': 'integer', 'description': 'Quantity ordered'}
                                    },
                                    'required': ['name', 'quantity']
                                }
                            }
                        },
                        'required': ['name', 'party_size', 'date', 'time', 'phone_number']
                    }
                },
                'get_reservation': {
                    'function': 'get_reservation',
                    'purpose': 'Look up existing reservations by reservation number (preferred) or name. When found by reservation number, asks for confirmation using the name from the database.',
                    'argument': {
                        'type': 'object',
                        'properties': {
                            'reservation_number': {'type': 'string', 'description': '6-digit reservation number to find (preferred search method)'},
                            'reservation_id': {'type': 'integer', 'description': 'Specific reservation ID to find'},
                            'name': {'type': 'string', 'description': 'Customer full name, first name, or last name to search by (partial matches work)'},
                            'first_name': {'type': 'string', 'description': 'Customer first name to search by'},
                            'last_name': {'type': 'string', 'description': 'Customer last name to search by'},
                            'date': {'type': 'string', 'description': 'Reservation date to search by (YYYY-MM-DD)'},
                            'time': {'type': 'string', 'description': 'Reservation time to search by (HH:MM)'},
                            'party_size': {'type': 'integer', 'description': 'Number of people to search by'},
                            'email': {'type': 'string', 'description': 'Customer email address to search by'},
                            'phone_number': {'type': 'string', 'description': 'Customer phone number (fallback search method only)'}
                        }
                    }
                },
                'update_reservation': {
                    'function': 'update_reservation',
                    'purpose': 'Update an existing reservation - can search by reservation number first, then fallback to other methods',
                    'argument': {
                        'type': 'object',
                        'properties': {
                            'reservation_number': {'type': 'string', 'description': '6-digit reservation number (preferred method)'},
                            'reservation_id': {'type': 'integer', 'description': 'Reservation ID (alternative method)'},
                            'name': {'type': 'string', 'description': 'Customer name'},
                            'party_size': {'type': 'integer', 'description': 'Number of people'},
                            'date': {'type': 'string', 'description': 'Reservation date (YYYY-MM-DD)'},
                            'time': {'type': 'string', 'description': 'Reservation time (HH:MM)'},
                            'phone_number': {'type': 'string', 'description': 'Customer phone number'},
                            'special_requests': {'type': 'string', 'description': 'Special requests or dietary restrictions'}
                        },
                        'required': []
                    }
                },
                'cancel_reservation': {
                    'function': 'cancel_reservation',
                    'purpose': 'Cancel a reservation - can search by reservation number first, then fallback to other methods',
                    'argument': {
                        'type': 'object',
                        'properties': {
                            'reservation_number': {'type': 'string', 'description': '6-digit reservation number (preferred method)'},
                            'reservation_id': {'type': 'integer', 'description': 'Reservation ID (alternative method)'},
                            'phone_number': {'type': 'string', 'description': 'Customer phone number for verification'}
                        },
                        'required': []
                    }
                },
                'get_menu': {
                    'function': 'get_menu',
                    'purpose': 'Get the restaurant menu',
                    'argument': {
                        'type': 'object',
                        'properties': {}
                    }
                },
                'create_order': {
                    'function': 'create_order',
                    'purpose': 'Create a new food order with optional payment processing. Can be standalone order or linked to a reservation.',
                    'argument': {
                        'type': 'object',
                        'properties': {
                            'reservation_id': {'type': 'integer', 'description': 'Associated reservation ID (optional for standalone orders)'},
                            'items': {
                                'type': 'array', 
                                'description': 'List of menu items to order with quantities',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'name': {'type': 'string', 'description': 'Menu item name'},
                                        'quantity': {'type': 'integer', 'description': 'Quantity to order'}
                                    },
                                    'required': ['name', 'quantity']
                                }
                            },
                            'customer_name': {'type': 'string', 'description': 'Customer name for standalone orders'},
                            'customer_phone': {'type': 'string', 'description': 'Customer phone number for standalone orders'},
                            'order_type': {'type': 'string', 'description': 'Order type: pickup or delivery', 'enum': ['pickup', 'delivery']},
                            'special_instructions': {'type': 'string', 'description': 'Special cooking instructions'},
                            'payment_preference': {'type': 'string', 'description': 'Payment preference: "now" to pay immediately with credit card, "pickup" to pay at pickup (default)', 'enum': ['now', 'pickup']}
                        },
                        'required': ['items']
                    }
                },
                'get_order_status': {
                    'function': 'get_order_status',
                    'purpose': 'Get the status of an order - can search by order number first, then fallback to other methods',
                    'argument': {
                        'type': 'object',
                        'properties': {
                            'order_number': {'type': 'string', 'description': '6-digit order number (preferred method)'},
                            'order_id': {'type': 'integer', 'description': 'Order ID (alternative method)'},
                            'reservation_id': {'type': 'integer', 'description': 'Reservation ID (alternative method)'},
                            'customer_phone': {'type': 'string', 'description': 'Customer phone number for verification'}
                        }
                    }
                },
                'update_order_status': {
                    'function': 'update_order_status',
                    'purpose': 'Update the status of an order - can search by order number first, then fallback to other methods',
                    'argument': {
                        'type': 'object',
                        'properties': {
                            'order_number': {'type': 'string', 'description': '6-digit order number (preferred method)'},
                            'order_id': {'type': 'integer', 'description': 'Order ID (alternative method)'},
                            'status': {'type': 'string', 'description': 'New order status'}
                        },
                        'required': []
                    }
                },

                'pay_reservation': {
                    'function': 'pay_reservation',
                    'purpose': 'Process payment for a reservation with step-by-step card detail collection to avoid number confusion. Guides customers through providing each card detail separately.',
                    'argument': {
                        'type': 'object',
                        'properties': {
                            'reservation_number': {'type': 'string', 'description': '6-digit reservation number to pay for'},
                            'cardholder_name': {'type': 'string', 'description': 'Name on the credit card'},
                            'phone_number': {'type': 'string', 'description': 'SMS number for receipt (will use caller ID if not provided)'},
                            'payment_step': {'type': 'string', 'description': 'Current step in payment process: start, card_number, expiry_month, expiry_year, cvv, zip_code'},
                            'card_number': {'type': 'string', 'description': '16-digit credit card number (collected step by step)'},
                            'expiry_month': {'type': 'string', 'description': 'Card expiration month (1-12)'},
                            'expiry_year': {'type': 'string', 'description': 'Card expiration year (last 2 digits)'},
                            'cvv': {'type': 'string', 'description': '3-digit security code'},
                            'zip_code': {'type': 'string', 'description': '5-digit billing ZIP code'}
                        },
                        'required': []
                    }
                },
                'pay_order': {
                    'function': 'pay_order',
                    'purpose': 'Process payment for an existing order using SignalWire Pay and Stripe. Use this when customers want to pay for their order over the phone.',
                    'argument': {
                        'type': 'object',
                        'properties': {
                            'order_number': {'type': 'string', 'description': '6-digit order number to pay for'},
                            'order_id': {'type': 'integer', 'description': 'Order ID (alternative to order_number)'},
                            'customer_name': {'type': 'string', 'description': 'Customer name for verification'},
                            'phone_number': {'type': 'string', 'description': 'Phone number for SMS receipt (will use caller ID if not provided)'}
                        },
                        'required': []
                    }
                },
                'transfer_to_manager': {
                    'function': 'transfer_to_manager',
                    'purpose': 'Transfer to manager'
                },
                'schedule_callback': {
                    'function': 'schedule_callback',
                    'purpose': 'Schedule a callback'
                }
            }
            
            # Return only the requested function signatures
            signatures = {}
            for func_name in requested_functions:
                if func_name in all_signatures:
                    signatures[func_name] = all_signatures[func_name]
                else:
                    print(f"⚠️  Requested function '{func_name}' not found")
            
            return jsonify(signatures)
        
        # Check if this is a call initialization request (contains call metadata but no function)
        if 'call' in data and 'call_state' in data.get('call', {}):
            call_info = data.get('call', {})
            call_state = call_info.get('call_state')
            
            if call_state == 'created':
                print("📞 Handling call initialization request")
                call_id = call_info.get('call_id')
                from_number = call_info.get('from')
                to_number = call_info.get('to')
                
                print(f"   Call ID: {call_id}")
                print(f"   From: {from_number}")
                print(f"   To: {to_number}")
                
                                # Return SWML response to start the conversation
                swml_response = {
                    "version": "1.0.0",
                    "sections": {
                        "main": [
                            {
                                "ai": {
                                    "languages": [
                                        {
                                            "id": "0e061b67-e1ec-4d6f-97d3-0684298552ec",
                                            "code": "en",
                                            "provider": "rime",
                                            "voice": "rime.spore",
                                            "name": "English"
                                        }
                                    ],
                                    "params": {
                                        "acknowledge_interruptions": "false",
                                        "asr_diarize": "true",
                                        "asr_speaker_affinity": "true",
                                        "audible_debug": "true",
                                        "background_file_volume": "0",
                                        "debug_webhook_level": "1",
                                        "end_of_speech_timeout": 500,
                                        "function_wait_for_talking": "false",
                                        "hold_on_process": "false",
                                        "inactivity_timeout": "600000",
                                        "interrupt_on_noise": "false",
                                        "languages_enabled": "true",
                                        "llm_diarize_aware": "true",
                                        "local_tz": "America/New_York",
                                        "max_speech_timeout": 15000,
                                        "openai_asr_engine": "deepgram:nova-3",
                                        "save_conversation": "true",
                                        "silence_timeout": 500,
                                        "static_greeting_no_barge": "false",
                                        "swaig_allow_settings": "true",
                                        "swaig_allow_swml": "true",
                                        "swaig_post_conversation": "true",
                                        "temperature": 0.6,
                                        "top_p": 0.6,
                                        "transfer_summary": "false",
                                        "transparent_barge": "false",
                                        "tts_number_format": "international",
                                        "verbose_logs": "true",
                                        "wait_for_user": "false"
                                    },
                                    "SWAIG": {
                                        "defaults": {
                                            "web_hook_url": f"{request.url_root}receptionist"
                                        },
                                        "functions": [
                                            {
                                                "function": "get_current_time",
                                                "purpose": "Get the current time"
                                            },
                                            {
                                                "function": "get_current_date",
                                                "purpose": "Get the current date"
                                            },
                                            {
                                                "function": "create_reservation",
                                                "purpose": "Create a new restaurant reservation"
                                            },
                                            {
                                                "function": "get_reservation",
                                                "purpose": "Look up existing reservations - ALWAYS ask for reservation number first (6-digit number), then fallback to name if needed"
                                            },
                                            {
                                                "function": "update_reservation",
                                                "purpose": "Update an existing reservation"
                                            },
                                            {
                                                "function": "cancel_reservation",
                                                "purpose": "Cancel a reservation"
                                            },
                                            {
                                                "function": "get_menu",
                                                "purpose": "Get restaurant menu items by category or all items"
                                            },
                                            {
                                                "function": "create_order",
                                                "purpose": "Create a new food order with optional payment processing"
                                            },
                                            {
                                                "function": "get_order_status",
                                                "purpose": "Get order status"
                                            },
                                            {
                                                "function": "update_order_status",
                                                "purpose": "Update order status"
                                            },
                                            {
                                                "function": "pay_reservation",
                                                "purpose": "Collect payment for a reservation/order using SignalWire Pay and Stripe."
                                            },
                                            {
                                                "function": "pay_order",
                                                "purpose": "Process payment for an existing order using SignalWire Pay and Stripe."
                                            },
                                            {
                                                "function": "transfer_to_manager",
                                                "purpose": "Transfer to manager"
                                            },
                                            {
                                                "function": "schedule_callback",
                                                "purpose": "Schedule a callback"
                                            }
                                        ]
                                    },
                                    "prompt": {
                                        "text": "Hi there! I'm Bobby from Bobby's Table. Great to have you call us today! How can I help you out? Whether you're looking to make a reservation, check on an existing one, hear about our menu, or place an order, I'm here to help make it easy for you.\n\nIMPORTANT CONVERSATION GUIDELINES:\n\n**RESERVATION LOOKUPS - CRITICAL:**\n- When customers want to check their reservation, ALWAYS ask for their reservation number FIRST\n- Say: 'Do you have your reservation number? It's a 6-digit number we sent you when you made the reservation.'\n- Only if they don't have it, then ask for their name as backup\n- Reservation numbers are the fastest and most accurate way to find reservations\n- Handle spoken numbers like 'seven eight nine zero one two' which becomes '789012'\n\n**ORDER CREATION - CRITICAL:**\n- When customers want to place an order, use the create_order function with specific menu items\n- ALWAYS extract exact menu item names and quantities from what customers say\n- If customer says 'I want buffalo wings', extract: items=[{\"name\": \"Buffalo Wings\", \"quantity\": 1}]\n- If customer says 'two burgers', extract: items=[{\"name\": \"Ribeye Steak\", \"quantity\": 2}] (match closest menu item)\n- ALWAYS ask customers if they want to pay now (credit card) or at pickup/delivery\n- Set payment_preference to 'now' if they want to pay immediately, 'pickup' if they'll pay later\n- Get customer name and phone number for the order\n- Ask if it's pickup or delivery (default to pickup)\n- For delivery orders, get the delivery address\n\n**RESERVATION PRE-ORDERING - CRITICAL:**\n- When making reservations, ALWAYS ask if customers want to pre-order from the menu\n- For parties larger than one person, ask for each person's name and their individual food preferences\n- When customers mention food items during reservation requests, use the pre_order parameter\n- Use pre_order format: [{\"name\": \"Menu Item Name\", \"quantity\": 1}]\n- Examples: pre_order=[{\"name\": \"Kraft Lemonade\", \"quantity\": 1}, {\"name\": \"Buffalo Wings\", \"quantity\": 2}]\n- Extract exact menu item names from what customers say\n\n**🚨 PAYMENTS - CRITICAL PAYMENT RULE 🚨:**\n**NEVER EVER call pay_reservation directly! ALWAYS call get_card_details FIRST!**\n\n**MANDATORY PAYMENT FLOW:**\n1. Customer wants to pay → IMMEDIATELY call get_card_details function\n2. get_card_details will collect reservation number and cardholder name\n3. get_card_details will ask: 'Would you like me to proceed with collecting your card details now?'\n4. ONLY after customer confirms 'yes' → THEN call pay_reservation function\n5. pay_reservation will prompt customer to enter card details via phone keypad (card number, expiration, CVV, ZIP)\n\n**EXAMPLES:**\n- Customer: 'I want to pay my bill' → YOU: Call get_card_details function\n- Customer: 'Yes, I want to pay' → YOU: Call get_card_details function\n- Customer: 'Can I pay for my reservation?' → YOU: Call get_card_details function\n\n**NEVER DO THIS:**\n- ❌ NEVER call pay_reservation when customer first asks to pay\n- ❌ NEVER skip get_card_details step\n- ❌ NEVER call pay_reservation directly\n\n**OTHER GUIDELINES:**\n- Always say numbers as words (say 'one' instead of '1', 'two' instead of '2', etc.)\n- Be conversational and helpful - guide customers through the pre-ordering process naturally"
                                    }
                                }
                            }
                        ]
                    }
                }
                
                return jsonify(swml_response)
        
        # Extract function name and parameters
        function_name = data.get('function')
        ai_session_id = data.get('ai_session_id', 'unknown')
        call_id = data.get('call_id', 'unknown')
        
        # Enhanced session tracking and logging
        print(f"📞 Session Info:")
        print(f"   AI Session ID: {ai_session_id}")
        print(f"   Call ID: {call_id}")
        print(f"   Function: {function_name}")
        
        # Log conversation context if available
        call_log = data.get('call_log', [])
        if call_log:
            print(f"📝 Conversation context ({len(call_log)} messages):")
            for i, msg in enumerate(call_log[-3:]):  # Show last 3 messages
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')[:100]  # Truncate
                print(f"   {i+1}. {role}: {content}...")
        
        # Enhanced request validation
        if not function_name:
            print("❌ No function name provided in request")
            print(f"   Available keys in request: {list(data.keys())}")
            
            # Check if this might be a different type of request
            if 'call' in data:
                print("📞 Detected call initialization request")
                # Handle call initialization - this should be handled earlier
                return jsonify({'error': 'Call initialization should be handled earlier'}), 400
            else:
                print("⚠️  Unknown request type")
                return jsonify({'error': 'No function name provided'}), 400
        
        # Handle different parameter formats more robustly
        params = {}
        if 'params' in data:
            params = data['params']
        elif 'argument' in data:
            argument = data['argument']
            if isinstance(argument, dict):
                if 'parsed' in argument:
                    parsed = argument['parsed']
                    if isinstance(parsed, list) and len(parsed) > 0:
                        params = parsed[0]
                    elif isinstance(parsed, dict):
                        params = parsed
                elif 'raw' in argument:
                    try:
                        import json as json_module
                        params = json_module.loads(argument['raw'])
                    except json_module.JSONDecodeError:
                        print(f"⚠️  Failed to parse raw argument: {argument['raw']}")
                        params = {}
                else:
                    params = argument
            else:
                params = argument if argument else {}
        
        import json as json_module
        print(f"📋 Extracted parameters: {json_module.dumps(params, indent=2)[:300]}...")
        
        # Extract meta_data for context
        meta_data = data.get('meta_data', {})
        meta_data_token = data.get('meta_data_token', '')
        
        print(f"   Meta Data: {meta_data}")
        print(f"   Meta Data Token: {meta_data_token}")
        
        # Function blocking disabled - allow all function calls to proceed
        # should_block, block_reason = should_block_function_call(ai_session_id, function_name)
        # if should_block:
        #     print(f"🚫 Blocking repetitive function call: {block_reason}")
        #     
        #     # For get_menu, return the cached menu data
        #     if function_name == 'get_menu':
        #         memory = get_conversation_memory(ai_session_id)
        #         if memory['menu_data']:
        #             print("📋 Returning cached menu data")
        #             # Convert SwaigFunctionResult to dict if needed
        #             cached_data = memory['menu_data']
        #             if hasattr(cached_data, 'to_dict'):
        #                 cached_data = cached_data.to_dict()
        #             return jsonify(cached_data)
        #     
        #     return jsonify({
        #         "response": f"I already have that information from our previous conversation. Let me help you with something else instead."
        #     })
        
        print(f"✅ Function blocking disabled - allowing {function_name} to proceed")
        
        # Get call ID for payment session tracking
        call_id = data.get('call_id', 'unknown')
        
        # PAYMENT FLOW PROTECTION: Prevent non-payment functions during payment
        if is_payment_in_progress(call_id):
            if function_name != 'pay_reservation':
                print(f"🚫 PAYMENT PROTECTION: Blocking {function_name} during payment session {call_id}")
                print(f"   Payment session active - only pay_reservation allowed")
                
                # Return a response that redirects back to payment
                session = _payment_sessions.get(call_id, {})
                reservation_number = session.get('reservation_number', 'your reservation')
                
                response_message = (
                    f"I'm currently processing your payment for reservation {reservation_number}. "
                    "Let's continue with the payment process. Please provide your credit card information."
                )
                
                return jsonify({
                    'response': response_message,
                    'action': 'continue_payment'
                })
        
        # Route to appropriate agent function using skills-based architecture
        if function_name in agent._swaig_functions:
            print(f"✅ Calling agent function: {function_name}")
            
            # Preprocess parameters for specific functions
            if function_name == 'create_reservation':
                params = preprocess_reservation_params(params)
            
            function_handler = agent._swaig_functions[function_name]
            result = function_handler(params, data)
            print(f"✅ Function result: {result}")
            
            # Record the function call in memory
            record_function_call(ai_session_id, function_name, result)
            
            # Handle SwaigFunctionResult properly
            if hasattr(result, 'to_dict'):
                # This is a SwaigFunctionResult object - convert to proper SWAIG format
                swaig_response = result.to_dict()
                print(f"   SWAIG response: {swaig_response}")
                return jsonify(swaig_response)
            elif hasattr(result, 'response'):
                # Legacy handling for direct response access
                response_content = result.response
                print(f"   Response content type: {type(response_content)}")
                print(f"   Response content preview: {str(response_content)[:200]}...")
                
                # Check if the response is already JSON (for format="json" requests)
                if isinstance(response_content, (dict, list)):
                    # Structured data - wrap in SWAIG format
                    print("   Returning structured JSON data in SWAIG format")
                    return jsonify({"response": response_content})
                elif isinstance(response_content, str):
                    try:
                        # Try to parse as JSON first
                        import json
                        parsed_json = json.loads(response_content)
                        print("   Returning parsed JSON data in SWAIG format")
                        return jsonify({"response": parsed_json})
                    except (json.JSONDecodeError, ValueError):
                        # Not JSON, return as text message in SWAIG format
                        print("   Returning text message in SWAIG format")
                        return jsonify({"response": response_content})
                else:
                    print("   Returning stringified response in SWAIG format")
                    return jsonify({"response": str(response_content)})
            else:
                print("   No response attribute, returning stringified result in SWAIG format")
                return jsonify({"response": str(result)})
        else:
            print(f"❌ Unknown function: {function_name}")
            return jsonify({'success': False, 'message': f'Unknown function: {function_name}'}), 400
            
    except Exception as e:
        print(f"❌ Exception in SWAIG endpoint: {str(e)}")
        print(f"   Exception type: {type(e)}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'Error processing request: {str(e)}'}), 500

@app.route('/receptionist', methods=['GET'])
def swaig_receptionist_info():
    """Provide SWML document for the SWAIG agent"""
    agent = get_receptionist_agent()
    if not agent:
        return jsonify({'error': 'Agent not available'}), 503
    
    # Return SWML document that includes function definitions
    swml_response = {
        "version": "1.0.0",
        "sections": {
            "main": [
                {
                    "ai": {
                        "languages": [
                            {
                                "id": "0e061b67-e1ec-4d6f-97d3-0684298552ec",
                                "code": "en",
                                "provider": "rime",
                                "voice": "rime.spore",
                                "name": "English"
                            }
                        ],
                        "params": {
                            "acknowledge_interruptions": "false",
                            "asr_diarize": "true",
                            "asr_speaker_affinity": "true",
                            "audible_debug": "true",
                            "background_file_volume": "0",
                            "debug_webhook_level": "1",
                            "enable_thinking": "true",
                            "ai_model": "gpt-4.1-mini",
                            "end_of_speech_timeout": 500,
                            "function_wait_for_talking": "false",
                            "hold_on_process": "false",
                            "inactivity_timeout": "600000",
                            "interrupt_on_noise": "false",
                            "languages_enabled": "true",
                            "llm_diarize_aware": "true",
                            "local_tz": "America/New_York",
                            "max_speech_timeout": 15000,
                            "openai_asr_engine": "deepgram:nova-3",
                            "save_conversation": "true",
                            "silence_timeout": 500,
                            "static_greeting_no_barge": "false",
                            "swaig_allow_settings": "true",
                            "swaig_allow_swml": "true",
                            "swaig_post_conversation": "true",
                            "temperature": 0.6,
                            "top_p": 0.6,
                            "transfer_summary": "false",
                            "transparent_barge": "false",
                            "tts_number_format": "international",
                            "verbose_logs": "true",
                            "wait_for_user": "false"
                        },
                        "SWAIG": {
                            "defaults": {
                                "web_hook_url": f"{request.url_root}receptionist"
                            },
                            "functions": [
                                {
                                    "function": "create_reservation",
                                    "purpose": ('Create a new restaurant reservation with optional food pre-ordering. '
                                               'ALWAYS ask customers if they want to pre-order from the menu when making reservations. '
                                               'For parties larger than one, ask for each person\'s name and food preferences. '
                                               'Extract any food items mentioned during the reservation request and include them in party_orders.'),
                                    "argument": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string", "description": "Customer full name (extract from conversation if mentioned)"},
                                            "party_size": {"type": "integer", "description": "Number of people (extract from conversation)"},
                                            "date": {"type": "string", "description": "Reservation date in YYYY-MM-DD format (extract from conversation - today, tomorrow, specific dates)"},
                                            "time": {"type": "string", "description": "Reservation time in 24-hour HH:MM format (extract from conversation - convert PM/AM to 24-hour)"},
                                            "phone_number": {"type": "string", "description": "Customer phone number with country code (extract from conversation or use caller ID)"},
                                            "special_requests": {"type": "string", "description": "Optional special requests or dietary restrictions (extract from conversation)"},
                                            "old_school": {"type": "boolean", "description": "True for old school reservation (no pre-ordering)"},
                                            "party_orders": {
                                                "type": "array",
                                                "description": "Optional pre-orders for each person in the dining party. Use when customers want to order food in advance for their reservation.",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "person_name": {"type": "string", "description": "Name of person ordering (optional, can be 'Person 1', 'Person 2', etc.)"},
                                                        "items": {
                                                            "type": "array",
                                                            "description": "Menu items ordered by this person",
                                                            "items": {
                                                                "type": "object",
                                                                "properties": {
                                                                    "menu_item_id": {"type": "integer", "description": "ID of the menu item"},
                                                                    "quantity": {"type": "integer", "description": "Quantity ordered"}
                                                                },
                                                                "required": ["menu_item_id", "quantity"]
                                                            }
                                                        }
                                                    },
                                                    "required": ["items"]
                                                }
                                            }
                                        },
                                        "required": ['name', 'party_size', 'date', 'time', 'phone_number']
                                    }
                                },
                                {
                                    "function": "get_reservation",
                                    "purpose": "Look up existing reservations - ALWAYS ask for reservation number first (6-digit number), then fallback to name if needed",
                                    "argument": {
                                        "type": "object",
                                        "properties": {
                                            "reservation_number": {"type": "string", "description": "6-digit reservation number to find (preferred search method)"},
                                            "reservation_id": {"type": "integer", "description": "Specific reservation ID to find"},
                                            "name": {"type": "string", "description": "Customer full name, first name, or last name to search by (partial matches work)"},
                                            "first_name": {"type": "string", "description": "Customer first name to search by"},
                                            "last_name": {"type": "string", "description": "Customer last name to search by"},
                                            "date": {"type": "string", "description": "Reservation date to search by (YYYY-MM-DD)"},
                                            "time": {"type": "string", "description": "Reservation time to search by (HH:MM)"},
                                            "party_size": {"type": "integer", "description": "Number of people to search by"},
                                            "email": {"type": "string", "description": "Customer email address to search by"},
                                            "phone_number": {"type": "string", "description": "Customer phone number (fallback search method only)"}
                                        }
                                    }
                                },
                                {
                                    "function": "update_reservation",
                                    "purpose": "Update an existing reservation",
                                    "argument": {
                                        "type": "object",
                                        "properties": {
                                            "reservation_id": {"type": "integer", "description": "Reservation ID"},
                                            "name": {"type": "string", "description": "Customer name"},
                                            "party_size": {"type": "integer", "description": "Number of people"},
                                            "date": {"type": "string", "description": "Reservation date (YYYY-MM-DD)"},
                                            "time": {"type": "string", "description": "Reservation time (HH:MM)"},
                                            "phone_number": {"type": "string", "description": "Customer phone number"},
                                            "special_requests": {"type": "string", "description": "Special requests or dietary restrictions"}
                                        },
                                        "required": ["reservation_id"]
                                    }
                                },
                                {
                                    "function": "cancel_reservation",
                                    "purpose": "Cancel a reservation",
                                    "argument": {
                                        "type": "object",
                                        "properties": {
                                            "reservation_id": {"type": "integer", "description": "Reservation ID"},
                                            "phone_number": {"type": "string", "description": "Customer phone number for verification"}
                                        },
                                        "required": ["reservation_id"]
                                    }
                                },
                                {
                                    "function": "get_menu",
                                    "purpose": "Get restaurant menu items and categories",
                                    "argument": {
                                        "type": "object",
                                        "properties": {
                                            "category": {"type": "string", "description": "Optional menu category: 'breakfast', 'appetizers', 'main-courses', 'desserts', or 'drinks'. Leave empty for full menu"}
                                        }
                                    }
                                },
                                {
                                    "function": "create_order",
                                    "purpose": "Create a new food order. Extract menu items and quantities from natural language. If user says 'I want the salmon' or 'One cheesecake', extract that information. This will generate a unique order ID. Always ask customers if they want to pay now or at pickup/delivery.",
                                    "argument": {
                                        "type": "object",
                                        "properties": {
                                            "items": {
                                                "type": "array",
                                                "description": "List of menu items to order. Extract from natural language like 'I want the salmon', 'two burgers', 'one cheesecake', etc.",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "name": {"type": "string", "description": "Menu item name (extract from conversation)"},
                                                        "quantity": {"type": "integer", "description": "Quantity to order (extract from conversation, default to 1 if not specified)"}
                                                    },
                                                    "required": ["name", "quantity"]
                                                }
                                            },
                                            "customer_name": {"type": "string", "description": "Customer name for the order"},
                                            "customer_phone": {"type": "string", "description": "Customer phone number"},
                                            "order_type": {"type": "string", "description": "Order type: pickup or delivery (default to pickup)"},
                                            "payment_preference": {"type": "string", "description": "Payment preference: 'now' to pay immediately with credit card, or 'pickup' to pay at pickup/delivery (default)", "enum": ["now", "pickup"]},
                                            "special_instructions": {"type": "string", "description": "Special cooking instructions or dietary restrictions"},
                                            "customer_address": {"type": "string", "description": "Customer address (required for delivery orders)"}
                                        },
                                        "required": ["items"]
                                    }
                                },
                                {
                                    "function": "get_order_status",
                                    "purpose": "Get the status of an order",
                                    "argument": {
                                        "type": "object",
                                        "properties": {
                                            "order_id": {"type": "integer", "description": "Order ID"},
                                            "reservation_id": {"type": "integer", "description": "Reservation ID"}
                                        }
                                    }
                                },
                                {
                                    "function": "update_order_status",
                                    "purpose": "Update the status of an order",
                                    "argument": {
                                        "type": "object",
                                        "properties": {
                                            "order_id": {"type": "integer", "description": "Order ID"},
                                            "status": {"type": "string", "description": "New order status"}
                                        },
                                        "required": ["order_id", "status"]
                                    }
                                },
                                {
                                    "function": "pay_reservation",
                                    "purpose": "Collect payment for a reservation/order using SignalWire Pay and Stripe. This function guides customers through the payment process step by step, collecting reservation number and cardholder name as needed.",
                                    "argument": {
                                        "type": "object",
                                        "properties": {
                                            "reservation_number": {"type": "string", "description": "6-digit reservation number to pay for (will be extracted from conversation if not provided)"},
                                            "cardholder_name": {"type": "string", "description": "Name on the credit card (will be requested if not provided)"},
                                            "phone_number": {"type": "string", "description": "SMS number for receipt (will use caller ID if not provided)"}
                                        },
                                        "required": []
                                    }
                                },
                                {
                                    "function": "transfer_to_manager",
                                    "purpose": "Transfer to manager"
                                },
                                {
                                    "function": "schedule_callback",
                                    "purpose": "Schedule a callback"
                                },
                                {
                                    "function": "get_card_details",
                                    "purpose": "Collect payment information and confirm payment details before processing payment. This function should be called first when customers want to pay their bill.",
                                    "argument": {
                                        "type": "object",
                                        "properties": {
                                            "reservation_number": {"type": "string", "description": "6-digit reservation number to pay for (will be extracted from conversation if not provided)"},
                                            "cardholder_name": {"type": "string", "description": "Name on the credit card (will be requested if not provided)"},
                                            "card_number": {"type": "string", "description": "Credit card number (will be collected via secure DTMF)"},
                                            "expiry_date": {"type": "string", "description": "Card expiration date (will be collected via secure DTMF)"},
                                            "cvv": {"type": "string", "description": "Card CVV/security code (will be collected via secure DTMF)"},
                                            "zip_code": {"type": "string", "description": "Billing ZIP code (will be collected via secure DTMF)"}
                                        },
                                        "required": []
                                    }
                                },
                                {
                                    "function": "pay_reservation",
                                    "purpose": "Process payment for a reservation using SignalWire Pay and Stripe. This function should only be called after get_card_details has collected all necessary information and user has confirmed payment.",
                                    "argument": {
                                        "type": "object",
                                        "properties": {
                                            "reservation_number": {"type": "string", "description": "6-digit reservation number to pay for (required)"},
                                            "cardholder_name": {"type": "string", "description": "Name on the credit card (required)"},
                                            "phone_number": {"type": "string", "description": "SMS number for receipt (will use caller ID if not provided)"}
                                        },
                                        "required": ["reservation_number", "cardholder_name"]
                                    }
                                },
                                {
                                    "function": "pay_order",
                                    "purpose": "Process payment for an existing order using SignalWire Pay and Stripe. Use this when customers want to pay for their order over the phone.",
                                    "argument": {
                                        "type": "object",
                                        "properties": {
                                            "order_number": {"type": "string", "description": "6-digit order number to pay for"},
                                            "order_id": {"type": "integer", "description": "Order ID (alternative to order_number)"},
                                            "customer_name": {"type": "string", "description": "Customer name for verification"},
                                            "phone_number": {"type": "string", "description": "Phone number for SMS receipt (will use caller ID if not provided)"}
                                        },
                                        "required": []
                                    }
                                }
                            ]
                        },
                        "prompt": {
                            "text": "Hi there! I'm Bobby from Bobby's Table. Great to have you call us today! How can I help you out? Whether you're looking to make a reservation, check on an existing one, hear about our menu, or place an order, I'm here to help make it easy for you.\n\nIMPORTANT CONVERSATION GUIDELINES:\n\n**RESERVATION LOOKUPS - CRITICAL:**\n- When customers want to check their reservation, ALWAYS ask for their reservation number FIRST\n- Say: 'Do you have your reservation number? It's a 6-digit number we sent you when you made the reservation.'\n- Only if they don't have it, then ask for their name as backup\n- Reservation numbers are the fastest and most accurate way to find reservations\n- Handle spoken numbers like 'seven eight nine zero one two' which becomes '789012'\n\n**🚨 PAYMENTS - CRITICAL PAYMENT RULE 🚨:**\n**NEVER EVER call pay_reservation directly! ALWAYS call get_card_details FIRST!**\n\n**MANDATORY PAYMENT FLOW:**\n1. Customer wants to pay → IMMEDIATELY call get_card_details function\n2. get_card_details will collect reservation number and cardholder name\n3. get_card_details will ask: 'Would you like me to proceed with collecting your card details now?'\n4. ONLY after customer confirms 'yes' → THEN call pay_reservation function\n5. pay_reservation will prompt customer to enter card details via phone keypad (card number, expiration, CVV, ZIP)\n\n**EXAMPLES:**\n- Customer: 'I want to pay my bill' → YOU: Call get_card_details function\n- Customer: 'Yes, I want to pay' → YOU: Call get_card_details function\n- Customer: 'Can I pay for my reservation?' → YOU: Call get_card_details function\n\n**NEVER DO THIS:**\n- ❌ NEVER call pay_reservation when customer first asks to pay\n- ❌ NEVER skip get_card_details step\n- ❌ NEVER call pay_reservation directly\n\n**OTHER GUIDELINES:**\n- When making reservations, ALWAYS ask if customers want to pre-order from the menu\n- For parties larger than one person, ask for each person's name and their individual food preferences\n- Always say numbers as words (say 'one' instead of '1', 'two' instead of '2', etc.)\n- Extract food items mentioned during reservation requests and include them in party_orders\n- Be conversational and helpful - guide customers through the pre-ordering process naturally"
                        }
                    }
                }
            ]
        }
    }
    return jsonify(swml_response)

# Stripe API endpoints
@app.route('/api/stripe/config')
def get_stripe_config():
    """Get Stripe publishable key for frontend"""
    return jsonify({
        'publishable_key': STRIPE_PUBLISHABLE_KEY
    })

@app.route('/api/stripe/create-payment-intent', methods=['POST'])
def create_payment_intent():
    """Create a Stripe payment intent for reservations or orders"""
    try:
        data = request.get_json()
        reservation_id = data.get('reservation_id')
        order_id = data.get('order_id')
        amount = data.get('amount')  # Amount in cents
        currency = data.get('currency', 'usd')
        
        if not amount:
            return jsonify({'error': 'Missing amount'}), 400
        
        if not reservation_id and not order_id:
            return jsonify({'error': 'Missing reservation_id or order_id'}), 400
        
        metadata = {}
        
        if reservation_id:
            # Get reservation details
            reservation = Reservation.query.get(reservation_id)
            if not reservation:
                return jsonify({'error': 'Reservation not found'}), 404
            
            metadata = {
                'type': 'reservation',
                'reservation_id': reservation_id,
                'reservation_number': reservation.reservation_number,
                'customer_name': reservation.name,
                'customer_phone': reservation.phone_number
            }
        elif order_id:
            # Get order details
            order = Order.query.get(order_id)
            if not order:
                return jsonify({'error': 'Order not found'}), 404
            
            metadata = {
                'type': 'order',
                'order_id': order_id,
                'order_number': order.order_number,
                'customer_name': order.person_name,
                'customer_phone': order.customer_phone
            }
        
        # Create payment intent
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            metadata=metadata
        )
        
        return jsonify({
            'client_secret': intent.client_secret
        })
        
    except stripe.error.StripeError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

def send_payment_receipt_sms(reservation, payment_amount, phone_number=None, confirmation_number=None):
    """Send SMS receipt for payment"""
    try:
        from signalwire_agents.core.function_result import SwaigFunctionResult
        
        # Convert time to 12-hour format for SMS
        try:
            time_obj = datetime.strptime(str(reservation.time), '%H:%M')
            time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
        except (ValueError, TypeError):
            time_12hr = str(reservation.time)
        
        # Build SMS body
        sms_body = f"💳 Bobby's Table Payment Receipt\n\n"
        sms_body += f"✅ Payment Successful!\n\n"
        
        # Add confirmation number if provided
        if confirmation_number:
            sms_body += f"🎫 CONFIRMATION: {confirmation_number}\n\n"
        
        sms_body += f"Reservation Details:\n"
        sms_body += f"• Name: {reservation.name}\n"
        sms_body += f"• Date: {reservation.date}\n"
        sms_body += f"• Time: {time_12hr}\n"
        party_text = "person" if reservation.party_size == 1 else "people"
        sms_body += f"• Party Size: {reservation.party_size} {party_text}\n"
        sms_body += f"• Reservation #: {reservation.reservation_number}\n\n"
        sms_body += f"Payment Information:\n"
        sms_body += f"• Amount Paid: ${payment_amount:.2f}\n"
        sms_body += f"• Payment Date: {reservation.payment_date.strftime('%m/%d/%Y %I:%M %p')}\n"
        sms_body += f"• Payment ID: {reservation.payment_intent_id[-8:]}\n\n"
        sms_body += f"Thank you for your payment!\n"
        sms_body += f"We look forward to serving you.\n\n"
        sms_body += f"Bobby's Table Restaurant\n"
        sms_body += f"Reply STOP to stop."
        
        # Get SignalWire phone number from environment
        signalwire_from_number = os.getenv('SIGNALWIRE_FROM_NUMBER', '+15551234567')
        
        # Use provided phone_number or reservation.phone_number
        to_number = phone_number if phone_number else reservation.phone_number
        
        # Send SMS using SignalWire Agents SDK
        sms_function_result = SwaigFunctionResult().send_sms(
            to_number=to_number,
            from_number=signalwire_from_number,
            body=sms_body
        )
        
        return {'success': True, 'sms_sent': True, 'sms_result': 'Payment receipt SMS sent successfully'}
        
    except Exception as e:
        print(f"❌ SMS Error: Failed to send payment receipt SMS to {phone_number or reservation.phone_number}: {e}")
        return {'success': False, 'sms_sent': False, 'error': str(e)}

def send_order_payment_receipt_sms(order, payment_amount, phone_number=None, confirmation_number=None):
    """Send SMS receipt for order payment"""
    try:
        from signalwire_agents.core.function_result import SwaigFunctionResult
        
        # Convert time to 12-hour format for SMS
        try:
            time_obj = datetime.strptime(str(order.target_time), '%H:%M')
            time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
        except (ValueError, TypeError):
            time_12hr = str(order.target_time)
        
        # Build SMS body
        sms_body = f"💳 Bobby's Table Payment Receipt\n\n"
        sms_body += f"✅ Payment Successful!\n\n"
        
        # Add confirmation number if provided
        if confirmation_number:
            sms_body += f"🎫 CONFIRMATION: {confirmation_number}\n\n"
        
        sms_body += f"Order Details:\n"
        sms_body += f"• Customer: {order.person_name}\n"
        sms_body += f"• Order #: {order.order_number}\n"
        sms_body += f"• Type: {order.order_type.title()}\n"
        sms_body += f"• Ready Time: {time_12hr}\n"
        sms_body += f"• Date: {order.target_date}\n"
        if order.order_type == 'delivery' and order.customer_address:
            sms_body += f"• Delivery Address: {order.customer_address}\n"
        sms_body += f"\nPayment Information:\n"
        sms_body += f"• Amount Paid: ${payment_amount:.2f}\n"
        sms_body += f"• Payment Date: {order.payment_date.strftime('%m/%d/%Y %I:%M %p')}\n"
        sms_body += f"• Payment ID: {order.payment_intent_id[-8:]}\n\n"
        
        if order.order_type == 'pickup':
            sms_body += f"📍 Please come to Bobby's Table to collect your order at {time_12hr}.\n"
        else:
            sms_body += f"🚚 Your order will be delivered to {order.customer_address} around {time_12hr}.\n"
        
        sms_body += f"\nThank you for your payment!\n"
        sms_body += f"We look forward to serving you.\n\n"
        sms_body += f"Bobby's Table Restaurant\n"
        sms_body += f"Reply STOP to stop."
        
        # Get SignalWire phone number from environment
        signalwire_from_number = os.getenv('SIGNALWIRE_FROM_NUMBER', '+15551234567')
        
        # Use provided phone_number or order.customer_phone
        to_number = phone_number if phone_number else order.customer_phone
        
        # Send SMS using SignalWire
        from signalwire_agents.core.function_result import SwaigFunctionResult
        result = SwaigFunctionResult()
        result = result.send_sms(
            to_number=to_number,
            from_number=signalwire_from_number,
            body=sms_body
        )
        
        return {'success': True, 'sms_sent': True, 'sms_result': 'Order payment receipt SMS sent successfully'}
        
    except Exception as e:
        print(f"❌ SMS Error: Failed to send order payment receipt SMS to {phone_number or order.customer_phone}: {e}")
        return {'success': False, 'sms_sent': False, 'error': str(e)}

@app.route('/api/reservations/payment', methods=['POST'])
def update_reservation_payment():
    """Update reservation payment status"""
    try:
        data = request.get_json()
        reservation_id = data.get('reservation_id')
        payment_intent_id = data.get('payment_intent_id')
        amount = data.get('amount')
        status = data.get('status')
        sms_number = data.get('sms_number')  # Optional SMS number for receipt
        
        if not all([reservation_id, payment_intent_id, amount, status]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Get reservation
        reservation = Reservation.query.get(reservation_id)
        if not reservation:
            return jsonify({'error': 'Reservation not found'}), 404
        
        # Update payment information
        reservation.payment_status = status
        reservation.payment_intent_id = payment_intent_id
        reservation.payment_amount = amount
        reservation.payment_date = datetime.utcnow()
        
        db.session.commit()
        
        # Send SMS receipt if payment was successful
        sms_result = None
        if status == 'paid':
            # Use provided SMS number or fall back to reservation phone number
            receipt_phone = sms_number if sms_number else reservation.phone_number
            sms_result = send_payment_receipt_sms(reservation, amount, receipt_phone)
        
        return jsonify({
            'success': True,
            'message': 'Payment status updated successfully',
            'sms_result': sms_result
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update payment status'}), 500

def preprocess_reservation_params(params):
    """Preprocess reservation parameters to handle various date/time formats"""
    from datetime import datetime
    
    if not params:
        return params
    
    # Make a copy to avoid modifying the original
    processed_params = params.copy()
    
    print(f"🔍 Preprocessing reservation params: {params}")
    
    # Handle date and time format conversion
    if 'time' in processed_params:
        time_str = processed_params['time']
        print(f"   Original time: '{time_str}'")
        
        # Handle ISO datetime format (e.g., "2025-06-09T14:00:00")
        if 'T' in time_str and ':' in time_str:
            try:
                # Parse ISO datetime format
                iso_datetime = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                
                # Extract date and time components
                processed_params['date'] = iso_datetime.strftime("%Y-%m-%d")
                processed_params['time'] = iso_datetime.strftime("%H:%M")
                
                print(f"   ✅ Converted ISO datetime to date: '{processed_params['date']}', time: '{processed_params['time']}'")
                
            except ValueError as e:
                print(f"   ⚠️ Could not parse ISO datetime '{time_str}': {e}")
                # Keep original values and let the skill handle it
    
    # Ensure date is present if not already set
    if 'date' not in processed_params and 'time' in processed_params:
        time_str = processed_params['time']
        if 'T' in time_str:
            # Extract date from ISO datetime in time field
            try:
                iso_datetime = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                processed_params['date'] = iso_datetime.strftime("%Y-%m-%d")
                print(f"   ✅ Extracted date from time field: '{processed_params['date']}'")
            except ValueError:
                pass
    
    print(f"   Final processed params: {processed_params}")
    return processed_params

@app.route('/api/signalwire/payment-callback', methods=['POST'])
def signalwire_payment_callback():
    """
    Handle SignalWire Pay verb webhook. Create Stripe PaymentIntent and update reservation/order status.
    """
    try:
        data = request.get_json()
        print(f"🔔 Payment callback received: {data}")
        
        # SignalWire Pay verb sends data in different formats depending on the result
        # Success format: {"payment": {"status": "success", "amount": 42.50, ...}}
        # Error format: {"payment": {"status": "error", "error": "..."}}
        
        payment = data.get('payment', {})
        status = payment.get('status')
        description = payment.get('description', '')
        amount = payment.get('amount')
        payment_intent_id = payment.get('payment_processor_id') or payment.get('transaction_id')
        
        # Get parameters that were passed to the Pay verb
        parameters = payment.get('parameters', {})
        reservation_number = parameters.get('reservation_number')
        order_id = parameters.get('order_id')
        order_number = parameters.get('order_number')
        cardholder_name = parameters.get('cardholder_name')
        phone_number = parameters.get('phone_number')
        email = parameters.get('email')
        payment_type = parameters.get('payment_type', 'reservation')  # 'reservation' or 'order'
        
        # Fallback: Extract reservation/order number from description if not in parameters
        if not reservation_number and not order_number:
            import re
            reservation_match = re.search(r'Reservation #(\d+)', description)
            order_match = re.search(r'Order #(\d+)', description)
            
            if reservation_match:
                reservation_number = reservation_match.group(1)
                payment_type = 'reservation'
            elif order_match:
                order_number = order_match.group(1)
                payment_type = 'order'

        print(f"💳 Payment status: {status}, type: {payment_type}, reservation: {reservation_number}, order: {order_number}, amount: {amount}")

        if status == 'success' and (reservation_number or order_number):
            from models import Reservation, Order
            from datetime import datetime
            import uuid
            
            # Generate confirmation number like web version
            confirmation_number = f"CONF-{uuid.uuid4().hex[:8].upper()}"
            
            if payment_type == 'reservation' and reservation_number:
                # Handle reservation payment
                reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
                if reservation:
                    # Create Stripe PaymentIntent to match web version behavior
                    try:
                        stripe_intent = stripe.PaymentIntent.create(
                            amount=int(amount * 100),  # Convert to cents
                            currency='usd',
                            metadata={
                                'type': 'reservation',
                                'reservation_id': reservation.id,
                                'reservation_number': reservation_number,
                                'customer_name': reservation.name,
                                'customer_phone': reservation.phone_number,
                                'confirmation_number': confirmation_number,
                                'payment_source': 'voice_call'
                            },
                            description=f"Bobby's Table Reservation #{reservation_number}",
                            confirm=True,
                            payment_method_types=['card'],
                            return_url='https://bobbystable.com/payment-complete'
                        )
                        
                        print(f"✅ Created Stripe PaymentIntent: {stripe_intent.id}")
                        stripe_payment_id = stripe_intent.id
                        
                    except stripe.error.StripeError as e:
                        print(f"⚠️ Stripe API error: {e}")
                        # Fallback to SignalWire payment ID
                        stripe_payment_id = payment_intent_id or f"sw_pay_{reservation_number}"
                    
                    # Update reservation payment status
                    reservation.payment_status = 'paid'
                    reservation.payment_intent_id = stripe_payment_id
                    reservation.payment_amount = amount
                    reservation.payment_date = datetime.utcnow()
                    reservation.confirmation_number = confirmation_number
                    db.session.commit()
                    
                    print(f"✅ Updated reservation {reservation_number} payment status to paid")
                    print(f"✅ Generated confirmation number: {confirmation_number}")
                    
                    # Send SMS receipt using the phone number from parameters or reservation
                    receipt_phone = phone_number or reservation.phone_number
                    try:
                        sms_result = send_payment_receipt_sms(reservation, amount, receipt_phone, confirmation_number)
                        print(f"📱 SMS receipt sent to {receipt_phone}: {sms_result}")
                        
                        return jsonify({
                            'success': True, 
                            'message': f'Payment successful! Your confirmation number is {confirmation_number}. Bill marked as paid and SMS sent.',
                            'reservation_number': reservation_number,
                            'confirmation_number': confirmation_number,
                            'amount': amount,
                            'stripe_payment_id': stripe_payment_id,
                            'sms_result': sms_result,
                            'voice_response': f"Excellent! Your payment of ${amount:.2f} has been processed successfully. Your confirmation number is {confirmation_number}. I've also sent you an SMS receipt with all the details. Thank you for choosing Bobby's Table!"
                        })
                        
                    except Exception as e:
                        print(f"❌ SMS Error: {e}")
                        return jsonify({
                            'success': True, 
                            'warning': f'Payment succeeded with confirmation {confirmation_number}, but failed to send SMS: {str(e)}',
                            'reservation_number': reservation_number,
                            'confirmation_number': confirmation_number,
                            'amount': amount,
                            'stripe_payment_id': stripe_payment_id,
                            'voice_response': f"Excellent! Your payment of ${amount:.2f} has been processed successfully. Your confirmation number is {confirmation_number}. Please write this down for your records. Thank you for choosing Bobby's Table!"
                        })
                else:
                    print(f"❌ Reservation {reservation_number} not found")
                    return jsonify({'success': False, 'error': 'Reservation not found.'}), 404
                    
            elif payment_type == 'order' and (order_number or order_id):
                # Handle order payment
                order = None
                if order_number:
                    order = Order.query.filter_by(order_number=order_number).first()
                elif order_id:
                    order = Order.query.get(order_id)
                
                if order:
                    # Create Stripe PaymentIntent to match web version behavior
                    try:
                        stripe_intent = stripe.PaymentIntent.create(
                            amount=int(amount * 100),  # Convert to cents
                            currency='usd',
                            metadata={
                                'type': 'order',
                                'order_id': order.id,
                                'order_number': order.order_number,
                                'customer_name': order.person_name,
                                'customer_phone': order.customer_phone,
                                'confirmation_number': confirmation_number,
                                'payment_source': 'voice_call'
                            },
                            description=f"Bobby's Table Order #{order.order_number}",
                            confirm=True,
                            payment_method_types=['card'],
                            return_url='https://bobbystable.com/payment-complete'
                        )
                        
                        print(f"✅ Created Stripe PaymentIntent: {stripe_intent.id}")
                        stripe_payment_id = stripe_intent.id
                        
                    except stripe.error.StripeError as e:
                        print(f"⚠️ Stripe API error: {e}")
                        # Fallback to SignalWire payment ID
                        stripe_payment_id = payment_intent_id or f"sw_pay_{order_number or order_id}"
                    
                    # Update order payment status
                    order.payment_status = 'paid'
                    order.payment_intent_id = stripe_payment_id
                    order.payment_amount = amount
                    order.payment_date = datetime.utcnow()
                    order.confirmation_number = confirmation_number
                    db.session.commit()
                    
                    print(f"✅ Updated order {order.order_number} payment status to paid")
                    print(f"✅ Generated confirmation number: {confirmation_number}")
                    
                    # Send SMS receipt using the phone number from parameters or order
                    receipt_phone = phone_number or order.customer_phone
                    try:
                        sms_result = send_order_payment_receipt_sms(order, amount, receipt_phone, confirmation_number)
                        print(f"📱 SMS receipt sent to {receipt_phone}: {sms_result}")
                        
                        return jsonify({
                            'success': True, 
                            'message': f'Payment successful! Your confirmation number is {confirmation_number}. Order marked as paid and SMS sent.',
                            'order_number': order.order_number,
                            'confirmation_number': confirmation_number,
                            'amount': amount,
                            'stripe_payment_id': stripe_payment_id,
                            'sms_result': sms_result,
                            'voice_response': f"Excellent! Your payment of ${amount:.2f} has been processed successfully. Your confirmation number is {confirmation_number}. I've also sent you an SMS receipt with all the details. Thank you for choosing Bobby's Table!"
                        })
                        
                    except Exception as e:
                        print(f"❌ SMS Error: {e}")
                        return jsonify({
                            'success': True, 
                            'warning': f'Payment succeeded with confirmation {confirmation_number}, but failed to send SMS: {str(e)}',
                            'order_number': order.order_number,
                            'confirmation_number': confirmation_number,
                            'amount': amount,
                            'stripe_payment_id': stripe_payment_id,
                            'voice_response': f"Excellent! Your payment of ${amount:.2f} has been processed successfully. Your confirmation number is {confirmation_number}. Please write this down for your records. Thank you for choosing Bobby's Table!"
                        })
                else:
                    print(f"❌ Order {order_number or order_id} not found")
                    return jsonify({'success': False, 'error': 'Order not found.'}), 404
            else:
                print(f"❌ Invalid payment type or missing identifiers")
                return jsonify({'success': False, 'error': 'Invalid payment type or missing order/reservation identifiers.'}), 400
                
        elif status == 'error':
            error_msg = payment.get('error', 'Payment processing failed')
            print(f"❌ Payment failed: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 400
            
        else:
            print(f"❌ Invalid payment data: status={status}, reservation={reservation_number}")
            return jsonify({'success': False, 'error': 'Payment failed or reservation number not found.'}), 400
            
    except Exception as e:
        print(f"❌ Payment callback error: {e}")
        return jsonify({'success': False, 'error': 'Internal server error processing payment callback'}), 500

# Global payment state tracking using database for persistence
def is_payment_in_progress(call_id):
    """Check if a payment is currently in progress for this call"""
    try:
        # Check if there's an active payment session in the database
        from models import db
        
        # Use a simple table or cache mechanism
        # For now, use a simple in-memory approach but with better logging
        session_key = f"payment_session_{call_id}"
        
        # Check if session exists in app config (more persistent than global var)
        if not hasattr(app, 'payment_sessions'):
            app.payment_sessions = {}
        
        is_active = call_id in app.payment_sessions
        print(f"🔍 Checking payment session for {call_id}: {'ACTIVE' if is_active else 'INACTIVE'}")
        return is_active
        
    except Exception as e:
        print(f"❌ Error checking payment session: {e}")
        return False

def start_payment_session(call_id, reservation_number):
    """Start tracking a payment session"""
    try:
        if not hasattr(app, 'payment_sessions'):
            app.payment_sessions = {}
        
        app.payment_sessions[call_id] = {
            'reservation_number': reservation_number,
            'started_at': datetime.now(),
            'step': 'started'
        }
        print(f"🔒 Started payment session for call {call_id}, reservation {reservation_number}")
        print(f"🔍 Total active payment sessions: {len(app.payment_sessions)}")
        
    except Exception as e:
        print(f"❌ Error starting payment session: {e}")

def update_payment_step(call_id, step):
    """Update the current payment step"""
    try:
        if not hasattr(app, 'payment_sessions'):
            app.payment_sessions = {}
        
        if call_id in app.payment_sessions:
            app.payment_sessions[call_id]['step'] = step
            print(f"🔄 Payment session {call_id} updated to step: {step}")
        else:
            print(f"⚠️ Payment session {call_id} not found for step update")
            
    except Exception as e:
        print(f"❌ Error updating payment session: {e}")

def end_payment_session(call_id):
    """End a payment session"""
    try:
        if not hasattr(app, 'payment_sessions'):
            app.payment_sessions = {}
        
        if call_id in app.payment_sessions:
            session = app.payment_sessions.pop(call_id)
            print(f"✅ Ended payment session for call {call_id}")
            print(f"🔍 Remaining active payment sessions: {len(app.payment_sessions)}")
            return session
        else:
            print(f"⚠️ Payment session {call_id} not found for ending")
            return None
            
    except Exception as e:
        print(f"❌ Error ending payment session: {e}")
        return None

def cleanup_old_payment_sessions():
    """Clean up payment sessions older than 30 minutes"""
    try:
        if not hasattr(app, 'payment_sessions'):
            app.payment_sessions = {}
        
        cutoff = datetime.now() - timedelta(minutes=30)
        expired_sessions = [
            call_id for call_id, session in app.payment_sessions.items()
            if session.get('started_at', datetime.now()) < cutoff
        ]
        for call_id in expired_sessions:
            app.payment_sessions.pop(call_id, None)
            print(f"🧹 Cleaned up expired payment session: {call_id}")
            
    except Exception as e:
        print(f"❌ Error cleaning up payment sessions: {e}")

@app.route('/debug/payment-sessions', methods=['GET'])
def debug_payment_sessions():
    """Debug endpoint to check payment sessions"""
    if not hasattr(app, 'payment_sessions'):
        app.payment_sessions = {}
    
    return jsonify({
        'payment_sessions': app.payment_sessions,
        'session_count': len(app.payment_sessions)
    })

if __name__ == '__main__':
    import sys
    host = '0.0.0.0'
    port = 8080
    debug = False
    
    # Parse command line arguments
    if '--host' in sys.argv:
        host_index = sys.argv.index('--host') + 1
        if host_index < len(sys.argv):
            host = sys.argv[host_index]
    
    if '--port' in sys.argv:
        port_index = sys.argv.index('--port') + 1
        if port_index < len(sys.argv):
            port = int(sys.argv[port_index])
    
    if '--debug' in sys.argv:
        debug = True
    
    print("🍽️  Starting Bobby's Table Restaurant System")
    print("==================================================")
    print(f"🌐 Web Interface: http://{host}:{port}")
    print(f"📞 Voice Interface: http://{host}:{port}/receptionist")
    print(f"🍳 Kitchen Dashboard: http://{host}:{port}/kitchen")
    print("Press Ctrl+C to stop the service")
    print("--------------------------------------------------")
    app.run(host=host, port=port, debug=debug)
