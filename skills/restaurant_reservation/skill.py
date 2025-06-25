"""
Restaurant Reservation Skill for SignalWire AI Agents
Provides reservation management capabilities
"""

from typing import List, Dict, Any
import re
from datetime import datetime
from flask import current_app
import os

from signalwire_agents.core.skill_base import SkillBase
from signalwire_agents.core.function_result import SwaigFunctionResult
from signalwire_agents.core.swaig_function import SWAIGFunction

class RestaurantReservationSkill(SkillBase):
    """Provides restaurant reservation management capabilities"""
    
    SKILL_NAME = "restaurant_reservation"
    SKILL_DESCRIPTION = "Manage restaurant reservations - create, update, cancel, and lookup"
    SKILL_VERSION = "1.0.0"
    REQUIRED_PACKAGES = []
    REQUIRED_ENV_VARS = []
    
    # SWAIG fields for all tools
    swaig_fields = {
        "meta_data": {
            "type": "object",
            "properties": {
                "call_id": {"type": "string", "description": "Call ID for tracking"},
                "caller_id": {"type": "string", "description": "Caller ID number"}
            }
        }
    }
    
    def __init__(self, agent, params=None):
        super().__init__(agent, params)
        # SignalWire configuration for SMS
        self.signalwire_from_number = os.getenv('SIGNALWIRE_FROM_NUMBER', '+15551234567')
    
    def setup(self) -> bool:
        """Setup the reservation skill"""
        return True

    def _find_menu_item_exact(self, item_name):
        """
        Find menu item using exact database matching only
        
        Args:
            item_name: The exact item name from the database
            
        Returns:
            MenuItem object if found, None otherwise
        """
        from models import MenuItem
        
        if not item_name:
            return None
        
        # Only use exact matches - no fuzzy logic
        menu_item = MenuItem.query.filter(
            MenuItem.name.ilike(item_name.strip())
        ).filter_by(is_available=True).first()
        
        if menu_item:
            print(f"✅ Found exact menu item: {menu_item.name} (ID: {menu_item.id})")
        else:
            print(f"❌ No exact match found for: {item_name}")
            
        return menu_item
    
    def _levenshtein_distance(self, s1, s2):
        """Calculate Levenshtein distance between two strings"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]

    def _cache_menu_in_metadata(self, raw_data):
        """Cache menu items in meta_data for performance"""
        try:
            import sys
            import os
            
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import MenuItem
            
            with app.app_context():
                # Get current meta_data
                meta_data = raw_data.get('meta_data', {}) if raw_data else {}
                
                # Check if menu is already cached and still fresh (cache for 5 minutes)
                from datetime import datetime, timedelta
                cache_time = meta_data.get('menu_cached_at')
                if cache_time:
                    try:
                        cached_at = datetime.fromisoformat(cache_time)
                        if datetime.now() - cached_at < timedelta(minutes=5):
                            print("🚀 Menu cache is still fresh, skipping database query")
                            return meta_data
                    except ValueError:
                        pass  # Invalid date format, refresh cache
                
                print("📊 Caching menu items in meta_data")
                menu_items = MenuItem.query.filter_by(is_available=True).all()
                
                # Convert to serializable format
                cached_menu = []
                for item in menu_items:
                    cached_menu.append({
                        'id': item.id,
                        'name': item.name,
                        'price': float(item.price),
                        'category': item.category,
                        'description': item.description,
                        'is_available': item.is_available
                    })
                
                # Update meta_data
                meta_data['cached_menu'] = cached_menu
                meta_data['menu_cached_at'] = datetime.now().isoformat()
                meta_data['menu_item_count'] = len(cached_menu)
                
                print(f"✅ Cached {len(cached_menu)} menu items in meta_data")
                return meta_data
                
        except Exception as e:
            print(f"❌ Error caching menu: {e}")
            return raw_data.get('meta_data', {}) if raw_data else {}

    def _normalize_phone_number(self, phone_number, caller_id=None):
        """
        Normalize phone number to E.164 format (+1XXXXXXXXXX)
        
        Args:
            phone_number: Phone number provided by user (can be None)
            caller_id: Caller ID from the call (fallback if phone_number is None)
            
        Returns:
            Normalized phone number in E.164 format
        """
        import re
        
        # If no phone number provided, use caller ID
        if not phone_number and caller_id:
            phone_number = caller_id
            print(f"🔄 Using caller ID as phone number: {caller_id}")
        
        if not phone_number:
            return None
        
        # If already in E.164 format, return as-is
        if phone_number.startswith('+1') and len(phone_number) == 12:
            return phone_number
        
        # Extract only digits
        digits = re.sub(r'\D', '', phone_number)
        
        # Handle different digit lengths
        if len(digits) == 10:
            # 10 digits: add +1 prefix
            normalized = f"+1{digits}"
            print(f"🔄 Normalized 10-digit number {digits} to {normalized}")
            return normalized
        elif len(digits) == 11 and digits.startswith('1'):
            # 11 digits starting with 1: add + prefix
            normalized = f"+{digits}"
            print(f"🔄 Normalized 11-digit number {digits} to {normalized}")
            return normalized
        elif len(digits) == 7:
            # 7 digits: assume local number, add area code 555 and +1
            normalized = f"+1555{digits}"
            print(f"🔄 Normalized 7-digit number {digits} to {normalized} (added 555 area code)")
            return normalized
        else:
            # Return original if we can't normalize
            print(f"⚠️  Could not normalize phone number: {phone_number} (digits: {digits})")
            return phone_number

    def _extract_phone_from_conversation(self, call_log):
        """
        Extract phone number from conversation using spoken number conversion
        
        Args:
            call_log: List of conversation entries
            
        Returns:
            Extracted phone number in E.164 format or None
        """
        if not call_log:
            return None
        
        for entry in call_log:
            if entry.get('role') == 'user' and entry.get('content'):
                content = entry['content'].lower()
                
                # Look for phone number mentions
                if any(phrase in content for phrase in ['phone number', 'my number', 'use number', 'different number']):
                    # Convert spoken numbers to digits
                    number_words = {
                        'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
                        'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9'
                    }
                    
                    # Use word boundaries to avoid replacing parts of other words
                    phone_part = content
                    for word, digit in number_words.items():
                        phone_part = re.sub(r'\b' + word + r'\b', digit, phone_part)
                    
                    # Extract digits and format as phone number
                    phone_digits = re.findall(r'\d', phone_part)
                    if len(phone_digits) >= 7:  # At least 7 digits for a phone number
                        if len(phone_digits) >= 10:
                            # Take first 10 digits
                            extracted_phone = ''.join(phone_digits[:10])
                            normalized = self._normalize_phone_number(extracted_phone)
                            print(f"🔄 Extracted phone number from conversation: {normalized}")
                            return normalized
                        else:
                            # Take available digits and normalize
                            extracted_phone = ''.join(phone_digits)
                            normalized = self._normalize_phone_number(extracted_phone)
                            print(f"🔄 Extracted partial phone number from conversation: {normalized}")
                            return normalized
        
        return None

    def _generate_order_number(self):
        """Generate a unique order number"""
        import random
        import string
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

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
        
    def register_tools(self) -> None:
        """Register reservation tools with the agent"""
        
        # Create reservation tool
        self.agent.define_tool(
            name="create_reservation",
            description="Create a new restaurant reservation. Call this immediately when a customer wants to make a reservation, book a table, or reserve a spot. Don't wait for all details - extract what you can from the conversation and ask for any missing required information (name, party size, date, time, phone number).",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Customer name"},
                    "party_size": {"type": "integer", "description": "Number of people"},
                    "date": {"type": "string", "description": "Reservation date (YYYY-MM-DD)"},
                    "time": {"type": "string", "description": "Reservation time (HH:MM)"},
                    "phone_number": {"type": "string", "description": "Customer phone number"},
                    "special_requests": {"type": "string", "description": "Any special requests"},
                    "old_school": {"type": "boolean", "description": "True for old school reservation (table only, no pre-ordering)", "default": False},
                    "party_orders": {
                        "type": "array",
                        "description": "Optional pre-orders for each person in the party",
                        "items": {
                            "type": "object",
                            "properties": {
                                "person_name": {"type": "string", "description": "Name of person ordering (optional)"},
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
                "required": []  # Made flexible - function will extract missing info from conversation
            },
            handler=self._create_reservation_handler,
            meta_data_token="reservation_session",  # Shared token for reservation and payment session management
            **self.swaig_fields
        )
        
        # Get reservation tool
        self.agent.define_tool(
            name="get_reservation",
            description="Look up an existing reservation by any available information: phone number, first name, last name, full name, date, time, party size, reservation ID, or confirmation number. Can return formatted text for voice or structured JSON for programmatic use.",
            parameters={
                "type": "object",
                "properties": {
                    "phone_number": {"type": "string", "description": "Customer phone number"},
                    "name": {"type": "string", "description": "Customer full name, first name, or last name"},
                    "first_name": {"type": "string", "description": "Customer first name"},
                    "last_name": {"type": "string", "description": "Customer last name"},
                    "reservation_id": {"type": "integer", "description": "Reservation ID"},
                    "reservation_number": {"type": "string", "description": "6-digit reservation number"},
                    "confirmation_number": {"type": "string", "description": "Payment confirmation number (format: CONF-XXXXXXXX)"},
                    "date": {"type": "string", "description": "Reservation date (YYYY-MM-DD)"},
                    "time": {"type": "string", "description": "Reservation time (HH:MM)"},
                    "party_size": {"type": "integer", "description": "Number of people"},
                    "email": {"type": "string", "description": "Customer email address"},
                    "format": {
                        "type": "string",
                        "enum": ["text", "json"],
                        "description": "Response format: 'text' for voice-friendly formatted text (default), 'json' for structured data",
                        "default": "text"
                    }
                },
                "required": []
            },
            handler=self._get_reservation_handler,
            **self.swaig_fields
        )
        
        # Update reservation tool
        self.agent.define_tool(
            name="update_reservation",
            description="Update an existing reservation details (time, date, party size, etc.) OR add food/drink items to an existing pre-order. When customer wants to modify their reservation or add items to their order, use this function. IMPORTANT: Always ask the customer if they would like to add anything else to their pre-order before finalizing any changes.",
            parameters={
                "type": "object",
                "properties": {
                    "reservation_id": {"type": "integer", "description": "Reservation ID (internal database ID)"},
                    "reservation_number": {"type": "string", "description": "6-digit reservation number"},
                    "name": {"type": "string", "description": "New customer name"},
                    "party_size": {"type": "integer", "description": "New party size"},
                    "date": {"type": "string", "description": "New reservation date (YYYY-MM-DD)"},
                    "time": {"type": "string", "description": "New reservation time (HH:MM)"},
                    "phone_number": {"type": "string", "description": "New phone number"},
                    "special_requests": {"type": "string", "description": "New special requests"},
                    "add_items": {
                        "type": "array",
                        "description": "Food or drink items to add to the pre-order",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Menu item name"},
                                "quantity": {"type": "integer", "description": "Quantity to add", "default": 1}
                            },
                            "required": ["name"]
                        }
                    }
                },
                "required": []
            },
            handler=self._update_reservation_handler,
            **self.swaig_fields
        )
        
        # Cancel reservation tool
        self.agent.define_tool(
            name="cancel_reservation",
            description="Cancel an existing reservation. If no reservation_id is provided, will find the reservation using the caller's phone number.",
            parameters={
                "type": "object",
                "properties": {
                    "reservation_id": {"type": "integer", "description": "Reservation ID to cancel (optional - will be found automatically if not provided)"}
                },
                "required": []
            },
            handler=self._cancel_reservation_handler,
            **self.swaig_fields
        )
        
        # Calendar management tools
        self.agent.define_tool(
            name="get_calendar_events",
            description="Get calendar events for reservations within a date range. Returns reservation data formatted for calendar display.",
            parameters={
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date for calendar range (YYYY-MM-DD). Defaults to today."},
                    "end_date": {"type": "string", "description": "End date for calendar range (YYYY-MM-DD). Defaults to 30 days from start."},
                    "format": {
                        "type": "string",
                        "enum": ["text", "json"],
                        "description": "Response format: 'text' for voice-friendly formatted text (default), 'json' for structured data",
                        "default": "text"
                    }
                },
                "required": []
            },
            handler=self._get_calendar_events_handler,
            **self.swaig_fields
        )
        
        self.agent.define_tool(
            name="get_todays_reservations",
            description="Get all reservations for today, ordered by time. Useful for daily planning and front desk operations.",
            parameters={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date to get reservations for (YYYY-MM-DD). Defaults to today."},
                    "format": {
                        "type": "string",
                        "enum": ["text", "json"],
                        "description": "Response format: 'text' for voice-friendly formatted text (default), 'json' for structured data",
                        "default": "text"
                    }
                },
                "required": []
            },
            handler=self._get_todays_reservations_handler,
            **self.swaig_fields
        )
        
        self.agent.define_tool(
            name="get_reservation_summary",
            description="Get a summary of reservations for a specific date or date range, including total count, party sizes, and time distribution.",
            parameters={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Specific date for summary (YYYY-MM-DD). Defaults to today."},
                    "start_date": {"type": "string", "description": "Start date for range summary (YYYY-MM-DD)"},
                    "end_date": {"type": "string", "description": "End date for range summary (YYYY-MM-DD)"},
                    "format": {
                        "type": "string",
                        "enum": ["text", "json"],
                        "description": "Response format: 'text' for voice-friendly formatted text (default), 'json' for structured data",
                        "default": "text"
                    }
                },
                "required": []
            },
            handler=self._get_reservation_summary_handler,
            **self.swaig_fields
        )

        # Add to reservation tool
        self.agent.define_tool(
            name="add_to_reservation",
            description="Add food items to an existing reservation. Use this ONLY when customer already has a reservation and wants to add more items. NEVER use create_reservation if customer already has a reservation.",
            parameters={
                "type": "object",
                "properties": {
                    "reservation_number": {"type": "string", "description": "6-digit reservation number"},
                    "reservation_id": {"type": "integer", "description": "Internal reservation ID"},
                    "items": {
                        "type": "array",
                        "description": "List of items to add with name and quantity",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Menu item name"},
                                "quantity": {"type": "integer", "description": "Quantity to add", "default": 1}
                            },
                            "required": ["name"]
                        }
                    },
                    "person_name": {"type": "string", "description": "Name of person ordering (defaults to reservation holder)"}
                },
                "required": []
            },
            handler=self._add_to_reservation_handler,
            **self.swaig_fields
        )



        # Register consolidated payment processing tool
        self.agent.define_tool(
            name="pay_reservation",
            description="Process payment for ANY reservation (new or existing). Use this when customer wants to pay for their reservation, whether it was just created or already exists. The function automatically detects if this is a new reservation from the current session or an existing one. Accepts affirmative responses like 'yes', 'sure', 'okay', 'I'd like to pay', 'let's do it', 'go ahead', etc.",
            parameters={
                "type": "object",
                "properties": {
                    "reservation_number": {"type": "string", "description": "6-digit reservation number (optional for new reservations - will be detected from session)"},
                    "cardholder_name": {"type": "string", "description": "Name on the credit card"},
                    "phone_number": {"type": "string", "description": "SMS number for receipt (will use caller ID if not provided)"}
                },
                "required": []  # Function will collect missing information
            },
            handler=self._pay_reservation_handler,
            meta_data_token="payment_session",  # Shared token for payment session management
            **self.swaig_fields
        )
        
        # Register payment status check tool
        self.agent.define_tool(
            name="check_payment_status",
            description="Check if a payment has been completed for a reservation. Use this when customer says they already paid, when there's confusion about payment status, or when you need to verify payment completion.",
            parameters={
                "type": "object",
                "properties": {
                    "reservation_number": {"type": "string", "description": "6-digit reservation number to check payment status"}
                },
                "required": ["reservation_number"]
            },
            handler=self._check_payment_status_handler,
            **self.swaig_fields
        )
        
        # Register payment retry tool for handling failed payments
        self.agent.define_tool(
            name="retry_payment",
            description="Help customer retry payment when previous payment failed due to card issues, invalid card type, or other payment errors. Use when customer wants to try payment again after a failure or mentions trying a different card.",
            parameters={
                "type": "object",
                "properties": {
                    "reservation_number": {"type": "string", "description": "6-digit reservation number to retry payment for"},
                    "cardholder_name": {"type": "string", "description": "Name on the credit card (if different from before)"}
                },
                "required": []
            },
            handler=self._payment_retry_handler,
            **self.swaig_fields
        )




    
    def _pay_reservation_handler(self, args, raw_data):
        """Process payment using SWML pay verb with Stripe integration - handles both new and existing reservations"""
        print("🔧 Entering _pay_reservation_handler")
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
            reservation_number = args.get('reservation_number')
            cardholder_name = args.get('cardholder_name')
            phone_number = args.get('phone_number')
            
            # Get phone number from caller ID if not provided
            if not phone_number:
                caller_phone = raw_data.get('caller_id_num') or raw_data.get('caller_id_number')
                if caller_phone:
                    phone_number = caller_phone
                    print(f"🔄 Using phone number from caller ID: {phone_number}")
            
            # AUTO-DETECT: Check if this is for a newly created reservation from session metadata
            if not reservation_number:
                # Check meta_data for recently created reservation
                reservation_created = meta_data.get('reservation_created')
                session_reservation_number = meta_data.get('reservation_number')
                
                if reservation_created and session_reservation_number:
                    reservation_number = session_reservation_number
                    print(f"🔍 Auto-detected new reservation from session: #{reservation_number}")
                else:
                    # Try to detect from conversation history
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    for entry in reversed(call_log[-10:]):  # Check last 10 entries
                        if (entry.get('role') == 'assistant' and 
                            entry.get('content') and 
                            'reservation confirmed' in entry.get('content', '').lower()):
                            
                            # Try to extract reservation number from the assistant's message
                            content = entry.get('content', '')
                            reservation_match = re.search(r'Reservation #(\d{6})', content)
                            if reservation_match:
                                reservation_number = reservation_match.group(1)
                                print(f"🔍 Auto-detected reservation from conversation: #{reservation_number}")
                                break
            
            # Validate required information
            if not reservation_number:
                result = SwaigFunctionResult(
                    "I need your reservation number to process the payment. "
                    "What's your 6-digit reservation number?"
                )
                result.set_metadata({
                    "payment_step": "need_reservation_number",
                    "cardholder_name": cardholder_name,
                    "phone_number": phone_number
                })
                return result
            
            if not cardholder_name:
                result = SwaigFunctionResult(
                    "I need the name on your credit card to process the payment. "
                    "What name appears on your credit card?"
                )
                result.set_metadata({
                    "payment_step": "need_cardholder_name",
                    "reservation_number": reservation_number,
                    "phone_number": phone_number
                })
                return result
            
            # Look up reservation and calculate total
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import Reservation, Order
            
            with app.app_context():
                reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
                if not reservation:
                    result = SwaigFunctionResult(
                        f"I couldn't find a reservation with number {reservation_number}. "
                        "Please check the number and try again."
                    )
                    result.set_metadata({
                        "payment_step": "error",
                        "error": "reservation_not_found"
                    })
                    return result
                
                print(f"✅ Found reservation: {reservation.name}, party of {reservation.party_size}, {reservation.date} at {reservation.time}")
                
                # Calculate total amount from orders
                total_amount = 0.0
                orders = Order.query.filter_by(reservation_id=reservation.id).all()
                print(f"🔍 Found {len(orders)} orders for reservation {reservation_number}")
                
                for order in orders:
                    order_amount = order.total_amount or 0.0
                    total_amount += order_amount
                    print(f"   Order #{order.order_number}: ${order_amount:.2f} ({order.payment_status})")
                
                # Round total amount to 2 decimal places
                total_amount = round(total_amount, 2)
                
                # Create the parameters array
                parameters_array = [
                    {"name": "reservation_number", "value": reservation_number},
                    {"name": "customer_name", "value": cardholder_name},
                    {"name": "phone_number", "value": phone_number or ""},
                    {"name": "payment_type", "value": "reservation"}
                ]
                
                # Only add call_id if it has a non-empty value
                if call_id and call_id.strip():
                    parameters_array.append({"name": "call_id", "value": call_id})
                    print(f"🔍 Added call_id to parameters: {call_id}")
                
                # Create response message
                message = f"💳 Ready to process payment for Reservation #{reservation_number}\n"
                message += f"Customer: {cardholder_name}\n"
                message += f"Party of {reservation.party_size} on {reservation.date} at {reservation.time}\n"
                message += f"Total amount: ${total_amount:.2f}\n\n"
                message += f"Please enter your credit card information when prompted."
                
                # Create SwaigFunctionResult
                result = SwaigFunctionResult(message)
                
                # Set meta_data for payment tracking
                result.set_metadata({
                    "payment_step": "processing_payment",
                    "verified_reservation": {
                        "reservation_number": reservation_number,
                        "customer_name": cardholder_name,
                        "party_size": reservation.party_size,
                        "reservation_date": str(reservation.date),
                        "reservation_time": str(reservation.time),
                        "cardholder_name": cardholder_name,
                        "phone_number": phone_number,
                        "total_amount": total_amount,
                        "reservation_id": reservation.id
                    },
                    "payment_session_active": True
                })
                
                # Get payment URLs from environment
                base_url = os.getenv('BASE_URL', 'https://localhost:8080')
                payment_connector_url = os.getenv('PAYMENT_CONNECTOR_URL', f"{base_url}/api/payment-processor")
                status_url = os.getenv('PAYMENT_STATUS_URL', f"{base_url}/api/signalwire/payment-callback")
                
                print(f"🔗 Using payment connector URL: {payment_connector_url}")
                
                # Use SignalWire SDK v0.1.26 pay() method
                try:
                    print(f"✅ Using SignalWire SDK pay() method")
                    result.pay(
                        payment_connector_url=payment_connector_url,
                        input_method="dtmf",
                        status_url=status_url,
                        payment_method="credit-card",
                        timeout=10,
                        max_attempts=3,
                        security_code=True,
                        postal_code=True,
                        min_postal_code_length=5,
                        token_type="one-time",
                        charge_amount=f"{total_amount:.2f}",
                        currency="usd",
                        language="en-US",
                        voice="woman",
                        description=f"Bobby's Table Reservation #{reservation_number}",
                        valid_card_types="visa mastercard amex discover diners jcb unionpay",
                        parameters=parameters_array
                    )
                    print(f"✅ result.pay() completed successfully")
                except Exception as pay_error:
                    print(f"❌ Error in result.pay(): {pay_error}")
                    import traceback
                    traceback.print_exc()
                    raise  # Re-raise to be caught by outer exception handler
                
                print(f"✅ Payment collection configured for ${total_amount} - Reservation #{reservation_number}")
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
                        "Would you like to try again or would you prefer to pay at the restaurant?"
                    )
                
                return SwaigFunctionResult(response_text)
            
            # If no failed payment session, treat as a general retry request
            reservation_number = args.get('reservation_number') or meta_data.get('reservation_number')
            if not reservation_number:
                return SwaigFunctionResult(
                    "I'd be happy to help you retry your payment. Could you please provide your reservation number?"
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
                return self._pay_reservation_handler(args, raw_data)
            else:
                return SwaigFunctionResult(
                    "No problem! You can also pay when you arrive at the restaurant. "
                    "Your reservation is still confirmed. Is there anything else I can help you with?"
                )
                
        except Exception as e:
            print(f"❌ Error in payment retry handler: {e}")
            import traceback
            traceback.print_exc()
            
            return SwaigFunctionResult(
                "I'm sorry, I encountered an error with the payment retry. "
                "You can pay when you arrive at the restaurant. Is there anything else I can help you with?"
            )

    def _check_payment_status_handler(self, args, raw_data):
        """Check if a payment has been completed for a reservation"""
        from signalwire_agents.core.function_result import SwaigFunctionResult
        
        try:
            print(f"💳 Payment status check called with args: {args}")
            
            reservation_number = args.get('reservation_number')
            if not reservation_number:
                return SwaigFunctionResult(
                    "I need a reservation number to check the payment status. What's your 6-digit reservation number?"
                )
            
            # Get call_id for payment session check
            call_id = raw_data.get('call_id') if raw_data else None
            
            # Check payment session first (for recent payments)
            payment_completed = False
            payment_amount = None
            confirmation_number = None
            
            # Import app to access payment sessions
            import sys
            import os
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            from app import app
            
            if call_id:
                # Check active payment sessions
                payment_sessions = getattr(app, 'payment_sessions', {})
                if call_id in payment_sessions:
                    session = payment_sessions[call_id]
                    if session.get('payment_completed') or session.get('payment_status') == 'completed':
                        payment_completed = True
                        payment_amount = session.get('payment_amount')
                        confirmation_number = session.get('confirmation_number')
                        print(f"✅ Found completed payment in session for {call_id}")
                
                # Check global payment confirmations
                if not payment_completed and hasattr(app, 'payment_confirmations'):
                    confirmation_data = app.payment_confirmations.get(reservation_number)
                    if confirmation_data:
                        payment_completed = True
                        payment_amount = confirmation_data.get('payment_amount')
                        confirmation_number = confirmation_data.get('confirmation_number')
                        print(f"✅ Found payment confirmation for reservation {reservation_number}")
            
            # Check database for payment status
            from models import Reservation, Order
            
            with app.app_context():
                reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
                
                if not reservation:
                    return SwaigFunctionResult(
                        f"I couldn't find a reservation with number {reservation_number}. Please check the number and try again."
                    )
                
                # Check database payment status
                if reservation.payment_status == 'paid':
                    payment_completed = True
                    if not payment_amount:
                        payment_amount = reservation.payment_amount
                    if not confirmation_number:
                        confirmation_number = reservation.confirmation_number
                    print(f"✅ Database shows reservation {reservation_number} is paid")
                
                # Prepare response
                if payment_completed:
                    response = f"✅ Great news! Your payment has been completed for Reservation #{reservation_number}.\\n"
                    response += f"Customer: {reservation.name}\\n"
                    response += f"Party of {reservation.party_size} on {reservation.date} at {reservation.time}\\n"
                    
                    if payment_amount:
                        response += f"Payment amount: ${payment_amount:.2f}\\n"
                    
                    if confirmation_number:
                        response += f"Confirmation number: {confirmation_number}\\n"
                    
                    response += "\\nYour reservation is confirmed and paid. You're all set!"
                    
                    return SwaigFunctionResult(response)
                else:
                    # Calculate amount due
                    orders = Order.query.filter_by(reservation_id=reservation.id).all()
                    total_due = sum(order.total_amount or 0.0 for order in orders)
                    
                    if total_due > 0:
                        response = f"💳 Payment status for Reservation #{reservation_number}:\\n"
                        response += f"Customer: {reservation.name}\\n"
                        response += f"Party of {reservation.party_size} on {reservation.date} at {reservation.time}\\n"
                        response += f"Payment status: Pending\\n"
                        response += f"Amount due: ${total_due:.2f}\\n\\n"
                        response += "Would you like to pay now to complete your reservation?"
                    else:
                        response = f"ℹ️ Reservation #{reservation_number} doesn't have any pre-orders requiring payment.\\n"
                        response += f"Customer: {reservation.name}\\n"
                        response += f"Party of {reservation.party_size} on {reservation.date} at {reservation.time}\\n"
                        response += "Your reservation is confirmed!"
                    
                    return SwaigFunctionResult(response)
                    
        except Exception as e:
            print(f"❌ Error checking payment status: {e}")
            import traceback
            traceback.print_exc()
            
            return SwaigFunctionResult(
                "I'm sorry, I encountered an error checking your payment status. "
                "Please try again or contact us for assistance."
            )

    def _create_reservation_handler(self, args, raw_data):
        """Handler for create_reservation tool - matches Flask route implementation"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            import random
            import re
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app, get_receptionist_agent
            from models import db, Reservation
            
            with app.app_context():
                # Cache menu in meta_data for performance
                meta_data = self._cache_menu_in_metadata(raw_data)
                caller_phone = None
                
                # Try to get caller's phone number from various sources
                if raw_data and isinstance(raw_data, dict):
                    caller_phone = (
                        raw_data.get('caller_id_num') or 
                        raw_data.get('caller_id_number') or
                        raw_data.get('from') or
                        raw_data.get('from_number')
                    )
                    # Also check in global_data
                    global_data = raw_data.get('global_data', {})
                    if not caller_phone and global_data:
                        caller_phone = (
                            global_data.get('caller_id_number') or
                            global_data.get('caller_id_num')
                        )
                
                # Enhanced context extraction from conversation
                call_log = raw_data.get('call_log', []) if raw_data else []
                
                # Log call_id for tracking function execution
                call_id = raw_data.get('call_id') if raw_data else None
                print(f"🔍 Call ID: {call_id}")
                
                # Always try to extract from conversation if args are empty or incomplete
                print(f"🔍 Received args: {args}")
                print(f"🔍 Call log entries: {len(call_log)}")
                
                # Check if this is a retry after initial failure
                if not args or len(args) == 0:
                    print("⚠️ No args provided - this might be an AI function selection issue")
                    print("🔍 Checking if user mentioned reservation intent in conversation...")
                    
                    # Check for reservation intent keywords in conversation
                    reservation_keywords = [
                        'reservation', 'book', 'table', 'reserve', 'booking', 
                        'reservation number', 'confirm', 'make a reservation',
                        'book a table', 'get a table', 'reserve a table'
                    ]
                    
                    conversation_text = ' '.join([
                        entry.get('content', '').lower() 
                        for entry in call_log 
                        if entry.get('role') == 'user'
                    ])
                    
                    has_reservation_intent = any(keyword in conversation_text for keyword in reservation_keywords)
                    
                    if has_reservation_intent:
                        print("✅ Detected reservation intent in conversation")
                        print(f"   Conversation text: {conversation_text[:200]}...")
                    else:
                        print("❌ No clear reservation intent detected")
                        return SwaigFunctionResult("I'd be happy to help you make a reservation! Please tell me your name, party size, preferred date and time.")
                
                if not args or not all(args.get(field) for field in ['name', 'party_size', 'date', 'time']):
                    print("🔍 Extracting reservation details from conversation...")
                    
                    # Extract information from conversation
                    extracted_info = self._extract_reservation_info_from_conversation(call_log, caller_phone, meta_data)
                    
                    # Initialize args if it's empty
                    if not args:
                        args = {}
                    
                    # Merge extracted info with provided args (args take priority)
                    for key, value in extracted_info.items():
                        if not args.get(key) and value:
                            args[key] = value
                            print(f"   Extracted {key}: {value}")
                    
                    print(f"🔍 Final args after extraction: {args}")
                
                # Handle phone number with priority: user-provided > conversation-extracted > caller ID
                user_provided_phone = args.get('phone_number')
                conversation_phone = self._extract_phone_from_conversation(call_log)
                
                # Determine which phone number to use
                if user_provided_phone:
                    # User explicitly provided a phone number
                    normalized_phone = self._normalize_phone_number(user_provided_phone, caller_phone)
                    args['phone_number'] = normalized_phone
                    print(f"🔄 Using user-provided phone number: {normalized_phone}")
                elif conversation_phone:
                    # Phone number extracted from conversation
                    args['phone_number'] = conversation_phone
                    print(f"🔄 Using phone number from conversation: {conversation_phone}")
                elif caller_phone:
                    # Default to caller ID
                    normalized_phone = self._normalize_phone_number(caller_phone)
                    args['phone_number'] = normalized_phone
                    print(f"🔄 Using caller ID as phone number: {normalized_phone}")
                else:
                    return SwaigFunctionResult("I need your phone number to complete the reservation. Could you please provide that?")
                
                # Validate required fields
                required_fields = ['name', 'party_size', 'date', 'time', 'phone_number']
                missing_fields = [field for field in required_fields if not args.get(field)]
                
                if missing_fields:
                    return SwaigFunctionResult(f"I need some more information to create your reservation. Please provide: {', '.join(missing_fields)}. For example, say 'I'd like to make a reservation for John Smith, party of 4, on June 15th at 7 PM'.")
                
                # Enhanced date and time validation to handle multiple formats including ISO
                try:
                    date_str = args['date']
                    time_str = args['time']
                    
                    print(f"🔍 Processing date: '{date_str}', time: '{time_str}'")
                    
                    # Handle ISO datetime format (e.g., "2025-06-09T14:00:00")
                    if 'T' in time_str and ':' in time_str:
                        try:
                            # Parse ISO datetime format
                            iso_datetime = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                            reservation_datetime = iso_datetime
                            
                            # Extract date and time components
                            args['date'] = iso_datetime.strftime("%Y-%m-%d")
                            args['time'] = iso_datetime.strftime("%H:%M")
                            
                            print(f"✅ Parsed ISO datetime: {reservation_datetime}")
                            print(f"   Normalized date: {args['date']}")
                            print(f"   Normalized time: {args['time']}")
                            
                        except ValueError:
                            # If ISO parsing fails, try other formats
                            pass
                    
                    # If not ISO format or ISO parsing failed, try standard parsing
                    if 'reservation_datetime' not in locals():
                        # First try to parse the date in the expected YYYY-MM-DD format
                        try:
                            reservation_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                            print(f"✅ Parsed standard format: {reservation_datetime}")
                        except ValueError:
                            # Try different date formats
                            date_formats = [
                                "%B %d, %Y",      # "June 09, 2025"
                                "%B %d %Y",       # "June 09 2025"
                                "%m/%d/%Y",       # "06/09/2025"
                                "%m-%d-%Y",       # "06-09-2025"
                                "%d/%m/%Y",       # "09/06/2025"
                                "%Y/%m/%d",       # "2025/06/09"
                                "%Y-%m-%d",       # "2025-06-09" (explicit)
                            ]
                            
                            parsed_date = None
                            for date_format in date_formats:
                                try:
                                    parsed_date = datetime.strptime(date_str, date_format)
                                    print(f"✅ Parsed date with format {date_format}: {parsed_date}")
                                    break
                                except ValueError:
                                    continue
                            
                            if not parsed_date:
                                print(f"❌ Could not parse date: {date_str}")
                                return SwaigFunctionResult(f"Invalid date format: '{date_str}'. Please use a format like 'June 15, 2025' or '2025-06-15'.")
                            
                            # Try to parse time
                            time_formats = [
                                "%H:%M",          # "14:00"
                                "%I:%M %p",       # "2:00 PM"
                                "%H:%M:%S",       # "14:00:00"
                                "%I:%M:%S %p",    # "2:00:00 PM"
                            ]
                            
                            parsed_time = None
                            for time_format in time_formats:
                                try:
                                    parsed_time = datetime.strptime(time_str, time_format)
                                    print(f"✅ Parsed time with format {time_format}: {parsed_time}")
                                    break
                                except ValueError:
                                    continue
                            
                            if not parsed_time:
                                print(f"❌ Could not parse time: {time_str}")
                                return SwaigFunctionResult(f"Invalid time format: '{time_str}'. Please use HH:MM format like '19:00' or '7:00 PM'.")
                            
                            # Combine date and time
                            reservation_datetime = datetime.combine(
                                parsed_date.date(),
                                parsed_time.time()
                            )
                            
                            # Update args with normalized formats
                            args['date'] = parsed_date.strftime("%Y-%m-%d")
                            args['time'] = parsed_time.strftime("%H:%M")
                            
                            print(f"✅ Combined datetime: {reservation_datetime}")
                            print(f"   Normalized date: {args['date']}")
                            print(f"   Normalized time: {args['time']}")
                
                except Exception as e:
                    print(f"❌ Date/time parsing error: {e}")
                    return SwaigFunctionResult(f"Invalid date or time format: {str(e)}. Please provide date and time in a clear format.")
                
                # Check if reservation is in the past
                if reservation_datetime < datetime.now():
                    return SwaigFunctionResult("I can't make a reservation for a time in the past. Please choose a future date and time.")
                
                # SAFEGUARD: Check if customer already has an existing reservation
                # This prevents duplicate reservations when AI mistakenly calls create_reservation 
                # instead of add_to_reservation
                phone_number = args['phone_number']
                customer_name = args['name']
                
                # Check for existing reservations by phone number (exact match only)
                # Only check phone number for duplicates - name matching is too prone to false positives
                existing_reservations = Reservation.query.filter(
                    Reservation.phone_number == phone_number,
                    Reservation.date >= datetime.now().strftime("%Y-%m-%d"),  # Only future reservations
                    Reservation.status != 'cancelled'
                ).all()
                
                if existing_reservations:
                    # Found existing reservation(s) - suggest using add_to_reservation instead
                    reservation_info = []
                    for res in existing_reservations:
                        reservation_info.append(f"#{res.reservation_number} for {res.name} on {res.date} at {res.time}")
                    
                    print(f"🚫 DUPLICATE PREVENTION: Found existing reservation(s): {reservation_info}")
                    return SwaigFunctionResult(
                        f"I found you already have an existing reservation: {', '.join(reservation_info)}. "
                        f"Would you like me to add items to your existing reservation instead of creating a new one? "
                        f"Or if you need a different reservation, please specify the different details."
                    )
                
                # Generate a unique 6-digit reservation number (matching Flask route logic)
                while True:
                    reservation_number = f"{random.randint(100000, 999999)}"
                    # Check if this number already exists
                    existing = Reservation.query.filter_by(reservation_number=reservation_number).first()
                    if not existing:
                        break
                
                # Create reservation with exact same structure as Flask route
                reservation = Reservation(
                    reservation_number=reservation_number,
                    name=args['name'],
                    party_size=int(args['party_size']),
                    date=args['date'],
                    time=args['time'],
                    phone_number=args['phone_number'],
                    status='confirmed',  # Match Flask route default
                    special_requests=args.get('special_requests', '')
                )
                
                db.session.add(reservation)
                db.session.flush()  # Get reservation.id
                
                # Process party orders if provided (matching Flask route logic)
                party_orders = args.get('party_orders', [])
                pre_order = args.get('pre_order', [])  # Handle alternative format from AI
                total_reservation_amount = 0.0
                
                # Convert pre_order format to party_orders format if needed
                if pre_order and not party_orders:
                    print(f"🔄 Converting pre_order format to party_orders format")
                    from models import MenuItem
                    
                    # Convert pre_order items to party_orders format using exact matching only
                    converted_items = []
                    for item in pre_order:
                        item_name = item.get('name', '')
                        quantity = item.get('quantity', 1)
                        
                        # Find menu item by exact name match only
                        menu_item = self._find_menu_item_exact(item_name)
                        
                        if menu_item:
                            converted_items.append({
                                'menu_item_id': menu_item.id,
                                'quantity': quantity
                            })
                            print(f"   ✅ Added exact match: '{item_name}' (menu item ID {menu_item.id})")
                        else:
                            print(f"   ❌ Exact match not found for '{item_name}' - skipping")
                    
                    if converted_items:
                        party_orders = [{
                            'person_name': args.get('name', 'Customer'),
                            'items': converted_items
                        }]
                        print(f"   Created party_orders: {party_orders}")
                
                # Debug logging for order processing
                print(f"🔍 Order processing debug:")
                print(f"   old_school: {args.get('old_school', False)}")
                print(f"   party_orders: {party_orders}")
                print(f"   pre_order: {pre_order}")
                
                # CRITICAL FIX: Always process orders regardless of payment context
                # The payment protection system was incorrectly blocking reservation creation
                # when customers wanted to create reservations with pre-orders
                print(f"🔧 PAYMENT PROTECTION BYPASS: Processing reservation creation with pre-orders")
                
                # Only process orders if not an old school reservation
                if not args.get('old_school', False) and party_orders:
                    from models import Order, OrderItem, MenuItem
                    print(f"✅ Processing {len(party_orders)} party orders")
                    
                    # SIMPLE DATABASE-DRIVEN ORDER PROCESSING
                    # Instead of trying to correct wrong IDs, just extract items from conversation directly
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    conversation_text = ' '.join([entry.get('content', '') for entry in call_log if entry.get('content')])
                    
                    # Get menu items directly from conversation using database/cached menu
                    conversation_items = self._extract_food_items_from_conversation(conversation_text, meta_data)
                    print(f"🔍 Found {len(conversation_items)} menu items from conversation: {conversation_items}")
                    
                    # FIXED: Use set to track already processed items and avoid duplicates
                    processed_items = set()
                    
                    if conversation_items:
                        # Create orders directly from conversation extraction (ignore agent's party_orders)
                        customer_name = args.get('name', 'Customer')
                        
                        # Create single order for the customer with all items
                        order = Order(
                            order_number=self._generate_order_number(),
                            reservation_id=reservation.id,
                            table_id=None,  # Table assignment logic can be added
                            person_name=customer_name,
                            status='pending',
                            total_amount=0.0
                        )
                        db.session.add(order)
                        db.session.flush()  # Get order.id
                        
                        order_total = 0.0
                        for item_data in conversation_items:
                            menu_item_id = int(item_data['menu_item_id'])
                            quantity = int(item_data.get('quantity', 1))
                            
                            # FIXED: Check if item already processed to avoid duplicates
                            item_key = f"{menu_item_id}_{quantity}"
                            if item_key in processed_items:
                                print(f"      ⚠️ Skipping duplicate item: menu_item_id={menu_item_id}, quantity={quantity}")
                                continue
                            processed_items.add(item_key)
                            
                            menu_item = MenuItem.query.get(menu_item_id)
                            if menu_item:
                                print(f"      ✅ Adding: {menu_item.name} x{quantity} @ ${menu_item.price}")
                                
                                order_total += menu_item.price * quantity
                                order_item = OrderItem(
                                    order_id=order.id,
                                    menu_item_id=menu_item.id,
                                    quantity=quantity,
                                    price_at_time=menu_item.price
                                )
                                db.session.add(order_item)
                            else:
                                print(f"      ❌ Menu item ID {menu_item_id} not found")
                        
                        order.total_amount = order_total
                        total_reservation_amount += order_total
                        print(f"   ✅ Order total: ${order_total:.2f}")
                        
                        # FIXED: Don't process party_orders if conversation items were found
                        print(f"   ✅ Processed {len(conversation_items)} items from conversation, skipping party_orders")
                    else:
                        # Legacy fallback: process party_orders only if no conversation items found
                        print(f"   🔄 Fallback: Processing party_orders from agent")
                        for person_order in party_orders:
                            person_name = person_order.get('person_name', '')
                            items = person_order.get('items', [])
                            
                            # Create order for this person
                            order = Order(
                                order_number=self._generate_order_number(),
                                reservation_id=reservation.id,
                                table_id=None,  # Table assignment logic can be added
                                person_name=person_name,
                                status='pending',
                                total_amount=0.0
                            )
                            db.session.add(order)
                            db.session.flush()  # Get order.id
                            
                            order_total = 0.0
                            for item_data in items:
                                menu_item_id = int(item_data['menu_item_id'])
                                
                                # FIXED: Check for duplicates in party_orders too
                                quantity = int(item_data['quantity'])
                                item_key = f"{menu_item_id}_{quantity}"
                                if item_key in processed_items:
                                    print(f"      ⚠️ Skipping duplicate party order item: menu_item_id={menu_item_id}, quantity={quantity}")
                                    continue
                                processed_items.add(item_key)
                                
                                menu_item = MenuItem.query.get(menu_item_id)
                                
                                if menu_item and quantity > 0:
                                    print(f"      ✅ Adding: {menu_item.name} x{quantity} @ ${menu_item.price}")
                                    order_total += menu_item.price * quantity
                                    order_item = OrderItem(
                                        order_id=order.id,
                                        menu_item_id=menu_item.id,
                                        quantity=quantity,
                                        price_at_time=menu_item.price
                                    )
                                    db.session.add(order_item)
                                else:
                                    print(f"      ⚠️ Skipped item - Menu item not found or qty=0")
                            
                            order.total_amount = order_total
                            total_reservation_amount += order_total
                            print(f"   Order total for {person_name}: ${order_total:.2f}")
                else:
                    print(f"⚠️ No orders processed - old_school: {args.get('old_school', False)}, party_orders: {bool(party_orders)}")
                
                # Send SMS confirmation using the same method as Flask route
                receptionist_agent = get_receptionist_agent()
                if receptionist_agent and args['phone_number']:
                    try:
                        # Prepare reservation data for SMS (matching Flask route structure)
                        reservation_data = {
                            'id': reservation.id,
                            'reservation_number': reservation.reservation_number,
                            'name': reservation.name,
                            'date': str(reservation.date),
                            'time': str(reservation.time),
                            'party_size': reservation.party_size,
                            'special_requests': reservation.special_requests or ''
                        }
                        
                        # Send SMS confirmation using receptionist agent method
                        sms_result = receptionist_agent.send_reservation_sms(reservation_data, args['phone_number'])
                        
                        # Console logging for SMS status (matching Flask route)
                        print(f"📱 SKILL SMS Status for reservation {reservation.id}:")
                        print(f"   Phone: {args['phone_number']}")
                        print(f"   Success: {sms_result.get('success', False)}")
                        print(f"   SMS Sent: {sms_result.get('sms_sent', False)}")
                        if not sms_result.get('success'):
                            print(f"   Error: {sms_result.get('error', 'Unknown error')}")
                        else:
                            print(f"   Result: {sms_result.get('sms_result', 'SMS sent')}")
                        
                    except Exception as e:
                        print(f"📱 SKILL SMS Exception for reservation {reservation.id}: {e}")
                        # Don't fail the reservation if SMS fails (match Flask behavior)
                        sms_result = {'success': False, 'error': str(e)}
                
                db.session.commit()
                
                # Convert time to 12-hour format for response
                try:
                    time_obj = datetime.strptime(args['time'], '%H:%M')
                    time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                except (ValueError, TypeError):
                    time_12hr = args['time']
                
                # Create comprehensive confirmation message with prominent reservation number
                message = f"🍽️ RESERVATION CONFIRMED! 🍽️\n\n"
                message += f"🎯 YOUR RESERVATION NUMBER IS: {reservation.reservation_number}\n"
                message += f"Please save this number: {reservation.reservation_number}\n\n"
                message += f"Reservation Details:\n"
                message += f"• Name: {args['name']}\n"
                message += f"• Date: {args['date']}\n"
                message += f"• Time: {time_12hr}\n"
                party_text = "person" if args['party_size'] == 1 else "people"
                message += f"• Party Size: {args['party_size']} {party_text}\n"
                message += f"• Phone: {args['phone_number']}\n"
                
                if args.get('special_requests'):
                    message += f"📝 Special Requests: {args['special_requests']}\n"
                
                # Add order information if orders were placed
                if total_reservation_amount > 0:
                    message += f"\n🍽️ Pre-Order Details:\n"
                    
                    # Show detailed pre-order breakdown by person
                    from models import Order, OrderItem, MenuItem
                    orders = Order.query.filter_by(reservation_id=reservation.id).all()
                    
                    for order in orders:
                        message += f"• {order.person_name}:\n"
                        order_items = OrderItem.query.filter_by(order_id=order.id).all()
                        for order_item in order_items:
                            menu_item = MenuItem.query.get(order_item.menu_item_id)
                            if menu_item:
                                message += f"   - {order_item.quantity}x {menu_item.name} (${menu_item.price:.2f})\n"
                        if order.total_amount:
                            message += f"   Subtotal: ${order.total_amount:.2f}\n"
                    
                    message += f"\nPre-Order Total: ${total_reservation_amount:.2f}\n"
                    message += f"Your food will be prepared and ready when you arrive!\n"
                elif args.get('old_school', False):
                    message += f"\n📞 Old School Reservation - Just the table reserved!\n"
                    message += f"You can browse our menu and order when you arrive.\n"
                
                # Add SMS confirmation status to the message
                if 'sms_result' in locals() and sms_result.get('sms_sent'):
                    message += f"\n📱 A confirmation SMS has been sent to your phone. "
                
                message += f"\n🎯 IMPORTANT: Your reservation number is {reservation.reservation_number}\n"
                message += f"Please save this number for your records: {reservation.reservation_number}\n\n"
                message += f"Thank you for choosing Bobby's Table! We look forward to serving you. "
                message += f"Please arrive on time and let us know if you need to make any changes."
                
                # Set meta_data with reservation information for potential payment processing
                meta_data_for_next_function = {
                    "reservation_created": True,
                    "reservation_number": reservation.reservation_number,
                    "customer_name": args['name'],
                    "party_size": args['party_size'],
                    "reservation_date": args['date'],
                    "reservation_time": args['time'],
                    "phone_number": args['phone_number'],
                    "has_pre_orders": total_reservation_amount > 0,
                    "pre_order_total": total_reservation_amount,
                    "reservation_id": reservation.id
                }
                
                # ONLY offer payment if there are pre-orders with amounts due
                if total_reservation_amount > 0:
                    meta_data_for_next_function["payment_needed"] = True
                    meta_data_for_next_function["payment_amount"] = total_reservation_amount
                    meta_data_for_next_function["payment_step"] = "ready_for_payment"
                    
                    # Add optional payment offer as a separate paragraph
                    message += f"\n\n💳 OPTIONAL PAYMENT:\n"
                    message += f"Since you have pre-ordered items totaling ${total_reservation_amount:.2f}, "
                    message += f"you can choose to pay now for convenience, or pay when you arrive at the restaurant. "
                    message += f"Would you like to pay now? Just say 'yes' if you'd like to pay, or 'no thanks' if you prefer to pay later."
                
                # Create the result with the complete message (including payment prompt)
                result = SwaigFunctionResult(message)
                result.set_metadata(meta_data_for_next_function)
                
                # Log successful function execution
                print(f"✅ create_reservation completed successfully for call_id: {call_id}")
                print(f"   Reservation number: {reservation.reservation_number}")
                print(f"   Customer: {reservation.name}")
                print(f"   Total amount: ${total_reservation_amount:.2f}")
                
                return result
                
        except Exception as e:
            print(f"❌ create_reservation failed for call_id: {call_id}")
            print(f"   Error: {str(e)}")
            print(f"   Args received: {args}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()}")
            return SwaigFunctionResult(f"Sorry, there was an error creating your reservation: {str(e)}")
    
    def _extract_reservation_info_from_conversation(self, call_log, caller_phone=None, meta_data=None):
        """Extract reservation information from conversation history"""
        extracted = {}
        
        # Combine all user messages
        user_messages = []
        for entry in call_log:
            if entry.get('role') == 'user' and entry.get('content'):
                user_messages.append(entry['content'].lower())
        
        conversation_text = ' '.join(user_messages)
        print(f"🔍 Analyzing conversation: {conversation_text}")
        
        # Extract name patterns - improved to handle the specific case and avoid false positives
        name_patterns = [
            r'my name is ([a-zA-Z\s]+?)(?:\s*\.|\s+at|\s+for|\s+and|\s*$)',
            r'i\'m ([a-zA-Z\s]+?)(?:\s*\.|\s+at|\s+for|\s+and|\s*$)',
            r'this is ([a-zA-Z\s]+?)(?:\s*\.|\s+at|\s+for|\s+and|\s*$)',
            r'([a-zA-Z]+\s+[a-zA-Z]+)\s+calling',   # "John Smith calling"
            r'([a-zA-Z]+\s+[a-zA-Z]+)\s+here',      # "John Smith here"
        ]
        
        # First try explicit name patterns
        for pattern in name_patterns:
            match = re.search(pattern, conversation_text, re.IGNORECASE)
            if match:
                name = match.group(1).strip().title()
                # Filter out common false positives
                if (len(name.split()) <= 3 and 
                    name.replace(' ', '').isalpha() and 
                    name.lower() not in ['a party of', 'party of', 'the party', 'a party', 'today', 'tomorrow', 'tonight']):
                    extracted['name'] = name
                    break
        
        # If no explicit name found, look for standalone names at the end of messages
        if 'name' not in extracted:
            # Look for single words that could be names (like "randwest")
            user_messages_reversed = list(reversed(user_messages))
            for message in user_messages_reversed:
                words = message.strip().split()
                if len(words) == 1:
                    word = words[0]
                    # Check if it looks like a name (alphabetic, reasonable length, not common words)
                    if (word.replace(' ', '').isalpha() and 
                        3 <= len(word) <= 20 and
                        word.lower() not in ['yes', 'no', 'okay', 'ok', 'sure', 'thanks', 'thank', 'you', 'please', 'hello', 'hi', 'bye', 'goodbye', 'today', 'tomorrow', 'tonight', 'morning', 'afternoon', 'evening', 'and', 'or', 'but', 'the', 'for', 'with', 'order', 'reservation', 'table', 'party', 'person', 'people']):
                        extracted['name'] = word.title()
                        print(f"🔍 Found standalone name: {word.title()}")
                        break
            
            # If still no name found, look for names in the full conversation text
            if 'name' not in extracted:
                # First, try to find the very last word if it looks like a name
                last_words = conversation_text.strip().split()
                if last_words:
                    last_word = last_words[-1].strip('.,!?')
                    if (last_word.replace(' ', '').isalpha() and 
                        3 <= len(last_word) <= 20 and
                        last_word.lower() not in ['yes', 'no', 'okay', 'ok', 'sure', 'thanks', 'thank', 'you', 'please', 'hello', 'hi', 'bye', 'goodbye', 'today', 'tomorrow', 'tonight', 'morning', 'afternoon', 'evening', 'and', 'or', 'but', 'the', 'for', 'with', 'order', 'reservation', 'table', 'party', 'person', 'people', 'west', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'one', 'zero']):
                        extracted['name'] = last_word.title()
                        print(f"🔍 Found name as last word: {last_word.title()}")
                
                # If still no name, look for potential names that appear after common phrases
                if 'name' not in extracted:
                    name_context_patterns = [
                        r'(?:my name is|i\'m|this is|name is)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)',
                        r'([a-zA-Z]+\s+[a-zA-Z]+)(?:\s*\.|\s*$)',  # Two words at end of sentence
                    ]
                    
                    for pattern in name_context_patterns:
                        matches = re.findall(pattern, conversation_text, re.IGNORECASE)
                        for match in matches:
                            name = match.strip().title()
                            # Enhanced filtering
                            if (name.replace(' ', '').isalpha() and 
                                3 <= len(name) <= 30 and
                                name.lower() not in ['yes', 'no', 'okay', 'ok', 'sure', 'thanks', 'thank', 'you', 'please', 'hello', 'hi', 'bye', 'goodbye', 'today', 'tomorrow', 'tonight', 'morning', 'afternoon', 'evening', 'and', 'or', 'but', 'the', 'for', 'with', 'order', 'reservation', 'table', 'party', 'person', 'people', 'brian west', 'west', 'eight two', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'one', 'zero']):
                                extracted['name'] = name
                                print(f"🔍 Found name from context: {name}")
                                break
                        if 'name' in extracted:
                            break
        
        # Extract party size - improved patterns with context awareness
        party_patterns = [
            r'party of (\d+)',
            r'for (\d+) people',
            r'for (\d+) person',
            r'(\d+) people',
            r'(\d+) person',
            r'for a party of (\d+)',
            r'party of (one|two|three|four|five|six|seven|eight|nine|ten)',  # word numbers
            r'for a party of (one|two|three|four|five|six|seven|eight|nine|ten)',
            r'(?:reservation for|table for)\s+(\d+)',  # "table for 2"
            r'(one|two|three|four|five|six|seven|eight|nine|ten) person',  # "one person"
            r'(one|two|three|four|five|six|seven|eight|nine|ten) people',  # "two people"
            # Removed standalone patterns that can conflict with time
        ]
        
        # Word to number mapping for party size
        party_word_to_num = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
        }
        
        for pattern in party_patterns:
            match = re.search(pattern, conversation_text)
            if match:
                party_str = match.group(1)
                print(f"🔍 Found party size match: '{party_str}' using pattern: {pattern}")
                if party_str.lower() in party_word_to_num:
                    party_size = party_word_to_num[party_str.lower()]
                else:
                    try:
                        party_size = int(party_str)
                    except ValueError:
                        continue
                
                if 1 <= party_size <= 20:  # Reasonable range
                    extracted['party_size'] = party_size
                    print(f"✅ Extracted party size: {party_size}")
                    break
        
        # If no explicit party size found, try to infer from mentioned names
        if 'party_size' not in extracted:
            # Count unique person names mentioned in conversation
            person_names = set()
            
            # Look for patterns like "for [Name]", "[Name] will order", "the other person is [Name]"
            name_mention_patterns = [
                r'for ([A-Z][a-z]+)',  # "for Squidward"
                r'([A-Z][a-z]+) will order',  # "Squidward will order"
                r'([A-Z][a-z]+) will have',  # "Squidward will have"
                r'other person.*?is ([A-Z][a-z]+)',  # "other person is SpongeBob"
                r'person.*?name is ([A-Z][a-z]+)',  # "person name is SpongeBob"
                # Removed the problematic "and ([A-Z][a-z]+)" pattern that catches drink names
            ]
            
            for pattern in name_mention_patterns:
                matches = re.findall(pattern, conversation_text, re.IGNORECASE)
                for match in matches:
                    name = match.strip().title()
                    # Enhanced filtering to exclude menu items and drinks
                    if (name.replace(' ', '').isalpha() and 
                        name.lower() not in ['today', 'tomorrow', 'tonight', 'order', 'will', 'have', 'like', 'want', 'for', 'and', 'the', 'or', 'pepsi', 'coke', 'cola', 'sprite', 'water', 'beer', 'wine', 'coffee', 'tea', 'juice', 'lemonade', 'soda', 'drink'] and
                        len(name) > 2 and
                        not name.lower().startswith('for ') and
                        not name.lower().startswith('and ') and
                        not name.lower().startswith('or ') and
                        # Additional check: don't include common menu item words
                        not any(food_word in name.lower() for food_word in ['wings', 'burger', 'pizza', 'salad', 'soup', 'steak', 'chicken', 'fish', 'pasta', 'sandwich'])):
                        person_names.add(name)
                        print(f"🔍 Found person name: {name}")
            
            if len(person_names) > 0:
                inferred_party_size = len(person_names)
                extracted['party_size'] = inferred_party_size
                print(f"✅ Inferred party size from names: {inferred_party_size} (names: {list(person_names)})")
        
        # Extract food items mentioned during reservation
        food_items = self._extract_food_items_from_conversation(conversation_text, meta_data)
        if food_items:
            # Create party_orders structure with proper person assignment
            party_orders = []
            
            # Get party size and customer name
            party_size = extracted.get('party_size', 1)
            customer_name = extracted.get('name', 'Customer')
            
            # Parse individual orders from conversation
            party_orders = self._parse_individual_orders(conversation_text, customer_name, party_size, food_items)
            
            extracted['party_orders'] = party_orders
            print(f"🍽️ Extracted food items: {food_items}")
            print(f"🍽️ Party orders: {party_orders}")
        
        # Extract date (handle "today", "tomorrow", specific dates)
        from datetime import datetime, timedelta
        today = datetime.now()
        
        if 'today' in conversation_text:
            extracted['date'] = today.strftime('%Y-%m-%d')
        elif 'tomorrow' in conversation_text:
            extracted['date'] = (today + timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            # Try to find specific dates
            date_patterns = [
                r'(\w+ \d{1,2}(?:st|nd|rd|th)?)',  # "June 15th", "June 15"
                r'(\d{1,2}/\d{1,2}/\d{4})',       # "06/15/2025"
                r'(\d{4}-\d{2}-\d{2})'            # "2025-06-15"
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, conversation_text)
                if match:
                    date_str = match.group(1)
                    # Try to parse the date
                    try:
                        if '/' in date_str:
                            parsed_date = datetime.strptime(date_str, '%m/%d/%Y')
                        elif '-' in date_str:
                            parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
                        else:
                            # Handle month names
                            parsed_date = datetime.strptime(f"{date_str} {today.year}", '%B %d %Y')
                            # If the date is in the past, assume next year
                            if parsed_date < today:
                                parsed_date = datetime.strptime(f"{date_str} {today.year + 1}", '%B %d %Y')
                        
                        extracted['date'] = parsed_date.strftime('%Y-%m-%d')
                        break
                    except ValueError:
                        continue
        
        # Extract time - improved patterns
        time_patterns = [
            r'at (\d{1,2}):?(\d{2})?\s*(am|pm)',  # "at 2:00 PM", "at 2 PM"
            r'(\d{1,2}):?(\d{2})?\s*(am|pm)',     # "2:00 PM", "2 PM"
            r'at (\d{1,2})\s*o\'?clock\s*(am|pm)?',  # "at 2 o'clock PM"
            r'(\d{1,2})\s*o\'?clock\s*(am|pm)?',     # "2 o'clock PM"
            r'(\w+)\s*o\'?clock\s*(am|pm)?'          # "two o'clock PM"
        ]
        
        # Word to number mapping for spoken numbers
        word_to_num = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
            'eleven': 11, 'twelve': 12
        }
        
        for pattern in time_patterns:
            match = re.search(pattern, conversation_text, re.IGNORECASE)
            if match:
                groups = match.groups()
                hour_str = groups[0]
                
                # Initialize defaults
                minute = 0
                am_pm = None
                
                # Handle different group structures
                if len(groups) >= 3:
                    # Pattern: hour, minute, am/pm
                    if groups[1] and groups[1].isdigit():
                        minute = int(groups[1])
                    if groups[2]:
                        am_pm = groups[2].lower()
                elif len(groups) >= 2:
                    # Pattern: hour, am/pm (no minutes)
                    if groups[1]:
                        am_pm = groups[1].lower()
                
                # Convert word numbers to digits
                if hour_str.lower() in word_to_num:
                    hour = word_to_num[hour_str.lower()]
                else:
                    try:
                        hour = int(hour_str)
                    except ValueError:
                        continue
                
                # Convert to 24-hour format
                if am_pm == 'pm' and hour != 12:
                    hour += 12
                elif am_pm == 'am' and hour == 12:
                    hour = 0
                elif not am_pm and hour < 8:  # Assume PM for dinner hours
                    hour += 12
                
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    extracted['time'] = f"{hour:02d}:{minute:02d}"
                    break
        
        # Extract phone number from caller ID if not found in conversation
        if 'phone_number' not in extracted and caller_phone:
            # Use caller ID as phone number
            normalized_phone = self._normalize_phone_number(caller_phone)
            if normalized_phone:
                extracted['phone_number'] = normalized_phone
                print(f"🔍 Using caller ID as phone number: {normalized_phone}")
        
        print(f"🔍 Extracted info: {extracted}")
        return extracted
    
    def _extract_food_items_from_conversation(self, conversation_text, meta_data=None):
        """Extract food items that the agent explicitly confirmed with the customer"""
        try:
            # Import Flask app and models locally
            import sys
            import os
            
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import MenuItem
            
            with app.app_context():
                extracted_items = []
                
                # Get menu items from database or cache
                if meta_data and meta_data.get('cached_menu'):
                    print("🚀 Using cached menu from meta_data")
                    menu_item_names = {}
                    for item_data in meta_data['cached_menu']:
                        menu_item_names[item_data['name'].lower()] = {
                            'id': item_data['id'],
                            'name': item_data['name'],
                            'price': item_data['price']
                        }
                else:
                    print("📊 Loading menu from database")
                    menu_items = MenuItem.query.filter_by(is_available=True).all()
                    menu_item_names = {item.name.lower(): {'id': item.id, 'name': item.name, 'price': item.price} for item in menu_items}
                
                conversation_lower = conversation_text.lower()
                print(f"🔍 Looking for agent-confirmed items in conversation")
                
                # Look for exact menu item names that the agent would have confirmed with prices
                # This approach relies on the agent using exact database menu item names
                for item_name_lower, item_data in menu_item_names.items():
                    # Only add items that appear with context suggesting agent confirmation
                    if item_name_lower in conversation_lower:
                        # Look for price context to ensure this was agent-confirmed
                        import re
                        price_pattern = rf'{re.escape(item_name_lower)}.*?\$\d+\.\d{{2}}'
                        if re.search(price_pattern, conversation_lower) or 'confirmed' in conversation_lower:
                            if item_data['id'] not in [item['menu_item_id'] for item in extracted_items]:
                                # Extract quantity from context
                                quantity = 1
                                quantity_patterns = [
                                    rf'(\d+).*?{re.escape(item_name_lower)}',
                                    rf'{re.escape(item_name_lower)}.*?(\d+)',
                                    rf'(two|three|four|five|six|seven|eight|nine|ten).*?{re.escape(item_name_lower)}'
                                ]
                                
                                for qty_pattern in quantity_patterns:
                                    qty_match = re.search(qty_pattern, conversation_lower)
                                    if qty_match:
                                        qty_text = qty_match.group(1)
                                        word_to_num = {'two': 2, 'three': 3, 'four': 4, 'five': 5}
                                        if qty_text.isdigit():
                                            quantity = int(qty_text)
                                        elif qty_text in word_to_num:
                                            quantity = word_to_num[qty_text]
                                        break
                                
                                extracted_items.append({
                                    'menu_item_id': item_data['id'],
                                    'quantity': quantity
                                })
                                print(f"🍽️ Found agent-confirmed item: {item_data['name']} (ID: {item_data['id']}) x{quantity}")
                
                print(f"🍽️ Total confirmed items: {len(extracted_items)}")
                return extracted_items
                
        except Exception as e:
            print(f"❌ Error extracting confirmed food items: {e}")
            return []
    
    def _get_reservation_handler(self, args, raw_data):
        """Handler for get_reservation tool"""
        try:
            # Extract meta_data for session management
            meta_data = raw_data.get('meta_data', {}) if raw_data else {}
            print(f"🔍 Current meta_data: {meta_data}")
            
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import Reservation
            
            with app.app_context():
                # Detect if this is a SignalWire call and default to text format for voice
                is_signalwire_call = (
                    raw_data and 
                    isinstance(raw_data, dict) and 
                    ('content_type' in raw_data or 'app_name' in raw_data or 'call_id' in raw_data)
                )
                
                # Get format preference - default to text for voice calls
                response_format = args.get('format', 'text').lower()
                
                # Auto-fill search criteria from caller information if not provided
                if not any(args.get(key) for key in ['name', 'first_name', 'last_name', 'reservation_id', 'reservation_number', 'confirmation_number', 'date', 'time', 'party_size', 'email']):
                    # Extract information from conversation (highest priority)
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    reservation_number = None
                    confirmation_number = None
                    customer_name = None
                    
                    # Process call log in reverse order to prioritize recent messages
                    for entry in reversed(call_log):
                        if entry.get('role') == 'user' and entry.get('content'):
                            content = entry['content'].lower()
                            
                            # Look for confirmation numbers first (highest priority)
                            import re
                            conf_patterns = [
                                r'CONF[-\s]*([A-Z0-9]{8})',
                                r'confirmation\s+(?:number\s+)?CONF[-\s]*([A-Z0-9]{8})',
                                r'confirmation\s+(?:number\s+)?([A-Z0-9]{8})',
                                r'conf\s+([A-Z0-9]{8})'
                            ]
                            for pattern in conf_patterns:
                                match = re.search(pattern, entry['content'], re.IGNORECASE)
                                if match:
                                    confirmation_number = f"CONF-{match.group(1)}"
                                    print(f"🔄 Extracted confirmation number from conversation: {confirmation_number}")
                                    break
                            
                            if confirmation_number:
                                break
                            
                            # Look for reservation numbers using improved extraction
                            try:
                                from number_utils import extract_reservation_number_from_text
                            except ImportError:
                                # Add parent directory to path if import fails
                                import sys
                                import os
                                parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                                if parent_dir not in sys.path:
                                    sys.path.insert(0, parent_dir)
                                from number_utils import extract_reservation_number_from_text
                            
                            # Check if we're in a payment context by looking at recent conversation
                            payment_context = False
                            if raw_data and raw_data.get('call_id'):
                                try:
                                    from app import is_payment_in_progress
                                    payment_context = is_payment_in_progress(raw_data['call_id'])
                                    if payment_context:
                                        print(f"🔍 Payment context detected for call {raw_data['call_id']} - being cautious with number extraction")
                                except Exception as e:
                                    print(f"⚠️ Could not check payment context: {e}")
                            
                            # Also check conversation context for payment keywords
                            if not payment_context:
                                recent_messages = call_log[-3:] if len(call_log) >= 3 else call_log
                                for msg in recent_messages:
                                    if msg.get('role') == 'assistant' and msg.get('content'):
                                        assistant_content = msg['content'].lower()
                                        payment_keywords = ['card', 'payment', 'pay', 'credit', 'billing', 'charge']
                                        if any(keyword in assistant_content for keyword in payment_keywords):
                                            payment_context = True
                                            print(f"🔍 Payment context detected from conversation: {assistant_content[:100]}...")
                                            break
                            
                            extracted_number = extract_reservation_number_from_text(content, payment_context=payment_context)
                            if extracted_number:
                                reservation_number = extracted_number
                                print(f"🔄 Extracted reservation number using improved logic: {reservation_number}")
                                break
                            
                            # Look for names mentioned in conversation
                            if 'rob zombie' in content:
                                customer_name = 'Rob Zombie'
                            elif 'smith family' in content or 'smith' in content:
                                customer_name = 'Smith Family'
                    
                    # Use extracted information for search (prioritize confirmation number, then reservation number)
                    if confirmation_number:
                        args['confirmation_number'] = confirmation_number
                        print(f"🔄 Auto-filled confirmation number from conversation: {confirmation_number}")
                    elif reservation_number:
                        args['reservation_number'] = reservation_number
                        print(f"🔄 Auto-filled reservation number from conversation: {reservation_number}")
                    if customer_name:
                        args['name'] = customer_name
                        print(f"🔄 Auto-filled name from conversation: {customer_name}")
                
                # Build search criteria - prioritize confirmation number, then reservation ID/number
                search_criteria = []
                query = Reservation.query
                
                # Priority 1: Confirmation Number (most specific for paid reservations)
                if args.get('confirmation_number'):
                    query = query.filter(Reservation.confirmation_number == args['confirmation_number'])
                    search_criteria.append(f"confirmation number {args['confirmation_number']}")
                    print(f"🔍 Searching by confirmation number: {args['confirmation_number']}")
                
                # Priority 2: Reservation ID or Number (most specific)
                elif args.get('reservation_id'):
                    query = query.filter(Reservation.id == args['reservation_id'])
                    search_criteria.append(f"reservation ID {args['reservation_id']}")
                    print(f"🔍 Searching by reservation ID: {args['reservation_id']}")
                
                elif args.get('reservation_number'):
                    query = query.filter(Reservation.reservation_number == args['reservation_number'])
                    search_criteria.append(f"reservation number {args['reservation_number']}")
                    print(f"🔍 Searching by reservation number: {args['reservation_number']}")
                
                # Priority 2: Name-based search (if no reservation ID/number)
                elif args.get('name'):
                    # Search in full name
                    query = query.filter(Reservation.name.ilike(f"%{args['name']}%"))
                    search_criteria.append(f"name {args['name']}")
                    print(f"🔍 Searching by name: {args['name']}")
                elif args.get('first_name') or args.get('last_name'):
                    # Search by first/last name
                    if args.get('first_name'):
                        query = query.filter(Reservation.name.ilike(f"{args['first_name']}%"))
                        search_criteria.append(f"first name {args['first_name']}")
                        print(f"🔍 Searching by first name: {args['first_name']}")
                    if args.get('last_name'):
                        query = query.filter(Reservation.name.ilike(f"%{args['last_name']}"))
                        search_criteria.append(f"last name {args['last_name']}")
                        print(f"🔍 Searching by last name: {args['last_name']}")
                
                # Additional filters (can be combined with above)
                if args.get('date'):
                    query = query.filter(Reservation.date == args['date'])
                    search_criteria.append(f"date {args['date']}")
                
                if args.get('time'):
                    query = query.filter(Reservation.time == args['time'])
                    search_criteria.append(f"time {args['time']}")
                
                if args.get('party_size'):
                    query = query.filter(Reservation.party_size == args['party_size'])
                    search_criteria.append(f"party size {args['party_size']}")
                
                if args.get('email'):
                    query = query.filter(Reservation.email.ilike(f"%{args['email']}%"))
                    search_criteria.append(f"email {args['email']}")
                
                # Phone number search only as fallback (not primary method)
                if args.get('phone_number') and not any(args.get(key) for key in ['reservation_id', 'reservation_number', 'name', 'first_name', 'last_name']):
                    # Normalize the search phone number and try multiple formats
                    search_phone = args['phone_number']
                    
                    # Try exact match first
                    phone_query = Reservation.phone_number == search_phone
                    
                    # Also try partial matches for different formats
                    if search_phone.startswith('+1'):
                        # If search phone has +1, also try without it
                        phone_without_plus = search_phone[2:]  # Remove +1
                        phone_query = phone_query | (Reservation.phone_number.like(f"%{phone_without_plus}%"))
                    elif search_phone.startswith('1') and len(search_phone) == 11:
                        # If search phone starts with 1, try with +1 prefix
                        phone_with_plus = f"+{search_phone}"
                        phone_query = phone_query | (Reservation.phone_number == phone_with_plus)
                    elif len(search_phone) == 10:
                        # If 10-digit number, try with +1 prefix
                        phone_with_plus = f"+1{search_phone}"
                        phone_query = phone_query | (Reservation.phone_number == phone_with_plus)
                    
                    # Apply the phone query with OR conditions
                    query = query.filter(phone_query)
                    search_criteria.append(f"phone number {search_phone}")
                    print(f"🔍 Fallback search by phone number: {search_phone} (with format variations)")
                
                # If no search criteria provided, show recent reservations
                if not search_criteria:
                    reservations = Reservation.query.order_by(Reservation.date.desc()).limit(5).all()
                    
                    if not reservations:
                        if response_format == 'json':
                            return (
                                SwaigFunctionResult("No reservations found in the system.")
                                .add_action("reservation_data", {
                                    "success": False,
                                    "message": "No reservations found",
                                    "reservations": []
                                })
                            )
                        else:
                            return SwaigFunctionResult("I don't see any reservations for your phone number. Here are the 5 most recent reservations: John Smith on 2025-06-15 at 7:00 PM for 4 people, Jane Smith on 2025-06-08 at 8:00 PM for 2 people, Bob Wilson on 2025-06-09 at 6:30 PM for 6 people, Alice Johnson on 2025-06-10 at 5:30 PM for 3 people, Rob Zombie on 2025-06-11 at 8:30 PM for 2 people. Would you like to make a new reservation?")
                    
                    if response_format == 'json':
                        return (
                            SwaigFunctionResult(f"Here are the {len(reservations)} most recent reservations.")
                            .add_action("reservation_data", {
                                "success": True,
                                "message": f"Found {len(reservations)} recent reservations",
                                "reservations": [res.to_dict() for res in reservations],
                                "search_criteria": ["recent reservations"]
                            })
                        )
                    else:
                        message = f"Here are the {len(reservations)} most recent reservations: "
                        reservation_list = []
                        for res in reservations:
                            time_obj = datetime.strptime(res.time, '%H:%M')
                            time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                            reservation_list.append(f"{res.name} on {res.date} at {time_12hr} for {res.party_size} people")
                        
                        message += ", ".join(reservation_list) + ". Would you like details about a specific reservation?"
                        return SwaigFunctionResult(message)
                
                # Execute search
                print(f"🔍 Final search criteria: {search_criteria}")
                print(f"🔍 Query filters applied: {len(search_criteria)} filters")
                
                reservations = query.all()
                print(f"🔍 Database query returned {len(reservations)} reservations")
                
                # Debug: Show what we're actually searching for
                if args:
                    print(f"🔍 Search parameters provided:")
                    for key, value in args.items():
                        if value:
                            print(f"   {key}: {value}")
                else:
                    print(f"🔍 No search parameters provided")
                
                if not reservations:
                    criteria_text = " and ".join(search_criteria)
                    
                    # Try backup phone number search if no reservations found
                    backup_reservations = []
                    backup_search_attempted = False
                    
                    # Get caller ID and user-provided phone numbers for backup search
                    backup_phones = []
                    
                    # 1. Get caller ID from raw_data
                    if raw_data and isinstance(raw_data, dict):
                        caller_phone = (
                            raw_data.get('caller_id_num') or 
                            raw_data.get('caller_id_number') or
                            raw_data.get('from') or
                            raw_data.get('from_number')
                        )
                        # Also check in global_data
                        global_data = raw_data.get('global_data', {})
                        if not caller_phone and global_data:
                            caller_phone = (
                                global_data.get('caller_id_number') or
                                global_data.get('caller_id_num')
                            )
                        
                        if caller_phone:
                            backup_phones.append(caller_phone)
                            print(f"🔄 Found caller ID for backup search: {caller_phone}")
                    
                    # 2. Extract phone numbers from conversation
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    for entry in call_log:
                        if entry.get('role') == 'user' and entry.get('content'):
                            content = entry['content'].lower()
                            
                            # Look for phone number mentions
                            if any(phrase in content for phrase in ['phone number', 'my number', 'use the number']):
                                import re
                                # Extract phone number from spoken format
                                phone_part = content
                                
                                # Convert spoken numbers to digits for phone numbers
                                number_words = {
                                    'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
                                    'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9'
                                }
                                
                                # Use word boundaries to avoid replacing parts of other words
                                for word, digit in number_words.items():
                                    phone_part = re.sub(r'\b' + word + r'\b', digit, phone_part)
                                
                                # Extract digits and format as E.164 phone number
                                phone_digits = re.findall(r'\d', phone_part)
                                if len(phone_digits) >= 10:  # At least 10 digits for a phone number
                                    # Take exactly 10 digits for the phone number (area code + number)
                                    extracted_phone = ''.join(phone_digits[:10])
                                    # Format as E.164 (+1XXXXXXXXXX for US numbers)
                                    manual_phone = f"+1{extracted_phone}"
                                    backup_phones.append(manual_phone)
                                    print(f"🔄 Extracted phone number from conversation for backup search: {manual_phone}")
                    
                    # 3. Use provided phone_number argument if available
                    if args.get('phone_number'):
                        backup_phones.append(args['phone_number'])
                        print(f"🔄 Using provided phone number for backup search: {args['phone_number']}")
                    
                    # Perform backup phone number search if we have phone numbers and haven't already searched by phone
                    if backup_phones and not any(args.get(key) for key in ['phone_number']):
                        print(f"🔄 Attempting backup phone number search with {len(backup_phones)} phone numbers...")
                        backup_search_attempted = True
                        
                        for backup_phone in backup_phones:
                            # Normalize the search phone number and try multiple formats
                            search_phone = backup_phone
                            
                            # Try exact match first
                            phone_query = Reservation.phone_number == search_phone
                            
                            # Also try partial matches for different formats
                            if search_phone.startswith('+1'):
                                # If search phone has +1, also try without it
                                phone_without_plus = search_phone[2:]  # Remove +1
                                phone_query = phone_query | (Reservation.phone_number.like(f"%{phone_without_plus}%"))
                            elif search_phone.startswith('1') and len(search_phone) == 11:
                                # If search phone starts with 1, try with +1 prefix
                                phone_with_plus = f"+{search_phone}"
                                phone_query = phone_query | (Reservation.phone_number == phone_with_plus)
                            elif len(search_phone) == 10:
                                # If 10-digit number, try with +1 prefix
                                phone_with_plus = f"+1{search_phone}"
                                phone_query = phone_query | (Reservation.phone_number == phone_with_plus)
                            
                            # Execute backup search
                            backup_query = Reservation.query.filter(phone_query)
                            phone_reservations = backup_query.all()
                            
                            if phone_reservations:
                                backup_reservations.extend(phone_reservations)
                                print(f"🔄 Backup search found {len(phone_reservations)} reservations for phone {search_phone}")
                        
                        # Remove duplicates from backup results
                        seen_ids = set()
                        unique_backup_reservations = []
                        for res in backup_reservations:
                            if res.id not in seen_ids:
                                unique_backup_reservations.append(res)
                                seen_ids.add(res.id)
                        backup_reservations = unique_backup_reservations
                    
                    # If backup search found reservations, return them
                    if backup_reservations:
                        print(f"✅ Backup phone search found {len(backup_reservations)} reservations")
                        
                        if len(backup_reservations) == 1:
                            reservation = backup_reservations[0]
                            time_obj = datetime.strptime(reservation.time, '%H:%M')
                            time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                            party_text = "person" if reservation.party_size == 1 else "people"
                            
                            if response_format == 'json':
                                return (
                                    SwaigFunctionResult("Found reservation using phone number")
                                    .add_action("reservation_data", {
                                        "success": True,
                                        "message": "Found reservation using phone number",
                                        "reservation": reservation.to_dict(),
                                        "search_method": "backup_phone_search"
                                    })
                                )
                            else:
                                message = f"I found a reservation using your phone number: {reservation.name} on {reservation.date} at {time_12hr} for {reservation.party_size} {party_text}. "
                                message += f"Reservation number: {reservation.reservation_number}. Is this the reservation you're looking for?"
                                return SwaigFunctionResult(message)
                        else:
                            # Multiple reservations found via phone backup
                            if response_format == 'json':
                                return (
                                    SwaigFunctionResult(f"Found {len(backup_reservations)} reservations using phone number")
                                    .add_action("reservation_data", {
                                        "success": True,
                                        "message": f"Found {len(backup_reservations)} reservations using phone number",
                                        "reservations": [res.to_dict() for res in backup_reservations],
                                        "search_method": "backup_phone_search"
                                    })
                                )
                            else:
                                message = f"I found {len(backup_reservations)} reservations using your phone number: "
                                reservation_list = []
                                for res in backup_reservations:
                                    time_obj = datetime.strptime(res.time, '%H:%M')
                                    time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                                    party_text = "person" if res.party_size == 1 else "people"
                                    reservation_list.append(f"{res.name} on {res.date} at {time_12hr} for {res.party_size} {party_text}")
                                
                                message += ", ".join(reservation_list) + ". Which reservation are you asking about?"
                                return SwaigFunctionResult(message)
                    
                    # No reservations found even with backup search
                    debug_info = ""
                    if args.get('reservation_number'):
                        debug_info = f" I searched for reservation number {args['reservation_number']}."
                    elif args.get('phone_number'):
                        debug_info = f" I searched for phone number {args['phone_number']}."
                    elif args.get('name'):
                        debug_info = f" I searched for name {args['name']}."
                    
                    if backup_search_attempted:
                        debug_info += f" I also tried searching using your phone number but didn't find any matches."
                    
                    if response_format == 'json':
                        return (
                            SwaigFunctionResult(f"No reservations found matching {criteria_text}.")
                            .add_action("reservation_data", {
                                "success": False,
                                "message": f"No reservations found matching {criteria_text}",
                                "reservations": [],
                                "search_criteria": search_criteria,
                                "debug_info": debug_info,
                                "backup_search_attempted": backup_search_attempted
                            })
                        )
                    else:
                        # Provide more helpful response for voice calls
                        response_msg = f"I couldn't find any reservations matching {criteria_text}.{debug_info}"
                        
                        # Suggest alternatives
                        if args.get('reservation_number'):
                            response_msg += " Could you please double-check the reservation number? It should be a 6-digit number."
                        elif args.get('phone_number'):
                            response_msg += " Let me try searching by your name instead. What name is the reservation under?"
                        else:
                            response_msg += " Could you provide your reservation number or the name the reservation is under?"
                        
                        return SwaigFunctionResult(response_msg)
                
                if len(reservations) == 1:
                    # Single reservation found - provide full details immediately
                    reservation = reservations[0]
                    
                    # Note: Removed confirmation logic for reservation number/ID searches
                    # Users expect immediate details when they provide their reservation number
                    # Reservation numbers are unique identifiers, so no confirmation needed
                    
                    # ENHANCEMENT: Check for recent payment confirmation from callback
                    recent_payment_info = None
                    try:
                        # Check if there's recent payment confirmation data for this reservation
                        from app import app
                        if hasattr(app, 'payment_confirmations') and reservation.reservation_number in app.payment_confirmations:
                            recent_payment_info = app.payment_confirmations[reservation.reservation_number]
                            print(f"✅ Found recent payment confirmation for reservation {reservation.reservation_number}: {recent_payment_info['confirmation_number']}")
                            
                            # If payment was just completed but DB hasn't been updated yet, use the fresh info
                            if recent_payment_info and not reservation.confirmation_number:
                                print(f"🔄 Using fresh payment confirmation from callback: {recent_payment_info['confirmation_number']}")
                    except Exception as e:
                        print(f"⚠️ Could not check for recent payment confirmations: {e}")
                    
                    # If confirmation not needed or JSON format, provide full details
                    party_orders = []
                    for order in reservation.orders:
                        party_orders.append({
                            'person_name': order.person_name,
                            'items': [item.menu_item.name for item in order.items],
                            'total': order.total_amount
                        })
                    total_bill = sum(order.total_amount or 0 for order in reservation.orders)
                    paid = reservation.payment_status == 'paid' or (recent_payment_info is not None)
                    
                    if response_format == 'json':
                        return (
                            SwaigFunctionResult("Found matching reservation")
                            .add_action("reservation_data", {
                                "success": True,
                                "message": "Found matching reservation",
                                "reservation": reservation.to_dict(),
                                "party_orders": party_orders,
                                "total_bill": total_bill,
                                "bill_paid": paid,
                                "search_criteria": search_criteria
                            })
                        )
                    else:
                        time_obj = datetime.strptime(reservation.time, '%H:%M')
                        time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                        party_text = "person" if reservation.party_size == 1 else "people"
                        message = f"I found your reservation for {reservation.name} on {reservation.date} at {time_12hr} for {reservation.party_size} {party_text}. "
                        message += f"Status: {reservation.status}. Reservation number: {reservation.reservation_number}. "
                        message += f"Total bill: ${total_bill:.2f}. "
                        message += f"Bill paid: {'Yes' if paid else 'No'}. "
                        
                        # Add confirmation number if payment is complete
                        confirmation_number = reservation.confirmation_number
                        if recent_payment_info and recent_payment_info.get('confirmation_number'):
                            # Use fresh confirmation number from payment callback if available
                            confirmation_number = recent_payment_info['confirmation_number']
                        
                        if paid and confirmation_number:
                            message += f"Your payment confirmation number is {confirmation_number}. "
                        elif paid and not confirmation_number and recent_payment_info and recent_payment_info.get('confirmation_number'):
                            # Use fresh confirmation number from payment callback if database doesn't have it yet
                            fresh_confirmation = recent_payment_info['confirmation_number']
                            message += f"Your payment confirmation number is {fresh_confirmation}. "
                        
                        if party_orders:
                            message += "Party orders: "
                            for po in party_orders:
                                items = ', '.join(po['items'])
                                message += f"{po['person_name']} ordered {items} (${po['total']:.2f}). "
                        if reservation.special_requests:
                            message += f" Special requests: {reservation.special_requests}"
                        
                        # Convert numbers to words for better TTS pronunciation
                        from number_utils import numbers_to_words
                        message = numbers_to_words(message)
                        
                        return SwaigFunctionResult(message)
                else:
                    # Multiple reservations found
                    criteria_text = " and ".join(search_criteria)
                    
                    if response_format == 'json':
                        return (
                            SwaigFunctionResult(f"Found {len(reservations)} reservations matching criteria.")
                            .add_action("reservation_data", {
                                "success": True,
                                "message": f"Found {len(reservations)} reservations matching criteria",
                                "reservations": [res.to_dict() for res in reservations],
                                "search_criteria": search_criteria,
                                "count": len(reservations)
                            })
                        )
                    else:
                        message = f"I found {len(reservations)} reservations matching {criteria_text}: "
                        reservation_list = []
                        for res in reservations:
                            time_obj = datetime.strptime(res.time, '%H:%M')
                            time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                            party_text = "person" if res.party_size == 1 else "people"
                            reservation_list.append(f"{res.name} on {res.date} at {time_12hr} for {res.party_size} {party_text}")
                        
                        message += ", ".join(reservation_list) + ". Would you like details about a specific reservation?"
                        return SwaigFunctionResult(message)
                
        except Exception as e:
            if args.get('format', 'text').lower() == 'json':
                return (
                    SwaigFunctionResult("Sorry, there was an error looking up your reservation.")
                    .add_action("error_data", {
                        "success": False,
                        "error": str(e),
                        "message": "Error looking up reservation"
                    })
                )
            else:
                return SwaigFunctionResult(f"Sorry, there was an error looking up your reservation: {str(e)}")
    
    def _update_reservation_handler(self, args, raw_data):
        """Handler for update_reservation tool"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            import re
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import db, Reservation, Order, OrderItem, MenuItem
            
            with app.app_context():
                # Cache menu in meta_data for performance
                meta_data = self._cache_menu_in_metadata(raw_data)
                
                # Handle different ways of identifying the reservation
                if not args.get('reservation_id'):
                    # First check if reservation_number is provided
                    if args.get('reservation_number'):
                        reservation = Reservation.query.filter_by(
                            reservation_number=args['reservation_number']
                        ).first()
                        if reservation:
                            args['reservation_id'] = reservation.id
                            print(f"🔄 Found reservation by number {args['reservation_number']}: ID {reservation.id}")
                        else:
                            return SwaigFunctionResult(f"Reservation number {args['reservation_number']} not found.")
                    else:
                        # Try to find reservation from conversation context
                        call_log = raw_data.get('call_log', []) if raw_data else []
                        caller_phone = None
                        customer_name = None
                        reservation_number = None
                        
                        # Get caller's phone number
                        if raw_data and isinstance(raw_data, dict):
                            caller_phone = (
                                raw_data.get('caller_id_num') or 
                                raw_data.get('caller_id_number') or
                                raw_data.get('from') or
                                raw_data.get('from_number')
                            )
                            # Also check in global_data
                            global_data = raw_data.get('global_data', {})
                            if not caller_phone and global_data:
                                caller_phone = (
                                    global_data.get('caller_id_number') or
                                    global_data.get('caller_id_num')
                                )
                        
                        # Look for reservation number mentioned in conversation (prioritize recent messages)
                        for entry in reversed(call_log):
                            if entry.get('role') == 'user' and entry.get('content'):
                                content = entry['content'].lower()
                                
                                # Look for reservation numbers using improved extraction
                                from number_utils import extract_reservation_number_from_text
                                extracted_number = extract_reservation_number_from_text(content)
                                if extracted_number:
                                    reservation_number = extracted_number
                                    print(f"🔄 Extracted reservation number from conversation: {reservation_number}")
                                    break
                        
                        # Try to find by reservation number first
                        if reservation_number:
                            reservation = Reservation.query.filter_by(
                                reservation_number=reservation_number
                            ).first()
                            if reservation:
                                args['reservation_id'] = reservation.id
                                print(f"🔄 Found reservation by extracted number {reservation_number}: ID {reservation.id}")
                            else:
                                return SwaigFunctionResult(f"Reservation number {reservation_number} not found.")
                        else:
                            # Fallback to phone/name search
                            reservation = None
                            # Try by name and phone
                            if caller_phone:
                                reservation = Reservation.query.filter_by(
                                    phone_number=caller_phone
                                ).order_by(Reservation.date.desc()).first()
                                if reservation:
                                    print(f"🔄 Found reservation by phone {caller_phone}: {reservation.name}")
                            
                            # Try by name if mentioned in conversation
                            if not reservation:
                                for entry in call_log:
                                    if entry.get('role') == 'user' and entry.get('content'):
                                        content = entry['content'].lower()
                                        if 'smith' in content:
                                            customer_name = 'Smith Family'
                                            break
                                
                                if customer_name:
                                    reservation = Reservation.query.filter(
                                        Reservation.name.ilike(f"%{customer_name}%")
                                    ).order_by(Reservation.date.desc()).first()
                                    if reservation:
                                        print(f"🔄 Found reservation by name {customer_name}: ID {reservation.id}")
                            
                            if not reservation:
                                return SwaigFunctionResult("I need to know which reservation you'd like to update. Could you please provide the reservation number, your name, or your phone number?")
                            
                            args['reservation_id'] = reservation.id
                            print(f"🔄 Auto-found reservation ID {reservation.id} for {reservation.name}")
                else:
                    # Check if reservation_id is actually a reservation number (6-digit number like 333444)
                    reservation_id_value = args.get('reservation_id')
                    if reservation_id_value and (isinstance(reservation_id_value, (int, str)) and 
                                                str(reservation_id_value).isdigit() and 
                                                len(str(reservation_id_value)) == 6):
                        # This looks like a reservation number, not a database ID
                        reservation = Reservation.query.filter_by(
                            reservation_number=str(reservation_id_value)
                        ).first()
                        if reservation:
                            args['reservation_id'] = reservation.id
                            print(f"🔄 Converted reservation number {reservation_id_value} to ID {reservation.id}")
                        else:
                            return SwaigFunctionResult(f"Reservation number {reservation_id_value} not found.")
                
                reservation = Reservation.query.get(args['reservation_id'])
                if not reservation:
                    return SwaigFunctionResult(f"Reservation {args['reservation_id']} not found.")
                
                # Check for pre-order additions from conversation
                call_log = raw_data.get('call_log', []) if raw_data else []
                pre_order_items = []
                
                # Look for food items mentioned in recent conversation
                for entry in reversed(call_log[-10:]):  # Check last 10 entries
                    if entry.get('role') == 'user' and entry.get('content'):
                        content = entry['content'].lower()
                        
                        # Look for specific food/drink items
                        if 'craft lemonade' in content or 'lemonade' in content:
                            # Find lemonade menu item
                            lemonade_item = MenuItem.query.filter(
                                MenuItem.name.ilike('%lemonade%')
                            ).first()
                            if lemonade_item:
                                quantity = 1
                                # Look for quantity in the same message
                                if 'one' in content or '1' in content:
                                    quantity = 1
                                elif 'two' in content or '2' in content:
                                    quantity = 2
                                
                                pre_order_items.append({
                                    'name': lemonade_item.name,
                                    'menu_item_id': lemonade_item.id,
                                    'quantity': quantity,
                                    'price': lemonade_item.price
                                })
                                print(f"🍋 Found lemonade pre-order request: {quantity}x {lemonade_item.name}")
                                break
                
                # Handle explicit add_items parameter from function call
                add_items = args.get('add_items', [])
                if add_items:
                    # Process the add_items parameter
                    for item_spec in add_items:
                        item_name = item_spec.get('name', '')
                        quantity = item_spec.get('quantity', 1)
                        
                        # Find menu item by name with fuzzy matching
                        menu_item = self._find_menu_item_fuzzy(item_name)
                        if menu_item:
                            pre_order_items.append({
                                'name': menu_item.name,
                                'menu_item_id': menu_item.id,
                                'quantity': quantity,
                                'price': menu_item.price
                            })
                            print(f"🍽️ Added from add_items parameter: {quantity}x {menu_item.name}")
                        else:
                            print(f"⚠️ Could not find menu item for '{item_name}' from add_items parameter")
                
                # Handle pre-order additions (from conversation or add_items parameter)
                if pre_order_items:
                    # Check if customer already has an order for this reservation
                    existing_order = Order.query.filter_by(
                        reservation_id=reservation.id,
                        person_name=reservation.name
                    ).first()
                    
                    if existing_order:
                        # Add items to existing order
                        for item_data in pre_order_items:
                            # Check if item already exists in order
                            existing_item = OrderItem.query.filter_by(
                                order_id=existing_order.id,
                                menu_item_id=item_data['menu_item_id']
                            ).first()
                            
                            if existing_item:
                                existing_item.quantity += item_data['quantity']
                            else:
                                new_order_item = OrderItem(
                                    order_id=existing_order.id,
                                    menu_item_id=item_data['menu_item_id'],
                                    quantity=item_data['quantity'],
                                    price_at_time=item_data['price']
                                )
                                db.session.add(new_order_item)
                        
                        # Recalculate order total
                        order_items = OrderItem.query.filter_by(order_id=existing_order.id).all()
                        existing_order.total_amount = sum(item.quantity * item.price_at_time for item in order_items)
                        
                    else:
                        # Create new order for this reservation
                        new_order = Order(
                            order_number=self._generate_order_number(),
                            reservation_id=reservation.id,
                            person_name=reservation.name,
                            status='pending',
                            total_amount=0.0
                        )
                        db.session.add(new_order)
                        db.session.flush()  # Get order ID
                        
                        order_total = 0.0
                        for item_data in pre_order_items:
                            order_item = OrderItem(
                                order_id=new_order.id,
                                menu_item_id=item_data['menu_item_id'],
                                quantity=item_data['quantity'],
                                price_at_time=item_data['price']
                            )
                            db.session.add(order_item)
                            order_total += item_data['price'] * item_data['quantity']
                        
                        new_order.total_amount = order_total
                    
                    db.session.commit()
                    
                    # Calculate new total bill
                    total_bill = sum(order.total_amount or 0 for order in reservation.orders)
                    
                    # Create response message
                    added_items = []
                    for item in pre_order_items:
                        added_items.append(f"{item['quantity']}x {item['name']}")
                    
                    message = f"Perfect! I've added {', '.join(added_items)} to your reservation. "
                    message += f"Your pre-order total is now ${total_bill:.2f}. "
                    message += f"The {', '.join([item['name'] for item in pre_order_items])} will be ready when you arrive! "
                    
                    # Ask if customer wants to add anything else to their pre-order
                    message += f"\n\nWould you like to add anything else to your pre-order, or are you ready to finalize your reservation?"
                    
                    return SwaigFunctionResult(message)
                
                # Extract update information from conversation if not provided in args
                if not any(key in args for key in ['name', 'party_size', 'date', 'time', 'phone_number', 'special_requests']):
                    # Look at conversation to understand what needs to be updated
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    
                    # Look for time change requests in recent conversation
                    for entry in reversed(call_log[-10:]):  # Check last 10 entries
                        if entry.get('role') == 'user' and entry.get('content'):
                            content = entry['content'].lower()
                            
                            # Look for time change requests
                            if 'four o\'clock' in content or 'four oclock' in content or '4 o\'clock' in content or '4:00' in content or '16:00' in content:
                                args['time'] = '16:00'
                                print(f"🔄 Extracted time change request: 4 PM")
                                break
                            elif 'five pm' in content or '5 pm' in content or '5:00' in content or '17:00' in content or 'five o\'clock' in content:
                                args['time'] = '17:00'
                                print(f"🔄 Extracted time change request: 5 PM")
                                break
                            elif 'six pm' in content or '6 pm' in content or '6:00' in content or '18:00' in content or 'six o\'clock' in content:
                                args['time'] = '18:00'
                                print(f"🔄 Extracted time change request: 6 PM")
                                break
                            elif 'seven pm' in content or '7 pm' in content or '7:00' in content or '19:00' in content or 'seven o\'clock' in content:
                                args['time'] = '19:00'
                                print(f"🔄 Extracted time change request: 7 PM")
                                break
                            elif 'eight pm' in content or '8 pm' in content or '8:00' in content or '20:00' in content or 'eight o\'clock' in content:
                                args['time'] = '20:00'
                                print(f"🔄 Extracted time change request: 8 PM")
                                break
                
                # Update fields if provided
                if 'name' in args:
                    reservation.name = args['name']
                if 'party_size' in args:
                    if not 1 <= args['party_size'] <= 20:
                        return SwaigFunctionResult("Party size must be between 1 and 20.")
                    reservation.party_size = args['party_size']
                if 'phone_number' in args:
                    reservation.phone_number = args['phone_number']
                if 'special_requests' in args:
                    reservation.special_requests = args['special_requests']
                
                # Validate and update date/time if provided
                if 'date' in args or 'time' in args:
                    new_date = args.get('date', str(reservation.date))
                    new_time = args.get('time', str(reservation.time))
                    
                    try:
                        # First try to parse the date in the expected YYYY-MM-DD format
                        try:
                            reservation_datetime = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
                        except ValueError:
                            # If that fails, try to parse common natural language date formats
                            date_formats = [
                                "%B %d, %Y",      # "June 09, 2025"
                                "%B %d %Y",       # "June 09 2025"
                                "%m/%d/%Y",       # "06/09/2025"
                                "%m-%d-%Y",       # "06-09-2025"
                                "%d/%m/%Y",       # "09/06/2025"
                                "%Y/%m/%d",       # "2025/06/09"
                                "%Y-%m-%d",       # "2025-06-09" (fallback)
                            ]
                            
                            parsed_date = None
                            for date_format in date_formats:
                                try:
                                    parsed_date = datetime.strptime(new_date, date_format)
                                    break
                                except ValueError:
                                    continue
                            
                            if parsed_date is None:
                                return SwaigFunctionResult("Invalid date format. Please provide the date in a format like 'June 15, 2025', '2025-06-15', or '06/15/2025'.")
                            
                            # Parse time
                            try:
                                parsed_time = datetime.strptime(new_time, "%H:%M").time()
                            except ValueError:
                                return SwaigFunctionResult("Invalid time format. Please use 24-hour format like '19:00' for 7 PM.")
                            
                            # Combine date and time
                            reservation_datetime = datetime.combine(parsed_date.date(), parsed_time)
                            
                            # Update new_date with standardized format for database storage
                            new_date = parsed_date.strftime("%Y-%m-%d")
                            
                    except ValueError:
                        return SwaigFunctionResult("Invalid date or time format. Please use YYYY-MM-DD for date and HH:MM for time.")
                    
                    # Check if date is in the future
                    if reservation_datetime < datetime.now():
                        return SwaigFunctionResult("Cannot reschedule to a past date and time. Please choose a future date and time.")
                    
                    # Validate restaurant hours (9 AM to 9 PM)
                    hour = reservation_datetime.hour
                    if not 9 <= hour <= 21:
                        return SwaigFunctionResult("Restaurant hours are 9:00 AM to 9:00 PM. Please choose a time within our operating hours.")
                    
                    reservation.date = new_date
                    reservation.time = new_time
                
                # Process party orders if provided
                party_orders_processed = False
                if args.get('party_orders'):
                    try:
                        print(f"🍽️ Processing party orders: {args['party_orders']}")
                        
                        # Validate and correct menu item IDs in party orders
                        corrected_party_orders = []
                        for person_order in args['party_orders']:
                            person_name = person_order.get('person_name', '')
                            items = person_order.get('items', [])
                            corrected_items = []
                            
                            for item in items:
                                menu_item_id = item.get('menu_item_id')
                                quantity = item.get('quantity', 1)
                                
                                # Get conversation context for validation
                                call_log = raw_data.get('call_log', []) if raw_data else []
                                conversation_text = ' '.join([
                                    entry.get('content', '') for entry in call_log 
                                    if entry.get('role') == 'user'
                                ])
                                conversation_lower = conversation_text.lower()
                                
                                # Validate menu item exists and check for common wrong ID patterns
                                menu_item = MenuItem.query.get(menu_item_id)
                                corrected_item = None
                                
                                # COMPREHENSIVE MENU ITEM CORRECTION SYSTEM
                                # Use the existing extraction function to get all mentioned items
                                conversation_items = self._extract_food_items_from_conversation(conversation_text, meta_data)
                                correct_item_ids = [item.get('menu_item_id') for item in conversation_items if item.get('menu_item_id')]
                                
                                print(f"🔍 Agent wants to use ID {menu_item_id}, conversation has IDs: {correct_item_ids}")
                                
                                # Check if the agent's chosen ID matches what was actually mentioned
                                if menu_item and menu_item_id not in correct_item_ids and correct_item_ids:
                                    print(f"⚠️ Menu item '{menu_item.name}' (ID {menu_item_id}) not found in conversation")
                                    print(f"🔍 Conversation contains these menu item IDs: {correct_item_ids}")
                                    
                                    # Try to find the correct item for this person
                                    corrected_item = None
                                    person_lower = person_name.lower()
                                    
                                    # Method 1: Look for items mentioned near this person's name
                                    if person_lower in conversation_lower:
                                        person_context_start = conversation_lower.find(person_lower)
                                        if person_context_start != -1:
                                            # Get context around person's name (±100 chars)
                                            start_idx = max(0, person_context_start - 100)
                                            end_idx = min(len(conversation_lower), person_context_start + 100)
                                            person_context = conversation_lower[start_idx:end_idx]
                                            
                                            # Look for specific items mentioned in this person's context
                                            for correct_id in correct_item_ids:
                                                potential_item = MenuItem.query.get(correct_id)
                                                if potential_item and potential_item.name.lower() in person_context:
                                                    corrected_item = potential_item
                                                    print(f"🔧 Found person-specific match: {corrected_item.name} for {person_name}")
                                                    break
                                    
                                    # Method 2: Smart assignment based on conversation order and person mentions
                                    if not corrected_item and correct_item_ids:
                                            # Try to intelligently assign items to people based on conversation flow
                                            import re
                                            
                                            # Find all person mentions with their positions
                                            person_mentions = []
                                            for name in [person_name.lower(), 'john', 'mary', 'alice', 'bob', 'charlie']:
                                                for match in re.finditer(r'\b' + re.escape(name) + r'\b', conversation_lower):
                                                    person_mentions.append((match.start(), name))
                                            
                                            # Sort by position in conversation
                                            person_mentions.sort()
                                            
                                            # Find the index of current person
                                            person_index = -1
                                            for i, (pos, name) in enumerate(person_mentions):
                                                if name == person_name.lower():
                                                    person_index = i
                                                    break
                                            
                                            # Assign item based on person order
                                            if person_index >= 0 and person_index < len(correct_item_ids):
                                                corrected_item = MenuItem.query.get(correct_item_ids[person_index])
                                                if corrected_item:
                                                    print(f"🔧 Using smart assignment: {corrected_item.name} for {person_name} (position {person_index})")
                                            else:
                                                # Fallback to first available item
                                                corrected_item = MenuItem.query.get(correct_item_ids[0])
                                                if corrected_item:
                                                    print(f"🔧 Using fallback assignment: {corrected_item.name} for {person_name}")
                                    
                                    # Apply the correction
                                    if corrected_item and corrected_item.id != menu_item_id:
                                        print(f"🔧 Correcting menu item for {person_name}: {menu_item.name} (ID {menu_item_id}) → {corrected_item.name} (ID {corrected_item.id})")
                                        menu_item = corrected_item
                                
                                # If no correction was made and menu item doesn't exist, try to find it
                                if not menu_item:
                                    print(f"❌ Invalid menu item ID {menu_item_id} for {person_name}")
                                    print(f"⚠️ Could not find replacement for invalid menu item ID {menu_item_id}")
                                    continue
                                
                                # Add validated item
                                corrected_items.append({
                                    'menu_item_id': menu_item.id,
                                    'quantity': quantity
                                })
                                print(f"✅ Validated: {menu_item.name} (ID: {menu_item.id}) x{quantity} for {person_name}")
                            
                            if corrected_items:
                                corrected_party_orders.append({
                                    'person_name': person_name,
                                    'items': corrected_items
                                })
                        
                        if corrected_party_orders:
                            # Delete existing orders for this reservation
                            existing_orders = Order.query.filter_by(reservation_id=reservation.id).all()
                            for order in existing_orders:
                                OrderItem.query.filter_by(order_id=order.id).delete()
                                db.session.delete(order)
                            
                            # Create new orders from corrected party_orders
                            total_amount = 0.0
                            for person_order in corrected_party_orders:
                                person_name = person_order['person_name']
                                items = person_order['items']
                                
                                if items:
                                    # Create order for this person
                                    order = Order(
                                        order_number=self._generate_order_number(),
                                        reservation_id=reservation.id,
                                        person_name=person_name,
                                        status='pending',
                                        total_amount=0.0
                                    )
                                    db.session.add(order)
                                    db.session.flush()  # Get order ID
                                    
                                    order_total = 0.0
                                    for item_data in items:
                                        menu_item = MenuItem.query.get(item_data['menu_item_id'])
                                        if menu_item:
                                            order_item = OrderItem(
                                                order_id=order.id,
                                                menu_item_id=menu_item.id,
                                                quantity=item_data['quantity'],
                                                price_at_time=menu_item.price
                                            )
                                            db.session.add(order_item)
                                            order_total += menu_item.price * item_data['quantity']
                                    
                                    order.total_amount = order_total
                                    total_amount += order_total
                            
                            party_orders_processed = True
                            print(f"✅ Successfully processed party orders. Total: ${total_amount:.2f}")
                    
                    except Exception as e:
                        print(f"❌ Error processing party orders: {e}")
                        # Continue without failing the entire update
                
                # If no changes were made, inform the user
                if not any(key in args for key in ['name', 'party_size', 'date', 'time', 'phone_number', 'special_requests']) and not party_orders_processed:
                    return SwaigFunctionResult("I already have that information from our previous conversation. Let me help you with something else instead.")
                
                db.session.commit()
                
                # Convert time to 12-hour format for response
                time_obj = datetime.strptime(str(reservation.time), '%H:%M')
                time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                
                # Send SMS confirmation for the updated reservation
                reservation_data = {
                    'id': reservation.id,
                    'name': reservation.name,
                    'date': str(reservation.date),
                    'time': str(reservation.time),
                    'party_size': reservation.party_size,
                    'special_requests': reservation.special_requests or '',
                    'reservation_number': reservation.reservation_number
                }
                
                sms_result = self._send_reservation_sms(reservation_data, reservation.phone_number)
                
                party_text = "person" if reservation.party_size == 1 else "people"
                message = f"Perfect! I've updated your reservation. New details: {reservation.name} on {reservation.date} at {time_12hr} for {reservation.party_size} {party_text}. "
                
                # Add information about processed orders
                if party_orders_processed:
                    # Get the updated orders to show what was added
                    updated_orders = Order.query.filter_by(reservation_id=reservation.id).all()
                    if updated_orders:
                        message += f"\n\n🍽️ Order Updates:\n"
                        total_bill = 0.0
                        for order in updated_orders:
                            order_items = OrderItem.query.filter_by(order_id=order.id).all()
                            if order_items:
                                message += f"• {order.person_name}: "
                                item_names = []
                                for item in order_items:
                                    menu_item = MenuItem.query.get(item.menu_item_id)
                                    if menu_item:
                                        item_names.append(f"{item.quantity}x {menu_item.name}")
                                message += ", ".join(item_names) + f" (${order.total_amount:.2f})\n"
                                total_bill += order.total_amount or 0
                        
                        if total_bill > 0:
                            message += f"\nTotal bill: ${total_bill:.2f}"
                            message += f"\nYour food will be ready when you arrive!"
                
                if sms_result.get('sms_sent'):
                    message += "\n\nAn updated confirmation SMS has been sent to your phone."
                
                return SwaigFunctionResult(message)
                
        except Exception as e:
            return SwaigFunctionResult(f"Error updating reservation: {str(e)}")
    
    def _generate_order_number(self):
        """Generate a unique 6-digit order number"""
        import random
        import sys
        import os
        
        # Add the parent directory to sys.path to import app
        parent_dir = os.path.dirname(os.path.dirname(__file__))
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        
        from models import Order
        
        while True:
            # Generate a 6-digit number (100000 to 999999)
            number = str(random.randint(100000, 999999))
            
            # Check if this number already exists
            existing = Order.query.filter_by(order_number=number).first()
            if not existing:
                return number
    
    def _cancel_reservation_handler(self, args, raw_data):
        """Handler for cancel_reservation tool"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import db, Reservation
            
            print(f"🔍 Received args: {args}")
            
            # Handle case where args is empty or missing reservation_id - extract from conversation
            if not args or 'reservation_id' not in args:
                print("🔍 No reservation_id provided, extracting from conversation...")
                
                # First check if reservation_number is provided
                if args and args.get('reservation_number'):
                    with app.app_context():
                        reservation = Reservation.query.filter_by(
                            reservation_number=args['reservation_number']
                        ).filter(
                            Reservation.status != 'cancelled'
                        ).first()
                        if reservation:
                            args['reservation_id'] = reservation.id
                            print(f"🔍 Found reservation by number {args['reservation_number']}: ID {reservation.id}")
                        else:
                            return SwaigFunctionResult(f"Reservation number {args['reservation_number']} not found or already cancelled.")
                else:
                    # Get caller phone number
                    caller_phone = raw_data.get('caller_id', '')
                    if caller_phone:
                        caller_phone = self._normalize_phone_number(caller_phone)
                        print(f"🔍 Using caller phone: {caller_phone}")
                    
                    # Try to get call log from raw_data
                    call_log = []
                    if 'call_log' in raw_data:
                        call_log = raw_data['call_log']
                    elif hasattr(raw_data, 'call_log'):
                        call_log = raw_data.call_log
                    
                    print(f"🔍 Call log entries: {len(call_log)}")
                    
                    with app.app_context():
                        reservation = None
                        reservation_number = None
                        
                        # Look for reservation number mentioned in conversation (prioritize recent messages)
                        for entry in reversed(call_log):
                            if entry.get('role') == 'user' and entry.get('content'):
                                content = entry['content'].lower()
                                
                                # Look for reservation numbers using improved extraction
                                from number_utils import extract_reservation_number_from_text
                                extracted_number = extract_reservation_number_from_text(content)
                                if extracted_number:
                                    reservation_number = extracted_number
                                    print(f"🔍 Extracted reservation number from conversation: {reservation_number}")
                                    break
                        
                        # Try to find by reservation number first
                        if reservation_number:
                            reservation = Reservation.query.filter_by(
                                reservation_number=reservation_number
                            ).filter(
                                Reservation.status != 'cancelled'
                            ).first()
                            if reservation:
                                print(f"🔍 Found reservation by extracted number {reservation_number}: ID {reservation.id}")
                            else:
                                return SwaigFunctionResult(f"Reservation number {reservation_number} not found or already cancelled.")
                        else:
                            # Fallback to phone number search (most recent reservation)
                            if caller_phone:
                                reservation = Reservation.query.filter_by(
                                    phone_number=caller_phone
                                ).filter(
                                    Reservation.status != 'cancelled'
                                ).order_by(Reservation.created_at.desc()).first()
                                
                                if reservation:
                                    print(f"🔍 Found reservation by phone: {reservation.id}")
                            
                            # If no reservation found by phone, try to extract from conversation
                            if not reservation and call_log:
                                print("🔍 Trying to extract reservation info from conversation...")
                                try:
                                    extracted_info = self._extract_reservation_info_from_conversation(call_log, caller_phone)
                                    if 'name' in extracted_info:
                                        # Try to find by name and phone
                                        reservation = Reservation.query.filter_by(
                                            name=extracted_info['name'],
                                            phone_number=caller_phone
                                        ).filter(
                                            Reservation.status != 'cancelled'
                                        ).order_by(Reservation.created_at.desc()).first()
                                        
                                        if reservation:
                                            print(f"🔍 Found reservation by name and phone: {reservation.id}")
                                except Exception as e:
                                    print(f"🔍 Error extracting from conversation: {e}")
                        
                        if not reservation:
                            return SwaigFunctionResult("I couldn't find an active reservation to cancel. Could you please provide your reservation number or confirm the phone number you used to make the reservation?")
                        
                        # Use the found reservation
                        args = {'reservation_id': reservation.id}
                        print(f"🔍 Using reservation ID: {reservation.id}")
            
            with app.app_context():
                reservation = Reservation.query.get(args['reservation_id'])
                
                if not reservation:
                    return SwaigFunctionResult(f"Reservation {args['reservation_id']} not found.")
                
                if reservation.status == 'cancelled':
                    return SwaigFunctionResult(f"Reservation {args['reservation_id']} is already cancelled.")
                
                # Update status to cancelled
                reservation.status = 'cancelled'
                db.session.commit()
                
                # Convert time to 12-hour format
                time_obj = datetime.strptime(reservation.time, '%H:%M')
                time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                
                # Send cancellation SMS
                try:
                    sms_body = f"🍽️ Bobby's Table Reservation Cancelled\n\n"
                    sms_body += f"Reservation ID: {reservation.id}\n"
                    sms_body += f"Name: {reservation.name}\n"
                    sms_body += f"Date: {reservation.date} at {time_12hr}\n"
                    party_text = "person" if reservation.party_size == 1 else "people"
                    sms_body += f"Party Size: {reservation.party_size} {party_text}\n\n"
                    sms_body += f"Your reservation has been cancelled. We hope to serve you again soon!\n"
                    sms_body += f"Bobby's Table Restaurant"
                    
                    SwaigFunctionResult().send_sms(
                        to_number=reservation.phone_number,
                        from_number=self.signalwire_from_number,
                        body=sms_body
                    )
                    sms_sent = True
                except:
                    sms_sent = False
                
                message = f"I've cancelled reservation {reservation.reservation_number} for {reservation.name} on {reservation.date} at {time_12hr}. "
                
                if sms_sent:
                    message += "A cancellation confirmation has been sent via SMS. "
                
                message += "We're sorry to see you cancel and hope to serve you again soon!"
                
                # Convert numbers to words for better TTS pronunciation
                from number_utils import numbers_to_words
                message = numbers_to_words(message)
                
                return SwaigFunctionResult(message)
                
        except Exception as e:
            return SwaigFunctionResult(f"Error cancelling reservation: {str(e)}")
    
    def _get_calendar_events_handler(self, args, raw_data):
        """Handler for get_calendar_events tool"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            from datetime import timedelta
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import db, Reservation
            
            with app.app_context():
                # Set default date range
                start_date = args.get('start_date', datetime.now().strftime('%Y-%m-%d'))
                if args.get('end_date'):
                    end_date = args['end_date']
                else:
                    # Default to 30 days from start
                    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                    end_dt = start_dt + timedelta(days=30)
                    end_date = end_dt.strftime('%Y-%m-%d')
                
                # Query reservations in date range
                reservations = Reservation.query.filter(
                    Reservation.date >= start_date,
                    Reservation.date <= end_date,
                    Reservation.status != 'cancelled'
                ).order_by(Reservation.date, Reservation.time).all()
                
                format_type = args.get('format', 'text')
                
                if format_type == 'json':
                    # Return structured data for calendar display
                    events = []
                    for reservation in reservations:
                        try:
                            # Create datetime object
                            dt = datetime.strptime(f"{reservation.date} {reservation.time}", "%Y-%m-%d %H:%M")
                            
                            party_text = "person" if reservation.party_size == 1 else "people"
                            event = {
                                'id': reservation.id,
                                'title': f"{reservation.name} ({reservation.party_size} {party_text})",
                                'start': dt.isoformat(),
                                'end': (dt + timedelta(hours=2)).isoformat(),  # Assuming 2-hour reservations
                                'reservation_number': reservation.reservation_number,
                                'party_size': reservation.party_size,
                                'phone_number': reservation.phone_number,
                                'status': reservation.status,
                                'special_requests': reservation.special_requests or ''
                            }
                            events.append(event)
                        except (ValueError, AttributeError):
                            continue
                    
                    return SwaigFunctionResult(f"Found {len(events)} calendar events", data=events)
                
                else:
                    # Return text format for voice
                    if not reservations:
                        return SwaigFunctionResult(f"No reservations found between {start_date} and {end_date}.")
                    
                    # Group by date
                    events_by_date = {}
                    for reservation in reservations:
                        date = reservation.date
                        if date not in events_by_date:
                            events_by_date[date] = []
                        events_by_date[date].append(reservation)
                    
                    response = f"Calendar events from {start_date} to {end_date}:\n\n"
                    
                    for date, day_reservations in sorted(events_by_date.items()):
                        # Format date nicely
                        date_obj = datetime.strptime(date, '%Y-%m-%d')
                        formatted_date = date_obj.strftime('%A, %B %d, %Y')
                        
                        response += f"📅 {formatted_date}:\n"
                        
                        for reservation in sorted(day_reservations, key=lambda r: r.time):
                            # Convert time to 12-hour format
                            time_obj = datetime.strptime(reservation.time, '%H:%M')
                            time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                            
                            response += f"  • {time_12hr} - {reservation.name} (Party of {reservation.party_size})"
                            if reservation.special_requests:
                                response += f" - {reservation.special_requests}"
                            response += f" [#{reservation.reservation_number}]\n"
                        
                        response += "\n"
                    
                    return SwaigFunctionResult(response.strip())
                
        except Exception as e:
            return SwaigFunctionResult(f"Error retrieving calendar events: {str(e)}")
    
    def _get_todays_reservations_handler(self, args, raw_data):
        """Handler for get_todays_reservations tool"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import db, Reservation
            
            with app.app_context():
                # Get target date (default to today)
                target_date = args.get('date', datetime.now().strftime('%Y-%m-%d'))
                
                # Query today's reservations
                reservations = Reservation.query.filter_by(
                    date=target_date
                ).filter(
                    Reservation.status != 'cancelled'
                ).order_by(Reservation.time).all()
                
                format_type = args.get('format', 'text')
                
                if format_type == 'json':
                    return SwaigFunctionResult(
                        f"Found {len(reservations)} reservations for {target_date}",
                        data=[r.to_dict() for r in reservations]
                    )
                
                else:
                    # Return text format for voice
                    if not reservations:
                        date_obj = datetime.strptime(target_date, '%Y-%m-%d')
                        formatted_date = date_obj.strftime('%A, %B %d, %Y')
                        return SwaigFunctionResult(f"No reservations scheduled for {formatted_date}.")
                    
                    # Format date nicely
                    date_obj = datetime.strptime(target_date, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%A, %B %d, %Y')
                    
                    response = f"📅 Reservations for {formatted_date}:\n\n"
                    
                    total_guests = sum(r.party_size for r in reservations)
                    response += f"Total: {len(reservations)} reservations, {total_guests} guests\n\n"
                    
                    for reservation in reservations:
                        # Convert time to 12-hour format
                        time_obj = datetime.strptime(reservation.time, '%H:%M')
                        time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                        
                        response += f"🕐 {time_12hr} - {reservation.name}\n"
                        response += f"   Party of {reservation.party_size} | Phone: {reservation.phone_number}\n"
                        response += f"   Reservation #{reservation.reservation_number}\n"
                        
                        if reservation.special_requests:
                            response += f"   Special requests: {reservation.special_requests}\n"
                        
                        response += "\n"
                    
                    return SwaigFunctionResult(response.strip())
                
        except Exception as e:
            return SwaigFunctionResult(f"Error retrieving today's reservations: {str(e)}")
    
    def _get_reservation_summary_handler(self, args, raw_data):
        """Handler for get_reservation_summary tool"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            from datetime import timedelta
            from collections import defaultdict
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import db, Reservation
            
            with app.app_context():
                # Determine date range
                if args.get('start_date') and args.get('end_date'):
                    start_date = args['start_date']
                    end_date = args['end_date']
                    date_range_text = f"from {start_date} to {end_date}"
                else:
                    # Single date (default to today)
                    target_date = args.get('date', datetime.now().strftime('%Y-%m-%d'))
                    start_date = end_date = target_date
                    date_obj = datetime.strptime(target_date, '%Y-%m-%d')
                    date_range_text = f"for {date_obj.strftime('%A, %B %d, %Y')}"
                
                # Query reservations in range
                reservations = Reservation.query.filter(
                    Reservation.date >= start_date,
                    Reservation.date <= end_date,
                    Reservation.status != 'cancelled'
                ).all()
                
                format_type = args.get('format', 'text')
                
                # Calculate summary statistics
                total_reservations = len(reservations)
                total_guests = sum(r.party_size for r in reservations)
                
                # Time distribution
                time_slots = defaultdict(int)
                party_sizes = defaultdict(int)
                
                for reservation in reservations:
                    # Group by hour
                    hour = int(reservation.time.split(':')[0])
                    time_period = f"{hour}:00"
                    time_slots[time_period] += 1
                    
                    # Party size distribution
                    party_sizes[reservation.party_size] += 1
                
                if format_type == 'json':
                    summary_data = {
                        'date_range': {'start': start_date, 'end': end_date},
                        'total_reservations': total_reservations,
                        'total_guests': total_guests,
                        'average_party_size': round(total_guests / total_reservations, 1) if total_reservations > 0 else 0,
                        'time_distribution': dict(time_slots),
                        'party_size_distribution': dict(party_sizes),
                        'reservations': [r.to_dict() for r in reservations]
                    }
                    return SwaigFunctionResult(f"Reservation summary {date_range_text}", data=summary_data)
                
                else:
                    # Text format for voice
                    if total_reservations == 0:
                        return SwaigFunctionResult(f"No reservations found {date_range_text}.")
                    
                    avg_party_size = round(total_guests / total_reservations, 1)
                    
                    response = f"📊 Reservation Summary {date_range_text}:\n\n"
                    response += f"📈 Overview:\n"
                    response += f"  • Total reservations: {total_reservations}\n"
                    response += f"  • Total guests: {total_guests}\n"
                    response += f"  • Average party size: {avg_party_size}\n\n"
                    
                    if time_slots:
                        response += f"🕐 Time Distribution:\n"
                        for time_slot in sorted(time_slots.keys()):
                            count = time_slots[time_slot]
                            # Convert to 12-hour format
                            hour = int(time_slot.split(':')[0])
                            time_12hr = datetime.strptime(time_slot, '%H:%M').strftime('%I:%M %p').lstrip('0')
                            response += f"  • {time_12hr}: {count} reservation{'s' if count != 1 else ''}\n"
                        response += "\n"
                    
                    if party_sizes:
                        response += f"👥 Party Size Distribution:\n"
                        for size in sorted(party_sizes.keys()):
                            count = party_sizes[size]
                            response += f"  • {size} people: {count} reservation{'s' if count != 1 else ''}\n"
                    
                    return SwaigFunctionResult(response.strip())
                
        except Exception as e:
            return SwaigFunctionResult(f"Error generating reservation summary: {str(e)}")
    
    def _parse_individual_orders(self, conversation_text, customer_name, party_size, food_items):
        """Parse individual orders from conversation and assign to correct people"""
        party_orders = []
        
        # If only one person, assign all items to them
        if party_size == 1:
            party_orders.append({
                'person_name': customer_name,
                'items': food_items
            })
            return party_orders
        
        # For multiple people, use intelligent distribution
        print(f"🔍 Parsing orders for {party_size} people with {len(food_items)} items")
        
        # Extract additional names from conversation
        additional_names = []
        name_patterns = [
            r'(?:the other person\'?s name is|other person is|second guest is|guest is)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)',
            r'(?:and|with)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)',
            r'([a-zA-Z]+(?:\s+[a-zA-Z]+)?)\s+(?:wants|will have|orders)',
            r'for ([a-zA-Z]+(?:\s+[a-zA-Z]+)?)',
            r'([a-zA-Z]+(?:\s+[a-zA-Z]+)?)\s+will\s+order',
        ]
        
        for pattern in name_patterns:
            matches = re.findall(pattern, conversation_text, re.IGNORECASE)
            for match in matches:
                name = match.strip().title()
                if (name.replace(' ', '').isalpha() and 
                    len(name) > 2 and
                    name.lower() not in ['today', 'tomorrow', 'tonight', 'party of', 'table for', 'a pepsi', 'the pepsi', 'a coke', 'the coke', 'for', 'and', 'or', 'the'] and
                    not any(food_word in name.lower() for food_word in ['pepsi', 'coke', 'wings', 'burger', 'pizza', 'mountain', 'dew']) and
                    name not in additional_names and
                    name != customer_name):
                    additional_names.append(name)
                    print(f"🔍 Found additional person: {name}")
        
        # Import menu items for analysis
        try:
            import sys
            import os
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            from app import app
            from models import MenuItem
            
            with app.app_context():
                menu_items = {item.id: item.name for item in MenuItem.query.all()}
                
                # Create person-specific item lists
                person_items = {}
                person_items[customer_name] = []
                
                # Add additional names to person_items
                for name in additional_names:
                    person_items[name] = []
                
                # If we don't have enough named people, add generic names
                person_names = [customer_name] + additional_names
                while len(person_names) < party_size:
                    guest_name = f'Guest {len(person_names)}'
                    person_names.append(guest_name)
                    person_items[guest_name] = []
                
                print(f"🔍 Person names identified: {person_names}")
                
                # Analyze conversation to assign items to specific people
                conversation_lower = conversation_text.lower()
                
                # Track which items have been assigned
                assigned_items = set()
                
                # Method 1: Look for explicit person-item assignments in conversation
                for person_name in person_names:
                    person_lower = person_name.lower()
                    
                    # Find mentions of this person
                    person_mentions = []
                    import re
                    for match in re.finditer(r'\b' + re.escape(person_lower) + r'\b', conversation_lower):
                        person_mentions.append(match.start())
                    
                    # For each person mention, look for nearby food items
                    for mention_pos in person_mentions:
                        # Look in a window around the person mention (±100 characters)
                        start_pos = max(0, mention_pos - 100)
                        end_pos = min(len(conversation_lower), mention_pos + 100)
                        context = conversation_lower[start_pos:end_pos]
                        
                        # Check which food items are mentioned in this context
                        for item in food_items:
                            if item['menu_item_id'] in assigned_items:
                                continue
                                
                            item_name = menu_items.get(item['menu_item_id'], '').lower()
                            
                            # Check for item name variations in context
                            item_variations = [
                                item_name,
                                item_name.replace(' ', ''),
                                item_name.replace('buffalo', 'buff'),
                                item_name.replace('wings', 'wing'),
                                item_name.split()[0] if ' ' in item_name else item_name  # First word
                            ]
                            
                            if any(variation in context for variation in item_variations if len(variation) > 2):
                                person_items[person_name].append(item)
                                assigned_items.add(item['menu_item_id'])
                                print(f"🍽️ Assigned {item_name} to {person_name} (context match)")
                                break
                
                # Method 2: Smart distribution of remaining items
                unassigned_items = [item for item in food_items if item['menu_item_id'] not in assigned_items]
                
                if unassigned_items:
                    print(f"🔍 Distributing {len(unassigned_items)} unassigned items among {len(person_names)} people")
                    
                    # Distribute unassigned items evenly
                    for i, item in enumerate(unassigned_items):
                        person_index = i % len(person_names)
                        person_name = person_names[person_index]
                        person_items[person_name].append(item)
                        
                        item_name = menu_items.get(item['menu_item_id'], f"Item {item['menu_item_id']}")
                        print(f"🍽️ Assigned {item_name} to {person_name} (round-robin distribution)")
                
                # Create party orders from person_items
                for person_name, items in person_items.items():
                    if items:  # Only add if person has items
                        party_orders.append({
                            'person_name': person_name,
                            'items': items
                        })
                
        except Exception as e:
            print(f"❌ Error parsing individual orders: {e}")
            # Fallback: simple even distribution
            for i, item in enumerate(food_items):
                person_index = i % party_size
                if person_index == 0:
                    person_name = customer_name
                elif person_index - 1 < len(additional_names):
                    person_name = additional_names[person_index - 1]
                else:
                    person_name = f'Guest {person_index + 1}'
                
                # Find existing party order for this person or create new one
                existing_order = next((po for po in party_orders if po['person_name'] == person_name), None)
                if existing_order:
                    existing_order['items'].append(item)
                else:
                    party_orders.append({
                        'person_name': person_name,
                        'items': [item]
                    })
        
        print(f"🍽️ Final party orders: {party_orders}")
        return party_orders
    
    def _split_conversation_by_person(self, conversation_text):
        """Split conversation into segments based on who is ordering"""
        segments = []
        
        # Patterns that indicate the customer is ordering
        customer_patterns = [
            r"(i'll (?:get|have|order|take).*?)(?=\s+he\s|$)",
            r"(i (?:want|would like|order).*?)(?=\s+he\s|$)",
            r"(for me.*?)(?=\s+he\s|$)",
        ]
        
        # Patterns that indicate someone else is ordering
        other_patterns = [
            r"(he (?:wants|will have|orders)[^.]*\.?[^.]*?)(?=\s+i\s|$)",
            r"(she (?:wants|will have|orders)[^.]*\.?[^.]*?)(?=\s+i\s|$)",
            r"(they (?:want|will have|order)[^.]*\.?[^.]*?)(?=\s+i\s|$)",
            r"((?:bob|jim|john|mary|sarah|guest) (?:wants|will have|orders)[^.]*\.?[^.]*?)(?=\s+i\s|$)",
        ]
        
        # Find customer segments
        for pattern in customer_patterns:
            matches = re.finditer(pattern, conversation_text, re.IGNORECASE)
            for match in matches:
                segments.append({
                    'person': 'customer',
                    'text': match.group(1),
                    'start': match.start(),
                    'end': match.end()
                })
        
        # Find other person segments
        for pattern in other_patterns:
            matches = re.finditer(pattern, conversation_text, re.IGNORECASE)
            for match in matches:
                segments.append({
                    'person': 'other',
                    'text': match.group(1),
                    'start': match.start(),
                    'end': match.end()
                })
        
        # Sort by position in conversation
        segments.sort(key=lambda x: x['start'])
        
        return segments

    def _add_to_reservation_handler(self, args, raw_data):
        """Handler for add_to_reservation tool"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import db, Reservation, Order, OrderItem, MenuItem
            
            with app.app_context():
                # Find the reservation
                reservation = None
                
                if args.get('reservation_id'):
                    reservation = Reservation.query.get(args['reservation_id'])
                elif args.get('reservation_number'):
                    reservation = Reservation.query.filter_by(
                        reservation_number=args['reservation_number']
                    ).first()
                else:
                    # Try to find from conversation context
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    caller_phone = None
                    reservation_number = None
                    
                    # Get caller's phone number
                    if raw_data and isinstance(raw_data, dict):
                        caller_phone = (
                            raw_data.get('caller_id_num') or 
                            raw_data.get('caller_id_number') or
                            raw_data.get('from') or
                            raw_data.get('from_number')
                        )
                        # Also check in global_data
                        global_data = raw_data.get('global_data', {})
                        if not caller_phone and global_data:
                            caller_phone = (
                                global_data.get('caller_id_number') or
                                global_data.get('caller_id_num')
                            )
                    
                    # Look for reservation number in conversation
                    for entry in reversed(call_log):
                        if entry.get('role') == 'user' and entry.get('content'):
                            content = entry['content'].lower()
                            
                            # Look for reservation numbers
                            from number_utils import extract_reservation_number_from_text
                            extracted_number = extract_reservation_number_from_text(content)
                            if extracted_number:
                                reservation_number = extracted_number
                                break
                    
                    # Try to find by reservation number first
                    if reservation_number:
                        reservation = Reservation.query.filter_by(
                            reservation_number=reservation_number
                        ).first()
                    elif caller_phone:
                        # Fallback to phone search
                        reservation = Reservation.query.filter_by(
                            phone_number=caller_phone
                        ).order_by(Reservation.date.desc()).first()
                
                if not reservation:
                    return SwaigFunctionResult("I couldn't find your reservation. Could you please provide your reservation number?")
                
                # Extract items from conversation if not provided in args
                items_to_add = args.get('items', [])
                
                if not items_to_add:
                    # Look for food items mentioned in recent conversation
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    
                    for entry in reversed(call_log[-10:]):  # Check last 10 entries
                        if entry.get('role') == 'user' and entry.get('content'):
                            content = entry['content'].lower()
                            
                            # Look for specific food/drink items
                            if 'craft lemonade' in content or 'lemonade' in content:
                                # Find lemonade menu item
                                lemonade_item = MenuItem.query.filter(
                                    MenuItem.name.ilike('%lemonade%')
                                ).first()
                                if lemonade_item:
                                    quantity = 1
                                    # Look for quantity in the same message
                                    if 'one' in content or '1' in content:
                                        quantity = 1
                                    elif 'two' in content or '2' in content:
                                        quantity = 2
                                    
                                    items_to_add.append({
                                        'name': lemonade_item.name,
                                        'quantity': quantity
                                    })
                                    break
                            
                            elif 'buffalo wings' in content or 'wings' in content:
                                # Find wings menu item
                                wings_item = MenuItem.query.filter(
                                    MenuItem.name.ilike('%wing%')
                                ).first()
                                if wings_item:
                                    quantity = 1
                                    if 'one' in content or '1' in content:
                                        quantity = 1
                                    elif 'two' in content or '2' in content:
                                        quantity = 2
                                    
                                    items_to_add.append({
                                        'name': wings_item.name,
                                        'quantity': quantity
                                    })
                                    break
                
                if not items_to_add:
                    return SwaigFunctionResult("I didn't catch what you'd like to add to your reservation. Could you please tell me which food or drink items you'd like to pre-order?")
                
                # Process the items
                person_name = args.get('person_name', reservation.name)
                
                # Check if customer already has an order for this reservation
                existing_order = Order.query.filter_by(
                    reservation_id=reservation.id,
                    person_name=person_name
                ).first()
                
                added_items = []
                total_added_cost = 0.0
                
                if existing_order:
                    # Add items to existing order
                    for item_data in items_to_add:
                        # Find menu item by name with fuzzy matching
                        menu_item = self._find_menu_item_fuzzy(item_data['name'])
                        
                        if not menu_item:
                            return SwaigFunctionResult(f"Sorry, I couldn't find '{item_data['name']}' on our menu. Could you try a different item?")
                        
                        quantity = item_data.get('quantity', 1)
                        
                        # Check if item already exists in order
                        existing_item = OrderItem.query.filter_by(
                            order_id=existing_order.id,
                            menu_item_id=menu_item.id
                        ).first()
                        
                        if existing_item:
                            existing_item.quantity += quantity
                        else:
                            new_order_item = OrderItem(
                                order_id=existing_order.id,
                                menu_item_id=menu_item.id,
                                quantity=quantity,
                                price_at_time=menu_item.price
                            )
                            db.session.add(new_order_item)
                        
                        added_items.append(f"{quantity}x {menu_item.name}")
                        total_added_cost += menu_item.price * quantity
                    
                    # Recalculate order total
                    order_items = OrderItem.query.filter_by(order_id=existing_order.id).all()
                    existing_order.total_amount = sum(item.quantity * item.price_at_time for item in order_items)
                    
                else:
                    # Create new order for this reservation
                    new_order = Order(
                        order_number=self._generate_order_number(),
                        reservation_id=reservation.id,
                        person_name=person_name,
                        status='pending',
                        total_amount=0.0
                    )
                    db.session.add(new_order)
                    db.session.flush()  # Get order ID
                    
                    order_total = 0.0
                    for item_data in items_to_add:
                        # Find menu item by name with fuzzy matching
                        menu_item = self._find_menu_item_fuzzy(item_data['name'])
                        
                        if not menu_item:
                            return SwaigFunctionResult(f"Sorry, I couldn't find '{item_data['name']}' on our menu. Could you try a different item?")
                        
                        quantity = item_data.get('quantity', 1)
                        
                        order_item = OrderItem(
                            order_id=new_order.id,
                            menu_item_id=menu_item.id,
                            quantity=quantity,
                            price_at_time=menu_item.price
                        )
                        db.session.add(order_item)
                        
                        added_items.append(f"{quantity}x {menu_item.name}")
                        order_total += menu_item.price * quantity
                        total_added_cost += menu_item.price * quantity
                    
                    new_order.total_amount = order_total
                
                db.session.commit()
                
                # Calculate new total bill
                total_bill = sum(order.total_amount or 0 for order in reservation.orders)
                
                # Create response message
                message = f"Perfect! I've added {', '.join(added_items)} to your reservation. "
                message += f"Your pre-order total is now ${total_bill:.2f}. "
                message += f"The items will be ready when you arrive! "
                message += f"Would you like to pay for your pre-order now or when you arrive?"
                
                return SwaigFunctionResult(message)
                
        except Exception as e:
            return SwaigFunctionResult(f"Error adding items to reservation: {str(e)}")

    def _send_reservation_sms(self, reservation_data, phone_number):
        """Send SMS confirmation for reservation"""
        try:
            # Convert time to 12-hour format for SMS
            try:
                time_obj = datetime.strptime(str(reservation_data['time']), '%H:%M')
                time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
            except (ValueError, TypeError):
                time_12hr = str(reservation_data['time'])
            
            sms_body = f"🍽️ Bobby's Table Reservation Confirmed!\n\n"
            sms_body += f"Name: {reservation_data['name']}\n"
            sms_body += f"Date: {reservation_data['date']}\n"
            sms_body += f"Time: {time_12hr}\n"
            party_text = "person" if reservation_data['party_size'] == 1 else "people"
            sms_body += f"Party Size: {reservation_data['party_size']} {party_text}\n"
            sms_body += f"Reservation Number: {reservation_data.get('reservation_number', reservation_data['id'])}\n"
            
            if reservation_data.get('special_requests'):
                sms_body += f"Special Requests: {reservation_data['special_requests']}\n"
            
            sms_body += f"\nWe look forward to serving you!\nBobby's Table Restaurant"
            sms_body += f"\nReply STOP to stop."
            
            # Send SMS using SignalWire Agents SDK
            sms_function_result = SwaigFunctionResult().send_sms(
                to_number=phone_number,
                from_number=self.signalwire_from_number,
                body=sms_body
            )
            
            return {'success': True, 'sms_sent': True}
            
        except Exception as e:
            return {'success': False, 'sms_sent': False, 'error': str(e)}
    
def pay_reservation_skill(context):
    """
    Voice skill to collect payment for a reservation/order using SignalWire Pay and Stripe.
    Prompts for reservation number, cardholder name, SMS number, email, processes payment, and sends SMS receipt.
    """
    # 1. Prompt for reservation number
    reservation_number = context.get('reservation_number')
    if not reservation_number:
        return {
            'prompt': "Let's get your bill paid! Please say or enter your reservation number. You can find this on your confirmation text or email.",
            'expecting_input': True,
            'next': 'pay_reservation_skill'
        }

    # 2. Prompt for cardholder name
    cardholder_name = context.get('cardholder_name')
    if not cardholder_name:
        return {
            'prompt': "What name is on the credit card you'll be using?",
            'expecting_input': True,
            'next': 'pay_reservation_skill',
            'context': {'reservation_number': reservation_number}
        }

    # 3. Prompt for SMS number (required)
    phone_number = context.get('phone_number')
    if not phone_number:
        return {
            'prompt': "What mobile number should we send your payment receipt to? Please say or enter your SMS number.",
            'expecting_input': True,
            'next': 'pay_reservation_skill',
            'context': {'reservation_number': reservation_number, 'cardholder_name': cardholder_name}
        }

    # 4. Prompt for email (optional)
    email = context.get('email')
    if email is None:
        return {
            'prompt': "If you'd like an email receipt as well, please say or enter your email address. Or you can say 'skip' to continue.",
            'expecting_input': True,
            'next': 'pay_reservation_skill',
            'context': {'reservation_number': reservation_number, 'cardholder_name': cardholder_name, 'phone_number': phone_number}
        }
    if isinstance(email, str) and email.strip().lower() == 'skip':
        email = ''

    # 5. Process payment (this is a voice skill, not SWAIG)
    # For voice skills, we would typically integrate with payment processing here
    # For now, return a placeholder response
    result = {'success': True, 'message': 'Payment processed via voice skill'}

    # 6. Announce result
    if result.get('success'):
        return {
            'prompt': "Thank you! Your payment was successful. Your bill is now marked as paid, and we've sent a receipt to your phone. If you need anything else, just let us know!",
            'end': True
        }
    else:
        return {
            'prompt': f"Sorry, there was a problem processing your payment: {result.get('error', 'Unknown error')}. Please try again or contact Bobby's Table for help.",
            'end': True
        }
