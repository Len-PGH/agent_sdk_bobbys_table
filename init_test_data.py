from app import app, db
from models import Reservation, Table, MenuItem, Order, OrderItem
from datetime import datetime, timedelta
import random

def generate_order_number():
    """Generate a unique 6-digit order number"""
    while True:
        # Generate a 6-digit number (100000 to 999999)
        number = str(random.randint(100000, 999999))
        
        # Check if this number already exists
        existing = Order.query.filter_by(order_number=number).first()
        if not existing:
            return number

def init_test_data():
    """Initialize the database with test data."""
    with app.app_context():
        # Clear existing data
        OrderItem.query.delete()
        Order.query.delete()
        Reservation.query.delete()
        Table.query.delete()
        MenuItem.query.delete()
        
        # Add test tables
        tables = [
            Table(table_number=1, capacity=2, status='available', location='Window'),
            Table(table_number=2, capacity=4, status='available', location='Center'),
            Table(table_number=3, capacity=6, status='available', location='Back'),
            Table(table_number=4, capacity=2, status='available', location='Window'),
            Table(table_number=5, capacity=4, status='available', location='Center'),
            Table(table_number=6, capacity=8, status='available', location='Private Room')
        ]
        db.session.add_all(tables)
        
        # Add a full, modern menu
        menu_items = [
            # Starters
            MenuItem(name='Truffle Fries', description='Crispy fries tossed in truffle oil and parmesan', price=8.00, category='Starter'),
            MenuItem(name='Buffalo Wings', description='Crispy chicken wings tossed in spicy buffalo sauce, served with celery and blue cheese', price=12.99, category='Starter'),
            MenuItem(name='Ahi Tuna Tartare', description='Fresh ahi tuna, avocado, sesame, wonton crisps', price=14.00, category='Starter'),
            MenuItem(name='Charred Octopus', description='Grilled octopus, lemon, smoked paprika aioli', price=15.00, category='Starter'),
            MenuItem(name='Heirloom Tomato Salad', description='Heirloom tomatoes, burrata, basil, olive oil', price=12.00, category='Starter'),
            # Mains
            MenuItem(name='Sous Vide Ribeye', description='12oz ribeye, garlic mash, seasonal veg', price=34.00, category='Main'),
            MenuItem(name='Miso Glazed Salmon', description='Atlantic salmon, miso glaze, jasmine rice', price=28.00, category='Main'),
            MenuItem(name='Vegan Buddha Bowl', description='Quinoa, roasted veg, tahini dressing', price=19.00, category='Main'),
            MenuItem(name='Lobster Tagliatelle', description='Fresh pasta, lobster, tomato cream sauce', price=32.00, category='Main'),
            # Desserts
            MenuItem(name='Molten Chocolate Cake', description='Warm chocolate cake, vanilla gelato', price=10.00, category='Dessert'),
            MenuItem(name='Lemon Tart', description='Tangy lemon curd, almond crust, meringue', price=9.00, category='Dessert'),
            MenuItem(name='Affogato', description='Espresso poured over vanilla gelato', price=7.00, category='Dessert'),
            # Cocktails
            MenuItem(name='Cucumber Gimlet', description='Gin, cucumber, lime, simple syrup', price=13.00, category='Cocktail'),
            MenuItem(name='Spicy Paloma', description='Tequila, grapefruit, lime, chili salt', price=13.00, category='Cocktail'),
            MenuItem(name='Smoked Old Fashioned', description='Bourbon, bitters, smoked orange', price=15.00, category='Cocktail'),
            # Wine
            MenuItem(name='Chardonnay', description='Glass of premium Chardonnay', price=11.00, category='Wine'),
            MenuItem(name='Pinot Noir', description='Glass of premium Pinot Noir', price=12.00, category='Wine'),
            MenuItem(name='Prosecco', description='Glass of sparkling Prosecco', price=10.00, category='Wine'),
            # Non-Alcoholic
            MenuItem(name='Craft Lemonade', description='House-made lemonade, fresh herbs', price=5.00, category='Non-Alcoholic'),
            MenuItem(name='Cold Brew Coffee', description='Iced cold brew, oat milk available', price=5.00, category='Non-Alcoholic'),
            MenuItem(name='Sparkling Water', description='San Pellegrino, 500ml', price=4.00, category='Non-Alcoholic'),
            MenuItem(name='Herbal Tea', description='Selection of premium herbal teas', price=4.00, category='Non-Alcoholic'),
        ]
        db.session.add_all(menu_items)
        
        # Add test reservations with 6-digit reservation numbers and comprehensive data
        today = datetime.now().date()
        reservations = [
            Reservation(
                reservation_number='123456', 
                name='John Smith', 
                party_size=4, 
                date='2025-06-15', 
                time='19:00', 
                phone_number='+1234567890', 
                status='confirmed',
                special_requests='Anniversary dinner, window table preferred',
                payment_status='paid',
                payment_amount=91.00
            ),
            Reservation(
                reservation_number='789012', 
                name='Jane Smith', 
                party_size=2, 
                date=str(today), 
                time='20:00', 
                phone_number='+1987654321', 
                status='confirmed',
                special_requests='Vegetarian options needed',
                payment_status='partial',
                payment_amount=42.00
            ),
            Reservation(
                reservation_number='345678', 
                name='Bob Wilson', 
                party_size=6, 
                date=str(today + timedelta(days=1)), 
                time='18:30', 
                phone_number='+1122334455', 
                status='pending',
                special_requests='Business dinner, quiet table please',
                payment_status='unpaid'
            ),
            Reservation(
                reservation_number='901234', 
                name='Alice Johnson', 
                party_size=3, 
                date=str(today + timedelta(days=2)), 
                time='17:30', 
                phone_number='+1555666777', 
                status='confirmed',
                special_requests='Birthday celebration, high chair needed',
                payment_status='unpaid'
            ),
            Reservation(
                reservation_number='567890', 
                name='Rob Zombie', 
                party_size=2, 
                date=str(today + timedelta(days=3)), 
                time='20:30', 
                phone_number='+1999888777', 
                status='confirmed',
                special_requests='Gluten-free menu required',
                payment_status='unpaid'
            ),
            Reservation(
                reservation_number='246810', 
                name='Maria Garcia', 
                party_size=8, 
                date=str(today + timedelta(days=4)), 
                time='19:30', 
                phone_number='+1444555666', 
                status='confirmed',
                special_requests='Large family gathering, private room if available',
                payment_status='unpaid'
            )
        ]
        db.session.add_all(reservations)
        
        # Add comprehensive test orders with proper person names and complete data
        db.session.flush()  # Ensure reservations have IDs
        
        # Orders for John Smith's reservation (reservation_id=1, party_size=4) - All paid since completed
        john_orders = [
            Order(order_number=generate_order_number(), reservation_id=1, table_id=1, person_name='John Smith', status='completed', total_amount=34.00, payment_status='paid', payment_amount=34.00),
            Order(order_number=generate_order_number(), reservation_id=1, table_id=1, person_name='Sarah Smith', status='completed', total_amount=28.00, payment_status='paid', payment_amount=28.00),
            Order(order_number=generate_order_number(), reservation_id=1, table_id=1, person_name='Mike Smith', status='completed', total_amount=19.00, payment_status='paid', payment_amount=19.00),
            Order(order_number=generate_order_number(), reservation_id=1, table_id=1, person_name='Emma Smith', status='completed', total_amount=10.00, payment_status='paid', payment_amount=10.00)
        ]
        db.session.add_all(john_orders)
        db.session.flush()
        
        # Order items for John Smith's family
        john_order_items = [
            # John's order - Sous Vide Ribeye
            OrderItem(order_id=john_orders[0].id, menu_item_id=5, quantity=1, price_at_time=34.00),
            # Sarah's order - Miso Glazed Salmon
            OrderItem(order_id=john_orders[1].id, menu_item_id=6, quantity=1, price_at_time=28.00),
            # Mike's order - Vegan Buddha Bowl
            OrderItem(order_id=john_orders[2].id, menu_item_id=7, quantity=1, price_at_time=19.00),
            # Emma's order - Molten Chocolate Cake
            OrderItem(order_id=john_orders[3].id, menu_item_id=9, quantity=1, price_at_time=10.00)
        ]
        db.session.add_all(john_order_items)
        
        # Orders for Jane Smith's reservation (reservation_id=2, party_size=2) - Mixed payment status
        jane_orders = [
            Order(order_number=generate_order_number(), reservation_id=2, table_id=2, person_name='Jane Smith', status='in_progress', total_amount=42.00, payment_status='paid', payment_amount=42.00),
            Order(order_number=generate_order_number(), reservation_id=2, table_id=2, person_name='David Wilson', status='in_progress', total_amount=47.00, payment_status='unpaid')
        ]
        db.session.add_all(jane_orders)
        db.session.flush()
        
        # Order items for Jane Smith's party
        jane_order_items = [
            # Jane's order - Ahi Tuna Tartare + Lobster Tagliatelle
            OrderItem(order_id=jane_orders[0].id, menu_item_id=2, quantity=1, price_at_time=14.00),
            OrderItem(order_id=jane_orders[0].id, menu_item_id=8, quantity=1, price_at_time=32.00),
            # David's order - Charred Octopus + Sous Vide Ribeye
            OrderItem(order_id=jane_orders[1].id, menu_item_id=3, quantity=1, price_at_time=15.00),
            OrderItem(order_id=jane_orders[1].id, menu_item_id=5, quantity=1, price_at_time=34.00)
        ]
        db.session.add_all(jane_order_items)
        
        # Add some standalone orders (pickup/delivery without reservations) - Various payment statuses
        standalone_orders = [
            Order(
                order_number=generate_order_number(),
                person_name='Lisa Chen',
                status='pending',
                total_amount=45.00,
                target_date=str(today),
                target_time='19:30',
                order_type='pickup',
                customer_phone='+15551234567',
                special_instructions='Extra spicy',
                payment_status='unpaid'
            ),
            Order(
                order_number=generate_order_number(),
                person_name='Mark Rodriguez',
                status='preparing',
                total_amount=67.00,
                target_date=str(today),
                target_time='20:00',
                order_type='delivery',
                customer_phone='+15559876543',
                customer_address='123 Main St, Anytown, ST 12345',
                special_instructions='Ring doorbell twice',
                payment_status='paid',
                payment_amount=67.00
            )
        ]
        db.session.add_all(standalone_orders)
        db.session.flush()
        
        # Order items for standalone orders
        standalone_order_items = [
            # Lisa's pickup order
            OrderItem(order_id=standalone_orders[0].id, menu_item_id=1, quantity=1, price_at_time=8.00),  # Truffle Fries
            OrderItem(order_id=standalone_orders[0].id, menu_item_id=6, quantity=1, price_at_time=28.00), # Miso Glazed Salmon
            OrderItem(order_id=standalone_orders[0].id, menu_item_id=11, quantity=1, price_at_time=7.00),  # Affogato
            # Mark's delivery order
            OrderItem(order_id=standalone_orders[1].id, menu_item_id=4, quantity=1, price_at_time=12.00), # Heirloom Tomato Salad
            OrderItem(order_id=standalone_orders[1].id, menu_item_id=8, quantity=1, price_at_time=32.00), # Lobster Tagliatelle
            OrderItem(order_id=standalone_orders[1].id, menu_item_id=12, quantity=1, price_at_time=13.00), # Cucumber Gimlet
            OrderItem(order_id=standalone_orders[1].id, menu_item_id=9, quantity=1, price_at_time=10.00)  # Molten Chocolate Cake
        ]
        db.session.add_all(standalone_order_items)
        
        db.session.commit()
        print("Test data initialized successfully!")

