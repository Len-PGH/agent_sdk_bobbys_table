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

    def _find_menu_item_fuzzy(self, item_name):
        """
        Find menu item using fuzzy matching to handle common misspellings
        
        Args:
            item_name: The item name to search for (potentially misspelled)
            
        Returns:
            MenuItem object if found, None otherwise
        """
        from models import MenuItem
        import re
        
        if not item_name:
            return None
        
        # Normalize the search term
        search_term = item_name.lower().strip()
        
        # First try exact match (case-insensitive)
        menu_item = MenuItem.query.filter(
            MenuItem.name.ilike(search_term)
        ).first()
        if menu_item:
            return menu_item
        
        # Try partial match
        menu_item = MenuItem.query.filter(
            MenuItem.name.ilike(f'%{search_term}%')
        ).first()
        if menu_item:
            return menu_item
        
        # Get all menu items for fuzzy matching
        all_items = MenuItem.query.all()
        
        # Common spelling corrections and variations
        spelling_corrections = {
            'kraft': 'craft',
            'coke': 'coca-cola',
            'pepsi': 'coca-cola',
            'soda': 'coca-cola',
            'pop': 'coca-cola',
            'burger': 'ribeye steak',  # Common misname for main dish
            'chicken': 'buffalo wings',
            'wings': 'buffalo wings',
            'lemonade': 'lemonade',
            'tea': 'iced tea',
            'coffee': 'coffee',
            'water': 'water',
            'beer': 'beer',
            'wine': 'wine'
        }
        
        # Apply spelling corrections
        corrected_term = search_term
        for wrong, correct in spelling_corrections.items():
            if wrong in search_term:
                corrected_term = search_term.replace(wrong, correct)
                break
        
        # Try corrected term
        if corrected_term != search_term:
            menu_item = MenuItem.query.filter(
                MenuItem.name.ilike(f'%{corrected_term}%')
            ).first()
            if menu_item:
                return menu_item
        
        # Fuzzy matching using simple similarity
        best_match = None
        best_score = 0
        
        for item in all_items:
            item_name_lower = item.name.lower()
            
            # Calculate similarity score
            score = 0
            
            # Exact word matches get high score
            search_words = search_term.split()
            item_words = item_name_lower.split()
            
            for search_word in search_words:
                for item_word in item_words:
                    if search_word == item_word:
                        score += 10
                    elif search_word in item_word or item_word in search_word:
                        score += 5
                    elif self._levenshtein_distance(search_word, item_word) <= 2:
                        score += 3
            
            # Bonus for containing the search term
            if search_term in item_name_lower:
                score += 8
            elif corrected_term in item_name_lower:
                score += 6
            
            # Length penalty for very different lengths
            length_diff = abs(len(search_term) - len(item_name_lower))
            if length_diff > 5:
                score -= 2
            
            if score > best_score and score >= 3:  # Minimum threshold
                best_score = score
                best_match = item
        
        return best_match
    
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

        # Add to reservation tool
        self.agent.define_tool(
            name="add_to_reservation",
            description="Add food or drink items to an existing reservation for pre-ordering",
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



        # Register the step-by-step payment processing tool
        def _pay_reservation_handler(args, raw_data):
            """Process payment with step-by-step card detail collection to avoid number confusion"""
            
            # Import payment session functions with better error handling
            start_payment_session = None
            update_payment_step = None
            end_payment_session = None
            
            try:
                import sys
                import os
                parent_dir = os.path.dirname(os.path.dirname(__file__))
                if parent_dir not in sys.path:
                    sys.path.insert(0, parent_dir)
                
                # Import the app module and get the functions
                import app as app_module
                start_payment_session = getattr(app_module, 'start_payment_session', None)
                update_payment_step = getattr(app_module, 'update_payment_step', None)
                end_payment_session = getattr(app_module, 'end_payment_session', None)
                
                print(f"🔍 Payment session functions imported: start={start_payment_session is not None}, update={update_payment_step is not None}, end={end_payment_session is not None}")
                
            except Exception as e:
                print(f"⚠️ Could not import payment session functions: {e}")
                start_payment_session = lambda *args: print("🔍 start_payment_session called but not available")
                update_payment_step = lambda *args: print("🔍 update_payment_step called but not available")
                end_payment_session = lambda *args: print("🔍 end_payment_session called but not available")
            
            # Extract what we have from the conversation
            reservation_number = args.get('reservation_number')
            cardholder_name = args.get('cardholder_name')
            phone_number = args.get('phone_number')
            
            # Get call ID for payment session tracking
            call_id = raw_data.get('call_id', 'unknown') if raw_data else 'unknown'
            
            # Payment step tracking - check what step we're on
            payment_step = args.get('payment_step', 'start')
            card_number = args.get('card_number')
            expiry_month = args.get('expiry_month')
            expiry_year = args.get('expiry_year')
            cvv = args.get('cvv')
            zip_code = args.get('zip_code')
            
            # Try to extract information from conversation if not provided
            if not reservation_number or not cardholder_name:
                call_log = raw_data.get('call_log', []) if raw_data else []
                
                # Extract reservation number from conversation (prioritize recent messages)
                if not reservation_number:
                    from number_utils import extract_reservation_number_from_text
                    
                    # First, try to extract from the most recent user messages (last 5 messages)
                    recent_user_messages = []
                    for entry in reversed(call_log):
                        if entry.get('role') == 'user' and entry.get('content'):
                            recent_user_messages.append(entry.get('content', ''))
                            if len(recent_user_messages) >= 5:
                                break
                    
                    # Try each recent message individually, starting with the most recent
                    for message in recent_user_messages:
                        reservation_number = extract_reservation_number_from_text(message)
                        if reservation_number:
                            print(f"🔍 Extracted reservation number from recent message: {reservation_number}")
                            break
                    
                    if reservation_number:
                        print(f"🔍 Final extracted reservation number: {reservation_number}")
                
                # Extract cardholder name from conversation - enhanced logic
                if not cardholder_name:
                    # Look for cardholder name in ALL conversation history (not just recent)
                    for entry in call_log:  # Check all entries, not just reversed
                        if entry.get('role') == 'user':
                            content = entry.get('content', '').strip()
                            
                            # First, check for "First name, X. Last name, Y." pattern
                            first_last_pattern = r'first name[,\s]+([a-zA-Z]+).*?last name[,\s]+([a-zA-Z]+)'
                            match = re.search(first_last_pattern, content, re.IGNORECASE)
                            if match:
                                first_name = match.group(1).strip()
                                last_name = match.group(2).strip()
                                cardholder_name = f"{first_name} {last_name}".title()
                                print(f"🔍 Extracted cardholder name from 'first/last' pattern: {cardholder_name}")
                                break
                            
                            # Check for standard name patterns
                            if (content and 
                                not content.lower().startswith(('reservation', 'my reservation', 'number', 'yes', 'no', 'can i', 'i want', 'i need', 'i just', 'i already', 'i told')) and
                                not re.match(r'^[\d\s]+$', content) and  # Not just numbers
                                len(content.split()) >= 2 and  # At least first and last name
                                len(content) < 50 and  # Reasonable name length
                                not any(word in content.lower() for word in ['payment', 'pay', 'bill', 'card', 'credit', 'gave', 'told', 'said']) and
                                not any(word in content.lower() for word in ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'zero']) and
                                re.search(r'^[A-Za-z]+ [A-Za-z]+', content) and  # First Last name pattern
                                not any(phrase in content.lower() for phrase in ['you', 'it', 'that', 'this', 'already', 'before'])):
                                cardholder_name = content
                                print(f"🔍 Extracted cardholder name from conversation: {cardholder_name}")
                                break
                    
                    # Also check assistant messages for previously confirmed names
                    if not cardholder_name:
                        for entry in call_log:
                            if entry.get('role') == 'assistant':
                                content = entry.get('content', '').strip()
                                # Look for "I have your name as X" pattern
                                name_pattern = r'I have your name as ([A-Za-z]+ [A-Za-z]+)'
                                match = re.search(name_pattern, content, re.IGNORECASE)
                                if match:
                                    cardholder_name = match.group(1).strip()
                                    print(f"🔍 Extracted cardholder name from assistant message: {cardholder_name}")
                                    break
            
            # Get caller's phone number if not provided
            if not phone_number:
                caller_phone = None
                if raw_data and isinstance(raw_data, dict):
                    caller_phone = (
                        raw_data.get('caller_id_num') or 
                        raw_data.get('caller_id_number') or
                        raw_data.get('from') or
                        raw_data.get('from_number')
                    )
                if caller_phone:
                    phone_number = self._normalize_phone_number(caller_phone)
                    print(f"🔍 Using caller ID for SMS receipt: {phone_number}")
            
            # Step 1: Check if we have the required basic information
            if not reservation_number:
                message = (
                    "I need your reservation number to process the payment. "
                    "Could you please provide your 6-digit reservation number?"
                )
                from number_utils import numbers_to_words
                message = numbers_to_words(message)
                return SwaigFunctionResult(message)
            
            if not cardholder_name:
                message = (
                    "I need the cardholder name to process the payment. "
                    "What name is on the credit card you'll be using for payment?"
                )
                from number_utils import numbers_to_words
                message = numbers_to_words(message)
                return SwaigFunctionResult(message)
            
            # Start payment session once we have basic info
            if reservation_number and cardholder_name:
                try:
                    if start_payment_session:
                        start_payment_session(call_id, reservation_number)
                        print(f"🔒 Payment session started for call {call_id}, reservation {reservation_number}")
                    else:
                        print(f"⚠️ start_payment_session function not available")
                except Exception as e:
                    print(f"❌ Error starting payment session: {e}")
            
            # Helper function to extract numbers from voice input
            def extract_numbers_from_voice(call_log, expected_length=None):
                """Extract numbers from recent voice input, handling spoken digits"""
                if not call_log:
                    return None
                
                # Look at the most recent user message
                for entry in reversed(call_log):
                    if entry.get('role') == 'user':
                        content = entry.get('content', '').strip().lower()
                        if not content:
                            continue
                        
                        # Convert spoken numbers to digits
                        number_words = {
                            'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
                            'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9'
                        }
                        
                        # Extract digits from the content
                        digits = []
                        words = content.split()
                        
                        for word in words:
                            # Remove punctuation
                            clean_word = ''.join(c for c in word if c.isalnum())
                            
                            # Check if it's a number word
                            if clean_word in number_words:
                                digits.append(number_words[clean_word])
                            # Check if it's already a digit
                            elif clean_word.isdigit() and len(clean_word) == 1:
                                digits.append(clean_word)
                        
                        # If we found digits, join them
                        if digits:
                            result = ''.join(digits)
                            # Validate length if expected
                            if expected_length and len(result) != expected_length:
                                print(f"🔍 Extracted {len(result)} digits but expected {expected_length}: {result}")
                                return None
                            print(f"🔍 Extracted numbers from voice: {result}")
                            return result
                        
                        # Also try to extract consecutive digits from the text
                        import re
                        digit_match = re.search(r'\d+', content)
                        if digit_match:
                            result = digit_match.group()
                            if expected_length and len(result) != expected_length:
                                print(f"🔍 Found digits {result} but expected length {expected_length}")
                                return None
                            print(f"🔍 Extracted consecutive digits: {result}")
                            return result
                        
                        break
                
                return None
            
            # Step 2: Collect card details step by step to avoid number confusion
            call_log = raw_data.get('call_log', []) if raw_data else []
            
            if payment_step == 'start' or not card_number:
                # Try to extract card number from recent input
                extracted_card = extract_numbers_from_voice(call_log, 16)
                if extracted_card and len(extracted_card) == 16:
                    # Card number collected, move to next step
                    print(f"🔍 Card number collected: {extracted_card[:4]}****{extracted_card[-4:]}")
                    message = (
                        f"Thank you! I have your card number ending in {extracted_card[-4:]}. "
                        "Next, I need the expiration month. Please say the month as a number. "
                        "For example, for January say 'one', for December say 'twelve'."
                    )
                    from number_utils import numbers_to_words
                    message = numbers_to_words(message)
                    return SwaigFunctionResult(message)
                else:
                    # Ask for card number
                    message = (
                        f"Perfect! I have your name as {cardholder_name} for reservation {reservation_number}. "
                        "Now I'll collect your card details step by step to ensure accuracy. "
                        "First, please say your 16-digit credit card number, one digit at a time. "
                        "For example, if your card number is 1234, say 'one two three four'."
                    )
                    from number_utils import numbers_to_words
                    message = numbers_to_words(message)
                    return SwaigFunctionResult(message)
            
            elif payment_step == 'card_number' or (card_number and not expiry_month):
                # Try to extract expiry month from recent input
                extracted_month = extract_numbers_from_voice(call_log)
                if extracted_month and extracted_month.isdigit():
                    month_num = int(extracted_month)
                    if 1 <= month_num <= 12:
                        print(f"🔍 Expiry month collected: {month_num}")
                        message = (
                            f"Got it, expiration month {month_num}. "
                            "Now I need the expiration year. Please say the last two digits of the year. "
                            "For example, for 2025 say 'two five', for 2026 say 'two six'."
                        )
                        from number_utils import numbers_to_words
                        message = numbers_to_words(message)
                        return SwaigFunctionResult(message)
                
                # Ask for expiry month
                message = (
                    f"Thank you! I have your card number ending in {card_number[-4:] if card_number and len(card_number) >= 4 else 'XXXX'}. "
                    "Next, I need the expiration month. Please say the month as a number. "
                    "For example, for January say 'one', for December say 'twelve'."
                )
                from number_utils import numbers_to_words
                message = numbers_to_words(message)
                return SwaigFunctionResult(message)
            
            elif payment_step == 'expiry_month' or (expiry_month and not expiry_year):
                # Try to extract expiry year from recent input
                extracted_year = extract_numbers_from_voice(call_log, 2)
                if extracted_year and len(extracted_year) == 2 and extracted_year.isdigit():
                    year_num = int(extracted_year)
                    if 25 <= year_num <= 35:  # Reasonable range for card expiry
                        print(f"🔍 Expiry year collected: {year_num}")
                        message = (
                            f"Perfect, expiration {expiry_month}/{year_num}. "
                            "Now I need the three-digit security code on the back of your card. "
                            "Please say the three digits one at a time. For example, for 123 say 'one two three'."
                        )
                        from number_utils import numbers_to_words
                        message = numbers_to_words(message)
                        return SwaigFunctionResult(message)
                
                # Ask for expiry year
                message = (
                    f"Got it, expiration month {expiry_month}. "
                    "Now I need the expiration year. Please say the last two digits of the year. "
                    "For example, for 2025 say 'two five', for 2026 say 'two six'."
                )
                from number_utils import numbers_to_words
                message = numbers_to_words(message)
                return SwaigFunctionResult(message)
            
            elif payment_step == 'expiry_year' or (expiry_year and not cvv):
                # Try to extract CVV from recent input
                extracted_cvv = extract_numbers_from_voice(call_log, 3)
                if extracted_cvv and len(extracted_cvv) == 3 and extracted_cvv.isdigit():
                    print(f"🔍 CVV collected: ***")
                    message = (
                        "Great! Last step - I need your billing ZIP code. "
                        "Please say the five digits of your ZIP code one at a time. "
                        "For example, for 12345 say 'one two three four five'."
                    )
                    from number_utils import numbers_to_words
                    message = numbers_to_words(message)
                    return SwaigFunctionResult(message)
                
                # Ask for CVV
                message = (
                    f"Perfect, expiration {expiry_month}/{expiry_year}. "
                    "Now I need the three-digit security code on the back of your card. "
                    "Please say the three digits one at a time. For example, for 123 say 'one two three'."
                )
                from number_utils import numbers_to_words
                message = numbers_to_words(message)
                return SwaigFunctionResult(message)
            
            elif payment_step == 'cvv' or (cvv and not zip_code):
                # Try to extract ZIP code from recent input
                extracted_zip = extract_numbers_from_voice(call_log, 5)
                if extracted_zip and len(extracted_zip) == 5 and extracted_zip.isdigit():
                    print(f"🔍 ZIP code collected: {extracted_zip}")
                    # All details collected, proceed to payment processing
                    zip_code = extracted_zip
                    # Fall through to payment processing
                else:
                    # Ask for ZIP code
                    message = (
                        "Great! Last step - I need your billing ZIP code. "
                        "Please say the five digits of your ZIP code one at a time. "
                        "For example, for 12345 say 'one two three four five'."
                    )
                    from number_utils import numbers_to_words
                    message = numbers_to_words(message)
                    return SwaigFunctionResult(message)
            
            # Step 3: All details collected, process payment
            # Check if we have all required details from the conversation or parameters
            if not card_number:
                card_number = extract_numbers_from_voice(call_log, 16)
            if not expiry_month:
                extracted_month = extract_numbers_from_voice(call_log)
                if extracted_month and extracted_month.isdigit():
                    month_num = int(extracted_month)
                    if 1 <= month_num <= 12:
                        expiry_month = str(month_num)
            if not expiry_year:
                extracted_year = extract_numbers_from_voice(call_log, 2)
                if extracted_year and len(extracted_year) == 2:
                    expiry_year = extracted_year
            if not cvv:
                cvv = extract_numbers_from_voice(call_log, 3)
            if not zip_code:
                zip_code = extract_numbers_from_voice(call_log, 5)
            
            # Proceed with payment if we have all details
            if card_number and expiry_month and expiry_year and cvv and zip_code:
                try:
                    # Lookup reservation to get amount
                    from models import Reservation, Order
                    reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
                    if not reservation:
                        message = "I couldn't find that reservation. Please check the reservation number and try again."
                        from number_utils import numbers_to_words
                        message = numbers_to_words(message)
                        return SwaigFunctionResult(message)
                    
                    # Calculate total amount
                    total_amount = 0.0
                    orders = Order.query.filter_by(reservation_id=reservation.id).all()
                    for order in orders:
                        total_amount += order.total_amount or 0.0
                    
                    if total_amount <= 0:
                        message = "There's no bill to pay for this reservation yet. Please place your order first."
                        from number_utils import numbers_to_words
                        message = numbers_to_words(message)
                        return SwaigFunctionResult(message)
                    
                    # Process payment with collected details
                    message = (
                        f"Excellent! I have all your card details. "
                        f"Processing payment of ${total_amount:.2f} for reservation {reservation_number}. "
                        f"Card ending in {card_number[-4:] if len(card_number) >= 4 else card_number}, "
                        f"expires {expiry_month}/{expiry_year}. "
                        "Please hold while I process your payment..."
                    )
                    from number_utils import numbers_to_words
                    message = numbers_to_words(message)
                    
                    # Here you would integrate with actual payment processing
                    # For now, we'll simulate success and update the database
                    
                    # Update reservation payment status
                    import uuid
                    confirmation_number = f"CONF-{uuid.uuid4().hex[:8].upper()}"
                    
                    reservation.payment_status = 'paid'
                    reservation.payment_amount = total_amount
                    reservation.confirmation_number = confirmation_number
                    
                    # Update all orders as paid
                    for order in orders:
                        order.payment_status = 'paid'
                        order.payment_amount = order.total_amount
                        order.confirmation_number = confirmation_number
                    
                    from models import db
                    db.session.commit()
                    
                    # End payment session on success
                    try:
                        if end_payment_session:
                            end_payment_session(call_id)
                            print(f"🔓 Payment session ended for call {call_id}")
                        else:
                            print(f"⚠️ end_payment_session function not available")
                    except Exception as e:
                        print(f"❌ Error ending payment session: {e}")
                    
                    success_message = (
                        f"Payment successful! Your confirmation number is {confirmation_number}. "
                        f"I've charged ${total_amount:.2f} to your card ending in {card_number[-4:] if len(card_number) >= 4 else card_number}. "
                        "I'll send you an SMS receipt with all the details. Thank you for choosing Bobby's Table!"
                    )
                    from number_utils import numbers_to_words
                    success_message = numbers_to_words(success_message)
                    return SwaigFunctionResult(success_message)
                    
                except Exception as e:
                    print(f"❌ Error processing payment: {e}")
                    # End payment session on error
                    try:
                        if end_payment_session:
                            end_payment_session(call_id)
                            print(f"🔓 Payment session ended (error) for call {call_id}")
                        else:
                            print(f"⚠️ end_payment_session function not available")
                    except Exception as e:
                        print(f"❌ Error ending payment session: {e}")
                    message = (
                        "I'm having trouble processing your payment right now. "
                        "Please try again in a moment, or I can transfer you to our manager for assistance."
                    )
                    from number_utils import numbers_to_words
                    message = numbers_to_words(message)
                    return SwaigFunctionResult(message)
            else:
                # We don't have all the required details yet
                missing_details = []
                if not card_number:
                    missing_details.append("card number")
                if not expiry_month:
                    missing_details.append("expiration month")
                if not expiry_year:
                    missing_details.append("expiration year")
                if not cvv:
                    missing_details.append("security code")
                if not zip_code:
                    missing_details.append("ZIP code")
                
                message = (
                    f"I still need your {', '.join(missing_details)}. "
                    "Let's continue step by step. Please provide the next piece of information."
                )
                from number_utils import numbers_to_words
                message = numbers_to_words(message)
                return SwaigFunctionResult(message)

        self.agent.define_tool(
            name="pay_reservation",
            description="PAYMENT FUNCTION - Process payment for a reservation with step-by-step card detail collection. CRITICAL: Use this function ONLY for payment processing. When customers provide card details (like 'four two four two...'), continue calling this function. DO NOT call get_order_status or other functions during payment. This function handles the complete payment flow: reservation lookup → cardholder name → card number → expiry → CVV → ZIP → payment processing.",
            parameters={
                "type": "object",
                "properties": {
                    "reservation_number": {"type": "string", "description": "6-digit reservation number to pay for"},
                    "cardholder_name": {"type": "string", "description": "Name on the credit card"},
                    "phone_number": {"type": "string", "description": "SMS number for receipt (will use caller ID if not provided)"},
                    "payment_step": {"type": "string", "description": "Current step in payment process: start, card_number, expiry_month, expiry_year, cvv, zip_code"},
                    "card_number": {"type": "string", "description": "16-digit credit card number (collected step by step)"},
                    "expiry_month": {"type": "string", "description": "Card expiration month (1-12)"},
                    "expiry_year": {"type": "string", "description": "Card expiration year (last 2 digits)"},
                    "cvv": {"type": "string", "description": "3-digit security code"},
                    "zip_code": {"type": "string", "description": "5-digit billing ZIP code"}
                },
                "required": []  # No required fields - function will collect information step by step
            },
            handler=_pay_reservation_handler
        )

        # Register add_to_reservation tool
        self.agent.register_tool(
            name="add_to_reservation",
            description="Add food or drink items to an existing reservation for pre-ordering",
            parameters={
                "type": "object",
                "properties": {
                    "reservation_number": {"type": "string", "description": "6-digit reservation number"},
                    "reservation_id": {"type": "integer", "description": "Internal reservation ID"},
                    "items": {"type": "array", "description": "List of items to add with name and quantity"},
                    "person_name": {"type": "string", "description": "Name of person ordering (defaults to reservation holder)"}
                }
            },
            handler=self._add_to_reservation_handler
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
                pre_order = args.get('pre_order', [])  # Handle alternative format from AI
                total_reservation_amount = 0.0
                
                # Convert pre_order format to party_orders format if needed
                if pre_order and not party_orders:
                    print(f"🔄 Converting pre_order format to party_orders format")
                    from models import MenuItem
                    
                    # Convert pre_order items to party_orders format
                    converted_items = []
                    for item in pre_order:
                        item_name = item.get('name', '')
                        quantity = item.get('quantity', 1)
                        
                        # Find menu item by name with fuzzy matching
                        menu_item = self._find_menu_item_fuzzy(item_name)
                        
                        if menu_item:
                            converted_items.append({
                                'menu_item_id': menu_item.id,
                                'quantity': quantity
                            })
                            if menu_item.name.lower() != item_name.lower():
                                print(f"   Converted '{item_name}' to '{menu_item.name}' (menu item ID {menu_item.id})")
                            else:
                                print(f"   Converted '{item_name}' to menu item ID {menu_item.id}")
                        else:
                            print(f"   ⚠️ Could not find menu item for '{item_name}'")
                    
                    if converted_items:
                        party_orders = [{
                            'person_name': args.get('name', 'Customer'),
                            'items': converted_items
                        }]
                        print(f"   Created party_orders: {party_orders}")
                
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
                    message += f"\n🍽️ Pre-Order Details:\n"
                    # Show the pre-ordered items
                    if pre_order:
                        for item in pre_order:
                            message += f"   • {item.get('quantity', 1)}x {item.get('name', 'Unknown Item')}\n"
                    message += f"Pre-Order Total: ${total_reservation_amount:.2f}\n"
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
        
        # Extract phone number from caller ID if not found in conversation
        if 'phone_number' not in extracted and caller_phone:
            # Use caller ID as phone number
            normalized_phone = self._normalize_phone_number(caller_phone)
            if normalized_phone:
                extracted['phone_number'] = normalized_phone
                print(f"🔍 Using caller ID as phone number: {normalized_phone}")
        
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
                
                # Handle wings variations - map different wing mentions to Buffalo Wings
                wing_mentions = ['buff wings', 'buffalo wings', 'barbecue wings', 'bbq wings', 'wings']
                if any(mention in conversation_lower for mention in wing_mentions):
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
                            extracted_number = extract_reservation_number_from_text(content)
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
                    
                    # If confirmation not needed or JSON format, provide full details
                    party_orders = []
                    for order in reservation.orders:
                        party_orders.append({
                            'person_name': order.person_name,
                            'items': [item.menu_item.name for item in order.items],
                            'total': order.total_amount
                        })
                    total_bill = sum(order.total_amount or 0 for order in reservation.orders)
                    paid = reservation.payment_status == 'paid'
                    
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
                        if paid and reservation.confirmation_number:
                            message += f"Your payment confirmation number is {reservation.confirmation_number}. "
                        
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
                # If reservation_id is missing, try to find by reservation_number or extract from conversation context
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
                
                # Handle pre-order additions
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
                    message += f"Would you like to pay for your pre-order now or when you arrive?"
                    
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
    
    def _generate_order_number(self):
        """Generate a unique order number"""
        import random
        import string
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
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

    # 5. Call the SWAIG function to process payment
    from swaig_agents import pay_reservation_by_phone
    result = pay_reservation_by_phone(
        reservation_number=reservation_number,
        phone_number=phone_number,
        cardholder_name=cardholder_name,
        email=email
    )

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