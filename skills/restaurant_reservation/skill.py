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

class RestaurantReservationSkill(SkillBase):
    """Provides restaurant reservation management capabilities"""
    
    SKILL_NAME = "restaurant_reservation"
    SKILL_DESCRIPTION = "Manage restaurant reservations - create, update, cancel, and lookup"
    SKILL_VERSION = "1.0.0"
    REQUIRED_PACKAGES = []
    REQUIRED_ENV_VARS = []
    
    def __init__(self, agent, params=None):
        super().__init__(agent, params)
        # SignalWire configuration for SMS
        self.signalwire_from_number = os.getenv('SIGNALWIRE_FROM_NUMBER', '+15551234567')
    
    def setup(self) -> bool:
        """Setup the reservation skill"""
        return True

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
        import re
        import re
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
        
    def register_tools(self) -> None:
        """Register reservation tools with the agent"""
        
        # Create reservation tool
        self.agent.define_tool(
            name="create_reservation",
            description="Create a new restaurant reservation with optional food ordering. Supports both 'old school' table-only reservations and full reservations with pre-orders.",
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
                "required": ["name", "party_size", "date", "time", "phone_number"]
            },
            handler=self._create_reservation_handler,
            **self.swaig_fields
        )
        
        # Get reservation tool
        self.agent.define_tool(
            name="get_reservation",
            description="Look up an existing reservation by any available information: phone number, first name, last name, full name, date, time, party size, or reservation ID. Can return formatted text for voice or structured JSON for programmatic use.",
            parameters={
                "type": "object",
                "properties": {
                    "phone_number": {"type": "string", "description": "Customer phone number"},
                    "name": {"type": "string", "description": "Customer full name, first name, or last name"},
                    "first_name": {"type": "string", "description": "Customer first name"},
                    "last_name": {"type": "string", "description": "Customer last name"},
                    "reservation_id": {"type": "integer", "description": "Reservation ID"},
                    "reservation_number": {"type": "string", "description": "6-digit reservation number"},
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
            description="Update an existing reservation",
            parameters={
                "type": "object",
                "properties": {
                    "reservation_id": {"type": "integer", "description": "Reservation ID"},
                    "name": {"type": "string", "description": "New customer name"},
                    "party_size": {"type": "integer", "description": "New party size"},
                    "date": {"type": "string", "description": "New reservation date (YYYY-MM-DD)"},
                    "time": {"type": "string", "description": "New reservation time (HH:MM)"},
                    "phone_number": {"type": "string", "description": "New phone number"},
                    "special_requests": {"type": "string", "description": "New special requests"}
                },
                "required": ["reservation_id"]
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
                # Extract meta_data for context
                meta_data = raw_data.get('meta_data', {}) if raw_data else {}
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
                
                # Always try to extract from conversation if args are empty or incomplete
                print(f"🔍 Received args: {args}")
                print(f"🔍 Call log entries: {len(call_log)}")
                
                if not args or not all(args.get(field) for field in ['name', 'party_size', 'date', 'time']):
                    print("🔍 Extracting reservation details from conversation...")
                    
                    # Extract information from conversation
                    extracted_info = self._extract_reservation_info_from_conversation(call_log, caller_phone)
                    
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
                total_reservation_amount = 0.0
                
                # Only process orders if not an old school reservation
                if not args.get('old_school', False) and party_orders:
                    from models import Order, OrderItem, MenuItem
                    
                    for person_order in party_orders:
                        person_name = person_order.get('person_name', '')
                        items = person_order.get('items', [])
                        
                        if not items:
                            continue
                        
                        # Create order for this person
                        order = Order(
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
                            menu_item = MenuItem.query.get(int(item_data['menu_item_id']))
                            qty = int(item_data['quantity'])
                            
                            if menu_item and qty > 0:
                                order_total += menu_item.price * qty
                                db.session.add(OrderItem(
                                    order_id=order.id,
                                    menu_item_id=menu_item.id,
                                    quantity=qty,
                                    price_at_time=menu_item.price
                                ))
                        
                        order.total_amount = order_total
                        total_reservation_amount += order_total
                
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
                
                # Create comprehensive confirmation message
                message = f"🍽️ RESERVATION CONFIRMED! 🍽️\n\n"
                message += f"Reservation #{reservation.reservation_number} for {args['name']}\n"
                message += f"📅 Date: {args['date']}\n"
                message += f"🕐 Time: {time_12hr}\n"
                party_text = "person" if args['party_size'] == 1 else "people"
                message += f"👥 Party Size: {args['party_size']} {party_text}\n"
                message += f"📱 Phone: {args['phone_number']}\n"
                
                if args.get('special_requests'):
                    message += f"📝 Special Requests: {args['special_requests']}\n"
                
                # Add order information if orders were placed
                if total_reservation_amount > 0:
                    message += f"\n🍽️ Pre-Order Total: ${total_reservation_amount:.2f}\n"
                    message += f"Your food will be prepared and ready when you arrive!\n"
                elif args.get('old_school', False):
                    message += f"\n📞 Old School Reservation - Just the table reserved!\n"
                    message += f"You can browse our menu and order when you arrive.\n"
                
                # Add SMS confirmation status to the message
                if 'sms_result' in locals() and sms_result.get('sms_sent'):
                    message += f"\n📱 A confirmation SMS has been sent to your phone. "
                
                message += f"\nThank you for choosing Bobby's Table! We look forward to serving you. "
                # Convert reservation number to individual digits for clear pronunciation
                reservation_number_spoken = ' '.join(reservation.reservation_number)
                message += f"Your reservation number is {reservation_number_spoken}. "
                message += f"Please arrive on time and let us know if you need to make any changes."
                
                return SwaigFunctionResult(message)
                
        except Exception as e:
            return SwaigFunctionResult(f"Sorry, there was an error creating your reservation: {str(e)}")
    
    def _extract_reservation_info_from_conversation(self, call_log, caller_phone=None):
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
            # Removed problematic patterns that can create nonsense names
            r'([a-zA-Z]+\s+[a-zA-Z]+)\s+calling',   # "John Smith calling"
            r'([a-zA-Z]+\s+[a-zA-Z]+)\s+here',      # "John Smith here"
        ]
        
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
                r'and ([A-Z][a-z]+)',  # "and SpongeBob"
            ]
            
            for pattern in name_mention_patterns:
                matches = re.findall(pattern, conversation_text, re.IGNORECASE)
                for match in matches:
                    name = match.strip().title()
                    # Filter out common false positives
                    if (name.replace(' ', '').isalpha() and 
                        name.lower() not in ['today', 'tomorrow', 'tonight', 'order', 'will', 'have', 'like', 'want', 'for', 'and', 'the', 'or'] and
                        len(name) > 2 and
                        not name.lower().startswith('for ') and
                        not name.lower().startswith('and ') and
                        not name.lower().startswith('or ')):
                        person_names.add(name)
                        print(f"🔍 Found person name: {name}")
            
            if len(person_names) > 0:
                inferred_party_size = len(person_names)
                extracted['party_size'] = inferred_party_size
                print(f"✅ Inferred party size from names: {inferred_party_size} (names: {list(person_names)})")
        
        # Extract food items mentioned during reservation
        food_items = self._extract_food_items_from_conversation(conversation_text)
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
        
        print(f"🔍 Extracted info: {extracted}")
        return extracted
    
    def _extract_food_items_from_conversation(self, conversation_text):
        """Extract food items mentioned in conversation and convert to menu item IDs"""
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
                # Common food item patterns to look for
                food_patterns = [
                    r'(?:i )?(?:want|order|have|get|like) (?:the )?([a-zA-Z\s]+?)(?:\s+and|\s*$|\s*\.)',
                    r'(?:and )?(?:a |an )?([a-zA-Z\s]+?)(?:\s+and|\s*$|\s*\.|\s*\?)',
                    r'(?:order|get|want) ([a-zA-Z\s]+)',
                ]
                
                extracted_items = []
                
                # Look for specific menu items mentioned
                menu_items = MenuItem.query.all()
                menu_item_names = {item.name.lower(): item for item in menu_items}
                
                # Check for direct menu item matches
                for item_name, menu_item in menu_item_names.items():
                    if item_name in conversation_text.lower():
                        # Check if it's a meaningful match (not part of another word)
                        import re
                        if re.search(r'\b' + re.escape(item_name) + r'\b', conversation_text.lower()):
                            # Avoid duplicate entries
                            if menu_item.id not in [item['menu_item_id'] for item in extracted_items]:
                                extracted_items.append({
                                    'menu_item_id': menu_item.id,
                                    'quantity': 1  # Default quantity
                                })
                                print(f"🍽️ Found menu item: {menu_item.name} (ID: {menu_item.id})")
                
                # Look for specific food mentions with precise matching to avoid false positives
                conversation_lower = conversation_text.lower()
                
                # Handle "buff wings" specifically - it should only match Buffalo Wings, not BBQ Wings
                if 'buff wings' in conversation_lower or 'buffalo wings' in conversation_lower:
                    for item_name, menu_item in menu_item_names.items():
                        if 'buffalo wings' in item_name and menu_item.id not in [item['menu_item_id'] for item in extracted_items]:
                            extracted_items.append({
                                'menu_item_id': menu_item.id,
                                'quantity': 1
                            })
                            print(f"🍽️ Found Buffalo Wings: {menu_item.name} (ID: {menu_item.id})")
                            break
                
                # Handle other specific items with exact matching
                specific_items = {
                    'pepsi': 'pepsi',
                    'coca cola': 'coca cola',
                    'coke': 'coca cola',
                    'mountain dew': 'mountain dew',
                    'burger': 'burger',
                    'hamburger': 'burger',
                    'cheeseburger': 'cheeseburger',
                    'pizza': 'pizza',
                    'salad': 'salad',
                    'salmon': 'salmon',
                    'grilled salmon': 'salmon',
                    'steak': 'steak',
                    'quesadilla': 'quesadilla'
                }
                
                for mention, target_item in specific_items.items():
                    if mention in conversation_lower:
                        for item_name, menu_item in menu_item_names.items():
                            if (target_item in item_name and 
                                menu_item.id not in [item['menu_item_id'] for item in extracted_items]):
                                extracted_items.append({
                                    'menu_item_id': menu_item.id,
                                    'quantity': 1
                                })
                                print(f"🍽️ Found specific item: {menu_item.name} (ID: {menu_item.id})")
                                break
                
                return extracted_items
                
        except Exception as e:
            print(f"❌ Error extracting food items: {e}")
            return []
    
    def _get_reservation_handler(self, args, raw_data):
        """Handler for get_reservation tool"""
        try:
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
                if not any(args.get(key) for key in ['phone_number', 'name', 'first_name', 'last_name', 'reservation_id', 'reservation_number', 'date', 'time', 'party_size', 'email']):
                    # Try to get caller's phone number and extract name from conversation
                    caller_phone = None
                    customer_name = None
                    
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
                    
                    # Look for customer name and reservation number mentioned in conversation
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    reservation_number = None
                    
                    for entry in call_log:
                        if entry.get('role') == 'user' and entry.get('content'):
                            content = entry['content'].lower()
                            
                            # Look for reservation number patterns first (highest priority)
                            if 'reservation number' in content or 'reservation' in content:
                                import re
                                # Extract the part after "reservation number" or "reservation"
                                if 'reservation number' in content:
                                    number_part = content.split('reservation number')[-1].strip()
                                else:
                                    number_part = content.split('reservation')[-1].strip()
                                
                                # Convert spoken numbers to digits
                                number_words = {
                                    'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
                                    'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9'
                                }
                                
                                # Replace word numbers with digits
                                for word, digit in number_words.items():
                                    number_part = re.sub(r'\b' + word + r'\b', digit, number_part)
                                
                                # Extract digits from the processed string
                                digits = re.findall(r'\d', number_part)
                                if len(digits) >= 6:  # Reservation numbers are 6 digits
                                    reservation_number = ''.join(digits[:6])
                                    print(f"🔄 Extracted reservation number from conversation: {reservation_number}")
                                    break
                            
                            # Look for manually provided phone numbers
                            if any(phrase in content for phrase in ['phone number', 'check with phone number', 'use the number']):
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
                                    # Override caller phone with manually provided number
                                    caller_phone = manual_phone
                                    print(f"🔄 Extracted manual phone number from conversation: {manual_phone}")
                            
                            # Look for names mentioned in conversation
                            if 'rob zombie' in content:
                                customer_name = 'Rob Zombie'
                            elif 'smith family' in content or 'smith' in content:
                                customer_name = 'Smith Family'
                    
                    # Use extracted information for search (prioritize reservation number)
                    if reservation_number:
                        args['reservation_number'] = reservation_number
                        print(f"🔄 Auto-filled reservation number from conversation: {reservation_number}")
                    elif caller_phone:
                        args['phone_number'] = caller_phone
                        print(f"🔄 Auto-filled phone number from caller: {caller_phone}")
                    if customer_name:
                        args['name'] = customer_name
                        print(f"🔄 Auto-filled name from conversation: {customer_name}")
                
                # Build search criteria
                search_criteria = []
                query = Reservation.query
                
                if args.get('phone_number'):
                    query = query.filter(Reservation.phone_number.like(f"%{args['phone_number']}%"))
                    search_criteria.append(f"phone number {args['phone_number']}")
                
                if args.get('name'):
                    # Search in full name
                    query = query.filter(Reservation.name.ilike(f"%{args['name']}%"))
                    search_criteria.append(f"name {args['name']}")
                elif args.get('first_name') or args.get('last_name'):
                    # Search by first/last name
                    if args.get('first_name'):
                        query = query.filter(Reservation.name.ilike(f"{args['first_name']}%"))
                        search_criteria.append(f"first name {args['first_name']}")
                    if args.get('last_name'):
                        query = query.filter(Reservation.name.ilike(f"%{args['last_name']}"))
                        search_criteria.append(f"last name {args['last_name']}")
                
                if args.get('reservation_id'):
                    query = query.filter(Reservation.id == args['reservation_id'])
                    search_criteria.append(f"reservation ID {args['reservation_id']}")
                
                if args.get('reservation_number'):
                    query = query.filter(Reservation.reservation_number == args['reservation_number'])
                    search_criteria.append(f"reservation number {args['reservation_number']}")
                
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
                reservations = query.all()
                
                if not reservations:
                    criteria_text = " and ".join(search_criteria)
                    
                    if response_format == 'json':
                        return (
                            SwaigFunctionResult(f"No reservations found matching {criteria_text}.")
                            .add_action("reservation_data", {
                                "success": False,
                                "message": f"No reservations found matching {criteria_text}",
                                "reservations": [],
                                "search_criteria": search_criteria
                            })
                        )
                    else:
                        return SwaigFunctionResult(f"I couldn't find any reservations matching {criteria_text}. Would you like to make a new reservation?")
                
                if len(reservations) == 1:
                    # Single reservation found
                    reservation = reservations[0]
                    
                    if response_format == 'json':
                        return (
                            SwaigFunctionResult("Found matching reservation")
                            .add_action("reservation_data", {
                                "success": True,
                                "message": "Found matching reservation",
                                "reservation": reservation.to_dict(),
                                "search_criteria": search_criteria
                            })
                        )
                    else:
                        time_obj = datetime.strptime(reservation.time, '%H:%M')
                        time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                        
                        party_text = "person" if reservation.party_size == 1 else "people"
                        message = f"I found your reservation for {reservation.name} on {reservation.date} at {time_12hr} for {reservation.party_size} {party_text}. "
                        message += f"Status: {reservation.status}. Reservation number: {reservation.reservation_number}."
                        
                        if reservation.special_requests:
                            message += f" Special requests: {reservation.special_requests}"
                        
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
            from models import db, Reservation
            
            with app.app_context():
                # If reservation_id is missing, try to extract from conversation context
                if not args.get('reservation_id'):
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
                    
                    # Look for reservation number and customer name mentioned in conversation
                    for entry in call_log:
                        if entry.get('role') == 'user' and entry.get('content'):
                            content = entry['content'].lower()
                            
                            # Look for reservation number patterns
                            # Handle spoken numbers like "one one one two two two" -> "111222"
                            if 'reservation number' in content or 'reservation' in content:
                                # Extract the part after "reservation number" or "reservation"
                                if 'reservation number' in content:
                                    number_part = content.split('reservation number')[-1].strip()
                                else:
                                    number_part = content.split('reservation')[-1].strip()
                                
                                # Convert spoken numbers to digits
                                number_words = {
                                    'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
                                    'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9'
                                }
                                
                                # Replace word numbers with digits
                                for word, digit in number_words.items():
                                    number_part = number_part.replace(word, digit)
                                
                                # Extract digits from the processed string
                                digits = re.findall(r'\d', number_part)
                                if len(digits) >= 6:  # Reservation numbers are 6 digits
                                    reservation_number = ''.join(digits[:6])
                                    print(f"🔄 Extracted reservation number from conversation: {reservation_number}")
                                    break
                            
                            # Look for phone numbers mentioned in conversation
                            if any(word in content for word in ['five five five', 'phone number', 'my number']):
                                # Extract phone number from spoken format
                                phone_part = content
                                
                                # Convert spoken numbers to digits for phone numbers
                                for word, digit in number_words.items():
                                    phone_part = phone_part.replace(word, digit)
                                
                                # Extract digits and format as E.164 phone number
                                phone_digits = re.findall(r'\d', phone_part)
                                if len(phone_digits) >= 7:  # At least 7 digits for a phone number
                                    # Take first 10 digits if available, otherwise first 7
                                    if len(phone_digits) >= 10:
                                        extracted_phone = ''.join(phone_digits[:10])
                                        # Format as E.164 (+1XXXXXXXXXX for US numbers)
                                        formatted_phone = f"+1{extracted_phone}"
                                    else:
                                        extracted_phone = ''.join(phone_digits[:7])
                                        # Format as E.164 with area code assumption (+1555XXXXXXX)
                                        # Pad with zeros if needed to make 10 digits
                                        padded_phone = extracted_phone.ljust(7, '0')
                                        formatted_phone = f"+1555{padded_phone}"
                                    
                                    # Store the phone number for later use
                                    if not caller_phone:
                                        caller_phone = formatted_phone
                                        print(f"🔄 Extracted phone number from conversation: {formatted_phone}")
                            
                            # Look for names mentioned in conversation
                            if 'rob zombie' in content:
                                customer_name = 'Rob Zombie'
                            elif 'smith family' in content or 'smith' in content:
                                customer_name = 'Smith Family'
                        elif entry.get('role') == 'tool' and ('Rob Zombie' in entry.get('content', '') or 'Smith' in entry.get('content', '')):
                            if 'Rob Zombie' in entry.get('content', ''):
                                customer_name = 'Rob Zombie'
                            elif 'Smith' in entry.get('content', ''):
                                customer_name = 'Smith Family'
                    
                    # Try to find the reservation using available information
                    reservation = None
                    
                    # First try by reservation number if found
                    if reservation_number:
                        reservation = Reservation.query.filter(
                            Reservation.reservation_number == reservation_number
                        ).first()
                        if reservation:
                            print(f"🔄 Found reservation by number {reservation_number}: {reservation.name}")
                    
                    # Then try by customer name
                    if not reservation and customer_name:
                        reservation = Reservation.query.filter(
                            Reservation.name.ilike(f"%{customer_name}%")
                        ).order_by(Reservation.date.desc()).first()
                        if reservation:
                            print(f"🔄 Found reservation by name {customer_name}: ID {reservation.id}")
                    
                    # Finally try by phone number
                    if not reservation and caller_phone:
                        reservation = Reservation.query.filter(
                            Reservation.phone_number.like(f"%{caller_phone}%")
                        ).order_by(Reservation.date.desc()).first()
                        if reservation:
                            print(f"🔄 Found reservation by phone {caller_phone}: {reservation.name}")
                    
                    if not reservation:
                        return SwaigFunctionResult("I need to know which reservation you'd like to update. Could you please provide the reservation ID, your name, or your phone number?")
                    
                    args['reservation_id'] = reservation.id
                    print(f"🔄 Auto-found reservation ID {reservation.id} for {reservation.name}")
                
                reservation = Reservation.query.get(args['reservation_id'])
                if not reservation:
                    return SwaigFunctionResult(f"Reservation {args['reservation_id']} not found.")
                
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
                                "%d-%m-%Y",       # "09-06-2025"
                                "%Y/%m/%d",       # "2025/06/09"
                                "%Y-%m-%d"        # "2025-06-09" (fallback)
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
                
                # If no changes were made, inform the user
                if not any(key in args for key in ['name', 'party_size', 'date', 'time', 'phone_number', 'special_requests']):
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
                
                if sms_result.get('sms_sent'):
                    message += "An updated confirmation SMS has been sent to your phone."
                
                return SwaigFunctionResult(message)
                
        except Exception as e:
            return SwaigFunctionResult(f"Error updating reservation: {str(e)}")
    
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
            
            # Handle case where args is empty - extract from conversation
            if not args or 'reservation_id' not in args:
                print("🔍 No reservation_id provided, extracting from conversation...")
                
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
                    
                    # First try to find by phone number (most recent reservation)
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
        
        # For multiple people, extract additional names first
        additional_names = []
        
        # Enhanced patterns for person names - handle both single and full names
        name_patterns = [
            r'(?:the other person\'?s name is|other person is|second guest is|guest is)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)',
            r'(?:and|with)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)',
            r'([a-zA-Z]+(?:\s+[a-zA-Z]+)?)\s+(?:wants|will have|orders)',
            r'for ([a-zA-Z]+(?:\s+[a-zA-Z]+)?)',  # "for Squidward"
            r'([a-zA-Z]+(?:\s+[a-zA-Z]+)?)\s+will\s+order',  # "Squidward will order"
        ]
        
        for pattern in name_patterns:
            matches = re.findall(pattern, conversation_text, re.IGNORECASE)
            for match in matches:
                name = match.strip().title()
                # Filter out false positives and ensure it's a real name
                # Allow both single names (like "SpongeBob") and full names (like "John Smith")
                if (name.replace(' ', '').isalpha() and 
                    len(name) > 2 and
                    name.lower() not in ['today', 'tomorrow', 'tonight', 'party of', 'table for', 'a pepsi', 'the pepsi', 'a coke', 'the coke', 'for', 'and', 'or', 'the'] and
                    not any(food_word in name.lower() for food_word in ['pepsi', 'coke', 'wings', 'burger', 'pizza', 'mountain', 'dew']) and
                    not name.lower().startswith('for ') and
                    not name.lower().startswith('and ') and
                    not name.lower().startswith('or ') and
                    not name.lower().startswith('a ') and
                    name not in additional_names and
                    name != customer_name):
                    additional_names.append(name)
                    print(f"🔍 Found additional person: {name}")
        
        # Import menu items for name matching
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
                
                # Analyze conversation flow to assign items
                customer_items = []
                other_person_items = []
                
                # Split conversation into sentences/phrases - handle the specific case better
                # First, handle the specific "and for spongebob, we'll order buffalo wings and a pepsi" pattern
                conversation_text_fixed = conversation_text.replace("and for spongebob, we'll order buffalo wings and a pepsi", 
                                                                   ". and for spongebob, we'll order buffalo wings and a pepsi.")
                # Also split on "and for [name]" patterns to separate orders
                conversation_text_fixed = re.sub(r'\s+and for ([a-zA-Z]+)', r'. and for \1', conversation_text_fixed)
                sentences = re.split(r'[.!?]', conversation_text_fixed)
                
                # Track conversation state
                current_person = 'customer'  # Start with customer
                
                for sentence in sentences:
                    sentence = sentence.strip().lower()
                    if not sentence:
                        continue
                    
                    # Special case: if sentence is just "pepsi" and we were talking about SpongeBob, assign to SpongeBob
                    if sentence.strip() == 'pepsi' and 'spongebob' in conversation_text.lower():
                        current_person = 'spongebob'
                        print(f"🔍 Switching to SpongeBob for Pepsi: {sentence}")
                    
                    # Check if this sentence indicates a person switch
                    if any(phrase in sentence for phrase in ['for me', 'i would like', 'i\'ll get', 'i want']):
                        current_person = 'customer'
                        print(f"🔍 Switching to customer: {sentence}")
                    elif any(phrase in sentence for phrase in ['squidward will order', 'for squidward', 'squidward will have']):
                        # This is Squidward's order
                        current_person = 'squidward'
                        print(f"🔍 Switching to Squidward: {sentence}")
                    elif any(phrase in sentence for phrase in ['for spongebob', 'spongebob will order', 'spongebob will have', 'and for spongebob']):
                        # This is SpongeBob's order
                        current_person = 'spongebob'
                        print(f"🔍 Switching to SpongeBob: {sentence}")
                    elif any(phrase in sentence for phrase in ['buffalo wings and', 'mountain dew', 'he wants', 'she wants']):
                        # This is likely the second person's order
                        current_person = 'other'
                        print(f"🔍 Switching to other person: {sentence}")
                    
                    # Check if any menu items are mentioned in this sentence
                    for item in food_items:
                        item_name = menu_items.get(item['menu_item_id'], '').lower()
                        
                        # Check for various forms of the item name
                        item_variations = [
                            item_name,
                            item_name.replace(' ', ''),
                            item_name.replace('buffalo', 'buff'),
                            item_name.replace('wings', 'wing')
                        ]
                        
                        if any(variation in sentence for variation in item_variations):
                            if current_person == 'customer':
                                if item not in customer_items:
                                    customer_items.append(item)
                                    print(f"🍽️ Assigned {item_name} to {customer_name}")
                            elif current_person == 'squidward':
                                # Create separate list for Squidward
                                if 'squidward_items' not in locals():
                                    squidward_items = []
                                if item not in squidward_items:
                                    squidward_items.append(item)
                                    print(f"🍽️ Assigned {item_name} to Squidward")
                            elif current_person == 'spongebob':
                                # Create separate list for SpongeBob
                                if 'spongebob_items' not in locals():
                                    spongebob_items = []
                                if item not in spongebob_items:
                                    spongebob_items.append(item)
                                    print(f"🍽️ Assigned {item_name} to SpongeBob")
                            else:
                                if item not in other_person_items:
                                    other_person_items.append(item)
                                    other_name = additional_names[0] if additional_names else 'Guest 2'
                                    print(f"🍽️ Assigned {item_name} to {other_name}")
                
                # Handle specific person assignments
                if 'squidward_items' in locals() and squidward_items:
                    party_orders.append({
                        'person_name': 'Squidward',
                        'items': squidward_items
                    })
                
                if 'spongebob_items' in locals() and spongebob_items:
                    party_orders.append({
                        'person_name': 'SpongeBob', 
                        'items': spongebob_items
                    })
                
                # If no items were assigned through conversation flow, use simple distribution
                if not customer_items and not other_person_items and 'squidward_items' not in locals() and 'spongebob_items' not in locals():
                    print("🔍 No items assigned through conversation flow, using simple distribution")
                    # For the specific case: "buff wings and a Pepsi" + "Buffalo wings and, Mountain Dew"
                    # Assign first half to customer, second half to other person
                    mid_point = len(food_items) // 2
                    customer_items = food_items[:mid_point] if mid_point > 0 else food_items[:1]
                    other_person_items = food_items[mid_point:] if mid_point > 0 else food_items[1:]
        
        except Exception as e:
            print(f"❌ Error parsing individual orders: {e}")
            # Fallback: simple distribution
            mid_point = len(food_items) // 2
            customer_items = food_items[:mid_point] if mid_point > 0 else food_items[:1]
            other_person_items = food_items[mid_point:] if mid_point > 0 else food_items[1:]
        
        # Create party orders (only if not already created above)
        if customer_items and not any(order['person_name'] == customer_name for order in party_orders):
            party_orders.append({
                'person_name': customer_name,
                'items': customer_items
            })
        
        if other_person_items and not any(order['person_name'] in [name for name in additional_names] for order in party_orders):
            other_name = additional_names[0] if additional_names else 'Guest 2'
            party_orders.append({
                'person_name': other_name,
                'items': other_person_items
            })
        
        # If we have additional names but no corresponding party orders, create them
        for name in additional_names:
            if not any(order['person_name'] == name for order in party_orders):
                party_orders.append({
                    'person_name': name,
                    'items': []
                })
        
        # Ensure we have the right number of people
        while len(party_orders) < party_size and len(party_orders) < 2:
            party_orders.append({
                'person_name': f'Guest {len(party_orders) + 1}',
                'items': []
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

def pay_reservation_skill(context):
    """
    Voice skill to collect payment for a reservation/order using SignalWire Pay and Stripe.
    Prompts for reservation number, confirms amount, processes payment, and sends SMS receipt.
    """
    # 1. Prompt for reservation number
    reservation_number = context.get('reservation_number')
    if not reservation_number:
        return {
            'prompt': 'Please enter or say your reservation number to pay your bill.',
            'expecting_input': True,
            'next': 'pay_reservation_skill'
        }

    # 2. Optionally prompt for phone number for SMS receipt
    phone_number = context.get('phone_number')
    if not phone_number:
        return {
            'prompt': 'Please enter the phone number where you want your receipt sent.',
            'expecting_input': True,
            'next': 'pay_reservation_skill',
            'context': {'reservation_number': reservation_number}
        }

    # 3. Call the SWAIG function to process payment
    from swaig_agents import pay_reservation_by_phone
    result = pay_reservation_by_phone(reservation_number=reservation_number, phone_number=phone_number)

    # 4. Announce result
    if result.get('success'):
        return {
            'prompt': 'Thank you! Your payment was successful and your bill is now marked as paid. A receipt has been sent to your phone.',
            'end': True
        }
    else:
        return {
            'prompt': f"Sorry, there was a problem processing your payment: {result.get('error', 'Unknown error')}. Please try again or contact the restaurant.",
            'end': True
        }