def populate_menu_items():
    menu_items = [
        # BREAKFAST (Available until 11 AM)
        {'name': 'Classic Pancakes', 'description': 'Three fluffy buttermilk pancakes with maple syrup and butter', 'price': 8.99, 'category': 'breakfast'},
        {'name': 'Blueberry Pancakes', 'description': 'Pancakes loaded with fresh blueberries and whipped cream', 'price': 9.99, 'category': 'breakfast'},
        {'name': 'Western Omelette', 'description': 'Three-egg omelette with ham, peppers, onions, and cheese', 'price': 10.99, 'category': 'breakfast'},
        {'name': 'Veggie Omelette', 'description': 'Three-egg omelette with mushrooms, spinach, tomatoes, and cheese', 'price': 9.99, 'category': 'breakfast'},
        {'name': 'Breakfast Burrito', 'description': 'Scrambled eggs, bacon, hash browns, and cheese wrapped in a flour tortilla', 'price': 9.49, 'category': 'breakfast'},
        {'name': 'French Toast', 'description': 'Thick-cut brioche bread with cinnamon, vanilla, and maple syrup', 'price': 8.99, 'category': 'breakfast'},
        {'name': 'Eggs Benedict', 'description': 'Poached eggs on English muffins with Canadian bacon and hollandaise', 'price': 12.99, 'category': 'breakfast'},
        {'name': 'Breakfast Platter', 'description': 'Two eggs any style, bacon or sausage, hash browns, and toast', 'price': 11.99, 'category': 'breakfast'},
        
        # APPETIZERS
        {'name': 'Buffalo Wings', 'description': 'Crispy chicken wings tossed in spicy buffalo sauce with blue cheese', 'price': 12.99, 'category': 'appetizers'},
        {'name': 'BBQ Wings', 'description': 'Chicken wings glazed with tangy BBQ sauce', 'price': 12.99, 'category': 'appetizers'},
        {'name': 'Mozzarella Sticks', 'description': 'Golden fried mozzarella with marinara dipping sauce', 'price': 8.99, 'category': 'appetizers'},
        {'name': 'Loaded Nachos', 'description': 'Tortilla chips topped with cheese, jalapeños, sour cream, and guacamole', 'price': 11.99, 'category': 'appetizers'},
        {'name': 'Spinach Artichoke Dip', 'description': 'Creamy spinach and artichoke dip served with tortilla chips', 'price': 9.99, 'category': 'appetizers'},
        {'name': 'Potato Skins', 'description': 'Crispy potato skins loaded with cheese, bacon, and green onions', 'price': 9.99, 'category': 'appetizers'},
        {'name': 'Onion Rings', 'description': 'Beer-battered onion rings served with ranch dressing', 'price': 7.99, 'category': 'appetizers'},
        {'name': 'Jalapeño Poppers', 'description': 'Jalapeños stuffed with cream cheese, wrapped in bacon', 'price': 8.99, 'category': 'appetizers'},
        {'name': 'Calamari Rings', 'description': 'Crispy fried squid rings with marinara and lemon', 'price': 10.99, 'category': 'appetizers'},
        {'name': 'Chicken Quesadilla', 'description': 'Grilled chicken and cheese in a flour tortilla with salsa and sour cream', 'price': 9.99, 'category': 'appetizers'},
        {'name': 'Loaded Fries', 'description': 'French fries topped with cheese, bacon bits, and green onions', 'price': 8.99, 'category': 'appetizers'},
        {'name': 'Pretzel Bites', 'description': 'Warm soft pretzel bites with beer cheese dipping sauce', 'price': 7.99, 'category': 'appetizers'},
        
        # MAIN COURSES
        {'name': 'Classic Cheeseburger', 'description': '8oz beef patty with American cheese, lettuce, tomato, onion, and pickles', 'price': 13.99, 'category': 'main-courses'},
        {'name': 'Bacon Cheeseburger', 'description': '8oz beef patty with bacon, cheddar cheese, lettuce, tomato, and onion', 'price': 15.99, 'category': 'main-courses'},
        {'name': 'BBQ Burger', 'description': '8oz beef patty with BBQ sauce, onion rings, and cheddar cheese', 'price': 15.99, 'category': 'main-courses'},
        {'name': 'Mushroom Swiss Burger', 'description': '8oz beef patty with sautéed mushrooms and Swiss cheese', 'price': 15.99, 'category': 'main-courses'},
        {'name': 'Ribeye Steak', 'description': '12oz ribeye steak grilled to perfection with garlic butter', 'price': 24.99, 'category': 'main-courses'},
        {'name': 'New York Strip', 'description': '10oz New York strip steak with herb butter', 'price': 22.99, 'category': 'main-courses'},
        {'name': 'Grilled Chicken Breast', 'description': 'Seasoned grilled chicken breast with lemon herb sauce', 'price': 16.99, 'category': 'main-courses'},
        {'name': 'BBQ Ribs', 'description': 'Full rack of baby back ribs with BBQ sauce and coleslaw', 'price': 19.99, 'category': 'main-courses'},
        {'name': 'Fish and Chips', 'description': 'Beer-battered cod with french fries and tartar sauce', 'price': 15.99, 'category': 'main-courses'},
        {'name': 'Grilled Salmon', 'description': 'Atlantic salmon with lemon dill sauce and seasonal vegetables', 'price': 18.99, 'category': 'main-courses'},
        {'name': 'Chicken Parmesan', 'description': 'Breaded chicken breast with marinara sauce and mozzarella over pasta', 'price': 17.99, 'category': 'main-courses'},
        {'name': 'Philly Cheesesteak', 'description': 'Sliced steak with peppers, onions, and provolone on a hoagie roll', 'price': 12.99, 'category': 'main-courses'},
        {'name': 'Club Sandwich', 'description': 'Turkey, ham, bacon, lettuce, tomato, and mayo on toasted bread', 'price': 11.99, 'category': 'main-courses'},
        {'name': 'Buffalo Chicken Wrap', 'description': 'Crispy buffalo chicken with lettuce, tomato, and ranch in a tortilla', 'price': 10.99, 'category': 'main-courses'},
        {'name': 'Caesar Salad', 'description': 'Crisp romaine lettuce with Caesar dressing, croutons, and parmesan', 'price': 9.99, 'category': 'main-courses'},
        {'name': 'Chicken Caesar Salad', 'description': 'Caesar salad topped with grilled chicken breast', 'price': 13.99, 'category': 'main-courses'},
        {'name': 'Cobb Salad', 'description': 'Mixed greens with chicken, bacon, blue cheese, eggs, and avocado', 'price': 14.99, 'category': 'main-courses'},
        {'name': 'Chicken Tenders', 'description': 'Crispy chicken tenders with honey mustard and french fries', 'price': 12.99, 'category': 'main-courses'},
        {'name': 'Meatloaf', 'description': 'Homestyle meatloaf with mashed potatoes and green beans', 'price': 14.99, 'category': 'main-courses'},
        {'name': 'Shepherd\'s Pie', 'description': 'Ground beef and vegetables topped with mashed potatoes', 'price': 13.99, 'category': 'main-courses'},
        
        # DESSERTS
        {'name': 'New York Cheesecake', 'description': 'Rich and creamy cheesecake with graham cracker crust', 'price': 6.99, 'category': 'desserts'},
        {'name': 'Chocolate Brownie Sundae', 'description': 'Warm chocolate brownie with vanilla ice cream and hot fudge', 'price': 7.99, 'category': 'desserts'},
        {'name': 'Apple Pie', 'description': 'Classic apple pie with cinnamon and vanilla ice cream', 'price': 6.99, 'category': 'desserts'},
        {'name': 'Chocolate Cake', 'description': 'Rich chocolate layer cake with chocolate frosting', 'price': 6.99, 'category': 'desserts'},
        {'name': 'Ice Cream Sundae', 'description': 'Three scoops of vanilla ice cream with your choice of toppings', 'price': 5.99, 'category': 'desserts'},
        {'name': 'Key Lime Pie', 'description': 'Tangy key lime pie with whipped cream', 'price': 6.99, 'category': 'desserts'},
        {'name': 'Bread Pudding', 'description': 'Warm bread pudding with vanilla sauce and cinnamon', 'price': 6.99, 'category': 'desserts'},
        
        # DRINKS - Non-Alcoholic
        {'name': 'Coca-Cola', 'description': 'Classic Coca-Cola soft drink', 'price': 2.99, 'category': 'drinks'},
        {'name': 'Pepsi', 'description': 'Classic Pepsi cola soft drink', 'price': 2.99, 'category': 'drinks'},
        {'name': 'Diet Pepsi', 'description': 'Zero-calorie Pepsi cola', 'price': 2.99, 'category': 'drinks'},
        {'name': 'Mountain Dew', 'description': 'Citrus-flavored Pepsi product', 'price': 2.99, 'category': 'drinks'},
        {'name': 'Sierra Mist', 'description': 'Lemon-lime soda by Pepsi', 'price': 2.99, 'category': 'drinks'},
        {'name': 'Dr Pepper', 'description': 'Classic Dr Pepper soda', 'price': 2.99, 'category': 'drinks'},
        {'name': 'Root Beer', 'description': 'Classic root beer soda', 'price': 2.99, 'category': 'drinks'},
        {'name': 'Lemonade', 'description': 'Fresh squeezed lemonade', 'price': 3.49, 'category': 'drinks'},
        {'name': 'Iced Tea', 'description': 'Freshly brewed iced tea', 'price': 2.99, 'category': 'drinks'},
        {'name': 'Coffee', 'description': 'Freshly brewed coffee', 'price': 2.99, 'category': 'drinks'},
        {'name': 'Hot Tea', 'description': 'Selection of hot teas', 'price': 2.99, 'category': 'drinks'},
        {'name': 'Orange Juice', 'description': 'Freshly squeezed orange juice', 'price': 3.99, 'category': 'drinks'},
        {'name': 'Apple Juice', 'description': 'Pure apple juice', 'price': 3.49, 'category': 'drinks'},
        {'name': 'Cranberry Juice', 'description': 'Tart cranberry juice', 'price': 3.49, 'category': 'drinks'},
        {'name': 'Milk', 'description': 'Cold whole milk', 'price': 2.99, 'category': 'drinks'},
        {'name': 'Chocolate Milk', 'description': 'Rich chocolate milk', 'price': 3.49, 'category': 'drinks'},
        
        # DRINKS - Alcoholic
        {'name': 'Draft Beer', 'description': 'Selection of draft beers on tap', 'price': 4.99, 'category': 'drinks'},
        {'name': 'Bottled Beer', 'description': 'Domestic and imported bottled beers', 'price': 4.49, 'category': 'drinks'},
        {'name': 'House Wine', 'description': 'Red or white house wine by the glass', 'price': 6.99, 'category': 'drinks'},
        {'name': 'Premium Wine', 'description': 'Premium wine selection by the glass', 'price': 8.99, 'category': 'drinks'},
        {'name': 'Margarita', 'description': 'Classic margarita with lime and salt rim', 'price': 8.99, 'category': 'drinks'},
        {'name': 'Long Island Iced Tea', 'description': 'Mixed drink with multiple spirits and cola', 'price': 9.99, 'category': 'drinks'},
        {'name': 'Whiskey Sour', 'description': 'Whiskey with lemon juice and simple syrup', 'price': 8.99, 'category': 'drinks'},
        {'name': 'Bloody Mary', 'description': 'Vodka with tomato juice and spices', 'price': 8.99, 'category': 'drinks'},
        {'name': 'Mojito', 'description': 'Rum with mint, lime, and soda water', 'price': 8.99, 'category': 'drinks'},
        {'name': 'Old Fashioned', 'description': 'Whiskey with bitters, sugar, and orange peel', 'price': 9.99, 'category': 'drinks'},
    ]

    for item in menu_items:
        menu_item = MenuItem(
            name=item['name'],
            description=item['description'],
            price=item['price'],
            category=item['category']
        )
        db.session.add(menu_item)
    db.session.commit()

