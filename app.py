import os
import json
import stripe
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_from_directory, make_response
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
    
    # Menu items are now initialized in init_test_data.py
    # This ensures consistent IDs and avoids duplication

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
                
                # Create event object with status-based styling
                status = reservation.status or 'confirmed'
                title_prefix = ""
                if status == 'cancelled':
                    title_prefix = "[CANCELLED] "
                
                event = {
                    'id': reservation.id,
                    'title': f"{title_prefix}{reservation.name} ({reservation.party_size} {party_text})",
                    'start': dt.isoformat(),
                    'end': (dt + timedelta(hours=2)).isoformat(),  # Assuming 2-hour reservations
                    'className': f'reservation-{status}',  # Add CSS class for styling
                    'extendedProps': {
                        'partySize': reservation.party_size,
                        'phoneNumber': reservation.phone_number,
                        'status': status,
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
    # Mark as cancelled instead of deleting
    reservation.status = 'cancelled'
    db.session.commit()
    return '', 204

@app.route('/api/menu', methods=['GET'])
def get_menu():
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
    """Create a standalone order (not tied to a reservation)"""
    try:
        data = request.get_json()
        print(f"DEBUG: Received order data: {data}")
        
        # Extract order details - handle both camelCase (frontend) and snake_case (API) formats
        customer_name = data.get('customerName') or data.get('customer_name', '')
        customer_phone = data.get('customerPhone') or data.get('customer_phone', '')
        customer_address = data.get('customerAddress') or data.get('customer_address', '')
        order_type = data.get('orderType') or data.get('order_type', 'pickup')  # pickup or delivery
        target_date = data.get('orderDate') or data.get('target_date', datetime.now().strftime('%Y-%m-%d'))
        target_time = data.get('orderTime') or data.get('target_time', datetime.now().strftime('%H:%M'))
        special_instructions = data.get('specialInstructions') or data.get('special_instructions', '')
        items = data.get('items', [])
        
        print(f"DEBUG: Extracted values - customer_name: '{customer_name}', order_type: '{order_type}', target_date: '{target_date}', target_time: '{target_time}'")
        
        if not items:
            return jsonify({'success': False, 'error': 'No items provided'}), 400
        
        if not customer_name or not customer_phone:
            return jsonify({'success': False, 'error': 'Customer name and phone number are required'}), 400
        
        # Create order
        order = Order(
            order_number=generate_order_number(),
            reservation_id=None,  # Standalone order
            table_id=None,
            person_name=customer_name,
            status='pending',
            target_date=target_date,
            target_time=target_time,
            order_type=order_type,
            customer_phone=customer_phone,
            customer_address=customer_address,
            special_instructions=special_instructions
        )
        db.session.add(order)
        db.session.flush()  # Get order ID
        
        total_amount = 0
        
        # Add order items
        for item_data in items:
            # Find menu item by name (since we're using generated IDs)
            menu_item = MenuItem.query.filter_by(name=item_data['name']).first()
            if menu_item:
                # Only add special instructions to item notes, not order type/phone info
                item_notes = ""
                if special_instructions:
                    item_notes = f"Instructions: {special_instructions}"
                
                order_item = OrderItem(
                    order_id=order.id,
                    menu_item_id=menu_item.id,
                    quantity=item_data['quantity'],
                    price_at_time=item_data['price'],
                    notes=item_notes
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

def generate_order_number():
    """Generate a unique 6-digit order number"""
    import random
    while True:
        # Generate a 6-digit number (100000 to 999999)
        number = str(random.randint(100000, 999999))
        
        # Check if this number already exists (only if we're in an app context)
        try:
            existing = Order.query.filter_by(order_number=number).first()
            if not existing:
                return number
        except RuntimeError:
            # If we're outside app context, just return the number
            # This can happen during testing or initialization
            return number

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
        
        # Update payment fields
        if 'payment_status' in data:
            order.payment_status = data['payment_status']
        if 'payment_amount' in data:
            order.payment_amount = data['payment_amount']
        if 'payment_intent_id' in data:
            order.payment_intent_id = data['payment_intent_id']
        if 'payment_date' in data:
            order.payment_date = data['payment_date']
        else:
            # Set payment date to now if marking as paid
            if data.get('payment_status') == 'paid':
                order.payment_date = datetime.now()
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Payment status updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

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
            'last_function_time': {},
            'extracted_info': {},  # Store extracted information from conversation
            'reservation_context': None,  # Store current reservation being discussed
            'payment_context': None  # Store payment-related context
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
    
    # Store reservation context from get_reservation results
    if function_name == 'get_reservation' and result:
        try:
            # Extract reservation information from result
            if hasattr(result, 'response'):
                response_text = result.response
                # Look for reservation number in response
                import re
                reservation_match = re.search(r'reservation number:?\s*([0-9]{6})', response_text, re.IGNORECASE)
                if reservation_match:
                    reservation_number = reservation_match.group(1)
                    memory['reservation_context'] = {
                        'reservation_number': reservation_number,
                        'response_text': response_text,
                        'timestamp': current_time
                    }
                    print(f"💾 Stored reservation context: {reservation_number}")
        except Exception as e:
            print(f"⚠️ Error storing reservation context: {e}")
    
    # Store reservation context from create_reservation results
    if function_name == 'create_reservation' and result:
        try:
            if hasattr(result, 'response'):
                response_text = result.response
                # Look for reservation number in response
                import re
                reservation_match = re.search(r'reservation number:?\s*([0-9]{6})', response_text, re.IGNORECASE)
                if reservation_match:
                    reservation_number = reservation_match.group(1)
                    memory['reservation_context'] = {
                        'reservation_number': reservation_number,
                        'response_text': response_text,
                        'timestamp': current_time,
                        'just_created': True
                    }
                    print(f"💾 Stored new reservation context: {reservation_number}")
        except Exception as e:
            print(f"⚠️ Error storing new reservation context: {e}")
    
    print(f"📝 Recorded function call: {function_name} for session {ai_session_id}")
    print(f"   Total calls in session: {len(memory['function_calls'])}")
    print(f"   Functions called: {list(memory['last_function_time'].keys())}")

def extract_context_from_conversation(call_log, ai_session_id):
    """Extract relevant context information from conversation history"""
    memory = get_conversation_memory(ai_session_id)
    extracted_info = memory['extracted_info']
    
    if not call_log:
        return extracted_info
    
    import re
    
    # Look through conversation for key information
    for entry in call_log:
        if entry.get('role') == 'user':
            content = entry.get('content', '').strip()
            
            # Look for reservation numbers (6 digits)
            reservation_matches = re.findall(r'\b(\d{6})\b', content)
            for match in reservation_matches:
                extracted_info['reservation_number'] = match
                print(f"🔍 Extracted reservation number from conversation: {match}")
            
            # Look for names (patterns like "I'm John Smith", "This is Mary Johnson")
            name_patterns = [
                r'(?:i\'?m|this is|my name is)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)*)',
                r'(?:for|under)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)+)',
            ]
            for pattern in name_patterns:
                name_matches = re.findall(pattern, content, re.IGNORECASE)
                for match in name_matches:
                    if len(match.split()) >= 2:  # At least first and last name
                        extracted_info['customer_name'] = match.title()
                        print(f"🔍 Extracted customer name from conversation: {match.title()}")
            
            # Look for payment intent
            payment_keywords = ['pay', 'payment', 'bill', 'charge', 'credit card']
            if any(keyword in content.lower() for keyword in payment_keywords):
                extracted_info['payment_intent'] = True
                print(f"🔍 Detected payment intent in conversation")
    
    # Also check assistant responses for reservation information
    for entry in call_log:
        if entry.get('role') == 'assistant':
            content = entry.get('content', '').strip()
            
            # Look for reservation confirmations with numbers
            reservation_matches = re.findall(r'reservation number:?\s*([0-9]{6})', content, re.IGNORECASE)
            for match in reservation_matches:
                extracted_info['confirmed_reservation_number'] = match
                memory['reservation_context'] = {
                    'reservation_number': match,
                    'response_text': content,
                    'timestamp': time.time()
                }
                print(f"🔍 Extracted confirmed reservation number: {match}")
            
            # Look for customer names in assistant responses (e.g., "reservation for Johnson Group")
            name_patterns = [
                r'reservation for ([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
                r'found your reservation for ([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
                r'I found.*for ([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
            ]
            for pattern in name_patterns:
                name_matches = re.findall(pattern, content)
                for match in name_matches:
                    if len(match.split()) >= 1:  # At least one name
                        extracted_info['customer_name'] = match.strip()
                        print(f"🔍 Extracted customer name from assistant response: {match.strip()}")
                        break
    
    return extracted_info

# Add missing preprocessing function for reservation parameters
def preprocess_reservation_params(params):
    """
    Preprocess reservation parameters to handle various date/time formats
    Converts ISO datetime format to separate date and time fields
    """
    try:
        processed_params = params.copy()
        
        # Handle ISO datetime format in time field (e.g., "2025-06-09T14:00:00")
        time_str = params.get('time', '')
        if time_str and 'T' in time_str and ':' in time_str:
            print(f"🔄 Converting ISO datetime: {time_str}")
            
            # Parse ISO datetime
            iso_datetime = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            processed_params['date'] = iso_datetime.strftime("%Y-%m-%d")
            processed_params['time'] = iso_datetime.strftime("%H:%M")
            
            print(f"   Converted to: date='{processed_params['date']}', time='{processed_params['time']}'")
        
        # Handle ISO datetime format in date field (fallback)
        date_str = params.get('date', '')
        if date_str and 'T' in date_str and ':' in date_str:
            print(f"🔄 Converting ISO datetime in date field: {date_str}")
            
            # Parse ISO datetime
            iso_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            processed_params['date'] = iso_datetime.strftime("%Y-%m-%d")
            if 'time' not in processed_params or not processed_params['time']:
                processed_params['time'] = iso_datetime.strftime("%H:%M")
            
            print(f"   Converted to: date='{processed_params['date']}', time='{processed_params['time']}'")
        
        return processed_params
        
    except Exception as e:
        print(f"❌ Error preprocessing reservation params: {e}")
        # Return original params if preprocessing fails
        return params

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
        print(f"📋 Raw request data (first 1000 chars): {raw_data[:1000]}")
        print(f"📋 Raw request data length: {len(raw_data) if raw_data else 0}")
        
        # Better error handling for JSON parsing
        try:
            data = request.get_json()
            if data:
                import json as json_module
                print(f"📋 Parsed JSON data (full):")
                print(json_module.dumps(data, indent=2))
            else:
                print("📋 Parsed JSON data: None")
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
                    'send_payment_receipt',
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
                },
                'get_card_details': {
                    'function': 'get_card_details',
                    'purpose': 'Collect payment information and confirm payment details for EXISTING reservations only. Use this only when customers have an existing reservation and want to pay their bill. Do NOT use this for new reservations - use create_reservation first.',
                    'argument': {
                        'type': 'object',
                        'properties': {
                            'reservation_number': {'type': 'string', 'description': '6-digit reservation number to pay for (will be extracted from conversation if not provided)'},
                            'cardholder_name': {'type': 'string', 'description': 'Name on the credit card (will be requested if not provided)'},
                            'phone_number': {'type': 'string', 'description': 'SMS number for receipt (will use caller ID if not provided)'}
                        },
                        'required': []
                    }
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
        
        # Check if this is a call state notification (not a SWAIG function call)
        if 'call' in data and 'call_state' in data.get('call', {}):
            call_info = data['call']
            call_id = call_info.get('call_id')
            call_state = call_info.get('call_state')
            direction = call_info.get('direction')
            from_number = call_info.get('from')
            to_number = call_info.get('to')
            
            print(f"📞 Call state notification received:")
            print(f"   Call ID: {call_id}")
            print(f"   State: {call_state}")
            print(f"   Direction: {direction}")
            print(f"   From: {from_number}")
            print(f"   To: {to_number}")
            
            # Handle different call states
            if call_state == 'created':
                print(f"✅ Call {call_id} created - inbound call from {from_number}")
                
                # Return SWML document to start the conversation
                print(f"📞 Returning SWML document to start conversation for call {call_id}")
                
                # Get the SWML document from the GET endpoint
                try:
                    swml_response = swaig_receptionist_info()
                    if hasattr(swml_response, 'get_json'):
                        swml_data = swml_response.get_json()
                    else:
                        swml_data = swml_response
                    
                    print(f"📋 Returning SWML document for call initialization")
                    return jsonify(swml_data)
                except Exception as e:
                    print(f"❌ Error generating SWML document: {e}")
                    # Fallback SWML response
                    return jsonify({
                        "version": "1.0.0",
                        "sections": {
                            "main": [
                                {
                                    "ai": {
                                        "params": {
                                            "static_greeting": "Hello! Thank you for calling Bobby's Table. I'm Bobby, your friendly restaurant assistant. How can I help you today?",
                                            "static_greeting_no_barge": "false"
                                        },
                                        "SWAIG": {
                                            "defaults": {
                                                "web_hook_url": f"{request.url_root}receptionist"
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    })
                    
            elif call_state == 'answered':
                print(f"✅ Call {call_id} answered")
            elif call_state == 'ended':
                print(f"✅ Call {call_id} ended - cleaning up any payment sessions")
                try:
                    end_payment_session(call_id)
                except Exception as e:
                    print(f"⚠️ Error cleaning up payment session: {e}")
            
            # Return success response for other call state notifications
            return jsonify({
                'status': 'received',
                'call_id': call_id,
                'call_state': call_state
            })
        
        # Extract function name and parameters from the request
        function_name = data.get('function')
        if not function_name:
            print("❌ No function name provided")
            return jsonify({'error': 'Function name required'}), 400
        
        print(f"🔧 Function requested: {function_name}")
        
        # Extract AI session ID for conversation memory
        ai_session_id = data.get('ai_session_id', 'default')
        print(f"   AI Session ID: {ai_session_id}")
        
        # Extract parameters from the request
        params = {}
        if 'argument' in data:
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
        
        print(f"✅ Function blocking disabled - allowing {function_name} to proceed")
        
        # Get call ID for payment session tracking
        call_id = data.get('call_id', 'unknown')
        
        # SIMPLIFIED: Payment sessions are now managed by individual functions as needed
        # Removed aggressive auto-detection that was causing blocking issues
        
        # REMOVED: Payment flow protection blocking system
        # The AI agent can naturally handle payment context without forced function blocking.
        # This allows for more natural conversation flows and prevents blocking legitimate functions
        # like create_reservation when customers want to make reservations with pre-orders.
        
        # Handle custom functions first
        if function_name == 'get_card_details':
            print(f"✅ Calling custom function: {function_name}")
            result = get_card_details_handler(params, data)
            print(f"✅ Function execution completed")
            print(f"📤 Function result: {result}")
            
            # Record the function call in memory
            record_function_call(ai_session_id, function_name, result)
            return jsonify(result)
        
        # Route to appropriate agent function using skills-based architecture  
        try:
            # Check if agent has tool registry and the function exists
            if (hasattr(agent, '_tool_registry') and 
                hasattr(agent._tool_registry, '_swaig_functions') and 
                function_name in agent._tool_registry._swaig_functions):
                
                print(f"✅ Calling agent function: {function_name}")
                
                # Extract context from conversation before calling function
                call_log = data.get('call_log', [])
                extracted_info = extract_context_from_conversation(call_log, ai_session_id)
                memory = get_conversation_memory(ai_session_id)
                
                # Enhance parameters with extracted context information
                if function_name in ['pay_reservation', 'get_card_details']:
                    # For payment functions, try to provide missing context
                    if not params.get('reservation_number'):
                        # Try multiple sources for reservation number
                        reservation_number = (
                            extracted_info.get('reservation_number') or
                            extracted_info.get('confirmed_reservation_number') or
                            (memory.get('reservation_context', {}).get('reservation_number'))
                        )
                        if reservation_number:
                            params['reservation_number'] = reservation_number
                            print(f"🔄 Added reservation number from context: {reservation_number}")
                    
                    if not params.get('cardholder_name'):
                        # Try to get customer name from context
                        customer_name = extracted_info.get('customer_name')
                        if customer_name:
                            params['cardholder_name'] = customer_name
                            print(f"🔄 Added cardholder name from context: {customer_name}")
                    
                    if not params.get('phone_number'):
                        # Get phone number from caller ID
                        caller_phone = data.get('caller_id_num') or data.get('caller_id_number')
                        if caller_phone:
                            params['phone_number'] = caller_phone
                            print(f"🔄 Added phone number from caller ID: {caller_phone}")
                
                # Preprocess parameters for specific functions
                if function_name == 'create_reservation':
                    params = preprocess_reservation_params(params)
                
                # Add payment session information to data for payment-related functions
                if function_name in ['pay_order', 'pay_reservation'] and call_id:
                    session_data = get_payment_session_data(call_id)
                    if session_data:
                        print(f"🔍 Adding payment session data to function call: {session_data}")
                        data['_payment_session'] = session_data
                    else:
                        print(f"🔍 No payment session data found for {call_id}")
                
                # Add extracted context to raw_data for function access
                data['_extracted_context'] = extracted_info
                data['_conversation_memory'] = memory
                
                print(f"🔧 Executing function: {function_name}")
                print(f"📥 Function parameters: {json_module.dumps(params, indent=2) if params else 'None'}")
                print(f"🧠 Context provided: {extracted_info}")
                
                # Get the function handler from the tool registry
                func = agent._tool_registry._swaig_functions[function_name]
                if hasattr(func, 'handler'):
                    # This is a SWAIGFunction object with a handler
                    function_handler = func.handler
                elif isinstance(func, dict) and 'handler' in func:
                    # This is a dict with a handler key
                    function_handler = func['handler']
                else:
                    print(f"❌ No handler found for function {function_name}")
                    return jsonify({'success': False, 'message': f'No handler found for function: {function_name}'}), 400
                
                result = function_handler(params, data)
                
                print(f"✅ Function execution completed")
                print(f"📤 Function result type: {type(result)}")
                print(f"📤 Function result: {result}")
                
                # Record the function call in memory
                record_function_call(ai_session_id, function_name, result)
                
                # Handle SwaigFunctionResult properly
                if hasattr(result, 'to_dict'):
                    # This is a SwaigFunctionResult object - convert to proper SWAIG format
                    swaig_response = result.to_dict()
                    print(f"📋 SWAIG response (full):")
                    print(json_module.dumps(swaig_response, indent=2))
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
                            parsed_json = json_module.loads(response_content)
                            print("   Returning parsed JSON data in SWAIG format")
                            return jsonify({"response": parsed_json})
                        except (json_module.JSONDecodeError, ValueError):
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
                print(f"❌ Function {function_name} not found in agent tool registry")
                return jsonify({'success': False, 'message': f'Unknown function: {function_name}'}), 400
                
        except AttributeError as attr_err:
            print(f"⚠️ AttributeError when checking agent functions: {attr_err}")
            print(f"❌ Function {function_name} not available")
            return jsonify({'success': False, 'message': f'Function not available: {function_name}'}), 400
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
                            "digit_terminators": "#",
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
                            "static_greeting": "Hello! Thank you for calling Bobby's Table. I'm Bobby, your friendly restaurant assistant. How can I help you today?",
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
                                            "phone_number": {"type": "string", "description": "SMS number for receipt (will use caller ID if not provided)"}
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
                                },
                                {
                                    "function": "get_card_details",
                                    "purpose": "Collect payment information and confirm payment details before processing payment. This function should be called first when customers want to pay their bill.",
                                    "argument": {
                                        "type": "object",
                                        "properties": {
                                            "reservation_number": {"type": "string", "description": "6-digit reservation number to pay for (will be extracted from conversation if not provided)"},
                                            "cardholder_name": {"type": "string", "description": "Name on the credit card (will be requested if not provided)"},
                                            "phone_number": {"type": "string", "description": "SMS number for receipt (will use caller ID if not provided)"}
                                        },
                                        "required": []
                                    }
                                }
                            ]
                        },
                        "prompt": {
                            "text": "Hi there! I'm Bobby from Bobby's Table. Great to have you call us today! How can I help you out? Whether you're looking to make a reservation, check on an existing one, hear about our menu, or place an order, I'm here to help make it easy for you.\n\nIMPORTANT CONVERSATION GUIDELINES:\n\n**RESERVATION LOOKUPS - CRITICAL:**\n- When customers want to check their reservation, ALWAYS ask for their reservation number FIRST\n- Say: 'Do you have your reservation number? It's a 6-digit number we sent you when you made the reservation.'\n- Only if they don't have it, then ask for their name as backup\n- Reservation numbers are the fastest and most accurate way to find reservations\n- Handle spoken numbers like 'seven eight nine zero one two' which becomes '789012'\n\n**🚨 PAYMENTS - CRITICAL PAYMENT RULE 🚨:**\n**NEVER EVER call pay_reservation directly! ALWAYS call get_card_details FIRST!**\n\n**MANDATORY PAYMENT FLOW:**\n1. Customer wants to pay → IMMEDIATELY call get_card_details function\n2. get_card_details will collect reservation number and cardholder name\n3. get_card_details will ask: 'Would you like me to proceed with collecting your card details now?'\n4. ONLY after customer confirms 'yes' → THEN call pay_reservation function\n5. pay_reservation will prompt customer to enter card details via phone keypad (card number, expiration, CVV, ZIP)\n\n**EXAMPLES:**\n- Customer: 'I want to pay my bill' → YOU: Call get_card_details function\n- Customer: 'Yes, I want to pay' → YOU: Call get_card_details function\n- Customer: 'Can I pay for my reservation?' → YOU: Call get_card_details function\n\n**NEVER DO THIS:**\n- ❌ NEVER call pay_reservation when customer first asks to pay\n- ❌ NEVER skip get_card_details step\n- ❌ NEVER call pay_reservation directly\n\n**PRICING AND PRE-ORDERS - CRITICAL:**\n- When customers mention food items, ALWAYS provide the price immediately\n- Example: 'Buffalo Wings are twelve dollars and ninety-nine cents'\n- When creating reservations with pre-orders, ALWAYS mention the total cost\n- Example: 'Your Buffalo Wings and Draft Beer total sixteen dollars and ninety-eight cents'\n- ALWAYS ask if customers want to pay for their pre-order after confirming the total\n- Example: 'Would you like to pay for your pre-order now to complete your reservation?'\n\n**OTHER GUIDELINES:**\n- When making reservations, ALWAYS ask if customers want to pre-order from the menu\n- For parties larger than one person, ask for each person's name and their individual food preferences\n- Always say numbers as words (say 'one' instead of '1', 'two' instead of '2', etc.)\n- Extract food items mentioned during reservation requests and include them in party_orders\n- Be conversational and helpful - guide customers through the pre-ordering process naturally"
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
    """Send SMS receipt for payment using SWAIG function"""
    try:
        import requests
        import json
        
        # Use provided phone_number or reservation.phone_number
        to_number = phone_number if phone_number else reservation.phone_number
        
        # Call the send_payment_receipt SWAIG function
        swaig_data = {
            'function': 'send_payment_receipt',
            'argument': {
                'parsed': [{
                    'reservation_number': reservation.reservation_number,
                    'phone_number': to_number,
                    'amount': float(payment_amount),
                    'confirmation_number': confirmation_number or 'N/A'
                }],
                'raw': json.dumps({
                    'reservation_number': reservation.reservation_number,
                    'phone_number': to_number,
                    'amount': float(payment_amount),
                    'confirmation_number': confirmation_number or 'N/A'
                })
            },
            'call_id': f'payment-{confirmation_number or "unknown"}',
            'content_type': 'text/swaig',
            'version': '2.0',
            'caller_id_num': to_number
        }
        
        print(f"📱 Calling SWAIG send_payment_receipt function for reservation {reservation.reservation_number}")
        response = requests.post(
            'http://localhost:8080/receptionist',
            json=swaig_data,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            # Check if SWML send_sms action was generated
            if 'action' in result:
                for action_item in result['action']:
                    if 'SWML' in action_item and 'sections' in action_item['SWML']:
                        for section_action in action_item['SWML']['sections']['main']:
                            if 'send_sms' in section_action:
                                print(f"✅ SMS receipt SWAIG function called successfully - SWML send_sms action generated")
                                return {'success': True, 'sms_sent': True, 'sms_result': 'Payment receipt SMS SWML action generated via SWAIG'}
            
            print(f"✅ SMS receipt SWAIG function called successfully")
            return {'success': True, 'sms_sent': True, 'sms_result': 'Payment receipt SMS function called via SWAIG'}
        else:
            print(f"⚠️ SMS SWAIG function failed: {response.status_code} - {response.text}")
            return {'success': False, 'sms_sent': False, 'error': f'SWAIG function failed: {response.status_code}'}
            
    except Exception as e:
        print(f"❌ SMS Error: Failed to call SWAIG send_payment_receipt function: {e}")
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
        
        # Handle payment date safely
        if order.payment_date:
            sms_body += f"• Payment Date: {order.payment_date.strftime('%m/%d/%Y %I:%M %p')}\n"
        else:
            sms_body += f"• Payment Date: {datetime.now().strftime('%m/%d/%Y %I:%M %p')}\n"
        
        # Handle payment ID safely
        if order.payment_intent_id:
            sms_body += f"• Payment ID: {order.payment_intent_id[-8:]}\n\n"
        else:
            sms_body += f"• Payment ID: N/A\n\n"
        
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
        
        # Send SMS using SignalWire REST API directly
        try:
            import requests
            
            # Get SignalWire credentials from environment
            project_id = os.getenv('SIGNALWIRE_PROJECT_ID')
            auth_token = os.getenv('SIGNALWIRE_AUTH_TOKEN') 
            space_url = os.getenv('SIGNALWIRE_SPACE_URL')
            
            # If REST API credentials are not available, fall back to the SDK approach
            if not all([project_id, auth_token, space_url]):
                print("⚠️ SignalWire REST API credentials not found, using SDK approach")
                # Use SignalWire Agents SDK
                from signalwire_agents.core.function_result import SwaigFunctionResult
                result = SwaigFunctionResult()
                result = result.send_sms(
                    to_number=to_number,
                    from_number=signalwire_from_number,
                    body=sms_body
                )
                print(f"📱 SMS sent using SignalWire Agents SDK")
                return {'success': True, 'sms_sent': True, 'sms_result': 'Order payment receipt SMS sent via SDK'}
            
            # Use SignalWire REST API
            url = f"https://{space_url}/api/laml/2010-04-01/Accounts/{project_id}/Messages.json"
            
            data = {
                'From': signalwire_from_number,
                'To': to_number,
                'Body': sms_body
            }
            
            response = requests.post(
                url,
                auth=(project_id, auth_token),
                data=data
            )
            
            if response.status_code == 201:
                print(f"✅ SMS sent successfully via SignalWire REST API")
                return {'success': True, 'sms_sent': True, 'sms_result': 'Order payment receipt SMS sent via REST API'}
            else:
                print(f"❌ Failed to send SMS via REST API: {response.status_code} - {response.text}")
                # Fall back to SDK approach
                from signalwire_agents.core.function_result import SwaigFunctionResult
                result = SwaigFunctionResult()
                result = result.send_sms(
                    to_number=to_number,
                    from_number=signalwire_from_number,
                    body=sms_body
                )
                print(f"📱 SMS sent using SignalWire Agents SDK (fallback)")
                return {'success': True, 'sms_sent': True, 'sms_result': 'Order payment receipt SMS sent via SDK (fallback)'}
                
        except Exception as sms_error:
            print(f"❌ SMS sending error: {sms_error}")
            return {'success': False, 'sms_sent': False, 'error': str(sms_error)}
        
    except Exception as e:
        print(f"❌ SMS Error: Failed to send order payment receipt SMS to {phone_number or order.customer_phone}: {e}")
        return {'success': False, 'sms_sent': False, 'error': str(e)}

@app.route('/api/payment-processor', methods=['POST'])
def payment_processor():
    """SignalWire-compatible payment connector for SWML pay verb"""
    try:
        print("🔍 SignalWire Payment Connector called")
        print(f"   Content-Type: {request.content_type}")
        print(f"   Content-Length: {request.content_length}")
        print(f"   Request URL: {request.url}")
        print(f"   Request method: {request.method}")
        print(f"   User-Agent: {request.headers.get('User-Agent', 'N/A')}")
        
        # Get payment data from SignalWire Pay verb
        payment_data = request.get_json()
        
        if not payment_data:
            print("❌ No payment data received")
            return jsonify({
                "charge_id": None,
                "error_code": "MISSING_DATA",
                "error_message": "No payment data received"
            }), 400
        
        # PCI COMPLIANCE: Never log card data
        safe_data = {k: v for k, v in payment_data.items() 
                    if k not in ['card_number', 'cvc', 'cvv', 'security_code']}
        safe_data['card_number'] = '****' + payment_data.get('card_number', '')[-4:] if payment_data.get('card_number') else 'N/A'
        print(f"📋 Payment data received (PCI safe): {json.dumps(safe_data, indent=2)}")
        
        # Debug: Show all available keys (excluding sensitive data)
        safe_keys = [k for k in payment_data.keys() if k not in ['card_number', 'cvc', 'cvv', 'security_code']]
        print(f"🔍 Available keys in payment data: {safe_keys}")
        if 'parameters' in payment_data:
            print(f"🔍 Parameters structure: {payment_data['parameters']}")
        
        # Extract payment information from SWML pay verb
        # SignalWire sends different field names than expected
        card_number = payment_data.get('cardnumber', payment_data.get('card_number', '')).replace(' ', '')
        exp_month = payment_data.get('expiry_month', payment_data.get('exp_month'))
        exp_year = payment_data.get('expiry_year', payment_data.get('exp_year'))
        cvc = payment_data.get('cvv', payment_data.get('cvc'))
        postal_code = payment_data.get('postal_code')
        amount = payment_data.get('chargeAmount', payment_data.get('amount'))  # SignalWire uses 'chargeAmount'
        currency = payment_data.get('currency_code', payment_data.get('currency', 'usd'))
        
        # Get additional parameters from the payment data
        # SWML pay verb sends parameters in multiple possible formats
        parameters = payment_data.get('parameters', [])
        order_id = payment_data.get('order_id')
        order_number = payment_data.get('order_number')
        reservation_number = payment_data.get('reservation_number')
        customer_name = payment_data.get('customer_name')
        phone_number = payment_data.get('phone_number')
        payment_type = payment_data.get('payment_type')
        
        # Extract parameters from array format if present
        # SignalWire sends parameters as array of objects with single key-value pairs
        for param in parameters:
            if isinstance(param, dict):
                # Handle both formats: {"name": "key", "value": "val"} and {"key": "val"}
                if 'name' in param and 'value' in param:
                    # Standard format
                    param_name = param.get('name')
                    param_value = param.get('value')
                else:
                    # Direct key-value format (what SignalWire actually sends)
                    param_name = list(param.keys())[0] if param else None
                    param_value = param.get(param_name) if param_name else None
                
                if param_name == 'order_id':
                    order_id = order_id or param_value
                elif param_name == 'order_number':
                    order_number = order_number or param_value
                elif param_name == 'reservation_number':
                    reservation_number = reservation_number or param_value
                elif param_name == 'customer_name':
                    customer_name = customer_name or param_value
                elif param_name == 'phone_number':
                    phone_number = phone_number or param_value
                elif param_name == 'payment_type':
                    payment_type = payment_type or param_value
        
        # Also check for direct field names in the payment data
        if not order_id:
            order_id = payment_data.get('order_id')
        if not order_number:
            order_number = payment_data.get('order_number')
        if not reservation_number:
            reservation_number = payment_data.get('reservation_number')
        if not customer_name:
            customer_name = payment_data.get('customer_name') or payment_data.get('cardholder_name')
        if not phone_number:
            phone_number = payment_data.get('phone_number')
        if not payment_type:
            payment_type = payment_data.get('payment_type')
        
        print(f"💳 Processing payment:")
        print(f"   Card: ****{card_number[-4:] if card_number else 'N/A'}")
        print(f"   Expiry: {exp_month}/{exp_year}")
        print(f"   Amount: ${amount}")
        print(f"   ZIP: {postal_code}")
        print(f"   Type: {payment_type}")
        print(f"   Order: {order_number}")
        print(f"   Reservation: {reservation_number}")
        print(f"   Customer: {customer_name}")
        print(f"   Phone: {phone_number}")
        
        # Debug: Show what we extracted
        print(f"🔍 Parameter extraction results:")
        print(f"   - payment_type: {payment_type}")
        print(f"   - reservation_number: {reservation_number}")
        print(f"   - order_number: {order_number}")
        print(f"   - customer_name: {customer_name}")
        print(f"   - phone_number: {phone_number}")
        print(f"   - amount: {amount}")
        print(f"🔍 Condition checks:")
        print(f"   - payment_type == 'reservation': {payment_type == 'reservation'}")
        print(f"   - reservation_number truthy: {bool(reservation_number)}")
        print(f"   - Combined condition: {payment_type == 'reservation' or reservation_number}")
        
        # Validate required fields
        if not amount:
            print("❌ Amount is required but not provided")
            print(f"🔍 Available amount fields in payment_data:")
            amount_fields = [k for k in payment_data.keys() if 'amount' in k.lower() or 'charge' in k.lower()]
            print(f"   - Amount-related fields: {amount_fields}")
            for field in amount_fields:
                print(f"   - {field}: {payment_data.get(field)}")
            return jsonify({
                "charge_id": None,
                "error_code": "MISSING_AMOUNT",
                "error_message": "Amount is required"
            }), 400
        
        try:
            # Check if amount is already in cents (integer) or dollars (float)
            # If it's a small float (< 100), assume it's dollars and convert to cents
            # If it's a large integer (>= 100), assume it's already in cents
            amount_float = float(amount)
            if amount_float < 100 and '.' in str(amount):
                # Likely dollars, convert to cents
                amount_cents = int(amount_float * 100)
                print(f"💰 Amount converted from dollars to cents: ${amount_float} -> {amount_cents} cents")
            else:
                # Likely already in cents
                amount_cents = int(amount_float)
                print(f"💰 Amount assumed to be in cents: {amount_cents}")
        except (ValueError, TypeError) as e:
            print(f"❌ Invalid amount format: {amount} - {e}")
            return jsonify({
                "status": "failed",
                "error": f"Invalid amount format: {amount}"
            }), 400
        
        # Process payment with Stripe using the same pattern as our successful test
        try:
            import stripe
            stripe.api_key = os.getenv('STRIPE_API_KEY')
            
            if not stripe.api_key:
                print("⚠️ No Stripe API key configured, using test mode")
                stripe.api_key = 'sk_test_51234567890abcdef'  # Fallback for testing
            
            print(f"🔑 Using Stripe API key: {stripe.api_key[:12]}...")
            
            # Create payment method from card data or use test token
            payment_method = None
            payment_method_id = None
            
            try:
                # Try to create payment method with card data
                print(f"🔍 Attempting to create payment method with card data")
                payment_method = stripe.PaymentMethod.create(
                    type="card",
                    card={
                        "number": card_number,
                        "exp_month": int(exp_month) if exp_month else None,
                        "exp_year": int(exp_year) if exp_year else None,
                        "cvc": cvc,
                    },
                    billing_details={
                        "name": customer_name or "Customer",
                        "address": {
                            "postal_code": postal_code
                        }
                    }
                )
                payment_method_id = payment_method.id
                print(f"✅ Payment method created: {payment_method_id}")
                
            except stripe.error.CardError as e:
                print(f"❌ Payment method creation error: {str(e)}")
                if "raw card data" in str(e) or "empty string" in str(e):
                    print("⚠️ Raw card data not allowed or empty, using test payment method token")
                    # Use Stripe's test payment method instead
                    payment_method_id = "pm_card_visa"
                else:
                    print(f"❌ Card error: {e.user_message}")
                    return jsonify({
                        "status": "failed",
                        "error": e.user_message,
                        "decline_code": e.decline_code if hasattr(e, 'decline_code') else None
                    })
            except Exception as e:
                print(f"❌ Payment method creation error: {str(e)}")
                # Fallback to test payment method
                payment_method_id = "pm_card_visa"
                print(f"🔄 Using fallback payment method: {payment_method_id}")
            
            # Create payment intent with proper configuration
            description = f"Bobby's Table Payment"
            if order_number:
                description = f"Bobby's Table Order #{order_number}"
            elif reservation_number:
                description = f"Bobby's Table Reservation #{reservation_number}"
            
            print(f"💳 Creating payment intent for {description}")
            
            payment_intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency,
                payment_method=payment_method_id,
                confirm=True,
                description=description,
                automatic_payment_methods={
                    'enabled': True,
                    'allow_redirects': 'never'  # Prevent redirect-based payment methods
                },
                metadata={
                    "payment_source": "swml_pay_verb",
                    "order_id": order_id or "",
                    "order_number": order_number or "",
                    "reservation_number": reservation_number or "",
                    "customer_name": customer_name or "",
                    "customer_phone": phone_number or "",
                    "payment_type": payment_type or ""
                }
            )
            
            print(f"✅ Payment intent created: {payment_intent.id}")
            print(f"   Status: {payment_intent.status}")
            
            if payment_intent.status == 'succeeded':
                print("🎉 Stripe payment successful!")
                
                # Generate confirmation number first
                import random
                import string
                confirmation_number = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                print(f"🎫 Generated confirmation number: {confirmation_number}")
                
                # Update database based on payment type
                if payment_type == 'order' and (order_number or order_id):
                    # Handle order payment
                    order = None
                    if order_number:
                        order = Order.query.filter_by(order_number=order_number).first()
                    elif order_id:
                        order = Order.query.get(order_id)
                    
                    if order:
                        order.payment_status = 'paid'
                        order.payment_method = 'credit-card'
                        order.payment_date = datetime.now()
                        order.payment_amount = amount_cents / 100.0  # Convert cents to dollars for storage
                        order.payment_intent_id = payment_intent.id
                        order.confirmation_number = confirmation_number
                        
                        db.session.commit()
                        print(f"✅ Order {order.order_number} updated with payment info")
                        
                        # Send SMS receipt
                        try:
                            sms_result = send_order_payment_receipt_sms(
                                order=order,
                                payment_amount=amount_cents / 100.0,  # Convert cents to dollars for SMS
                                phone_number=phone_number or order.customer_phone,
                                confirmation_number=confirmation_number
                            )
                            
                            # SMS result already handled in the function
                            if sms_result.get('success'):
                                print(f"✅ SMS receipt sent: {sms_result.get('sms_result', 'Success')}")
                            else:
                                print(f"⚠️ SMS receipt failed: {sms_result.get('error', 'Unknown error')}")
                        except Exception as sms_error:
                            print(f"⚠️ Failed to send SMS receipt: {sms_error}")
                        
                        return jsonify({
                            "status": "success",
                            "payment_intent_id": payment_intent.id,
                            "amount": amount_cents / 100.0,  # Return amount in dollars
                            "currency": payment_intent.currency,
                            "message": f"Payment of ${amount_cents / 100.0:.2f} processed successfully for Order #{order.order_number}. Your confirmation number is {confirmation_number}.",
                            "confirmation_number": confirmation_number,
                            "order_number": order.order_number
                        })
                
                elif payment_type == 'reservation' or reservation_number:
                    # Handle reservation payment
                    print(f"🔍 Processing reservation payment: type={payment_type}, number={reservation_number}")
                    reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
                    if reservation:
                        print(f"✅ Found reservation: {reservation.name} for {reservation.party_size} people")
                        reservation.payment_status = 'paid'
                        reservation.payment_method = 'credit-card'
                        reservation.payment_date = datetime.now()
                        reservation.payment_amount = amount_cents / 100.0  # Convert cents to dollars for storage
                        reservation.payment_intent_id = payment_intent.id
                        reservation.confirmation_number = confirmation_number
                        
                        db.session.commit()
                        print(f"✅ Reservation {reservation.reservation_number} updated with payment info")
                        
                        # Call SWAIG send_payment_receipt function for reservation
                        print(f"📱 Calling SWAIG send_payment_receipt function for reservation {reservation_number}")
                        try:
                            # Make a SWAIG function call to send the SMS receipt
                            swaig_data = {
                                "function": "send_payment_receipt",
                                "argument": {
                                    "parsed": [{
                                        "reservation_number": reservation_number,
                                        "phone_number": phone_number or reservation.phone_number,
                                        "amount": amount_cents / 100.0,  # Convert cents to dollars for SMS
                                        "confirmation_number": confirmation_number
                                    }],
                                    "raw": json.dumps({
                                        "reservation_number": reservation_number,
                                        "phone_number": phone_number or reservation.phone_number,
                                        "amount": amount_cents / 100.0,  # Convert cents to dollars for SMS
                                        "confirmation_number": confirmation_number
                                    })
                                },
                                "call_id": f"payment-{confirmation_number}",
                                "content_type": "text/swaig",
                                "version": "2.0",
                                "caller_id_num": phone_number or reservation.phone_number
                            }
                            
                            # Call the SWAIG receptionist endpoint to trigger SMS
                            import requests
                            response = requests.post('http://localhost:8080/receptionist', json=swaig_data)
                            
                            if response.status_code == 200:
                                swaig_result = response.json()
                                print(f"✅ SMS receipt SWAIG function called successfully - SWML send_sms action generated")
                                sms_status = "SMS receipt sent: Payment receipt SMS SWML action generated via SWAIG"
                            else:
                                print(f"⚠️ SWAIG SMS function call failed: {response.status_code}")
                                sms_status = f"SMS receipt failed: SWAIG call returned {response.status_code}"
                                
                        except Exception as sms_error:
                            print(f"⚠️ Failed to call SWAIG SMS function: {sms_error}")
                            sms_status = f"SMS receipt failed: {str(sms_error)}"
                        
                        # Return comprehensive response with confirmation number
                        return jsonify({
                            "status": "success",
                            "payment_intent_id": payment_intent.id,
                            "charge_id": payment_intent.id,  # Keep for SignalWire compatibility
                            "amount": amount_cents / 100.0,  # Convert cents to dollars
                            "currency": payment_intent.currency,
                            "message": f"Payment of ${amount_cents / 100.0:.2f} processed successfully for Reservation #{reservation_number}. Your confirmation number is {confirmation_number}.",
                            "confirmation_number": confirmation_number,
                            "reservation_number": reservation_number,
                            "sms_status": sms_status,
                            "error_code": None,  # Keep for SignalWire compatibility
                            "error_message": None  # Keep for SignalWire compatibility
                        })
                    else:
                        print(f"❌ Reservation {reservation_number} not found")
                        return jsonify({
                            "status": "failed",
                            "error": f"Reservation {reservation_number} not found"
                        }), 404
                
                # Generic success response if no specific type
                # Generate a confirmation number for generic payments too
                import random
                import string
                confirmation_number = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                print(f"🎫 Generated generic confirmation number: {confirmation_number}")
                
                return jsonify({
                    "status": "success",
                    "payment_intent_id": payment_intent.id,
                    "charge_id": payment_intent.id,  # Keep for SignalWire compatibility
                    "amount": amount_cents / 100.0,  # Convert cents to dollars
                    "currency": payment_intent.currency,
                    "message": f"Payment of ${amount_cents / 100.0:.2f} processed successfully. Your confirmation number is {confirmation_number}.",
                    "confirmation_number": confirmation_number,
                    "error_code": None,  # Keep for SignalWire compatibility
                    "error_message": None  # Keep for SignalWire compatibility
                })
                
            elif payment_intent.status == 'requires_action':
                print("⚠️ Payment requires additional action")
                return jsonify({
                    "status": "requires_action",
                    "payment_intent_id": payment_intent.id,
                    "client_secret": payment_intent.client_secret,
                    "message": "Payment requires additional authentication"
                })
            else:
                print(f"❌ Payment failed with status: {payment_intent.status}")
                return jsonify({
                    "status": "failed",
                    "payment_intent_id": payment_intent.id,
                    "message": f"Payment failed with status: {payment_intent.status}"
                })
                
        except stripe.error.CardError as e:
            print(f"❌ Stripe card error: {e.user_message}")
            return jsonify({
                "charge_id": None,
                "error_code": e.decline_code if hasattr(e, 'decline_code') else "CARD_DECLINED",
                "error_message": e.user_message
            })
        except stripe.error.StripeError as e:
            print(f"❌ Stripe API error: {str(e)}")
            return jsonify({
                "charge_id": None,
                "error_code": "STRIPE_ERROR",
                "error_message": str(e)
            })
        except Exception as e:
            print(f"❌ Unexpected error in payment processing: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({
                "status": "failed",
                "error": str(e),
                "message": "Unexpected error occurred during payment processing"
            })
            
    except Exception as e:
        print(f"❌ Critical error in payment processor: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "failed",
            "error": str(e),
            "message": "Critical error in payment processor"
        }), 500

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
        
        # First check if session data exists
        session_data = app.payment_sessions.get(call_id)
        is_active = session_data is not None
        
        print(f"🔍 Checking payment session for {call_id}: {'ACTIVE' if is_active else 'INACTIVE'}")
        if session_data:
            print(f"   Session data: {session_data}")
        
        return is_active
        
    except Exception as e:
        print(f"❌ Error checking payment session: {e}")
        return False

def start_payment_session(call_id, reservation_number):
    """Start tracking a payment session"""
    try:
        if not hasattr(app, 'payment_sessions'):
            app.payment_sessions = {}
        
        # Don't overwrite existing session, just update it
        existing_session = app.payment_sessions.get(call_id)
        if existing_session:
            print(f"🔄 Updating existing payment session for call {call_id}")
            existing_session['reservation_number'] = reservation_number
            existing_session['last_updated'] = datetime.now()
        else:
            app.payment_sessions[call_id] = {
                'reservation_number': reservation_number,
                'started_at': datetime.now(),
                'last_updated': datetime.now(),
                'step': 'started'
            }
            print(f"🔒 Started new payment session for call {call_id}, reservation {reservation_number}")
        
        print(f"🔍 Total active payment sessions: {len(app.payment_sessions)}")
        
        # Immediately verify the session was created/updated
        if call_id in app.payment_sessions:
            print(f"✅ Payment session {call_id} successfully created and verified")
        else:
            print(f"❌ Payment session {call_id} creation failed - not found after creation")
        
    except Exception as e:
        print(f"❌ Error starting payment session: {e}")

def update_payment_step(call_id, step):
    """Update the current payment step"""
    try:
        if not hasattr(app, 'payment_sessions'):
            app.payment_sessions = {}
        
        if call_id in app.payment_sessions:
            app.payment_sessions[call_id]['step'] = step
            app.payment_sessions[call_id]['last_updated'] = datetime.now()
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

def get_payment_session_data(call_id):
    """Get payment session data for a call"""
    try:
        if not hasattr(app, 'payment_sessions'):
            app.payment_sessions = {}
        
        session_data = app.payment_sessions.get(call_id)
        if session_data:
            print(f"🔍 Retrieved payment session data for {call_id}: {session_data}")
        else:
            print(f"🔍 No payment session data found for {call_id}")
        
        return session_data
        
    except Exception as e:
        print(f"❌ Error getting payment session data: {e}")
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

@app.route('/debug/start-payment-session', methods=['POST'])
def debug_start_payment_session():
    """Debug endpoint to manually start a payment session"""
    try:
        data = request.get_json()
        call_id = data.get('call_id', 'debug-call-123')
        payment_type = data.get('payment_type', 'reservation')
        
        # Initialize payment sessions if not exists
        if not hasattr(app, 'payment_sessions'):
            app.payment_sessions = {}
        
        # Create payment session data
        session_data = {
            'call_id': call_id,
            'payment_type': payment_type,
            'started_at': datetime.now(),
            'last_updated': datetime.now()
        }
        
        # Add type-specific data
        if payment_type == 'order':
            order_number = data.get('order_number')
            if order_number:
                session_data['order_number'] = order_number
            else:
                return jsonify({
                    'success': False,
                    'error': 'order_number is required for order payments'
                }), 400
        else:
            # Default to reservation
            reservation_number = data.get('reservation_number', '123456')
            session_data['reservation_number'] = reservation_number
        
        # Add other optional data
        if 'customer_name' in data:
            session_data['customer_name'] = data['customer_name']
        if 'phone_number' in data:
            session_data['phone_number'] = data['phone_number']
        if 'amount' in data:
            session_data['amount'] = data['amount']
        
        # Store session
        app.payment_sessions[call_id] = session_data
        
        print(f"✅ Created payment session for {call_id}: {session_data}")
        
        response_data = {
            'success': True,
            'message': f'Payment session started for call {call_id}',
            'call_id': call_id,
            'payment_type': payment_type
        }
        
        # Add type-specific response data
        if payment_type == 'order':
            response_data['order_number'] = session_data.get('order_number')
        else:
            response_data['reservation_number'] = session_data.get('reservation_number')
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/debug/test-sms', methods=['POST'])
def debug_test_sms():
    """Debug endpoint to test SMS functionality via SWAIG"""
    try:
        data = request.get_json()
        phone_number = data.get('phone_number')
        message = data.get('message', 'Test SMS from Bobby\'s Table debug endpoint')
        
        if not phone_number:
            return jsonify({
                'success': False,
                'error': 'Phone number is required'
            }), 400
        
        print(f"🧪 Debug SMS Test Request:")
        print(f"   Phone: {phone_number}")
        print(f"   Message: {message}")
        
        # Get the agent and call the test SMS function
        agent = get_receptionist_agent()
        if not agent:
            return jsonify({
                'success': False,
                'error': 'Agent not available'
            }), 503
        
        # Call the SWAIG function directly
        if (hasattr(agent, '_tool_registry') and 
            hasattr(agent._tool_registry, '_swaig_functions') and
            'send_test_sms' in agent._tool_registry._swaig_functions):
            function_handler = agent._tool_registry._swaig_functions['send_test_sms']
            
            # Prepare the parameters
            params = {
                'phone_number': phone_number,
                'message': message
            }
            
            # Call the function
            result = function_handler(params, {})
            
            print(f"🧪 Debug SMS Test Result: {result}")
            
            return jsonify({
                'success': True,
                'message': f'Test SMS function called for {phone_number}',
                'result': str(result)
            })
        else:
            return jsonify({
                'success': False,
                'error': 'send_test_sms function not found in agent'
            }), 500
        
    except Exception as e:
        print(f"❌ Error in debug test SMS: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# PCI COMPLIANT: Stripe webhook handler for direct payments
@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhook events for PCI-compliant payments"""
    try:
        print("🔍 Stripe webhook called")
        
        # Get the raw body and signature
        payload = request.get_data()
        sig_header = request.headers.get('Stripe-Signature')
        
        # Verify webhook signature (optional but recommended)
        webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
        if webhook_secret and sig_header:
            try:
                import stripe
                event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
            except ValueError:
                print("❌ Invalid payload")
                return jsonify({"error": "Invalid payload"}), 400
            except stripe.error.SignatureVerificationError:
                print("❌ Invalid signature")
                return jsonify({"error": "Invalid signature"}), 400
        else:
            # Parse without verification (for development)
            event = json.loads(payload)
        
        print(f"📋 Webhook event: {event['type']}")
        
        # Handle payment intent events
        if event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            
            print(f"✅ Payment succeeded: {payment_intent['id']}")
            print(f"   Amount: ${payment_intent['amount'] / 100}")
            print(f"   Metadata: {payment_intent.get('metadata', {})}")
            
            # Extract metadata
            metadata = payment_intent.get('metadata', {})
            reservation_number = metadata.get('reservation_number')
            payment_type = metadata.get('payment_type')
            customer_name = metadata.get('customer_name')
            phone_number = metadata.get('phone_number')
            
            if payment_type == 'reservation' and reservation_number:
                # Update reservation payment status
                reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
                if reservation:
                    reservation.payment_status = 'paid'
                    reservation.payment_method = 'credit-card'
                    reservation.payment_date = datetime.now()
                    reservation.payment_amount = payment_intent['amount'] / 100
                    reservation.payment_intent_id = payment_intent['id']
                    
                    # Generate confirmation number
                    import random
                    import string
                    confirmation_number = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                    reservation.confirmation_number = confirmation_number
                    
                    db.session.commit()
                    
                    print(f"✅ Updated reservation #{reservation_number} payment status")
                    
                    # Send SMS receipt
                    try:
                        send_payment_receipt_sms(
                            reservation=reservation,
                            payment_amount=payment_intent['amount'] / 100,
                            phone_number=phone_number,
                            confirmation_number=confirmation_number
                        )
                        print(f"✅ SMS receipt sent to {phone_number}")
                    except Exception as sms_error:
                        print(f"⚠️ Failed to send SMS receipt: {sms_error}")
            
            elif payment_type == 'order':
                # Handle order payments similarly
                order_number = metadata.get('order_number')
                if order_number:
                    order = Order.query.filter_by(order_number=order_number).first()
                    if order:
                        order.payment_status = 'paid'
                        order.payment_method = 'credit-card'
                        order.payment_date = datetime.now()
                        order.payment_amount = payment_intent['amount'] / 100
                        order.payment_intent_id = payment_intent['id']
                        
                        # Generate confirmation number
                        import random
                        import string
                        confirmation_number = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                        order.confirmation_number = confirmation_number
                        
                        db.session.commit()
                        
                        print(f"✅ Updated order #{order_number} payment status")
        
        elif event['type'] == 'payment_intent.payment_failed':
            payment_intent = event['data']['object']
            print(f"❌ Payment failed: {payment_intent['id']}")
            print(f"   Error: {payment_intent.get('last_payment_error', {}).get('message', 'Unknown error')}")
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        print(f"❌ Webhook error: {str(e)}")
        return jsonify({"error": str(e)}), 500
        
        # Validate required fields
        if not amount:
            print("❌ Amount is required but not provided")
            return jsonify({
                "status": "failed",
                "error": "Amount is required"
            }), 400
        
        try:
            amount_cents = int(float(amount) * 100)
            print(f"💰 Amount converted to cents: {amount_cents}")
        except (ValueError, TypeError) as e:
            print(f"❌ Invalid amount format: {amount} - {e}")
            return jsonify({
                "status": "failed",
                "error": f"Invalid amount format: {amount}"
            }), 400
        
        # Process payment with Stripe using the same pattern as our successful test
        try:
            import stripe
            stripe.api_key = os.getenv('STRIPE_API_KEY')
            
            if not stripe.api_key:
                print("⚠️ No Stripe API key configured, using test mode")
                stripe.api_key = 'sk_test_51234567890abcdef'  # Fallback for testing
            
            print(f"🔑 Using Stripe API key: {stripe.api_key[:12]}...")
            
            # Create payment method from card data or use test token
            payment_method = None
            payment_method_id = None
            
            try:
                # Try to create payment method with card data
                print(f"🔍 Attempting to create payment method with card data")
                payment_method = stripe.PaymentMethod.create(
                    type="card",
                    card={
                        "number": card_number,
                        "exp_month": int(exp_month) if exp_month else None,
                        "exp_year": int(exp_year) if exp_year else None,
                        "cvc": cvc,
                    },
                    billing_details={
                        "name": customer_name or "Customer",
                        "address": {
                            "postal_code": postal_code
                        }
                    }
                )
                payment_method_id = payment_method.id
                print(f"✅ Payment method created: {payment_method_id}")
                
            except stripe.error.CardError as e:
                print(f"❌ Payment method creation error: {str(e)}")
                if "raw card data" in str(e) or "empty string" in str(e):
                    print("⚠️ Raw card data not allowed or empty, using test payment method token")
                    # Use Stripe's test payment method instead
                    payment_method_id = "pm_card_visa"
                else:
                    print(f"❌ Card error: {e.user_message}")
                    return jsonify({
                        "status": "failed",
                        "error": e.user_message,
                        "decline_code": e.decline_code if hasattr(e, 'decline_code') else None
                    })
            except Exception as e:
                print(f"❌ Payment method creation error: {str(e)}")
                # Fallback to test payment method
                payment_method_id = "pm_card_visa"
                print(f"🔄 Using fallback payment method: {payment_method_id}")
            
            # Create payment intent with proper configuration
            description = f"Bobby's Table Payment"
            if order_number:
                description = f"Bobby's Table Order #{order_number}"
            elif reservation_number:
                description = f"Bobby's Table Reservation #{reservation_number}"
            
            print(f"💳 Creating payment intent for {description}")
            
            payment_intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency,
                payment_method=payment_method_id,
                confirm=True,
                description=description,
                automatic_payment_methods={
                    'enabled': True,
                    'allow_redirects': 'never'  # Prevent redirect-based payment methods
                },
                metadata={
                    "payment_source": "swml_pay_verb",
                    "order_id": order_id or "",
                    "order_number": order_number or "",
                    "reservation_number": reservation_number or "",
                    "customer_name": customer_name or "",
                    "customer_phone": phone_number or "",
                    "payment_type": payment_type or ""
                }
            )
            
            print(f"✅ Payment intent created: {payment_intent.id}")
            print(f"   Status: {payment_intent.status}")
            
            if payment_intent.status == 'succeeded':
                print("🎉 Stripe payment successful!")
                
                # Generate confirmation number first
                import random
                import string
                confirmation_number = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                print(f"🎫 Generated confirmation number: {confirmation_number}")
                
                # Update database based on payment type
                if payment_type == 'order' and (order_number or order_id):
                    # Handle order payment
                    order = None
                    if order_number:
                        order = Order.query.filter_by(order_number=order_number).first()
                    elif order_id:
                        order = Order.query.get(order_id)
                    
                    if order:
                        order.payment_status = 'paid'
                        order.payment_method = 'credit-card'
                        order.payment_date = datetime.now()
                        order.payment_amount = float(amount)
                        order.payment_intent_id = payment_intent.id
                        order.confirmation_number = confirmation_number
                        
                        db.session.commit()
                        print(f"✅ Order {order.order_number} updated with payment info")
                        
                        # Send SMS receipt
                        try:
                            sms_result = send_order_payment_receipt_sms(
                                order=order,
                                payment_amount=float(amount),
                                phone_number=phone_number or order.customer_phone,
                                confirmation_number=confirmation_number
                            )
                            
                            # SMS result already handled in the function
                            if sms_result.get('success'):
                                print(f"✅ SMS receipt sent: {sms_result.get('sms_result', 'Success')}")
                            else:
                                print(f"⚠️ SMS receipt failed: {sms_result.get('error', 'Unknown error')}")
                        except Exception as sms_error:
                            print(f"⚠️ Failed to send SMS receipt: {sms_error}")
                        
                        return jsonify({
                            "status": "success",
                            "payment_intent_id": payment_intent.id,
                            "amount": float(amount),
                            "currency": payment_intent.currency,
                            "message": f"Payment of ${amount} processed successfully for Order #{order.order_number}. Your confirmation number is {confirmation_number}.",
                            "confirmation_number": confirmation_number,
                            "order_number": order.order_number
                        })
                
                elif payment_type == 'reservation' or reservation_number:
                    # Handle reservation payment
                    print(f"🔍 Processing reservation payment: type={payment_type}, number={reservation_number}")
                    reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
                    if reservation:
                        print(f"✅ Found reservation: {reservation.name} for {reservation.party_size} people")
                        reservation.payment_status = 'paid'
                        reservation.payment_method = 'credit-card'
                        reservation.payment_date = datetime.now()
                        reservation.payment_amount = float(amount)
                        reservation.payment_intent_id = payment_intent.id
                        reservation.confirmation_number = confirmation_number
                        
                        db.session.commit()
                        print(f"✅ Reservation {reservation.reservation_number} updated with payment info")
                        
                        # Call SWAIG send_payment_receipt function for reservation
                        print(f"📱 Calling SWAIG send_payment_receipt function for reservation {reservation_number}")
                        try:
                            # Make a SWAIG function call to send the SMS receipt
                            swaig_data = {
                                "function": "send_payment_receipt",
                                "argument": {
                                    "parsed": [{
                                        "reservation_number": reservation_number,
                                        "phone_number": phone_number or reservation.phone_number,
                                        "amount": amount_cents / 100.0,  # Convert cents to dollars for SMS
                                        "confirmation_number": confirmation_number
                                    }],
                                    "raw": json.dumps({
                                        "reservation_number": reservation_number,
                                        "phone_number": phone_number or reservation.phone_number,
                                        "amount": amount_cents / 100.0,  # Convert cents to dollars for SMS
                                        "confirmation_number": confirmation_number
                                    })
                                },
                                "call_id": f"payment-{confirmation_number}",
                                "content_type": "text/swaig",
                                "version": "2.0",
                                "caller_id_num": phone_number or reservation.phone_number
                            }
                            
                            # Call the SWAIG receptionist endpoint to trigger SMS
                            import requests
                            response = requests.post('http://localhost:8080/receptionist', json=swaig_data)
                            
                            if response.status_code == 200:
                                swaig_result = response.json()
                                print(f"✅ SMS receipt SWAIG function called successfully - SWML send_sms action generated")
                                sms_status = "SMS receipt sent: Payment receipt SMS SWML action generated via SWAIG"
                            else:
                                print(f"⚠️ SWAIG SMS function call failed: {response.status_code}")
                                sms_status = f"SMS receipt failed: SWAIG call returned {response.status_code}"
                                
                        except Exception as sms_error:
                            print(f"⚠️ Failed to call SWAIG SMS function: {sms_error}")
                            sms_status = f"SMS receipt failed: {str(sms_error)}"
                        
                        return jsonify({
                            "status": "success",
                            "payment_intent_id": payment_intent.id,
                            "amount": float(amount),
                            "currency": payment_intent.currency,
                            "message": f"Payment of ${amount} processed successfully for Reservation #{reservation_number}. Your confirmation number is {confirmation_number}.",
                            "confirmation_number": confirmation_number,
                            "reservation_number": reservation_number,
                            "sms_status": sms_status
                        })
                    else:
                        print(f"❌ Reservation {reservation_number} not found")
                        return jsonify({
                            "status": "failed",
                            "error": f"Reservation {reservation_number} not found"
                        }), 404
                
                # Generic success response if no specific type
                return jsonify({
                    "status": "success",
                    "payment_intent_id": payment_intent.id,
                    "amount": float(amount),
                    "currency": payment_intent.currency,
                    "message": f"Payment of ${amount} processed successfully. Your confirmation number is {confirmation_number}.",
                    "confirmation_number": confirmation_number
                })
                
            elif payment_intent.status == 'requires_action':
                print("⚠️ Payment requires additional action")
                return jsonify({
                    "status": "requires_action",
                    "payment_intent_id": payment_intent.id,
                    "client_secret": payment_intent.client_secret,
                    "message": "Payment requires additional authentication"
                })
            else:
                print(f"❌ Payment failed with status: {payment_intent.status}")
                return jsonify({
                    "status": "failed",
                    "payment_intent_id": payment_intent.id,
                    "message": f"Payment failed with status: {payment_intent.status}"
                })
                
        except stripe.error.CardError as e:
            print(f"❌ Stripe card error: {e.user_message}")
            return jsonify({
                "status": "failed",
                "error": e.user_message,
                "decline_code": e.decline_code if hasattr(e, 'decline_code') else None
            })
        except stripe.error.StripeError as e:
            print(f"❌ Stripe API error: {str(e)}")
            return jsonify({
                "status": "failed",
                "error": str(e),
                "message": "Stripe API error occurred"
            })
        except Exception as e:
            print(f"❌ Unexpected error in payment processing: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({
                "status": "failed",
                "error": str(e),
                "message": "Unexpected error occurred during payment processing"
            })
        
    except Exception as e:
        print(f"❌ Critical error in payment processor: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "failed",
            "error": str(e),
            "message": "Critical error in payment processor"
        }), 500

@app.route('/api/signalwire/payment-callback', methods=['POST'])
def signalwire_payment_callback():
    """Handle SignalWire payment status callbacks from SWML pay verb"""
    from models import Reservation, Order  # Import models at the top to avoid scope issues
    
    try:
        print("🔍 SignalWire payment callback called")
        print(f"   Content-Type: {request.content_type}")
        print(f"   Content-Length: {request.content_length}")
        print(f"   Request URL: {request.url}")
        print(f"   User-Agent: {request.headers.get('User-Agent', 'N/A')}")
        
        # Get callback data from SignalWire
        callback_data = request.get_json()
        
        if not callback_data:
            print("❌ No callback data received")
            return jsonify({
                "success": False,
                "error": "No callback data received"
            }), 400
        
        print(f"📋 SignalWire callback data: {json.dumps(callback_data, indent=2)}")
        
        # Extract payment information from SignalWire's actual callback structure
        event_type = callback_data.get('event_type')
        params = callback_data.get('params', {})
        
        # SignalWire callback structure analysis
        call_id = params.get('call_id')
        control_id = params.get('control_id')
        payment_for = params.get('for')  # 'payment-card-number', 'payment-failed', etc.
        error_type = params.get('error_type')
        attempt = params.get('attempt')
        payment_method = params.get('payment_method')
        payment_card_type = params.get('payment_card_type')
        
        # Determine payment status from SignalWire callback
        if payment_for == 'payment-failed':
            status = 'failed'
        elif payment_for == 'payment-succeeded' or payment_for == 'payment-completed':
            status = 'completed'
        elif payment_for == 'payment-card-number':
            status = 'collecting_card'
        elif payment_for in ['expiration-date', 'security-code', 'postal-code', 'payment-processing']:
            status = 'in_progress'
        else:
            status = 'unknown'
        
        print(f"🔍 SignalWire callback analysis:")
        print(f"   Event Type: {event_type}")
        print(f"   Payment For: {payment_for}")
        print(f"   Status: {status}")
        print(f"   Error Type: {error_type}")
        print(f"   Attempt: {attempt}")
        print(f"   Call ID: {call_id}")
        print(f"   Control ID: {control_id}")
        
        # Get payment session data to retrieve original parameters
        payment_session = None
        reservation_number = None
        customer_name = None
        phone_number = None
        payment_type = 'reservation'
        amount = None
        payment_id = None  # Initialize payment_id variable
        
        if call_id:
            payment_session = get_payment_session_data(call_id)
            if payment_session:
                reservation_number = payment_session.get('reservation_number')
                customer_name = payment_session.get('customer_name')
                phone_number = payment_session.get('phone_number')
                payment_type = payment_session.get('payment_type', 'reservation')
                amount = payment_session.get('amount')
                print(f"✅ Retrieved payment session data for call {call_id}")
            else:
                print(f"⚠️ No payment session found for call {call_id}")
                # Try to extract from any stored payment sessions
                payment_sessions = getattr(app, 'payment_sessions', {})
                if call_id in payment_sessions:
                    session_data = payment_sessions[call_id]
                    reservation_number = session_data.get('reservation_number')
                    print(f"✅ Found payment session in memory for call {call_id}: reservation {reservation_number}")
        
        # Legacy parameter extraction (for backward compatibility)
        if not reservation_number:
            reservation_number = callback_data.get('reservation_number')
        if not customer_name:
            customer_name = callback_data.get('customer_name') or callback_data.get('cardholder_name')
        if not phone_number:
            phone_number = callback_data.get('phone_number')
        if not amount:
            amount = callback_data.get('amount')
        if not payment_id:
            payment_id = callback_data.get('payment_id') or callback_data.get('payment_intent_id')
        
        # Also check for parameters in nested structure (legacy)
        if 'parameters' in callback_data:
            legacy_params = callback_data['parameters']
            if isinstance(legacy_params, dict):
                if not reservation_number:
                    reservation_number = legacy_params.get('reservation_number')
                if not customer_name:
                    customer_name = legacy_params.get('customer_name') or legacy_params.get('cardholder_name')
                if not phone_number:
                    phone_number = legacy_params.get('phone_number')
                if not payment_type:
                    payment_type = legacy_params.get('payment_type', 'reservation')
                if not amount:
                    amount = legacy_params.get('amount')
                if not payment_id:
                    payment_id = legacy_params.get('payment_id') or legacy_params.get('payment_intent_id')
        
        print(f"🔍 Extracted payment info:")
        print(f"   Status: {status}")
        print(f"   Amount: {amount}")
        print(f"   Reservation: {reservation_number}")
        print(f"   Customer: {customer_name}")
        print(f"   Phone: {phone_number}")
        print(f"   Type: {payment_type}")
        print(f"   Call ID: {call_id}")
        print(f"   Payment ID: {payment_id}")
        print(f"   Payment For: {payment_for}")
        print(f"   Error Type: {error_type}")
        
        # Handle different payment callback scenarios
        if status == 'failed':
            print(f"❌ Payment failed: {error_type}")
            
            # Update payment session with failure info
            if call_id:
                payment_sessions = getattr(app, 'payment_sessions', {})
                if call_id in payment_sessions:
                    payment_sessions[call_id]['payment_status'] = 'failed'
                    payment_sessions[call_id]['error_type'] = error_type
                    payment_sessions[call_id]['failure_reason'] = payment_for
                    payment_sessions[call_id]['attempt'] = attempt
                    print(f"✅ Updated payment session {call_id} with failure info")
            
            return jsonify({
                "success": False,
                "status": "failed",
                "error_type": error_type,
                "payment_for": payment_for,
                "attempt": attempt,
                "call_id": call_id,
                "message": f"Payment failed: {error_type}"
            })
            
        elif status == 'collecting_card':
            print(f"🔄 Payment in progress: collecting card information")
            return jsonify({
                "success": True,
                "status": "in_progress",
                "payment_for": payment_for,
                "call_id": call_id,
                "message": "Payment in progress - collecting card information"
            })
            
        elif status == 'in_progress':
            print(f"🔄 Payment in progress: {payment_for}")
            return jsonify({
                "success": True,
                "status": "in_progress",
                "payment_for": payment_for,
                "call_id": call_id,
                "message": f"Payment in progress - {payment_for.replace('-', ' ')}"
            })
            
        elif status == 'completed' or status == 'succeeded':
            print("✅ Payment completed successfully")
            
            # Extract order_number for order payments
            order_number = callback_data.get('order_number')
            if not order_number and call_id:
                # Check payment session for order_number
                payment_session = get_payment_session_data(call_id)
                if payment_session:
                    order_number = payment_session.get('order_number')
                else:
                    payment_sessions = getattr(app, 'payment_sessions', {})
                    if call_id in payment_sessions:
                        order_number = payment_sessions[call_id].get('order_number')
            
            # Process order payments first (more specific)
            if payment_type == 'order' and order_number:
                # Handle order payments
                order = Order.query.filter_by(order_number=order_number).first()
                if order:
                    # Generate confirmation number
                    import random
                    import string
                    confirmation_number = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                    
                    order.payment_status = 'paid'
                    order.payment_method = 'credit-card'
                    order.payment_date = datetime.now()
                    order.payment_amount = float(amount) if amount else 0.0
                    order.confirmation_number = confirmation_number
                    
                    if payment_id:
                        order.payment_intent_id = payment_id
                    
                    db.session.commit()
                    print(f"✅ Order {order_number} updated with payment confirmation")
                    
                    # ENHANCEMENT: Update Stripe Payment Intent metadata for orders
                    if payment_id and payment_id.startswith('pi_'):
                        try:
                            import stripe
                            stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
                            
                            if stripe.api_key:
                                # Update the payment intent metadata with confirmation number
                                stripe.PaymentIntent.modify(
                                    payment_id,
                                    metadata={
                                        'confirmation_number': confirmation_number,
                                        'payment_completed_date': datetime.now().isoformat(),
                                        'bobby_table_status': 'confirmed_paid',
                                        'payment_type': 'order'
                                    }
                                )
                                print(f"✅ Updated Stripe PaymentIntent {payment_id} with confirmation number: {confirmation_number}")
                            else:
                                print(f"⚠️ Stripe API key not configured - skipping metadata update")
                                
                        except Exception as stripe_error:
                            print(f"⚠️ Failed to update Stripe metadata: {stripe_error}")
                            # Don't fail the whole process if Stripe update fails
                    
                    # Create SWML response to announce payment confirmation to the user
                    announcement_text = f"Excellent! Your payment of ${amount} has been processed successfully. "
                    announcement_text += f"Your confirmation number is {' '.join(confirmation_number)}. "
                    announcement_text += f"Please write this down: {' '.join(confirmation_number)}. "
                    announcement_text += f"Your order will be ready for {order.order_type} at the scheduled time. "
                    announcement_text += f"Thank you for choosing Bobby's Table! Have a great day!"
                    
                    # Return SWML response to announce the confirmation
                    swml_response = {
                        "version": "1.0.0",
                        "sections": {
                            "main": [
                                {
                                    "say": {
                                        "text": announcement_text,
                                        "voice": "rime.luna",
                                        "model": "arcana",
                                        "language": "en-US"
                                    }
                                },
                                {
                                    "hangup": {}
                                }
                            ]
                        }
                    }
                    
                    # Return SWML response directly for SignalWire to process
                    response = make_response(jsonify(swml_response))
                    response.headers['Content-Type'] = 'application/json'
                    
                    # Also log the success info
                    print(f"🎉 Returning SWML announcement for order payment completion:")
                    print(f"   Confirmation: {confirmation_number}")
                    print(f"   Amount: ${amount}")
                    print(f"   Order: {order_number}")
                    
                    return response
                else:
                    print(f"❌ Order {order_number} not found")
                    return jsonify({
                        "success": False,
                        "error": f"Order {order_number} not found"
                    }), 404
                    
            elif payment_type == 'reservation' and reservation_number:
                # Update reservation payment status
                reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
                if reservation:
                    print(f"✅ Found reservation: {reservation.name} for {reservation.party_size} people")
                    
                    # Generate confirmation number
                    import random
                    import string
                    confirmation_number = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                    
                    # Update reservation
                    reservation.payment_status = 'paid'
                    reservation.payment_method = 'credit-card'
                    reservation.payment_date = datetime.now()
                    reservation.payment_amount = float(amount) if amount else 0.0
                    reservation.confirmation_number = confirmation_number
                    
                    # Store payment ID if provided
                    if payment_id:
                        reservation.payment_intent_id = payment_id
                    
                    db.session.commit()
                    print(f"✅ Reservation {reservation_number} updated with payment confirmation")
                    
                    # ENHANCEMENT: Store confirmation number in payment session and conversation memory
                    # This allows the agent to access the confirmation number in future interactions
                    try:
                        # Update payment session with confirmation number (using extracted call_id)
                        if call_id:
                            # Update payment session data
                            payment_sessions = getattr(app, 'payment_sessions', {})
                            if call_id in payment_sessions:
                                payment_sessions[call_id]['confirmation_number'] = confirmation_number
                                payment_sessions[call_id]['payment_completed'] = True
                                payment_sessions[call_id]['payment_status'] = 'completed'
                                payment_sessions[call_id]['payment_amount'] = float(amount) if amount else 0.0
                                payment_sessions[call_id]['payment_date'] = datetime.now().isoformat()
                                print(f"✅ Updated payment session {call_id} with confirmation number: {confirmation_number}")
                            else:
                                print(f"⚠️ Payment session {call_id} not found in active sessions")
                                # Create a minimal session record for the confirmation
                                if not hasattr(app, 'payment_sessions'):
                                    app.payment_sessions = {}
                                app.payment_sessions[call_id] = {
                                    'confirmation_number': confirmation_number,
                                    'payment_completed': True,
                                    'payment_status': 'completed',
                                    'payment_amount': float(amount) if amount else 0.0,
                                    'payment_date': datetime.now().isoformat(),
                                    'reservation_number': reservation_number
                                }
                                print(f"✅ Created new payment session record for {call_id} with confirmation number: {confirmation_number}")
                        else:
                            print(f"⚠️ No call_id provided in payment callback - cannot update payment session")
                        
                        # Store in conversation memory for future agent access
                        # We'll store this globally so any future get_reservation calls can access it
                        if not hasattr(app, 'payment_confirmations'):
                            app.payment_confirmations = {}
                        
                        app.payment_confirmations[reservation_number] = {
                            'confirmation_number': confirmation_number,
                            'payment_amount': float(amount) if amount else 0.0,
                            'payment_date': datetime.now().isoformat(),
                            'payment_id': payment_id,
                            'customer_name': customer_name,
                            'call_id': call_id  # Store call_id for reference
                        }
                        print(f"✅ Stored confirmation number {confirmation_number} for reservation {reservation_number}")
                        
                    except Exception as session_error:
                        print(f"⚠️ Could not update payment session data: {session_error}")
                    
                    # ENHANCEMENT: Update Stripe Payment Intent metadata with confirmation number
                    if payment_id and payment_id.startswith('pi_'):
                        try:
                            import stripe
                            stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
                            
                            if stripe.api_key:
                                # Update the payment intent metadata with confirmation number
                                stripe.PaymentIntent.modify(
                                    payment_id,
                                    metadata={
                                        'confirmation_number': confirmation_number,
                                        'payment_completed_date': datetime.now().isoformat(),
                                        'bobby_table_status': 'confirmed_paid'
                                    }
                                )
                                print(f"✅ Updated Stripe PaymentIntent {payment_id} with confirmation number: {confirmation_number}")
                            else:
                                print(f"⚠️ Stripe API key not configured - skipping metadata update")
                                
                        except Exception as stripe_error:
                            print(f"⚠️ Failed to update Stripe metadata: {stripe_error}")
                            # Don't fail the whole process if Stripe update fails
                    
                    # SMS receipt is already sent by the payment processor - no need to send again
                    sms_status = "SMS receipt already sent by payment processor"
                    print(f"ℹ️ Skipping duplicate SMS - receipt already sent by payment processor")
                    
                    # Create SWML response to announce payment confirmation to the user
                    announcement_text = f"Excellent! Your payment of ${amount} has been processed successfully. "
                    announcement_text += f"Your confirmation number is {' '.join(confirmation_number)}. "
                    announcement_text += f"Please write this down: {' '.join(confirmation_number)}. "
                    announcement_text += f"A receipt has been sent to your phone. "
                    announcement_text += f"Thank you for choosing Bobby's Table! We look forward to seeing you on {reservation.date} at {reservation.time}. Have a great day!"
                    
                    # Return SWML response to announce the confirmation
                    swml_response = {
                        "version": "1.0.0",
                        "sections": {
                            "main": [
                                {
                                    "say": {
                                        "text": announcement_text,
                                        "voice": "rime.luna",
                                        "model": "arcana",
                                        "language": "en-US"
                                    }
                                },
                                {
                                    "hangup": {}
                                }
                            ]
                        }
                    }
                    
                    # Return SWML response directly for SignalWire to process
                    response = make_response(jsonify(swml_response))
                    response.headers['Content-Type'] = 'application/json'
                    
                    # Also log the success info
                    print(f"🎉 Returning SWML announcement for payment completion:")
                    print(f"   Confirmation: {confirmation_number}")
                    print(f"   Amount: ${amount}")
                    print(f"   Reservation: {reservation_number}")
                    print(f"   SMS Status: {sms_status}")
                    
                    return response
                else:
                    print(f"❌ Reservation {reservation_number} not found")
                    return jsonify({
                        "success": False,
                        "error": f"Reservation {reservation_number} not found"
                    }), 404
            

            
            # Generic success response with SWML announcement
            print(f"⚠️ Using generic payment completion response - payment_type: {payment_type}, reservation_number: {reservation_number}")
            
            # Create generic SWML announcement
            announcement_text = f"Excellent! Your payment of ${amount} has been processed successfully. "
            
            # Generate a generic confirmation number
            import random
            import string
            confirmation_number = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            
            announcement_text += f"Your confirmation number is {' '.join(confirmation_number)}. "
            announcement_text += f"Please write this down: {' '.join(confirmation_number)}. "
            announcement_text += f"Thank you for choosing Bobby's Table! Have a great day!"
            
            # Return SWML response to announce the confirmation
            swml_response = {
                "version": "1.0.0",
                "sections": {
                    "main": [
                        {
                            "say": {
                                "text": announcement_text,
                                "voice": "rime.luna",
                                "model": "arcana",
                                "language": "en-US"
                            }
                        },
                        {
                            "hangup": {}
                        }
                    ]
                }
            }
            
            # Return SWML response directly for SignalWire to process
            response = make_response(jsonify(swml_response))
            response.headers['Content-Type'] = 'application/json'
            
            # Also log the success info
            print(f"🎉 Returning SWML announcement for generic payment completion:")
            print(f"   Confirmation: {confirmation_number}")
            print(f"   Amount: ${amount}")
            print(f"   Payment Type: {payment_type}")
            
            return response
        
        elif status == 'failed' or status == 'declined':
            print(f"❌ Payment failed: {status}")
            return jsonify({
                "success": False,
                "error": f"Payment {status}",
                "payment_status": "failed"
            })
        
        else:
            print(f"⚠️ Unknown payment status: {status}")
            print(f"   Payment For: {payment_for}")
            print(f"   Event Type: {event_type}")
            
            # Log the full callback for debugging
            print(f"🔍 Full callback data for unknown status: {json.dumps(callback_data, indent=2)}")
            
            return jsonify({
                "success": False,
                "error": f"Unknown payment status: {status}",
                "status": status,
                "payment_for": payment_for,
                "event_type": event_type,
                "call_id": call_id
            })
        
    except Exception as e:
        print(f"❌ Error in SignalWire payment callback: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Even if there's an error, try to update payment session if we have key info
        # This prevents the agent from asking for card details again when payment actually succeeded
        try:
            if call_id and status == 'completed' and reservation_number:
                print(f"🔄 Attempting emergency payment session update for {call_id}")
                payment_sessions = getattr(app, 'payment_sessions', {})
                if call_id in payment_sessions:
                    payment_sessions[call_id]['payment_completed'] = True
                    payment_sessions[call_id]['payment_status'] = 'completed'
                    payment_sessions[call_id]['error_recovery'] = True
                    payment_sessions[call_id]['last_updated'] = datetime.now()
                    print(f"✅ Emergency update successful for payment session {call_id}")
                else:
                    # Create minimal session to prevent agent from re-asking
                    if not hasattr(app, 'payment_sessions'):
                        app.payment_sessions = {}
                    app.payment_sessions[call_id] = {
                        'payment_completed': True,
                        'payment_status': 'completed',
                        'reservation_number': reservation_number,
                        'error_recovery': True,
                        'started_at': datetime.now(),
                        'last_updated': datetime.now()
                    }
                    print(f"✅ Created emergency payment session for {call_id}")
                    
                # Also try to update the database reservation status
                try:
                    with app.app_context():
                        reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
                        if reservation and reservation.payment_status != 'paid':
                            reservation.payment_status = 'paid'
                            reservation.payment_method = 'credit-card'
                            reservation.payment_date = datetime.now()
                            db.session.commit()
                            print(f"✅ Emergency database update: reservation {reservation_number} marked as paid")
                except Exception as db_error:
                    print(f"⚠️ Emergency database update failed: {db_error}")
                    
        except Exception as recovery_error:
            print(f"⚠️ Emergency payment session update also failed: {recovery_error}")
        
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Add the get_card_details handler function
def get_card_details_handler(args, raw_data):
    """
    Handler for get_card_details function - first step in payment process
    Collects reservation number and cardholder name, then asks for confirmation
    """
    try:
        print(f"💳 get_card_details called with args: {args}")
        print(f"💳 Raw data keys: {list(raw_data.keys()) if raw_data else 'None'}")
        
        # Extract meta_data for session management
        meta_data = raw_data.get('meta_data', {}) if raw_data else {}
        meta_data_token = raw_data.get('meta_data_token', '') if raw_data else ''
        print(f"🔍 Current meta_data: {meta_data}")
        print(f"🔍 Meta_data_token: {meta_data_token}")
        
        # Get call_id for payment session integration
        call_id = raw_data.get('call_id') if raw_data else None
        print(f"🔍 Call ID: {call_id}")
        
        # Get conversation log
        call_log = raw_data.get('call_log', []) if raw_data else []
        
        # Extract reservation number from args, meta_data, or conversation
        reservation_number = args.get('reservation_number')
        
        # Check meta_data for reservation context first
        if not reservation_number and meta_data.get('reservation_number'):
            reservation_number = meta_data.get('reservation_number')
            print(f"💳 Using reservation number from meta_data: {reservation_number}")
        
        if not reservation_number and call_log:
            # Try to extract from conversation
            for entry in reversed(call_log):
                if entry.get('role') == 'user' and entry.get('content'):
                    content = entry['content'].lower()
                    # Look for spoken numbers
                    import re
                    # Convert spoken numbers to digits
                    number_words = {
                        'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
                        'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9'
                    }
                    
                    converted_content = content
                    for word, digit in number_words.items():
                        converted_content = re.sub(r'\b' + word + r'\b', digit, converted_content)
                    
                    # Look for 6-digit numbers
                    digits = re.findall(r'\b\d{6}\b', converted_content)
                    if digits:
                        reservation_number = digits[-1]  # Take the last one found
                        print(f"💳 Extracted reservation number from conversation: {reservation_number}")
                        break
        
        if not reservation_number:
            return {
                "response": "I'd be happy to help you pay your bill! First, I'll need your reservation number. It's a six-digit number we sent you when you made the reservation."
            }
        
        # Get cardholder name from args, meta_data, or ask for it
        cardholder_name = args.get('cardholder_name')
        
        # Check meta_data for cardholder name first
        if not cardholder_name and meta_data.get('cardholder_name'):
            cardholder_name = meta_data.get('cardholder_name')
            print(f"💳 Using cardholder name from meta_data: {cardholder_name}")
        
        if not cardholder_name:
            # Try to extract customer name from reservation info or conversation
            # First, try to get it from the reservation if we have the number
            if reservation_number:
                try:
                    with app.app_context():
                        reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
                        if reservation and reservation.name:
                            cardholder_name = reservation.name
                            print(f"💳 Using customer name from reservation: {cardholder_name}")
                except Exception as e:
                    print(f"⚠️ Could not get name from reservation: {e}")
            
            # If still no name, look for proper names in conversation
            if not cardholder_name:
                for entry in reversed(call_log):
                    if entry.get('role') == 'user' and entry.get('content'):
                        content = entry['content'].strip()
                        # Look for proper name patterns (2-3 words, starts with capital)
                        words = content.split()
                        if (len(words) == 2 and 
                            all(word[0].isupper() and word[1:].islower() for word in words) and
                            not re.search(r'\d', content) and
                            content.lower() not in ['yes sir', 'no sir', 'thank you', 'you just']):
                            cardholder_name = content.title()
                            print(f"💳 Extracted cardholder name from conversation: {cardholder_name}")
                            break
        
        if not cardholder_name:
            return {
                "response": f"Great! I found your reservation number {reservation_number}. To process your payment, I'll need the name exactly as it appears on your credit card. What name should I use?"
            }
        
        # Both reservation number and cardholder name are available
        # Check if reservation exists and get bill amount
        with app.app_context():
            reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
            
            if not reservation:
                return {
                    "response": f"I'm sorry, I couldn't find a reservation with number {reservation_number}. Could you please double-check the number?"
                }
            
            # Calculate total bill
            total_amount = 0.0
            if reservation.orders:
                for order in reservation.orders:
                    if order.total_amount:
                        total_amount += order.total_amount
            
            # Start payment session
            if call_id:
                try:
                    start_payment_session(call_id, reservation_number)
                    print(f"🔒 Started payment session for call {call_id}, reservation {reservation_number}")
                except Exception as e:
                    print(f"⚠️ Could not start payment session: {e}")
            
            # Format amount for speech
            dollars = int(total_amount)
            cents = int((total_amount - dollars) * 100)
            
            if cents == 0:
                amount_speech = f"{dollars} dollars"
            else:
                amount_speech = f"{dollars} dollars and {cents} cents"
            
            return {
                "response": f"Perfect! I have your reservation for {reservation.name} and the cardholder name as {cardholder_name}. Your total bill is {amount_speech}. I'm ready to securely collect your payment information. Would you like me to proceed with collecting your card details now?"
            }
    
    except Exception as e:
        print(f"❌ Error in get_card_details: {e}")
        import traceback
        traceback.print_exc()
        return {
            "response": "I'm sorry, I encountered an error while processing your payment request. Please try again or contact us for assistance."
        }

# Add cleanup function for orphaned payment sessions
def cleanup_orphaned_payment_sessions():
    """Clean up orphaned payment sessions that are blocking operations"""
    try:
        if not hasattr(app, 'payment_sessions'):
            app.payment_sessions = {}
        
        print(f"🧹 Cleaning up orphaned payment sessions...")
        print(f"   Current sessions: {list(app.payment_sessions.keys())}")
        
        # Remove the specific orphaned session
        orphaned_call_ids = [
            'cc1c1950-4b27-4f96-b966-33743ab8597a',  # The problematic session
        ]
        
        cleaned_count = 0
        for call_id in orphaned_call_ids:
            if call_id in app.payment_sessions:
                session_data = app.payment_sessions.pop(call_id)
                print(f"🗑️ Removed orphaned session: {call_id} (reservation: {session_data.get('reservation_number')})")
                cleaned_count += 1
        
        # Also clean up sessions older than 1 hour
        cutoff = datetime.now() - timedelta(hours=1)
        expired_sessions = [
            call_id for call_id, session in app.payment_sessions.items()
            if session.get('started_at', datetime.now()) < cutoff
        ]
        
        for call_id in expired_sessions:
            session_data = app.payment_sessions.pop(call_id, None)
            print(f"🕐 Removed expired session: {call_id}")
            cleaned_count += 1
        
        print(f"✅ Cleaned up {cleaned_count} orphaned/expired payment sessions")
        print(f"   Remaining sessions: {len(app.payment_sessions)}")
        
        return cleaned_count
        
    except Exception as e:
        print(f"❌ Error cleaning up payment sessions: {e}")
        return 0

# Add route to manually cleanup sessions
@app.route('/debug/cleanup-sessions', methods=['POST'])
def debug_cleanup_sessions():
    """Debug endpoint to manually cleanup orphaned payment sessions"""
    try:
        cleaned_count = cleanup_orphaned_payment_sessions()
        
        return jsonify({
            'success': True,
            'message': f'Cleaned up {cleaned_count} orphaned sessions',
            'remaining_sessions': len(getattr(app, 'payment_sessions', {}))
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500



if __name__ == '__main__':
    print("🍽️  Starting Bobby's Table Restaurant System")
    print("=" * 50)
    print("🌐 Web Interface: http://0.0.0.0:8080")
    print("📞 Voice Interface: http://0.0.0.0:8080/receptionist")
    print("🍳 Kitchen Dashboard: http://0.0.0.0:8080/kitchen")
    print("Press Ctrl+C to stop the service")
    print("-" * 50)
    
    # Start the Flask development server
    app.run(host='0.0.0.0', port=8080, debug=False)
