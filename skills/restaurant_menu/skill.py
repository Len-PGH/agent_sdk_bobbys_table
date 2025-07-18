"""
Restaurant Menu Skill for SignalWire AI Agents with Data Validation
"""

import os
import json
import copy
from datetime import datetime, timedelta
from signalwire_agents.core.skill_base import SkillBase
from signalwire_agents.core.function_result import SwaigFunctionResult
import re

class RestaurantMenuSkill(SkillBase):
    """Restaurant menu skill with data validation"""
    
    SKILL_NAME = "restaurant_menu"
    SKILL_DESCRIPTION = "Browse menu items with validation"
    SKILL_VERSION = "1.0.0"
    REQUIRED_PACKAGES = []
    REQUIRED_ENV_VARS = []

    def __init__(self, agent=None, skill_params=None):
        super().__init__(agent)
        self.skill_params = skill_params or {}
        self.description = "Restaurant menu system with data validation"
        # Register tools automatically when skill is initialized
        self.register_tools()

    def setup(self):
        """Setup method required by SkillBase"""
        return True

    def _format_phone_number(self, phone_number):
        """Format phone number for display - converts +15555555555 to (555) 555-5555"""
        if not phone_number:
            return "(555) 555-5555"  # fallback
        
        # Remove any non-digit characters
        digits = re.sub(r'\D', '', phone_number)
        
        # If it's an 11-digit number starting with 1, format as (XXX) XXX-XXXX
        if len(digits) == 11 and digits.startswith('1'):
            area_code = digits[1:4]
            exchange = digits[4:7]
            number = digits[7:11]
            return f"({area_code}) {exchange}-{number}"
        elif len(digits) == 10:
            area_code = digits[0:3]
            exchange = digits[3:6]
            number = digits[6:10]
            return f"({area_code}) {exchange}-{number}"
        else:
            return phone_number  # return as-is if we can't format it

    def _ensure_menu_cached(self, raw_data):
        """Cache menu with validation"""
        try:
            import sys
            import os
            
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import MenuItem
            
            with app.app_context():
                meta_data = raw_data.get('meta_data', {}) if raw_data else {}
                cache_time = meta_data.get('menu_cached_at')
                cached_menu = meta_data.get('cached_menu', [])
                
                if cache_time and cached_menu:
                    try:
                        cached_at = datetime.fromisoformat(cache_time)
                        if datetime.now() - cached_at < timedelta(minutes=10):
                            if self._validate_menu_cache(cached_menu):
                                print("Menu cache valid, using cached data")
                                return cached_menu, meta_data
                            else:
                                print("Menu cache validation failed, refreshing")
                                cached_menu = []
                        else:
                            print("Menu cache expired, refreshing")
                            cached_menu = []
                    except ValueError:
                        print("Invalid cache timestamp, refreshing")
                        cached_menu = []
                
                if not cached_menu:
                    print("Caching menu with validation")
                    menu_items = MenuItem.query.filter_by(is_available=True).all()
                    menu_items = sorted(menu_items, key=lambda item: len(item.name.lower()), reverse=True)
                    
                    cached_menu = []
                    for item in menu_items:
                        try:
                            menu_item_data = {
                                'id': int(item.id),
                                'name': str(item.name).strip(),
                                'price': float(item.price),
                                'category': str(item.category).strip(),
                                'description': str(item.description).strip(),
                                'is_available': bool(item.is_available)
                            }
                            
                            if self._validate_menu_item(menu_item_data):
                                cached_menu.append(menu_item_data)
                            else:
                                print(f"Skipping invalid menu item: {item.id}")
                        except Exception as item_error:
                            print(f"Error processing menu item {item.id}: {item_error}")
                            continue
                    
                    if not self._validate_menu_cache(cached_menu):
                        print("Menu cache validation failed after creation")
                        return [], raw_data.get('meta_data', {}) if raw_data else {}
                    
                    cached_menu = copy.deepcopy(cached_menu)
                    meta_data['cached_menu'] = cached_menu
                    meta_data['menu_cached_at'] = datetime.now().isoformat()
                    meta_data['menu_item_count'] = len(cached_menu)
                    
                    print(f"Successfully cached {len(cached_menu)} validated menu items")
                else:
                    print(f"Using validated cached menu with {len(cached_menu)} items")
                
                return cached_menu, meta_data
                
        except Exception as e:
            print(f"Error ensuring menu cache: {e}")
            return [], raw_data.get('meta_data', {}) if raw_data else {}

    def _validate_menu_item(self, item_data):
        """Validate a single menu item"""
        try:
            if not isinstance(item_data, dict):
                return False
            
            required_fields = ['id', 'name', 'price', 'category', 'description', 'is_available']
            for field in required_fields:
                if field not in item_data:
                    return False
            
            if not isinstance(item_data['id'], int) or item_data['id'] <= 0:
                return False
            
            if not isinstance(item_data['name'], str) or len(item_data['name'].strip()) == 0:
                return False
            
            if not isinstance(item_data['price'], (int, float)) or item_data['price'] < 0:
                return False
            
            if not isinstance(item_data['category'], str) or len(item_data['category'].strip()) == 0:
                return False
            
            if not isinstance(item_data['description'], str):
                return False
            
            if not isinstance(item_data['is_available'], bool):
                return False
            
            return True
            
        except Exception:
            return False

    def _validate_menu_cache(self, cached_menu):
        """Validate the complete menu cache"""
        try:
            if not isinstance(cached_menu, list):
                return False
            
            if len(cached_menu) == 0:
                return False
            
            seen_ids = set()
            valid_items = 0
            
            for i, item in enumerate(cached_menu):
                if not self._validate_menu_item(item):
                    return False
                
                item_id = item.get('id')
                if item_id in seen_ids:
                    return False
                seen_ids.add(item_id)
                valid_items += 1
            
            if len(cached_menu) > 500:
                return False
            
            if valid_items < 5:
                return False
            
            print(f"Menu cache validation passed: {valid_items} valid items")
            return True
            
        except Exception:
            return False

    def register_tools(self):
        """Register menu tools"""
        try:
            # Get menu tool
            self.agent.define_tool(
                name="get_menu",
                description="Show restaurant menu with validation",
                parameters={
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Menu category to filter by",
                            "enum": ["breakfast", "appetizers", "main-courses", "desserts", "drinks"]
                        },
                        "format": {
                            "type": "string",
                            "enum": ["text", "json"],
                            "description": "Response format",
                            "default": "text"
                        }
                    },
                    "required": []
                },
                handler=self._get_menu_handler
            )
            print("Registered get_menu tool with validation")
            
            # Create order tool
            self.agent.define_tool(
                name="create_order",
                description="Create a standalone food order for pickup or delivery",
                parameters={
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "Menu item name"},
                                    "quantity": {"type": "integer", "description": "Quantity to order", "default": 1},
                                    "price": {"type": "number", "description": "Price per item from menu"}
                                },
                                "required": ["name", "quantity", "price"]
                            },
                            "description": "List of menu items to order"
                        },
                        "customer_name": {
                            "type": "string",
                            "description": "Customer name for the order"
                        },
                        "customer_phone": {
                            "type": "string",
                            "description": "Customer phone number"
                        },
                        "order_type": {
                            "type": "string",
                            "enum": ["pickup", "delivery"],
                            "description": "Order type - pickup or delivery",
                            "default": "pickup"
                        },
                        "customer_address": {
                            "type": "string",
                            "description": "Customer address (required for delivery orders)"
                        },
                        "special_instructions": {
                            "type": "string",
                            "description": "Special instructions for the order"
                        },
                        "payment_preference": {
                            "type": "string",
                            "enum": ["now", "pickup"],
                            "description": "When customer wants to pay",
                            "default": "pickup"
                        }
                    },
                    "required": ["items", "customer_name", "customer_phone"]
                },
                handler=self._create_order_handler
            )
            print("Registered create_order tool with validation")
            
            # Send reservation SMS tool  
            self.agent.define_tool(
                name="send_reservation_sms",
                description="Send SMS confirmation for reservation with pre-order details",
                parameters={
                    "type": "object",
                    "properties": {
                        "phone_number": {
                            "type": "string",
                            "description": "Customer phone number"
                        },
                        "reservation_number": {
                            "type": "string", 
                            "description": "Reservation number"
                        },
                        "customer_name": {
                            "type": "string",
                            "description": "Customer name"
                        },
                        "party_size": {
                            "type": "integer",
                            "description": "Number of people"
                        },
                        "reservation_date": {
                            "type": "string",
                            "description": "Reservation date"
                        },
                        "reservation_time": {
                            "type": "string", 
                            "description": "Reservation time"
                        },
                        "pre_order_total": {
                            "type": "number",
                            "description": "Pre-order total amount"
                        },
                        "message_type": {
                            "type": "string",
                            "enum": ["confirmation", "reminder", "update"],
                            "description": "Type of SMS message",
                            "default": "confirmation"
                        }
                    },
                    "required": ["phone_number", "reservation_number"]
                },
                handler=self._send_reservation_sms_handler
            )
            print("Registered send_reservation_sms tool")
            
            # Send payment receipt SMS tool  
            self.agent.define_tool(
                name="send_payment_receipt",
                description="Send SMS payment receipt confirmation",
                parameters={
                    "type": "object",
                    "properties": {
                        "phone_number": {
                            "type": "string",
                            "description": "Customer phone number"
                        },
                        "reservation_number": {
                            "type": "string",
                            "description": "Reservation number"
                        },
                        "customer_name": {
                            "type": "string",
                            "description": "Customer name"
                        },
                        "payment_amount": {
                            "type": "number",
                            "description": "Payment amount"
                        },
                        "confirmation_number": {
                            "type": "string",
                            "description": "Payment confirmation number"
                        },
                        "reservation_date": {
                            "type": "string",
                            "description": "Reservation date"
                        },
                        "reservation_time": {
                            "type": "string",
                            "description": "Reservation time"
                        },
                        "party_size": {
                            "type": "integer",
                            "description": "Number of people in party"
                        }
                    },
                    "required": ["phone_number", "reservation_number", "payment_amount"]
                },
                handler=self._send_payment_receipt_handler
            )
            print("Registered send_payment_receipt tool")
            
            # Check order status tool
            self.agent.define_tool(
                name="get_order_details",
                description="Get order details and status for a to-go order for pickup or delivery. Search by order number, customer phone number, or customer name. Use this when customers ask about their order status or details.",
                parameters={
                    "type": "object",
                    "properties": {
                        "order_number": {
                            "type": "string",
                            "description": "5-digit order number"
                        },
                        "customer_phone": {
                            "type": "string", 
                            "description": "Customer phone number to look up order"
                        },
                        "customer_name": {
                            "type": "string",
                            "description": "Customer name to search for orders"
                        },
                        "format": {
                            "type": "string",
                            "enum": ["text", "json"],
                            "description": "Response format: 'text' for voice-friendly formatted text (default), 'json' for structured data",
                            "default": "text"
                        }
                    },
                    "required": []
                },
                handler=self._check_order_status_handler
            )
            print("Registered get_order_details tool")
            
            # Update order items tool
            self.agent.define_tool(
                name="update_order_items",
                description="Add or remove items from an existing order. Reservation orders can be updated if not paid yet. Pickup orders can only be updated if status is pending.",
                parameters={
                    "type": "object",
                    "properties": {
                        "order_number": {
                            "type": "string",
                            "description": "5-digit order number"
                        },
                        "customer_phone": {
                            "type": "string",
                            "description": "Customer phone number to find the order"
                        },
                        "customer_name": {
                            "type": "string",
                            "description": "Customer name to find the order"
                        },
                        "action": {
                            "type": "string",
                            "enum": ["add", "remove"],
                            "description": "Whether to add or remove items"
                        },
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "description": "Menu item name"
                                    },
                                    "quantity": {
                                        "type": "integer",
                                        "description": "Quantity to add or remove",
                                        "default": 1
                                    }
                                },
                                "required": ["name"]
                            },
                            "description": "List of items to add or remove"
                        }
                    },
                    "required": ["action", "items"]
                },
                handler=self._update_order_items_handler
            )
            print("Registered update_order_items tool")
            
            # Pay order tool
            self.agent.define_tool(
                name="pay_order",
                description="Process payment for an existing order using SignalWire Pay and Stripe. REQUIRES order number - use get_order_details first if customer doesn't have their order number. Use this ONLY when customers want to pay for their order over the phone.",
                parameters={
                    "type": "object",
                    "properties": {
                        "order_number": {
                            "type": "string",
                            "description": "5-digit order number to pay for (REQUIRED for payment)"
                        },
                        "order_id": {
                            "type": "integer",
                            "description": "Order ID (alternative to order_number)"
                        }
                    },
                    "required": ["order_number"]
                },
                handler=self._pay_order_handler
            )
            print("Registered pay_order tool")
            
        except Exception as e:
            print(f"Error registering restaurant menu tools: {e}")
            import traceback
            traceback.print_exc()

    def _get_menu_handler(self, args, raw_data):
        """Menu handler with validation"""
        try:
            cached_menu, meta_data = self._ensure_menu_cached(raw_data)
            
            if not cached_menu:
                result = SwaigFunctionResult("Sorry, the menu is currently unavailable.")
                result.set_metadata(meta_data)
                return result
            
            if args.get('category'):
                category = args['category'].lower()
                filtered_items = [item for item in cached_menu if item['category'].lower() == category]
                
                if not filtered_items:
                    result = SwaigFunctionResult(f"No items found in the {category} category.")
                    result.set_metadata(meta_data)
                    return result
                
                message = f"Here are our {category} items: "
                item_list = []
                for item in filtered_items[:20]:
                    item_list.append(f"{item['name']} for ${item['price']:.2f}")
                message += ", ".join(item_list)
                
                if len(filtered_items) > 20:
                    message += f" and {len(filtered_items) - 20} more items"
                
                result = SwaigFunctionResult(message)
                result.set_metadata(meta_data)
                return result
            else:
                categories = {}
                for item in cached_menu:
                    if item['category'] not in categories:
                        categories[item['category']] = []
                    categories[item['category']].append(item)
                
                message = f"Here's our menu with {len(cached_menu)} items: "
                for category, items in categories.items():
                    category_display = category.replace('-', ' ').title()
                    message += f"{category_display}: "
                    limited_items = items[:10]
                    item_list = []
                    for item in limited_items:
                        item_list.append(f"{item['name']} (${item['price']:.2f})")
                    message += ", ".join(item_list)
                    if len(items) > 10:
                        message += f" and {len(items) - 10} more"
                    message += ". "
                
                result = SwaigFunctionResult(message)
                result.set_metadata(meta_data)
                return result
                
        except Exception as e:
            print(f"Error in get_menu handler: {e}")
            return SwaigFunctionResult("Sorry, there was an error retrieving the menu.")

    def _get_random_party_orders(self, raw_data, party_names, food_per_person=1, drinks_per_person=1):
        """Generate random party orders for multiple people"""
        import random
        
        try:
            cached_menu, meta_data = self._ensure_menu_cached(raw_data)
            
            if not cached_menu:
                return {'success': False, 'error': 'Menu not available'}
            
            # Separate categories
            food_categories = ['breakfast', 'appetizers', 'main-courses', 'desserts']
            drink_categories = ['drinks']
            
            food_items = [item for item in cached_menu if item['category'] in food_categories]
            drink_items = [item for item in cached_menu if item['category'] in drink_categories]
            
            party_orders = []
            used_items = set()
            total_amount = 0.0
            
            for person_name in party_names:
                person_items = []
                person_total = 0.0
                
                # Select random food items
                available_food = [item for item in food_items if item['id'] not in used_items]
                if available_food:
                    for _ in range(min(food_per_person, len(available_food))):
                        if available_food:
                            selected_food = random.choice(available_food)
                            available_food.remove(selected_food)
                            used_items.add(selected_food['id'])
                            
                            person_items.append({
                                'menu_item_id': selected_food['id'],
                                'name': selected_food['name'],
                                'price': selected_food['price'],
                                'category': selected_food['category'],
                                'quantity': 1
                            })
                            person_total += selected_food['price']
                
                # Select random drink items
                available_drinks = [item for item in drink_items if item['id'] not in used_items]
                if available_drinks:
                    for _ in range(min(drinks_per_person, len(available_drinks))):
                        if available_drinks:
                            selected_drink = random.choice(available_drinks)
                            available_drinks.remove(selected_drink)
                            used_items.add(selected_drink['id'])
                            
                            person_items.append({
                                'menu_item_id': selected_drink['id'],
                                'name': selected_drink['name'],
                                'price': selected_drink['price'],
                                'category': selected_drink['category'],
                                'quantity': 1
                            })
                            person_total += selected_drink['price']
                
                party_orders.append({
                    'person_name': person_name,
                    'items': person_items,
                    'person_total': person_total
                })
                total_amount += person_total
            
            return {
                'success': True,
                'party_orders': party_orders,
                'total_amount': total_amount,
                'party_count': len(party_orders)
            }
            
        except Exception as e:
            print(f"Error generating random party orders: {e}")
            return {'success': False, 'error': str(e)}

    def _create_order_handler(self, args, raw_data):
        """Create a standalone food order with data validation"""
        try:
            import sys
            import os
            from datetime import datetime
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import Order, OrderItem, MenuItem, db
            
            with app.app_context():
                # Ensure menu is cached for item validation
                cached_menu, meta_data = self._ensure_menu_cached(raw_data)
                
                if not cached_menu:
                    result = SwaigFunctionResult("Sorry, our menu system is temporarily unavailable. Please try again later.")
                    result.set_metadata(meta_data)
                    return result
                
                # Validate required fields
                items = args.get('items', [])
                customer_name = args.get('customer_name')
                customer_phone = args.get('customer_phone')
                order_type = args.get('order_type', 'pickup')
                customer_address = args.get('customer_address', '')
                special_instructions = args.get('special_instructions', '')
                payment_preference = args.get('payment_preference', 'pickup')
                
                if not items:
                    result = SwaigFunctionResult("Please specify which items you'd like to order.")
                    result.set_metadata(meta_data)
                    return result
                
                if not customer_name or not customer_phone:
                    result = SwaigFunctionResult("I need your name and phone number to create the order.")
                    result.set_metadata(meta_data)
                    return result
                
                if order_type == 'delivery' and not customer_address:
                    result = SwaigFunctionResult("I need your delivery address for delivery orders.")
                    result.set_metadata(meta_data)
                    return result
                
                # Create menu lookup for faster access
                menu_lookup = {item['name'].lower(): item for item in cached_menu}
                
                # Validate and process items
                order_items = []
                total_amount = 0.0
                
                for item_spec in items:
                    item_name = item_spec.get('name', '').strip()
                    quantity = item_spec.get('quantity', 1)
                    item_price = item_spec.get('price', 0) # Get price from item_spec
                    
                    if not item_name:
                        continue
                    
                    # Find menu item with validation
                    menu_item = None
                    item_name_lower = item_name.lower()
                    
                    # Try exact match first
                    if item_name_lower in menu_lookup:
                        menu_item_data = menu_lookup[item_name_lower]
                    else:
                        # Try fuzzy matching
                        best_match = None
                        best_score = 0
                        
                        for cached_item in cached_menu:
                            cached_name_lower = cached_item['name'].lower()
                            
                            # Check for partial matches
                            if item_name_lower in cached_name_lower or cached_name_lower in item_name_lower:
                                # Calculate match score
                                common_words = set(item_name_lower.split()) & set(cached_name_lower.split())
                                score = len(common_words) / max(len(cached_name_lower.split()), 1)
                                
                                if score > best_score and score > 0.3:
                                    best_match = cached_item
                                    best_score = score
                        
                        menu_item_data = best_match
                    
                    if not menu_item_data:
                        result = SwaigFunctionResult(f"Sorry, I couldn't find '{item_name}' on our menu. Please check the menu and try again.")
                        result.set_metadata(meta_data)
                        return result
                    
                    if not menu_item_data['is_available']:
                        result = SwaigFunctionResult(f"Sorry, {menu_item_data['name']} is currently unavailable.")
                        result.set_metadata(meta_data)
                        return result
                    
                    # Validate quantity
                    try:
                        quantity = int(quantity)
                        if quantity <= 0:
                            quantity = 1
                    except (ValueError, TypeError):
                        quantity = 1
                    
                    # Validate price matches menu price
                    if abs(item_price - menu_item_data['price']) > 0.01:  # Allow for small floating point differences
                        result = SwaigFunctionResult(f"Price mismatch for {menu_item_data['name']}. Expected ${menu_item_data['price']:.2f}, got ${item_price:.2f}. Please use current menu prices.")
                        result.set_metadata(meta_data)
                        return result
                    
                    # Add to order
                    item_total = item_price * quantity # Use item_price from args
                    order_items.append({
                        'menu_item_id': menu_item_data['id'],
                        'name': menu_item_data['name'],
                        'quantity': quantity,
                        'price': item_price, # Store item_price in order_items
                        'total': item_total
                    })
                    total_amount += item_total
                
                if not order_items:
                    result = SwaigFunctionResult("No valid items found to order. Please check our menu and try again.")
                    result.set_metadata(meta_data)
                    return result
                
                # Generate order number (5-digit)
                import random
                import string
                order_number = ''.join(random.choices(string.digits, k=5))
                
                # Create the order
                new_order = Order(
                    order_number=order_number,
                    person_name=customer_name,
                    status='pending',
                    total_amount=total_amount,
                    order_type=order_type,
                    customer_phone=customer_phone,
                    customer_address=customer_address,
                    special_instructions=special_instructions,
                    payment_status='pending',
                    created_at=datetime.utcnow()
                )
                
                db.session.add(new_order)
                db.session.flush()  # Get the order ID
                
                # Add order items
                for item_data in order_items:
                    order_item = OrderItem(
                        order_id=new_order.id,
                        menu_item_id=item_data['menu_item_id'],
                        quantity=item_data['quantity'],
                        price_at_time=item_data['price']
                    )
                    db.session.add(order_item)
                
                db.session.commit()
                
                # Build confirmation message
                message = f"🍽️ ORDER CONFIRMED! 🍽️\n\n"
                message += f"📋 Order Number: {order_number}\n"
                message += f"👤 Customer: {customer_name}\n"
                message += f"📱 Phone: {customer_phone}\n"
                message += f"📦 Type: {order_type.title()}\n"
                
                if order_type == 'delivery':
                    message += f"📍 Address: {customer_address}\n"
                
                message += f"\n🍽️ Order Details:\n"
                for item_data in order_items:
                    message += f"• {item_data['quantity']}x {item_data['name']} - ${item_data['total']:.2f}\n"
                
                message += f"\n💰 Total: ${total_amount:.2f}\n"
                
                if special_instructions:
                    message += f"📝 Instructions: {special_instructions}\n"
                
                estimated_time = 20 if order_type == 'pickup' else 35
                message += f"\n⏰ Estimated {order_type} time: {estimated_time} minutes\n"
                
                if payment_preference == 'now':
                    message += f"\n💳 Payment will be processed now. Please have your payment method ready.\n"
                else:
                    message += f"\n💳 Payment due at {order_type}.\n"
                
                message += f"\nThank you for choosing Bobby's Table! We'll have your order ready soon."
                
                result = SwaigFunctionResult(message)
                result.set_metadata(meta_data)
                return result
                
        except Exception as e:
            print(f"Error creating order: {e}")
            import traceback
            traceback.print_exc()
            return SwaigFunctionResult("Sorry, there was an error creating your order. Please try again or call us directly.")



    def _send_reservation_sms_handler(self, args, raw_data):
        """Handle sending reservation SMS confirmations"""
        try:
            phone_number = args.get('phone_number', '').strip()
            reservation_number = args.get('reservation_number', '').strip()
            customer_name = args.get('customer_name', '').strip()
            party_size = args.get('party_size', 1)
            reservation_date = args.get('reservation_date', '').strip()
            reservation_time = args.get('reservation_time', '').strip()
            pre_order_total = args.get('pre_order_total', 0)
            message_type = args.get('message_type', 'confirmation')
            
            print(f"📱 SMS Reservation Confirmation Request:")
            print(f"   Phone: {phone_number}")
            print(f"   Reservation: {reservation_number}")
            print(f"   Customer: {customer_name}")
            print(f"   Party Size: {party_size}")
            print(f"   Date: {reservation_date}")
            print(f"   Time: {reservation_time}")
            print(f"   Pre-order Total: ${pre_order_total}")
            print(f"   Message Type: {message_type}")
            
            # Validate required fields
            if not phone_number:
                return SwaigFunctionResult("Phone number is required to send SMS confirmation.")
            
            if not reservation_number:
                return SwaigFunctionResult("Reservation number is required to send SMS confirmation.")
            
            # Send the SMS
            sms_result = self._send_reservation_sms(
                phone_number=phone_number,
                reservation_number=reservation_number,
                customer_name=customer_name,
                party_size=party_size,
                reservation_date=reservation_date,
                reservation_time=reservation_time,
                pre_order_total=pre_order_total,
                message_type=message_type
            )
            
            if sms_result.get('success', False):
                message = f"✅ SMS confirmation sent successfully to {phone_number}! "
                message += f"You should receive your reservation details shortly."
                
                # Update metadata
                meta_data = raw_data.get('meta_data', {}) if raw_data else {}
                meta_data.update({
                    'sms_sent': True,
                    'sms_phone': phone_number,
                    'sms_reservation': reservation_number,
                    'sms_timestamp': datetime.now().isoformat()
                })
                
                result = SwaigFunctionResult(message)
                result.set_metadata(meta_data)
                return result
            else:
                error_msg = sms_result.get('error', 'Unknown error')
                return SwaigFunctionResult(f"❌ Sorry, I couldn't send the SMS confirmation. {error_msg} Please try again or contact us directly.")
                
        except Exception as e:
            print(f"Error sending reservation SMS: {e}")
            return SwaigFunctionResult("Sorry, there was an error sending your SMS confirmation. Please try again or contact us directly.")

    def _send_reservation_sms(self, phone_number, reservation_number, customer_name=None, 
                             party_size=1, reservation_date=None, reservation_time=None, 
                             pre_order_total=0, message_type='confirmation'):
        """Send SMS confirmation for reservation - internal helper method"""
        try:
            from datetime import datetime
            
            # Build SMS message based on type
            if message_type == 'confirmation':
                sms_body = f"🍽️ Bobby's Table - Reservation Confirmed!\n\n"
                sms_body += f"📋 Reservation: #{reservation_number}\n"
                
                if customer_name:
                    sms_body += f"👤 Name: {customer_name}\n"
                
                if party_size and party_size > 1:
                    sms_body += f"👥 Party Size: {party_size} people\n"
                else:
                    sms_body += f"👥 Party Size: 1 person\n"
                
                if reservation_date:
                    sms_body += f"📅 Date: {reservation_date}\n"
                
                if reservation_time:
                    sms_body += f"⏰ Time: {reservation_time}\n"
                
                if pre_order_total and pre_order_total > 0:
                    sms_body += f"💰 Pre-order Total: ${pre_order_total:.2f}\n"
                
                sms_body += f"\n📍 Location: Bobby's Table Restaurant\n"
                sms_body += f"📞 Call us: {self._format_phone_number(os.getenv('SIGNALWIRE_FROM_NUMBER', '+15555555555'))}\n\n"
                sms_body += f"We look forward to serving you!\n"
                sms_body += f"Reply STOP to opt out."
                
            elif message_type == 'reminder':
                sms_body = f"🔔 Bobby's Table - Reservation Reminder\n\n"
                sms_body += f"📋 Reservation: #{reservation_number}\n"
                sms_body += f"⏰ Your reservation is coming up!\n"
                if reservation_date and reservation_time:
                    sms_body += f"📅 {reservation_date} at {reservation_time}\n"
                sms_body += f"\nSee you soon at Bobby's Table!"
                
            else:  # update
                sms_body = f"📝 Bobby's Table - Reservation Update\n\n"
                sms_body += f"📋 Reservation: #{reservation_number}\n"
                sms_body += f"Your reservation has been updated.\n"
                if reservation_date and reservation_time:
                    sms_body += f"📅 New time: {reservation_date} at {reservation_time}\n"
                sms_body += f"\nQuestions? Call us: {self._format_phone_number(os.getenv('SIGNALWIRE_FROM_NUMBER', '+15555555555'))}"
            
            # Get SignalWire credentials from environment
            signalwire_from_number = os.getenv('SIGNALWIRE_FROM_NUMBER', '+15555555555')
            
            print(f"📱 Sending SMS via SignalWire:")
            print(f"   From: {signalwire_from_number}")
            print(f"   To: {phone_number}")
            print(f"   Region: us")
            print(f"   Body: {repr(sms_body)}")
            
            # Use SignalWire send_sms method
            result = SwaigFunctionResult()
            result = result.send_sms(
                to_number=phone_number,
                from_number=signalwire_from_number,
                body=sms_body,
                region="us"
            )
            
            print(f"✅ SMS sent successfully to {phone_number}")
            print(f"📱 Result type: {type(result)}")
            print(f"📱 Result: {result}")
            
            if hasattr(result, 'to_dict'):
                print(f"📱 Result dict: {json.dumps(result.to_dict(), indent=2)}")
            
            return {'success': True, 'result': result}
            
        except Exception as e:
            print(f"Error sending reservation SMS: {e}")
            return {'success': False, 'error': f"SMS sending failed: {str(e)}"}

    def _send_payment_receipt_handler(self, args, raw_data):
        """Handle sending payment receipt SMS"""
        try:
            phone_number = args.get('phone_number', '').strip()
            reservation_number = args.get('reservation_number', '').strip()
            customer_name = args.get('customer_name', '').strip()
            payment_amount = args.get('payment_amount', 0)
            confirmation_number = args.get('confirmation_number', '').strip()
            reservation_date = args.get('reservation_date', '').strip()
            reservation_time = args.get('reservation_time', '').strip()
            party_size = args.get('party_size', 1)
            
            print(f"📱 SMS Payment Receipt Request:")
            print(f"   Phone: {phone_number}")
            print(f"   Reservation: {reservation_number}")
            print(f"   Customer: {customer_name}")
            print(f"   Payment Amount: ${payment_amount}")
            print(f"   Confirmation: {confirmation_number}")
            print(f"   Date: {reservation_date}")
            print(f"   Time: {reservation_time}")
            print(f"   Party Size: {party_size}")
            
            # Validate required fields
            if not phone_number:
                return SwaigFunctionResult("Phone number is required to send payment receipt.")
            
            if not reservation_number:
                return SwaigFunctionResult("Reservation number is required to send payment receipt.")
            
            if not payment_amount or payment_amount <= 0:
                return SwaigFunctionResult("Payment amount is required to send payment receipt.")
            
            # Send the SMS
            sms_result = self._send_payment_receipt(
                phone_number=phone_number,
                reservation_number=reservation_number,
                customer_name=customer_name,
                payment_amount=payment_amount,
                confirmation_number=confirmation_number,
                reservation_date=reservation_date,
                reservation_time=reservation_time,
                party_size=party_size
            )
            
            if sms_result.get('success', False):
                message = f"✅ Payment receipt sent successfully to {phone_number}! "
                message += f"Your payment confirmation has been delivered."
                
                # Update metadata
                meta_data = raw_data.get('meta_data', {}) if raw_data else {}
                meta_data.update({
                    'payment_sms_sent': True,
                    'payment_sms_phone': phone_number,
                    'payment_sms_reservation': reservation_number,
                    'payment_sms_amount': payment_amount,
                    'payment_sms_timestamp': datetime.now().isoformat()
                })
                
                result = SwaigFunctionResult(message)
                result.set_metadata(meta_data)
                return result
            else:
                error_msg = sms_result.get('error', 'Unknown error')
                return SwaigFunctionResult(f"❌ Sorry, I couldn't send the payment receipt. {error_msg} Please try again or contact us directly.")
                
        except Exception as e:
            print(f"Error sending payment receipt SMS: {e}")
            return SwaigFunctionResult("Sorry, there was an error sending your payment receipt. Please try again or contact us directly.")

    def _send_payment_receipt(self, phone_number, reservation_number, customer_name=None, 
                             payment_amount=0, confirmation_number=None, reservation_date=None, 
                             reservation_time=None, party_size=1):
        """Send SMS payment receipt - internal helper method"""
        try:
            from datetime import datetime
            
            # Build SMS message for payment receipt
            sms_body = f"💳 Bobby's Table - Payment Receipt\n\n"
            sms_body += f"📋 Reservation: #{reservation_number}\n"
            
            if customer_name:
                sms_body += f"👤 Name: {customer_name}\n"
            
            if party_size and party_size > 1:
                sms_body += f"👥 Party Size: {party_size} people\n"
            else:
                sms_body += f"👥 Party Size: 1 person\n"
            
            if reservation_date:
                sms_body += f"📅 Date: {reservation_date}\n"
            
            if reservation_time:
                sms_body += f"⏰ Time: {reservation_time}\n"
            
            sms_body += f"💰 Amount Paid: ${payment_amount:.2f}\n"
            
            if confirmation_number:
                sms_body += f"🔖 Confirmation: {confirmation_number}\n"
            
            sms_body += f"✅ Payment Status: COMPLETED\n"
            sms_body += f"📅 Processed: {datetime.now().strftime('%m/%d/%Y %I:%M %p')}\n\n"
            sms_body += f"📍 Bobby's Table Restaurant\n"
            sms_body += f"📞 Questions? Call: {self._format_phone_number(os.getenv('SIGNALWIRE_FROM_NUMBER', '+15555555555'))}\n\n"
            sms_body += f"Thank you for dining with us!\n"
            sms_body += f"Reply STOP to opt out."
            
            # Get SignalWire credentials from environment
            signalwire_from_number = os.getenv('SIGNALWIRE_FROM_NUMBER', '+15555555555')
            
            print(f"📱 Sending Payment Receipt SMS via SignalWire:")
            print(f"   From: {signalwire_from_number}")
            print(f"   To: {phone_number}")
            print(f"   Region: us")
            print(f"   Body: {repr(sms_body)}")
            
            # Use SignalWire send_sms method
            result = SwaigFunctionResult()
            result = result.send_sms(
                to_number=phone_number,
                from_number=signalwire_from_number,
                body=sms_body,
                region="us"
            )
            
            print(f"✅ Payment receipt SMS sent successfully to {phone_number}")
            print(f"📱 Result type: {type(result)}")
            print(f"📱 Result: {result}")
            
            if hasattr(result, 'to_dict'):
                print(f"📱 Result dict: {json.dumps(result.to_dict(), indent=2)}")
            
            return {'success': True, 'result': result}
            
        except Exception as e:
            print(f"Error sending payment receipt SMS: {e}")
            return {'success': False, 'error': f"SMS sending failed: {str(e)}"}

    def _check_order_status_handler(self, args, raw_data):
        """Handle getting order details and status"""
        try:
            import sys
            import os
            from datetime import datetime, timedelta
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import Order, OrderItem, MenuItem, db
            
            order_number = (args.get('order_number') or '').strip()
            customer_phone = (args.get('customer_phone') or '').strip()
            customer_name = (args.get('customer_name') or '').strip()
            
            print(f"📋 Check Order Status Request:")
            print(f"   Order Number: {order_number}")
            print(f"   Customer Phone: {customer_phone}")
            print(f"   Customer Name: {customer_name}")
            
            # Validate input - need either order number, phone number, or customer name
            if not order_number and not customer_phone and not customer_name:
                return SwaigFunctionResult("I need either your order number, phone number, or customer name to check your order status.")
            
            with app.app_context():
                # Build query based on available information
                query = Order.query
                
                if order_number:
                    # Clean up order number (remove any non-digits)
                    order_number_clean = ''.join(filter(str.isdigit, order_number))
                    query = query.filter(Order.order_number == order_number_clean)
                
                if customer_phone:
                    # Clean up phone number
                    phone_clean = ''.join(filter(str.isdigit, customer_phone))
                    if len(phone_clean) == 10:
                        phone_clean = f"+1{phone_clean}"
                    elif len(phone_clean) == 11 and phone_clean.startswith('1'):
                        phone_clean = f"+{phone_clean}"
                    elif not phone_clean.startswith('+'):
                        phone_clean = f"+{phone_clean}"
                    
                    # Search by customer_phone OR by reservation phone number
                    from models import Reservation
                    query = query.outerjoin(Reservation, Order.reservation_id == Reservation.id)
                    query = query.filter(
                        (Order.customer_phone == phone_clean) | 
                        (Reservation.phone_number == phone_clean)
                    )
                
                # Add name-based search if provided (and no order number specified)
                if customer_name and not order_number:
                    # Search by customer name in order records
                    query = query.filter(Order.person_name.ilike(f"%{customer_name}%"))
                    print(f"🔍 Searching by customer name: {customer_name}")
                
                # Get orders, prioritizing recent ones
                orders = query.order_by(Order.created_at.desc()).limit(5).all()
                
                if not orders:
                    if order_number:
                        return SwaigFunctionResult(f"❌ No order found with number {order_number}. Please check your order number and try again.")
                    else:
                        return SwaigFunctionResult(f"❌ No orders found for phone number {customer_phone}. Please check your phone number and try again.")
                
                # If multiple orders, show the most recent one or ask for clarification
                if len(orders) > 1 and not order_number:
                    message = f"📋 I found {len(orders)} orders for your phone number:\n\n"
                    for order in orders[:3]:  # Show up to 3 recent orders
                        message += f"• Order #{order.order_number} - {order.status.title()} - ${order.total_amount:.2f}\n"
                        message += f"  Placed: {order.created_at.strftime('%m/%d/%Y %I:%M %p')}\n"
                        if order.target_date and order.target_time:
                            message += f"  Ready: {order.target_date} at {order.target_time}\n"
                        message += "\n"
                    
                    message += "Please provide your specific order number to get detailed status information."
                    return SwaigFunctionResult(message)
                
                # Get the order (first one if multiple)
                order = orders[0]
                
                # Verify customer name if provided
                if customer_name and order.person_name:
                    name_match = customer_name.lower() in order.person_name.lower() or order.person_name.lower() in customer_name.lower()
                    if not name_match:
                        return SwaigFunctionResult(f"❌ The name provided doesn't match our records for order #{order.order_number}. Please verify your information.")
                
                # Build status message
                status_emoji = {
                    'pending': '⏳',
                    'preparing': '👨‍🍳',
                    'ready': '✅',
                    'completed': '📦',
                    'cancelled': '❌'
                }
                
                status_descriptions = {
                    'pending': 'Order received, waiting to be prepared',
                    'preparing': 'Order is being prepared in the kitchen',
                    'ready': 'Order is ready for pickup/delivery',
                    'completed': 'Order has been picked up/delivered',
                    'cancelled': 'Order has been cancelled'
                }
                
                # Get the format from args, default to text
                response_format = args.get('format', 'text').lower()

                if response_format == 'json':
                    # Build structured JSON response
                    order_data = {
                        'order_number': order.order_number,
                        'customer_name': order.person_name or 'N/A',
                        'customer_phone': order.customer_phone or 'N/A',
                        'order_type': order.order_type.title() if order.order_type else 'Pickup',
                        'status': order.status.upper(),
                        'status_description': status_descriptions.get(order.status, 'Status information not available'),
                        'target_date': order.target_date,
                        'target_time': order.target_time,
                        'items': [
                            {
                                'name': item.menu_item.name if item.menu_item else "Unknown Item",
                                'quantity': item.quantity,
                                'price': item.price_at_time * item.quantity,
                                'notes': item.notes
                            } for item in order.items
                        ],
                        'total_amount': order.total_amount,
                        'special_instructions': order.special_instructions,
                        'customer_address': order.customer_address if order.order_type == 'delivery' else None,
                        'payment_status': order.payment_status.title() if order.payment_status else 'N/A'
                    }
                    return SwaigFunctionResult(json.dumps(order_data))

                message = f"📋 **ORDER STATUS UPDATE**\n\n"
                message += f"🔢 Order Number: #{order.order_number}\n"
                message += f"👤 Customer: {order.person_name or 'N/A'}\n"
                message += f"📱 Phone: {order.customer_phone or 'N/A'}\n"
                message += f"📦 Type: {order.order_type.title() if order.order_type else 'Pickup'}\n\n"
                
                message += f"{status_emoji.get(order.status, '📋')} **Status: {order.status.upper()}**\n"
                message += f"   {status_descriptions.get(order.status, 'Status information not available')}\n\n"
                
                # Add timing information
                if order.target_date and order.target_time:
                    try:
                        target_datetime = datetime.strptime(f"{order.target_date} {order.target_time}", "%Y-%m-%d %H:%M")
                        now = datetime.now()
                        
                        if order.status == 'ready':
                            message += f"🎯 **Ready for {order.order_type or 'pickup'}!**\n"
                            if order.order_type == 'pickup':
                                message += f"📍 Please come to Bobby's Table to collect your order.\n"
                            else:
                                message += f"🚚 Your order is ready for delivery to {order.customer_address or 'your address'}.\n"
                        elif order.status == 'preparing':
                            time_diff = target_datetime - now
                            if time_diff.total_seconds() > 0:
                                minutes_left = int(time_diff.total_seconds() // 60)
                                message += f"⏰ Estimated ready time: {target_datetime.strftime('%I:%M %p')} ({minutes_left} minutes)\n"
                            else:
                                message += f"⏰ Should be ready soon!\n"
                        elif order.status == 'pending':
                            message += f"⏰ Target ready time: {target_datetime.strftime('%I:%M %p')}\n"
                        elif order.status == 'completed':
                            message += f"✅ Completed at: {target_datetime.strftime('%I:%M %p')}\n"
                        
                        message += f"📅 Date: {target_datetime.strftime('%A, %B %d, %Y')}\n\n"
                        
                    except ValueError:
                        message += f"📅 Target: {order.target_date} at {order.target_time}\n\n"
                
                # Add order items
                if order.items:
                    message += f"🍽️ **Order Items:**\n"
                    for item in order.items:
                        item_name = item.menu_item.name if item.menu_item else "Unknown Item"
                        message += f"• {item.quantity}x {item_name} - ${item.price_at_time * item.quantity:.2f}\n"
                        if item.notes:
                            message += f"  Note: {item.notes}\n"
                    
                    message += f"\n💰 **Total: ${order.total_amount:.2f}**\n"
                
                # Add special instructions
                if order.special_instructions:
                    message += f"\n📝 Special Instructions: {order.special_instructions}\n"
                
                # Add delivery address if applicable
                if order.order_type == 'delivery' and order.customer_address:
                    message += f"\n📍 Delivery Address: {order.customer_address}\n"
                
                # Add payment status
                if order.payment_status:
                    payment_emoji = {'paid': '✅', 'unpaid': '⏳', 'refunded': '🔄'}
                    message += f"\n💳 Payment: {payment_emoji.get(order.payment_status, '❓')} {order.payment_status.title()}\n"
                
                # Add helpful next steps
                message += f"\n📞 Questions? Call us at {self._format_phone_number(os.getenv('SIGNALWIRE_FROM_NUMBER', '+15555555555'))}\n"
                message += f"🏪 Bobby's Table Restaurant"
                
                # Update metadata
                meta_data = raw_data.get('meta_data', {}) if raw_data else {}
                meta_data.update({
                    'order_status_checked': True,
                    'order_number': order.order_number,
                    'order_status': order.status,
                    'order_type': order.order_type,
                    'check_timestamp': datetime.now().isoformat()
                })
                
                result = SwaigFunctionResult(message)
                result.set_metadata(meta_data)
                return result
                
        except Exception as e:
            print(f"Error checking order status: {e}")
            import traceback
            traceback.print_exc()
            return SwaigFunctionResult(f"Sorry, there was an error checking your order status. Please try again or contact us directly at {self._format_phone_number(os.getenv('SIGNALWIRE_FROM_NUMBER', '+15555555555'))}.") 

    def _update_order_items_handler(self, args, raw_data):
        """Handle updating order items (add/remove)"""
        try:
            import sys
            import os
            from datetime import datetime
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import Order, OrderItem, MenuItem, Reservation, db
            
            order_number = (args.get('order_number') or '').strip()
            customer_phone = (args.get('customer_phone') or '').strip()
            customer_name = (args.get('customer_name') or '').strip()
            action = args.get('action', 'add').lower()
            items = args.get('items', [])
            
            print(f"📋 Update Order Items Request:")
            print(f"   Order Number: {order_number}")
            print(f"   Customer Phone: {customer_phone}")
            print(f"   Customer Name: {customer_name}")
            print(f"   Action: {action}")
            print(f"   Items: {items}")
            
            # Validate input
            if not order_number and not customer_phone and not customer_name:
                return SwaigFunctionResult("I need either your order number, phone number, or customer name to find your order.")
            
            if not items:
                return SwaigFunctionResult("Please specify which items you'd like to add or remove.")
            
            if action not in ['add', 'remove']:
                return SwaigFunctionResult("Please specify whether you want to 'add' or 'remove' items.")
            
            with app.app_context():
                # Ensure menu is cached for item validation
                cached_menu, meta_data = self._ensure_menu_cached(raw_data)
                
                if not cached_menu:
                    return SwaigFunctionResult("Sorry, our menu system is temporarily unavailable. Please try again later.")
                
                # Find the order using the same logic as get_order_details
                query = Order.query
                
                if order_number:
                    # Clean up order number (remove any non-digits)
                    order_number_clean = ''.join(filter(str.isdigit, order_number))
                    query = query.filter(Order.order_number == order_number_clean)
                
                if customer_phone:
                    # Clean up phone number
                    phone_clean = ''.join(filter(str.isdigit, customer_phone))
                    if len(phone_clean) == 10:
                        phone_clean = f"+1{phone_clean}"
                    elif len(phone_clean) == 11 and phone_clean.startswith('1'):
                        phone_clean = f"+{phone_clean}"
                    elif not phone_clean.startswith('+'):
                        phone_clean = f"+{phone_clean}"
                    
                    # Search by customer_phone OR by reservation phone number
                    query = query.outerjoin(Reservation, Order.reservation_id == Reservation.id)
                    query = query.filter(
                        (Order.customer_phone == phone_clean) | 
                        (Reservation.phone_number == phone_clean)
                    )
                
                # Add name-based search if provided (and no order number specified)
                if customer_name and not order_number:
                    query = query.filter(Order.person_name.ilike(f"%{customer_name}%"))
                
                # Get orders, prioritizing recent ones
                orders = query.order_by(Order.created_at.desc()).limit(5).all()
                
                if not orders:
                    if order_number:
                        return SwaigFunctionResult(f"❌ No order found with number {order_number}. Please check your order number and try again.")
                    else:
                        return SwaigFunctionResult("❌ No orders found. Please check your information and try again.")
                
                # If multiple orders, we need to be more specific
                if len(orders) > 1 and not order_number:
                    message = f"📋 I found {len(orders)} orders. Please provide your specific order number:\n\n"
                    for order in orders[:3]:  # Show up to 3 recent orders
                        message += f"• Order #{order.order_number} - {order.status.title()} - ${order.total_amount:.2f}\n"
                        message += f"  Placed: {order.created_at.strftime('%m/%d/%Y %I:%M %p')}\n\n"
                    return SwaigFunctionResult(message)
                
                # Get the order
                order = orders[0]
                
                # Check if order can be updated based on type and status
                can_update = False
                reason = ""
                
                if order.order_type == 'reservation':
                    # For reservation orders, check payment status
                    if order.payment_status != 'paid':
                        can_update = True
                    else:
                        reason = "This reservation order has already been paid for and cannot be modified."
                elif order.order_type in ['pickup', 'delivery']:
                    # For pickup/delivery orders, check order status
                    if order.status == 'pending':
                        can_update = True
                    else:
                        reason = f"This {order.order_type} order is already {order.status} and cannot be modified."
                else:
                    # Default check for other order types
                    if order.status == 'pending' and order.payment_status != 'paid':
                        can_update = True
                    else:
                        reason = f"This order is {order.status} and cannot be modified."
                
                if not can_update:
                    return SwaigFunctionResult(f"❌ {reason}")
                
                # Create menu lookup for faster access
                menu_lookup = {item['name'].lower(): item for item in cached_menu}
                
                # Process items
                updated_items = []
                total_change = 0.0
                
                for item_spec in items:
                    item_name = item_spec.get('name', '').strip()
                    quantity = item_spec.get('quantity', 1)
                    
                    if not item_name:
                        continue
                    
                    # Validate quantity
                    try:
                        quantity = int(quantity)
                        if quantity <= 0:
                            quantity = 1
                    except (ValueError, TypeError):
                        quantity = 1
                    
                    # Find menu item with validation
                    menu_item_data = None
                    item_name_lower = item_name.lower()
                    
                    # Try exact match first
                    if item_name_lower in menu_lookup:
                        menu_item_data = menu_lookup[item_name_lower]
                    else:
                        # Try fuzzy matching
                        best_match = None
                        best_score = 0
                        
                        for cached_item in cached_menu:
                            cached_name_lower = cached_item['name'].lower()
                            
                            # Check for partial matches
                            if item_name_lower in cached_name_lower or cached_name_lower in item_name_lower:
                                # Calculate match score
                                common_words = set(item_name_lower.split()) & set(cached_name_lower.split())
                                score = len(common_words) / max(len(cached_name_lower.split()), 1)
                                
                                if score > best_score and score > 0.3:
                                    best_match = cached_item
                                    best_score = score
                        
                        menu_item_data = best_match
                    
                    if not menu_item_data:
                        return SwaigFunctionResult(f"Sorry, I couldn't find '{item_name}' on our menu. Please check the menu and try again.")
                    
                    if not menu_item_data['is_available']:
                        return SwaigFunctionResult(f"Sorry, {menu_item_data['name']} is currently unavailable.")
                    
                    # Process the action
                    if action == 'add':
                        # Add items to order
                        existing_item = OrderItem.query.filter_by(
                            order_id=order.id,
                            menu_item_id=menu_item_data['id']
                        ).first()
                        
                        if existing_item:
                            existing_item.quantity += quantity
                            updated_items.append(f"Added {quantity}x {menu_item_data['name']} (now {existing_item.quantity} total)")
                        else:
                            new_order_item = OrderItem(
                                order_id=order.id,
                                menu_item_id=menu_item_data['id'],
                                quantity=quantity,
                                price_at_time=menu_item_data['price']
                            )
                            db.session.add(new_order_item)
                            updated_items.append(f"Added {quantity}x {menu_item_data['name']}")
                        
                        total_change += menu_item_data['price'] * quantity
                        
                    elif action == 'remove':
                        # Remove items from order
                        existing_item = OrderItem.query.filter_by(
                            order_id=order.id,
                            menu_item_id=menu_item_data['id']
                        ).first()
                        
                        if not existing_item:
                            return SwaigFunctionResult(f"'{menu_item_data['name']}' is not in your order, so I can't remove it.")
                        
                        if existing_item.quantity <= quantity:
                            # Remove the item entirely
                            removed_quantity = existing_item.quantity
                            total_change -= menu_item_data['price'] * removed_quantity
                            db.session.delete(existing_item)
                            updated_items.append(f"Removed all {removed_quantity}x {menu_item_data['name']}")
                        else:
                            # Reduce quantity
                            existing_item.quantity -= quantity
                            total_change -= menu_item_data['price'] * quantity
                            updated_items.append(f"Removed {quantity}x {menu_item_data['name']} (now {existing_item.quantity} remaining)")
                
                # Update order total
                order.total_amount = (order.total_amount or 0.0) + total_change
                
                # Commit changes
                db.session.commit()
                
                # Build response message
                action_word = "added to" if action == 'add' else "removed from"
                message = f"✅ **ORDER UPDATED SUCCESSFULLY**\n\n"
                message += f"🔢 Order Number: #{order.order_number}\n"
                message += f"👤 Customer: {order.person_name or 'N/A'}\n\n"
                message += f"📝 **Items {action_word} your order:**\n"
                
                for item in updated_items:
                    message += f"• {item}\n"
                
                message += f"\n💰 **Order Total: ${order.total_amount:.2f}**"
                
                if total_change > 0:
                    message += f" (increased by ${total_change:.2f})"
                elif total_change < 0:
                    message += f" (decreased by ${abs(total_change):.2f})"
                
                message += f"\n\n📋 **Order Status:** {order.status.title()}"
                
                if order.order_type == 'reservation':
                    message += f"\n🏠 **Type:** Reservation Order"
                else:
                    message += f"\n📦 **Type:** {order.order_type.title()}"
                
                message += f"\n\n📞 Questions? Call us at {self._format_phone_number(os.getenv('SIGNALWIRE_FROM_NUMBER', '+15555555555'))}"
                
                return SwaigFunctionResult(message)
                
        except Exception as e:
            print(f"Error updating order items: {e}")
            import traceback
            traceback.print_exc()
            return SwaigFunctionResult(f"Sorry, there was an error updating your order. Please try again or call us directly at {self._format_phone_number(os.getenv('SIGNALWIRE_FROM_NUMBER', '+15555555555'))}.")

    def _detect_affirmative_response(self, call_log, context="payment"):
        """Detect if user gave an affirmative response in recent conversation"""
        if not call_log:
            return False
        
        # Common affirmative responses
        affirmative_patterns = [
            r'\b(yes|yeah|yep|yup|sure|okay|ok|alright|absolutely|definitely)\b',
            r'\b(let\'s do it|go ahead|sounds good|that works|perfect)\b',
            r'\b(i\'d like to|i want to|i would like to)\b.*\b(pay|payment)\b',
            r'\b(pay|payment|credit card|card)\b',
            r'\b(proceed|continue|confirm)\b'
        ]
        
        # Check the last few user messages for affirmative responses
        recent_entries = [entry for entry in reversed(call_log) if entry.get('role') == 'user'][:3]
        
        for entry in recent_entries:
            if entry.get('content'):
                content = entry.get('content', '').lower().strip()
                
                # Check for affirmative patterns
                for pattern in affirmative_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        print(f"🔍 Detected affirmative response for {context}: '{content}'")
                        return True
                
                # Also check for simple single-word responses
                if content in ['yes', 'yeah', 'yep', 'yup', 'sure', 'okay', 'ok', 'alright']:
                    print(f"🔍 Detected simple affirmative response: '{content}'")
                    return True
        
        return False

    def _pay_order_handler(self, args, raw_data):
        """Process payment using SWML pay verb with Stripe integration - handles both new and existing orders"""
        print("🔧 Entering _pay_order_handler")
        print(f"🔍 Function args: {args}")
        print(f"🔍 Function raw_data keys: {list(raw_data.keys()) if raw_data else None}")
        
        # Initialize result to None to help debug scope issues
        result = None
        print("🔍 Initialized result variable to None")
        
        try:
            from signalwire_agents.core.function_result import SwaigFunctionResult
            import os
            import re
            print("✅ Imports successful")
            
            # Extract meta_data for session management
            meta_data = raw_data.get('meta_data', {}) if raw_data else {}
            print(f"🔍 Current meta_data: {meta_data}")
            
            # Get call_id for payment session integration
            call_id = raw_data.get('call_id') if raw_data else None
            print(f"🔍 Call ID: {call_id}")
            
            # Extract basic payment information
            order_number = args.get('order_number')
            cardholder_name = args.get('cardholder_name')
            phone_number = args.get('phone_number')
            
            # Get phone number from caller ID if not provided
            if not phone_number:
                caller_phone = raw_data.get('caller_id_num') or raw_data.get('caller_id_number')
                if caller_phone:
                    phone_number = caller_phone
                    print(f"🔄 Using phone number from caller ID: {phone_number}")
            
            # AUTO-DETECT: Check if this is for a newly created order from session metadata
            if not order_number:
                # Check meta_data for recently created order
                order_created = meta_data.get('order_created')
                session_order_number = meta_data.get('order_number')
                payment_needed = meta_data.get('payment_needed')
                
                print(f"🔍 Auto-detection check:")
                print(f"   order_created: {order_created}")
                print(f"   session_order_number: {session_order_number}")
                print(f"   payment_needed: {payment_needed}")
                
                # Enhanced: Check for affirmative response to payment after order creation
                if (order_created and session_order_number and payment_needed and 
                    not args.get('order_number')):
                    # Check if user gave an affirmative response recently
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    if self._detect_affirmative_response(call_log, "payment"):
                        print(f"🔍 Detected affirmative payment response after order creation")
                        # Auto-fill ALL payment information from session
                        order_number = session_order_number
                        if not cardholder_name and meta_data.get('customer_name'):
                            cardholder_name = meta_data.get('customer_name')
                        if not phone_number and meta_data.get('phone_number'):
                            phone_number = meta_data.get('phone_number')
                        print(f"🔍 Auto-filled payment info: order#{order_number}, name={cardholder_name}, phone={phone_number}")
                
                if order_created and session_order_number:
                    order_number = session_order_number
                    print(f"🔍 Auto-detected new order from session: #{order_number}")
                    
                    # Also auto-fill cardholder name if available
                    if not cardholder_name:
                        session_customer_name = meta_data.get('customer_name')
                        if session_customer_name:
                            cardholder_name = session_customer_name
                            print(f"🔍 Auto-detected cardholder name: {cardholder_name}")
                    
                    # Auto-fill phone number if available
                    if not phone_number:
                        session_phone = meta_data.get('phone_number')
                        if session_phone:
                            phone_number = session_phone
                            print(f"🔍 Auto-detected phone number: {phone_number}")
                else:
                    # Try to detect from conversation history
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    for entry in reversed(call_log[-10:]):  # Check last 10 entries
                        if (entry.get('role') == 'assistant' and 
                            entry.get('content') and 
                            'order confirmed' in entry.get('content', '').lower()):
                            
                            # Try to extract order number from the assistant's message
                            content = entry.get('content', '')
                            order_match = re.search(r'Order #(\w+)', content)
                            if order_match:
                                order_number = order_match.group(1)
                                print(f"🔍 Auto-detected order from conversation: #{order_number}")
                                break
            
            # ENHANCED: Also check if we have session context but parameters were not auto-filled
            # CRITICAL FIX: Use main metadata order_number as highest priority
            if not order_number and meta_data.get('order_number'):
                order_number = meta_data.get('order_number')
                print(f"🔍 Using order_number from meta_data: #{order_number}")
                
            # BACKUP: Only fall back to verified_order if no main order_number found
            if not order_number and meta_data.get('verified_order', {}).get('order_number'):
                backup_order_number = meta_data.get('verified_order', {}).get('order_number')
                print(f"🔄 BACKUP: Using verified_order.order_number: #{backup_order_number}")
                order_number = backup_order_number
                
            if not cardholder_name and meta_data.get('customer_name'):
                cardholder_name = meta_data.get('customer_name')
                print(f"🔍 Using customer_name as cardholder_name from meta_data: {cardholder_name}")
                
            if not phone_number and meta_data.get('phone_number'):
                phone_number = meta_data.get('phone_number')
                print(f"🔍 Using phone_number from meta_data: {phone_number}")
            
            # Validate required information - but be smarter about what we ask for
            if not order_number:
                result = SwaigFunctionResult(
                    "I need your order number to process the payment. "
                    "What's your order number?"
                )
                result.set_metadata({
                    "payment_step": "need_order_number",
                    "cardholder_name": cardholder_name,
                    "phone_number": phone_number
                })
                return result
            
            # STEP 1: Look up order and show bill summary FIRST (before asking for cardholder name)
            # Look up order and calculate total
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app, start_payment_session
            from models import Order, OrderItem, MenuItem
            
            with app.app_context():
                order = Order.query.filter_by(order_number=order_number).first()
                if not order:
                    result = SwaigFunctionResult(
                        f"I couldn't find an order with number {order_number}. "
                        "Please check the number and try again."
                    )
                    result.set_metadata({
                        "payment_step": "error",
                        "error": "order_not_found"
                    })
                    return result
                
                print(f"✅ Found order: {order.person_name}, {order.order_type}, ${order.total_amount}")
                
                # Check if order can be paid
                if order.payment_status == 'paid':
                    return SwaigFunctionResult(f"✅ Order #{order.order_number} has already been paid for. Your payment confirmation number is {order.confirmation_number or 'N/A'}.")
                
                if order.status == 'cancelled':
                    return SwaigFunctionResult(f"❌ Order #{order.order_number} has been cancelled and cannot be paid for.")
                
                # Get total amount
                total_amount = round(order.total_amount or 0.0, 2)
                
                # Get order items for display
                order_items = OrderItem.query.filter_by(order_id=order.id).all()
                print(f"🔍 Found {len(order_items)} items for order {order_number}")
                
                # CHECK: Has the customer already confirmed the bill total?
                payment_confirmed = meta_data.get('payment_confirmed')
                payment_step = meta_data.get('payment_step')
                
                # If we're waiting for confirmation, check if user just gave an affirmative response
                if payment_step == 'awaiting_confirmation' and not payment_confirmed:
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    if self._detect_affirmative_response(call_log, "payment confirmation"):
                        payment_confirmed = True
                        print(f"🔍 Customer confirmed payment - proceeding with credit card collection")
                        
                        # CRITICAL FIX: Save confirmation state to metadata so it persists between function calls
                        current_metadata = meta_data.copy() if meta_data else {}
                        current_metadata['payment_confirmed'] = True
                        current_metadata['payment_step'] = 'confirmed'
                        
                        # Update the metadata in the raw_data for persistence
                        if hasattr(raw_data, 'get') and 'meta_data' in raw_data:
                            raw_data['meta_data'].update(current_metadata)
                        
                        meta_data = current_metadata  # Update local meta_data reference
                    else:
                        # Check for negative responses
                        negative_patterns = [
                            r'\b(no|nope|not|don\'t|cancel|stop|nevermind|never mind)\b',
                            r'\b(i don\'t want|i changed my mind|not interested)\b'
                        ]
                        
                        recent_entries = [entry for entry in reversed(call_log) if entry.get('role') == 'user'][:2]
                        for entry in recent_entries:
                            if entry.get('content'):
                                content = entry.get('content', '').lower().strip()
                                for pattern in negative_patterns:
                                    if re.search(pattern, content, re.IGNORECASE):
                                        print(f"🔍 Customer declined payment: '{content}'")
                                        result = SwaigFunctionResult(
                                            "No problem! Your order is still confirmed. "
                                            "You can pay when you pick up your order. "
                                            "Is there anything else I can help you with?"
                                        )
                                        result.set_metadata({
                                            "payment_step": "cancelled",
                                            "order_number": order_number
                                        })
                                        return result
                
                # STEP 2: Show bill summary and ask for confirmation (if not confirmed yet)
                if not payment_confirmed:
                    print(f"🔍 Showing bill total for confirmation: ${total_amount:.2f}")
                    
                    # Use order name for display, not cardholder name (since we don't have it yet)
                    customer_display_name = order.person_name
                    
                    # Create detailed order breakdown
                    order_details = []
                    if order_items:
                        for item in order_items:
                            menu_item = MenuItem.query.get(item.menu_item_id)
                            item_name = menu_item.name if menu_item else f"Item #{item.menu_item_id}"
                            order_details.append(f"• {item.quantity}x {item_name} - ${item.price_at_time * item.quantity:.2f}")
                    
                    message = f"📋 Bill Summary for Order #{order_number}\n\n"
                    message += f"👤 Customer: {customer_display_name}\n"
                    message += f"📦 Order Type: {order.order_type.title()}\n\n"
                    if order_details:
                        message += f"🍽️ Your Order:\n"
                        message += "\n".join(order_details) + "\n\n"
                    message += f"💰 Total Amount: ${total_amount:.2f}\n\n"
                    message += f"Would you like to proceed with payment of ${total_amount:.2f}? Please say 'yes' to continue or 'no' to cancel."
                    
                    # Return with confirmation request
                    result = SwaigFunctionResult(message)
                    result.set_metadata({
                        "payment_step": "awaiting_confirmation",
                        "order_number": order_number,
                        "customer_name": customer_display_name,
                        "cardholder_name": customer_display_name,  # AUTO-POPULATE: Use order name as cardholder name
                        "phone_number": phone_number,
                        "total_amount": total_amount,
                        "order_details": {
                            "order_number": order_number,
                            "customer_name": customer_display_name,
                            "order_type": order.order_type,
                            "order_id": order.id
                        }
                    })
                    return result
                
                # STEP 3: Payment confirmed - automatically use order name as cardholder name
                if not cardholder_name:
                    # Always use the order name as cardholder name (no need to ask)
                    if order.person_name:
                        cardholder_name = order.person_name
                        print(f"🔍 Auto-using order name as cardholder name: {cardholder_name}")
                    elif meta_data.get('customer_name'):
                        cardholder_name = meta_data.get('customer_name')
                        print(f"🔍 Auto-using customer name as cardholder name: {cardholder_name}")
                    else:
                        cardholder_name = "Card Holder"  # Default fallback
                        print(f"🔍 Using default cardholder name: {cardholder_name}")
                
                # STEP 4: We have confirmation AND cardholder name - proceed with payment
                print(f"🔍 Payment confirmed and cardholder name provided, proceeding with credit card collection for ${total_amount:.2f}")
                
                # Create the parameters array with cardholder_name to pre-populate SignalWire payment form
                parameters_array = [
                    {"name": "order_number", "value": order_number},
                    {"name": "customer_name", "value": cardholder_name},
                    {"name": "cardholder_name", "value": cardholder_name},  # Pre-populate to skip name prompt
                    {"name": "phone_number", "value": phone_number or ""},
                    {"name": "payment_type", "value": "order"}
                ]
                
                # Only add call_id if it has a non-empty value
                if call_id and call_id.strip():
                    parameters_array.append({"name": "call_id", "value": call_id})
                    print(f"🔍 Added call_id to parameters: {call_id}")
                
                # Create response message with payment result variables for immediate feedback
                if meta_data.get('order_created'):
                    message = f"🔄 Processing payment for ${total_amount:.2f}...\n\n"
                    message += f"I'll now collect your credit card information securely. Please have your card ready.\n\n"
                else:
                    message = f"🔄 Processing payment for ${total_amount:.2f}...\n\n"
                    message += f"I'll now collect your credit card information securely. Please have your card ready.\n\n"
                
                # Add SignalWire payment result variables for immediate success/failure feedback
                message += f"${{pay_payment_results.success ? "
                message += f"'🎉 Excellent! Your payment of ${total_amount:.2f} has been processed successfully! ' + "
                message += f"'Your confirmation number is ' + pay_payment_results.confirmation_number + '. ' + "
                message += f"'Thank you for ordering from Bobby\\'s Table!' : "
                message += f"'I\\'m sorry, there was an issue processing your payment: ' + pay_payment_results.error_message + '. ' + "
                message += f"'Please try again or contact the restaurant for assistance.'}}"
                
                # Create SwaigFunctionResult
                result = SwaigFunctionResult(message)
                
                # Set meta_data for payment tracking
                result.set_metadata({
                    "payment_step": "processing_payment",
                    "verified_order": {
                        "order_number": order_number,
                        "customer_name": cardholder_name,
                        "order_type": order.order_type,
                        "cardholder_name": cardholder_name,
                        "phone_number": phone_number,
                        "total_amount": total_amount,
                        "order_id": order.id
                    },
                    "payment_session_active": True
                })
                
                # Get payment URLs from environment
                base_url = os.getenv('SIGNALWIRE_PAYMENT_CONNECTOR_URL') or os.getenv('BASE_URL', 'https://localhost:8080')
                
                if base_url and not base_url.endswith('/api/payment-processor'):
                    payment_connector_url = f"{base_url.rstrip('/')}/api/payment-processor"
                else:
                    payment_connector_url = base_url or f"{os.getenv('BASE_URL', 'https://localhost:8080')}/api/payment-processor"
                
                status_url = payment_connector_url.replace('/api/payment-processor', '/api/signalwire/payment-callback')
                
                print(f"🔗 Using payment connector URL: {payment_connector_url}")
                
                # CRITICAL: Start payment session for callback tracking
                if call_id:
                    start_payment_session(call_id, order_number)
                    print(f"✅ Started payment session for call {call_id}, order {order_number}")
                else:
                    print(f"⚠️ No call_id provided - payment session tracking may be limited")
                
                # Use SignalWire SDK v0.1.26 pay() method
                try:
                    print(f"✅ Using SignalWire SDK pay() method")
                    result.pay(
                        payment_connector_url=payment_connector_url,
                        input_method="dtmf",
                        status_url=status_url,
                        payment_method="credit-card",
                        timeout=8,  # Increased to 2 minutes for realistic phone payment
                        max_attempts=5,  # Increased to 5 attempts
                        security_code=True,
                        postal_code=True,
                        min_postal_code_length=5,
                        token_type="one-time",
                        charge_amount=f"{total_amount:.2f}",
                        currency="usd",
                        language="en-US",
                        voice="rime.spore",
                        description=f"Bobby's Table Order #{order_number}",
                        valid_card_types="visa mastercard amex discover diners jcb unionpay",
                        ai_response="The payment status is ${pay_results}, do not mention anything else about collecting payment if successful",
                        parameters=parameters_array
                    )
                    print(f"✅ result.pay() completed successfully")
                except Exception as pay_error:
                    print(f"❌ Error in result.pay(): {pay_error}")
                    import traceback
                    traceback.print_exc()
                    raise  # Re-raise to be caught by outer exception handler
                
                print(f"✅ Payment collection configured for ${total_amount} - Order #{order_number}")
                return result
                
        except Exception as e:
            print(f"❌ Error processing payment: {e}")
            print(f"🔍 Exception type: {type(e)}")
            import traceback
            traceback.print_exc()
            
            # Create new result for error handling
            error_result = SwaigFunctionResult(
                "I'm sorry, there was an error processing your payment. "
                "Please try again or contact the restaurant directly."
            )
            error_result.set_metadata({
                "payment_step": "error",
                "error": str(e)
            })
            return error_result

    def _payment_retry_handler(self, args, raw_data):
        """Handle payment retry when the previous payment failed"""
        from signalwire_agents.core.function_result import SwaigFunctionResult
        
        try:
            print(f"🔄 Payment retry handler called with args: {args}")
            
            # Extract meta_data and call information
            meta_data = raw_data.get('meta_data', {}) if raw_data else {}
            call_id = raw_data.get('call_id') if raw_data else None
            
            # Get payment session data to understand what failed
            payment_session = None
            if call_id:
                # Import app to access payment_sessions
                import sys
                import os
                parent_dir = os.path.dirname(os.path.dirname(__file__))
                if parent_dir not in sys.path:
                    sys.path.insert(0, parent_dir)
                from app import app
                
                payment_sessions = getattr(app, 'payment_sessions', {})
                payment_session = payment_sessions.get(call_id)
                
            if payment_session and payment_session.get('payment_status') == 'failed':
                error_type = payment_session.get('error_type', 'unknown')
                failure_reason = payment_session.get('failure_reason', 'payment-failed')
                attempt = payment_session.get('attempt', '1')
                
                print(f"🔍 Previous payment failed: {error_type} ({failure_reason}) - attempt {attempt}")
                
                if error_type == 'invalid-card-type':
                    response_text = (
                        "I see your previous payment was declined because the card type wasn't recognized. "
                        "Please make sure you're using a Visa, Mastercard, American Express, or Discover card. "
                        "Would you like to try again with a different card?"
                    )
                elif error_type == 'invalid-card-number':
                    response_text = (
                        "Your card number wasn't recognized. Please double-check the card number and try again. "
                        "Would you like to retry the payment?"
                    )
                elif error_type == 'card-declined':
                    response_text = (
                        "Your card was declined by your bank. You may want to contact your bank or try a different card. "
                        "Would you like to try again?"
                    )
                else:
                    response_text = (
                        f"Your payment encountered an issue ({error_type}). "
                        "Would you like to try again or would you prefer to pay when you pick up your order?"
                    )
                
                return SwaigFunctionResult(response_text)
            
            # If no failed payment session, treat as a general retry request
            order_number = args.get('order_number') or meta_data.get('order_number')
            if not order_number:
                return SwaigFunctionResult(
                    "I'd be happy to help you retry your payment. Could you please provide your order number?"
                )
            
            # Check if user wants to retry
            call_log = raw_data.get('call_log', []) if raw_data else []
            user_wants_retry = self._detect_affirmative_response(call_log, "payment retry")
            
            if user_wants_retry:
                # Clear the failed payment status and retry
                if call_id and payment_session:
                    payment_session.pop('payment_status', None)
                    payment_session.pop('error_type', None)
                    payment_session.pop('failure_reason', None)
                    print(f"🔄 Cleared failed payment status for retry")
                
                # Call the main payment handler
                return self._pay_order_handler(args, raw_data)
            else:
                return SwaigFunctionResult(
                    "No problem! You can also pay when you pick up your order. "
                    "Your order is still confirmed. Is there anything else I can help you with?"
                )
                
        except Exception as e:
            print(f"❌ Error in payment retry handler: {e}")
            import traceback
            traceback.print_exc()
            
            return SwaigFunctionResult(
                "I'm sorry, I encountered an error with the payment retry. "
                "You can pay when you pick up your order. Is there anything else I can help you with?"
            ) 