def create_demo_reservation_with_party_orders():
    reservation = Reservation(
        reservation_number='111222',
        name='Smith Family',
        party_size=3,
        date='2025-06-10',
        time='18:30',
        phone_number='+15551234567',
        status='confirmed',
        special_requests='Window seat',
        payment_status='unpaid'
    )
    db.session.add(reservation)
    db.session.flush()
    party = [
        {'name': 'Bill', 'items': [('Classic Pancakes', 1), ('Coffee', 2)]},
        {'name': 'Susan', 'items': [('Western Omelette', 1), ('Orange Juice', 1)]},
        {'name': 'Tommy', 'items': [('Chocolate Cake', 1), ('Pepsi', 1)]},
    ]
    for person in party:
        order = Order(
            order_number=generate_order_number(),
            reservation_id=reservation.id,
            person_name=person['name'],
            status='pending',
            total_amount=0.0,
            payment_status='unpaid'
        )
        db.session.add(order)
        total = 0.0
        for item_name, qty in person['items']:
            menu_item = MenuItem.query.filter_by(name=item_name).first()
            if menu_item:
                db.session.add(OrderItem(
                    order=order,
                    menu_item=menu_item,
                    quantity=qty,
                    price_at_time=menu_item.price
                ))
                total += menu_item.price * qty
        order.total_amount = total
    db.session.commit()

def create_additional_demo_reservations():
    from models import Reservation, Order, OrderItem, MenuItem, db
    # Reservation 2
    reservation2 = Reservation(
        reservation_number='333444',
        name='Johnson Group',
        party_size=2,
        date='2025-06-11',
        time='12:00',
        phone_number='+15555678901',
        status='confirmed',
        special_requests='Birthday celebration',
        payment_status='unpaid'
    )
    db.session.add(reservation2)
    db.session.flush()
    party2 = [
        {'name': 'Alice', 'items': [('Caesar Salad', 1), ('Diet Pepsi', 1)]},
        {'name': 'Bob', 'items': [('Ribeye Steak', 1), ('Draft Beer', 1)]},
    ]
    for person in party2:
        order = Order(
            order_number=generate_order_number(),
            reservation_id=reservation2.id,
            person_name=person['name'],
            status='pending',
            total_amount=0.0,
            payment_status='unpaid'
        )
        db.session.add(order)
        total = 0.0
        for item_name, qty in person['items']:
            menu_item = MenuItem.query.filter_by(name=item_name).first()
            if menu_item:
                db.session.add(OrderItem(
                    order=order,
                    menu_item=menu_item,
                    quantity=qty,
                    price_at_time=menu_item.price
                ))
                total += menu_item.price * qty
        order.total_amount = total
    # Reservation 3
    reservation3 = Reservation(
        reservation_number='555666',
        name='Lee Family',
        party_size=4,
        date='2025-06-12',
        time='19:15',
        phone_number='+15559012345',
        status='confirmed',
        special_requests='High chair needed',
        payment_status='unpaid'
    )
    db.session.add(reservation3)
    db.session.flush()
    party3 = [
        {'name': 'David', 'items': [('BBQ Ribs', 1), ('Draft Beer', 1)]},
        {'name': 'Emma', 'items': [('Chicken Caesar Salad', 1), ('Lemonade', 1)]},
        {'name': 'Olivia', 'items': [('New York Cheesecake', 1), ('Coffee', 1)]},
        {'name': 'Lucas', 'items': [('Buffalo Wings', 1), ('Mountain Dew', 1)]},
    ]
    for person in party3:
        order = Order(
            order_number=generate_order_number(),
            reservation_id=reservation3.id,
            person_name=person['name'],
            status='pending',
            total_amount=0.0,
            payment_status='unpaid'
        )
        db.session.add(order)
        total = 0.0
        for item_name, qty in person['items']:
            menu_item = MenuItem.query.filter_by(name=item_name).first()
            if menu_item:
                db.session.add(OrderItem(
                    order=order,
                    menu_item=menu_item,
                    quantity=qty,
                    price_at_time=menu_item.price
                ))
                total += menu_item.price * qty
        order.total_amount = total
    db.session.commit()

def clear_existing_data():
    """Clear existing data from all tables"""
    from models import OrderItem, Order, Reservation, MenuItem, db
    
    # Delete in order to respect foreign key constraints
    OrderItem.query.delete()
    Order.query.delete()
    Reservation.query.delete()
    MenuItem.query.delete()
    db.session.commit()
    print("Existing data cleared.")

# Call the function to populate the menu items
def main():
    with app.app_context():
        db.create_all()
        clear_existing_data()
        populate_menu_items()
        create_demo_reservation_with_party_orders()
        create_additional_demo_reservations()

if __name__ == "__main__":
    main() 