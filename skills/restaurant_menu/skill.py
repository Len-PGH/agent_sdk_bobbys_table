"""
Restaurant Menu Skill for SignalWire AI Agents
Provides menu browsing and ordering capabilities
"""

import os
import json
from typing import List, Dict, Any
from datetime import datetime
from flask import current_app
import re

from signalwire_agents.core.skill_base import SkillBase
from signalwire_agents.core.function_result import SwaigFunctionResult

class RestaurantMenuSkill(SkillBase):
    """Provides restaurant menu and ordering capabilities"""
    
    SKILL_NAME = "restaurant_menu"
    SKILL_DESCRIPTION = "Browse menu items and manage orders"
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
        },
        "get_menu": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Menu category to filter by (optional)"
                }
            }
        },
        "create_order": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Menu item name"},
                            "quantity": {"type": "integer", "description": "Quantity to order"}
                        },
                        "required": ["name", "quantity"]
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
                    "description": "Order type - pickup or delivery"
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
                    "description": "When customer wants to pay - 'now' for immediate payment, 'pickup' for payment at pickup/delivery"
                }
            },
            "required": ["items", "customer_name", "customer_phone"]
        },
        "get_order_status": {
            "type": "object",
            "properties": {
                "order_number": {
                    "type": "string",
                    "description": "Order number to check status for"
                },
                "customer_phone": {
                    "type": "string",
                    "description": "Customer phone number for verification"
                }
            }
        },
        "update_order_status": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "integer",
                    "description": "Order ID to update"
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "preparing", "ready", "completed", "cancelled"],
                    "description": "New status for the order"
                }
            },
            "required": ["order_id", "status"]
        },
        "pay_order": {
            "type": "object",
            "properties": {
                "order_number": {
                    "type": "string",
                    "description": "Order number to pay for (optional if using verified order from context)"
                },
                "phone_number": {
                    "type": "string",
                    "description": "Customer phone number for verification"
                }
            }
        },
        "send_payment_receipt": {
            "type": "object",
            "properties": {
                "reservation_number": {
                    "type": "string",
                    "description": "Reservation number for the payment receipt"
                },
                "phone_number": {
                    "type": "string",
                    "description": "Phone number to send SMS receipt to"
                },
                "amount": {
                    "type": "number",
                    "description": "Payment amount"
                },
                "confirmation_number": {
                    "type": "string",
                    "description": "Payment confirmation number"
                }
            },
            "required": ["reservation_number", "phone_number", "amount", "confirmation_number"]
        },
        "payment_completed": {
            "type": "object",
            "properties": {
                "payment_type": {
                    "type": "string",
                    "enum": ["reservation", "order"],
                    "description": "Type of payment that was completed"
                },
                "confirmation_number": {
                    "type": "string",
                    "description": "Payment confirmation number"
                },
                "amount": {
                    "type": "number",
                    "description": "Payment amount"
                },
                "reservation_number": {
                    "type": "string",
                    "description": "Reservation number (if payment_type is reservation)"
                },
                "order_number": {
                    "type": "string",
                    "description": "Order number (if payment_type is order)"
                }
            },
            "required": ["payment_type", "confirmation_number", "amount"]
        },
        "send_test_sms": {
            "type": "object",
            "properties": {
                "phone_number": {
                    "type": "string",
                    "description": "Phone number to send test SMS to (in E.164 format like +15551234567)"
                },
                "message": {
                    "type": "string",
                    "description": "Custom message to send (optional, defaults to a test message)"
                }
            },
            "required": ["phone_number"]
        }
    }
    
    def __init__(self, agent, params=None):
        super().__init__(agent, params)
        # Get SignalWire phone number for SMS from environment variable
        self.signalwire_from_number = os.getenv('SIGNALWIRE_FROM_NUMBER', '+15551234567')
    
    def setup(self) -> bool:
        """Setup the menu skill"""
        return True

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
        ).filter_by(is_available=True).first()
        if menu_item:
            return menu_item
        
        # Try partial match
        menu_item = MenuItem.query.filter(
            MenuItem.name.ilike(f'%{search_term}%')
        ).filter_by(is_available=True).first()
        if menu_item:
            return menu_item
        
        # Get all available menu items for fuzzy matching
        all_items = MenuItem.query.filter_by(is_available=True).all()
        
        # Common spelling corrections and variations - FIXED to avoid wrong item selection
        spelling_corrections = {
            'kraft': 'craft',
            'coke': 'coca-cola',
            # REMOVED: 'pepsi': 'coca-cola' - this was causing Pepsi orders to get Coca-Cola
            # REMOVED: 'soda': 'coca-cola' - this was mapping all sodas to Coca-Cola
            # REMOVED: 'pop': 'coca-cola' - this was mapping all pops to Coca-Cola  
            # REMOVED: 'burger': 'ribeye steak' - this was mapping burgers to expensive steaks
            # REMOVED: 'chicken': 'buffalo wings' - this was mapping all chicken to wings
            # REMOVED: 'wings': 'buffalo wings' - this could map BBQ wings to Buffalo wings
            'lemonade': 'craft lemonade',  # More specific mapping
            'tea': 'iced tea',
            'coffee': 'coffee',
            'sparkling water': 'sparkling water',
            'water': 'sparkling water',  # Default to sparkling water since it's on menu
            'beer': 'draft beer',  # More specific
            'wine': 'house wine'   # More specific
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
            ).filter_by(is_available=True).first()
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

    def _extract_order_number_from_conversation(self, call_log):
        """Extract order number from conversation"""
        import re
        
        for entry in call_log:
            if entry.get('content'):
                content = entry['content'].lower()
                
                # Look for order number patterns (be specific to avoid reservation numbers)
                order_number_patterns = [
                    r'order number\s+is\s+(\d{6})',  # "order number is 123456"
                    r'order\s+(\d{6})',              # "order 123456"
                    r'order\s+number\s+(\d{6})',     # "order number 123456"
                    r'order\s+#\s*(\d{6})',          # "order # 123456"
                    r'order\s+id\s+(\d{6})',         # "order id 123456"
                ]
                
                for pattern in order_number_patterns:
                    match = re.search(pattern, content)
                    if match:
                        order_number = match.group(1)
                        print(f"🔍 Extracted order number from conversation: {order_number}")
                        return order_number
        
        return None

    def _build_payment_parameters(self, **kwargs):
        """Build payment parameters array with proper call_id handling"""
        parameters = []
        
        # Add all non-call_id parameters
        for key, value in kwargs.items():
            if key != 'call_id' and value is not None:
                if key == 'order_id':
                    parameters.append({"name": "order_id", "value": str(value)})
                elif key == 'order_number':
                    parameters.append({"name": "order_number", "value": value})
                elif key == 'customer_name':
                    parameters.append({"name": "customer_name", "value": value})
                elif key == 'phone_number':
                    parameters.append({"name": "phone_number", "value": value or ""})
                elif key == 'payment_type':
                    parameters.append({"name": "payment_type", "value": value})
                elif key == 'reservation_number':
                    parameters.append({"name": "reservation_number", "value": value})
        
        # Only add call_id if it has a non-empty value (schema requirement)
        call_id = kwargs.get('call_id')
        if call_id and call_id.strip():
            parameters.append({"name": "call_id", "value": call_id})
            print(f"🔍 Added call_id to parameters: {call_id}")
        else:
            print(f"🔍 Skipping call_id parameter (empty or None): {repr(call_id)}")
        
        return parameters

    def register_tools(self) -> None:
        """Register menu and ordering tools with the agent"""
        
        # Get menu tool
        self.agent.define_tool(
            name="get_menu",
            description="Get restaurant menu items by category or all items. Can return formatted text for voice or structured JSON for programmatic use.",
            parameters={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Menu category to filter by (breakfast, appetizers, main-courses, desserts, drinks). If not provided, returns all categories.",
                        "enum": ["breakfast", "appetizers", "main-courses", "desserts", "drinks"]
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
            handler=self._get_menu_handler,
            **self.swaig_fields
        )
        
        # Create order tool
        self.agent.define_tool(
            name="create_order",
            description="Create a pickup or delivery order. Extract menu items and quantities from natural language. If user says 'I want the salmon' or 'One cheesecake', extract that information. This will generate a unique order ID. Always ask customers if they want to pay now or at pickup/delivery.",
            parameters={
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
                    "order_type": {"type": "string", "description": "Order type: pickup or delivery (default to pickup)", "default": "pickup"},
                    "payment_preference": {"type": "string", "description": "Payment preference: 'now' to pay immediately with credit card, or 'pickup' to pay at pickup/delivery (default)", "enum": ["now", "pickup"], "default": "pickup"},
                    "special_instructions": {"type": "string", "description": "Special cooking instructions or dietary restrictions"},
                    "customer_address": {"type": "string", "description": "Customer address (required for delivery orders)"},
                    "skip_suggestions": {"type": "boolean", "description": "Skip drink suggestions and additional items (for internal use)", "default": False}
                },
                "required": ["items"]
            },
            handler=self._create_order_handler,
            **self.swaig_fields
        )
        
        # Add item to order tool
        self.agent.define_tool(
            name="add_item_to_order",
            description="Add additional items to an existing order that's being built",
            parameters={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "Additional menu items to add to the order",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Menu item name"},
                                "quantity": {"type": "integer", "description": "Quantity to add"}
                            },
                            "required": ["name", "quantity"]
                        }
                    },
                    "order_context": {"type": "string", "description": "Context about the current order being built"}
                },
                "required": ["items"]
            },
            handler=self._add_item_to_order_handler,
            **self.swaig_fields
        )
        
        # Finalize order tool
        self.agent.define_tool(
            name="finalize_order",
            description="Finalize and complete an order after all items have been added and confirmed",
            parameters={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "Final list of all menu items in the order",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Menu item name"},
                                "quantity": {"type": "integer", "description": "Quantity"}
                            },
                            "required": ["name", "quantity"]
                        }
                    },
                    "customer_name": {"type": "string", "description": "Customer name for the order"},
                    "customer_phone": {"type": "string", "description": "Customer phone number"},
                    "order_type": {"type": "string", "description": "Order type: pickup or delivery", "default": "pickup"},
                    "special_instructions": {"type": "string", "description": "Special cooking instructions or dietary restrictions"},
                    "customer_address": {"type": "string", "description": "Customer address (required for delivery orders)"}
                },
                "required": ["items"]
            },
            handler=self._finalize_order_handler,
            **self.swaig_fields
        )
        
        # Get order status tool
        self.agent.define_tool(
            name="get_order_status",
            description="Check the status of a PICKUP/DELIVERY ORDER (NOT for reservations or payments). CRITICAL: DO NOT use this function when customers want to pay bills, provide card details, or discuss reservations. For reservation payments, use pay_reservation. For order payments, use pay_order. This function is ONLY for checking order preparation status.",
            parameters={
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "description": "Order ID"},
                    "customer_phone": {"type": "string", "description": "Customer phone number"}
                }
            },
            handler=self._get_order_status_handler,
            **self.swaig_fields
        )
        
        # Update order status tool (for staff)
        self.agent.define_tool(
            name="update_order_status",
            description="Update the STATUS of an order (staff/kitchen function only). Use this to change order status like 'pending' to 'preparing' or 'ready' to 'completed'. DO NOT use this to add/remove items from orders.",
            parameters={
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "description": "Order ID"},
                    "new_status": {"type": "string", "description": "New status: pending, preparing, ready, completed, cancelled"}
                },
                "required": ["order_id", "new_status"]
            },
            handler=self._update_order_status_handler,
            **self.swaig_fields
        )
        
        # Update pending order tool (for customers)
        self.agent.define_tool(
            name="update_pending_order",
            description="Update any field of a pending order including items, customer info, delivery details, timing, and special instructions. Only works for pending orders.",
            parameters={
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "description": "Order ID to modify"},
                    "action": {
                        "type": "string", 
                        "enum": ["add", "remove", "change_quantity", "update_info"],
                        "description": "Action to perform: add new items, remove items, change quantity of existing items, or update order information"
                    },
                    "items": {
                        "type": "array",
                        "description": "Items to add, remove, or modify (for item actions)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Menu item name"},
                                "quantity": {"type": "integer", "description": "Quantity (for add/change_quantity actions)"}
                            },
                            "required": ["name"]
                        }
                    },
                    "customer_phone": {"type": "string", "description": "Customer phone number for verification or to update"},
                    "person_name": {"type": "string", "description": "Customer name to update"},
                    "target_date": {"type": "string", "description": "New target date for the order (YYYY-MM-DD)"},
                    "target_time": {"type": "string", "description": "New target time for the order (HH:MM)"},
                    "order_type": {
                        "type": "string",
                        "enum": ["pickup", "delivery"],
                        "description": "Order type: pickup or delivery"
                    },
                    "customer_address": {"type": "string", "description": "Delivery address (required for delivery orders)"},
                    "special_instructions": {"type": "string", "description": "Special instructions or notes for the order"}
                },
                "required": ["order_id", "action"]
            },
            handler=self._update_pending_order_handler,
            **self.swaig_fields
        )
        
        # Kitchen dashboard tools
        self.agent.define_tool(
            name="get_kitchen_orders",
            description="Get orders for kitchen dashboard, filtered by status and date/time range. Useful for kitchen staff to see what needs to be prepared.",
            parameters={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "preparing", "ready", "completed", "cancelled", "all"],
                        "description": "Filter orders by status. 'all' returns all orders.",
                        "default": "all"
                    },
                    "date": {"type": "string", "description": "Filter by date (YYYY-MM-DD). Defaults to today."},
                    "start_time": {"type": "string", "description": "Start time filter (HH:MM). Defaults to 00:00."},
                    "end_time": {"type": "string", "description": "End time filter (HH:MM). Defaults to 23:59."},
                    "format": {
                        "type": "string",
                        "enum": ["text", "json"],
                        "description": "Response format: 'text' for voice-friendly formatted text (default), 'json' for structured data",
                        "default": "text"
                    }
                },
                "required": []
            },
            handler=self._get_kitchen_orders_handler,
            **self.swaig_fields
        )
        
        self.agent.define_tool(
            name="get_order_queue",
            description="Get the current order queue organized by status (pending, preparing, ready). Useful for kitchen workflow management.",
            parameters={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Filter by date (YYYY-MM-DD). Defaults to today."},
                    "format": {
                        "type": "string",
                        "enum": ["text", "json"],
                        "description": "Response format: 'text' for voice-friendly formatted text (default), 'json' for structured data",
                        "default": "text"
                    }
                },
                "required": []
            },
            handler=self._get_order_queue_handler,
            **self.swaig_fields
        )
        
        self.agent.define_tool(
            name="get_kitchen_summary",
            description="Get a summary of kitchen operations including order counts, average preparation times, and workload distribution.",
            parameters={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date for summary (YYYY-MM-DD). Defaults to today."},
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
            handler=self._get_kitchen_summary_handler,
            **self.swaig_fields
        )
        
        # Consolidated pay order tool
        self.agent.define_tool(
            name="pay_order",
            description="Process payment for ANY order (new or existing). Use this when customers want to pay for their order, whether it was just created or already exists. The function automatically detects if this is a new order from the current session or an existing one. Accepts affirmative responses like 'yes', 'sure', 'okay', 'let's do it', 'go ahead', 'I'd like to pay', 'credit card', etc.",
            parameters={
                "type": "object",
                "properties": {
                    "order_number": {"type": "string", "description": "6-digit order number (optional for new orders - will be detected from session)"},
                    "order_id": {"type": "integer", "description": "Order ID (alternative to order_number)"},
                    "customer_name": {"type": "string", "description": "Customer name for verification"},
                    "cardholder_name": {"type": "string", "description": "Name on the credit card (optional, defaults to customer name)"},
                    "phone_number": {"type": "string", "description": "Phone number for SMS receipt (will use caller ID if not provided)"}
                },
                "required": []
            },
            handler=self._pay_order_handler,
            meta_data_token="payment_session",  # Shared token for payment session management
            **self.swaig_fields
        )
        
        # NOTE: The following functions are kept as internal methods but not exposed to AI:
        # - send_payment_receipt (internal callback only)
        # - payment_completed (internal callback only)  
        # - send_test_sms (testing only, not for production AI use)
        
        # Register send_payment_receipt for internal SWAIG callbacks (not for AI use)
        self.agent.define_tool(
            name="send_payment_receipt",
            description="Internal function to send payment receipt SMS (callback only, not for AI use)",
            parameters={
                "type": "object",
                "properties": {
                    "reservation_number": {"type": "string", "description": "Reservation number"},
                    "phone_number": {"type": "string", "description": "Phone number to send SMS to"},
                    "amount": {"type": "number", "description": "Payment amount in dollars"},
                    "confirmation_number": {"type": "string", "description": "Payment confirmation number"}
                },
                "required": ["reservation_number", "phone_number", "amount", "confirmation_number"]
            },
            handler=self._send_payment_receipt_handler,
            **self.swaig_fields
        )
    
    def _get_menu_handler(self, args, raw_data):
        """Handler for get_menu tool"""

        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import MenuItem
            
            with app.app_context():
                # Check if user is asking for specific items from conversation
                call_log = raw_data.get('call_log', []) if raw_data else []
                specific_item_request = None
                
                # Look for specific item requests in recent conversation
                for entry in reversed(call_log[-5:]):  # Check last 5 entries
                    if entry.get('role') == 'user' and entry.get('content'):
                        content = entry['content'].lower()
                        
                        # Check for specific item requests
                        if 'lemonade' in content:
                            specific_item_request = 'lemonade'
                            break
                        elif 'wings' in content:
                            specific_item_request = 'wings'
                            break
                        elif 'burger' in content:
                            specific_item_request = 'burger'
                            break
                        elif 'steak' in content:
                            specific_item_request = 'steak'
                            break
                
                # If user asked for a specific item, provide detailed info about that item
                if specific_item_request:
                    if specific_item_request == 'lemonade':
                        lemonade_items = MenuItem.query.filter(
                            MenuItem.name.ilike('%lemonade%'),
                            MenuItem.is_available == True
                        ).all()
                        
                        if lemonade_items:
                            message = "Here are our lemonade options: "
                            item_list = []
                            for item in lemonade_items:
                                item_list.append(f"{item.name} for ${item.price:.2f}")
                            message += ", ".join(item_list) + ". "
                            message += "Would you like to add any of these to your order?"
                            return SwaigFunctionResult(message)
                        else:
                            return SwaigFunctionResult("I'm sorry, we don't currently have lemonade available on our menu. Would you like to hear about our other drink options?")
                    
                    elif specific_item_request == 'wings':
                        wing_items = MenuItem.query.filter(
                            MenuItem.name.ilike('%wing%'),
                            MenuItem.is_available == True
                        ).all()
                        
                        if wing_items:
                            message = "Here are our wing options: "
                            item_list = []
                            for item in wing_items:
                                item_list.append(f"{item.name} for ${item.price:.2f}")
                            message += ", ".join(item_list) + ". "
                            message += "Would you like to add any of these to your order?"
                            return SwaigFunctionResult(message)
                
                # Detect if this is a SignalWire call and default to text format for voice
                # SignalWire calls include specific metadata in raw_data
                is_signalwire_call = (
                    raw_data and 
                    isinstance(raw_data, dict) and 
                    ('content_type' in raw_data or 'app_name' in raw_data or 'call_id' in raw_data)
                )
                
                # Get format preference - default to text for voice calls, json only if explicitly requested
                default_format = 'text'  # Always default to text for voice-friendly responses
                response_format = args.get('format', default_format).lower()
                
                if args.get('category'):
                    # Normalize category name to match database
                    category_map = {
                        'breakfast': 'breakfast',
                        'appetizers': 'appetizers', 
                        'starters': 'appetizers',
                        'starter': 'appetizers',
                        'main-courses': 'main-courses',
                        'main courses': 'main-courses',
                        'mains': 'main-courses',
                        'main': 'main-courses',
                        'desserts': 'desserts',
                        'dessert': 'desserts',
                        'drinks': 'drinks',
                        'non-alcoholic': 'drinks',
                        'cocktails': 'drinks',
                        'cocktail': 'drinks',
                        'wine': 'drinks',
                        'wines': 'drinks'
                    }
                    
                    category_display_names = {
                        'breakfast': 'Breakfast',
                        'appetizers': 'Appetizers', 
                        'main-courses': 'Main Courses',
                        'desserts': 'Desserts',
                        'drinks': 'Drinks'
                    }
                    
                    category = category_map.get(args['category'].lower(), args['category'].lower())
                    items = MenuItem.query.filter_by(category=category, is_available=True).all()
                    
                    if not items:
                        display_name = category_display_names.get(category, category.title())
                        if response_format == 'json':
                            return SwaigFunctionResult({
                                "success": False,
                                "message": f"No items found in {display_name} category",
                                "category": category,
                                "items": []
                            })
                        else:
                            return SwaigFunctionResult(f"I couldn't find any items in the {display_name} category. Would you like to hear about our other menu categories?")
                    
                    if response_format == 'json':
                        # Return structured JSON data with proper SWAIG format
                        display_name = category_display_names.get(category, category.title())
                        response_text = f"Here are our {display_name} items with {len(items)} options available."
                        
                        return (
                            SwaigFunctionResult(response_text)
                            .add_action("menu_data", {
                                "success": True,
                                "category": category,
                                "category_display_name": display_name,
                                "items": [item.to_dict() for item in items]
                            })
                        )
                    else:
                        # Return formatted text for voice
                        display_name = category_display_names.get(category, category.title())
                        message = f"Here are our {display_name} items: "
                        item_list = []
                        for item in items:
                            item_list.append(f"{item.name} for ${item.price:.2f}")
                        message += ", ".join(item_list) + ". Would you like to hear details about any specific item?"
                        return SwaigFunctionResult(message)
                    
                else:
                    # Get all menu items organized by category
                    categories = ['breakfast', 'appetizers', 'main-courses', 'desserts', 'drinks']
                    category_display_names = {
                        'breakfast': 'Breakfast',
                        'appetizers': 'Appetizers', 
                        'main-courses': 'Main Courses',
                        'desserts': 'Desserts',
                        'drinks': 'Drinks'
                    }
                    
                    if response_format == 'json':
                        # Return structured JSON data with proper SWAIG format
                        menu_data = {}
                        total_items = 0
                        for category in categories:
                            items = MenuItem.query.filter_by(category=category, is_available=True).all()
                            if items:
                                menu_data[category] = {
                                    "display_name": category_display_names[category],
                                    "items": [item.to_dict() for item in items]
                                }
                                total_items += len(items)
                        
                        response_text = f"Here's our complete menu with {len(menu_data)} categories and {total_items} items available."
                        
                        result = (
                            SwaigFunctionResult(response_text)
                            .add_action("menu_data", {
                                "success": True,
                                "menu": menu_data,
                                "total_categories": len(menu_data),
                                "total_items": total_items
                            })
                        )
                        # Store menu data in meta_data for future reference
                        result.add_action("set_meta_data", {
                            "menu_data": menu_data,
                            "menu_retrieved_at": datetime.now().isoformat(),
                            "total_items": total_items
                        })
                        return result
                    else:
                        # Return formatted text for voice - more concise for phone calls
                        # Get all available items across all categories
                        all_items = MenuItem.query.filter_by(is_available=True).all()
                        
                        if not all_items:
                            return SwaigFunctionResult("I'm sorry, our menu is currently unavailable. Please try again later.")
                        
                        # Group items by category for organized presentation
                        categories_with_items = {}
                        for item in all_items:
                            if item.category not in categories_with_items:
                                categories_with_items[item.category] = []
                            categories_with_items[item.category].append(item)
                        
                        # Build comprehensive menu response
                        message = f"Here's our complete menu with {len(all_items)} items available. "
                        
                        # List items by category
                        for category, items in categories_with_items.items():
                            category_display = category.replace('-', ' ').title()
                            message += f"For {category_display}, we have: "
                            item_list = []
                            for item in items:
                                item_list.append(f"{item.name} for ${item.price:.2f}")
                            message += ", ".join(item_list) + ". "
                        
                        message += "Would you like to hear more details about any category or specific item?"
                        
                        # Also include the menu data in the result for programmatic access
                        result = SwaigFunctionResult(message)
                        result.add_action("menu_data", {
                            "success": True,
                            "total_items": len(all_items),
                            "categories": list(categories_with_items.keys()),
                            "items": [item.to_dict() for item in all_items]
                        })
                        return result
                
        except Exception as e:
            if args.get('format', 'text').lower() == 'json':
                return (
                    SwaigFunctionResult("Sorry, there was an error retrieving the menu.")
                    .add_action("error_data", {
                        "success": False,
                        "error": str(e),
                        "message": "Error retrieving menu"
                    })
                )
            else:
                return SwaigFunctionResult(f"Sorry, there was an error retrieving the menu: {str(e)}")
    
    def _extract_order_from_conversation(self, user_messages):
        """Extract order items from natural language conversation"""
        try:
            # Import Flask app and models locally
            import sys
            import os
            import re
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import MenuItem
            
            with app.app_context():
                # Get all menu items for matching
                menu_items = MenuItem.query.filter_by(is_available=True).all()
                menu_item_names = [item.name.lower() for item in menu_items]
                
                extracted_items = []
                
                # Combine all user messages into one text for analysis
                conversation_text = " ".join(user_messages)
                
                # Common quantity words and numbers
                quantity_patterns = {
                    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
                    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
                    'a': 1, 'an': 1, 'single': 1, 'couple': 2, 'few': 3,
                    '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10
                }
                
                # Special handling for common menu items mentioned in conversation
                special_patterns = {
                    'buffalo wings': 'Buffalo Wings',
                    'buffalo wing': 'Buffalo Wings',
                    'wings': 'Buffalo Wings',
                    'bruschetta': 'Bruschetta',
                    'stuffed mushrooms': 'Stuffed Mushrooms',
                    'mushrooms': 'Stuffed Mushrooms',
                    'mozzarella sticks': 'Mozzarella Sticks',
                    'calamari': 'Calamari'
                }
                
                # First check for special patterns
                for pattern, item_name in special_patterns.items():
                    if pattern in conversation_text:
                        # Try to find quantity
                        quantity = 1  # Default quantity
                        
                        # Look for numbers or quantity words near the pattern
                        patterns_to_check = [
                            rf'(\d+)\s*{re.escape(pattern)}',  # "2 buffalo wings"
                            rf'{re.escape(pattern)}\s*(\d+)',  # "buffalo wings 2"
                            rf'(\w+)\s*{re.escape(pattern)}',  # "two buffalo wings"
                            rf'{re.escape(pattern)}\s*(\w+)',  # "buffalo wings two"
                        ]
                        
                        for qty_pattern in patterns_to_check:
                            match = re.search(qty_pattern, conversation_text)
                            if match:
                                qty_text = match.group(1).lower()
                                if qty_text.isdigit():
                                    quantity = int(qty_text)
                                elif qty_text in quantity_patterns:
                                    quantity = quantity_patterns[qty_text]
                                break
                        
                        extracted_items.append({
                            'name': item_name,
                            'quantity': quantity
                        })
                        
                        # Remove this pattern from conversation to avoid double-counting
                        conversation_text = conversation_text.replace(pattern, '', 1)
                
                # If no special patterns found, look for menu items mentioned in the conversation
                if not extracted_items:
                    for menu_item in menu_items:
                        item_name = menu_item.name.lower()
                        
                        # Check if the item name (or parts of it) appear in the conversation
                        if item_name in conversation_text:
                            # Try to find quantity near the item name
                            quantity = 1  # Default quantity
                            
                            # Look for numbers or quantity words near the item name
                            # Pattern: "number + item" or "item + number" or quantity words
                            patterns = [
                                rf'(\d+)\s*{re.escape(item_name)}',  # "2 salmon"
                                rf'{re.escape(item_name)}\s*(\d+)',  # "salmon 2"
                                rf'(\w+)\s*{re.escape(item_name)}',  # "two salmon"
                                rf'{re.escape(item_name)}\s*(\w+)',  # "salmon two"
                            ]
                            
                            for pattern in patterns:
                                match = re.search(pattern, conversation_text)
                                if match:
                                    qty_text = match.group(1).lower()
                                    if qty_text.isdigit():
                                        quantity = int(qty_text)
                                    elif qty_text in quantity_patterns:
                                        quantity = quantity_patterns[qty_text]
                                    break
                            
                            extracted_items.append({
                                'name': menu_item.name,
                                'quantity': quantity
                            })
                            
                            # Remove this item from conversation to avoid double-counting
                            conversation_text = conversation_text.replace(item_name, '', 1)
                
                # Also check for fuzzy matches to handle misspellings
                if not extracted_items:
                    # Extract potential food words from conversation
                    words = conversation_text.lower().split()
                    
                    # Look for food-related words and phrases
                    for i, word in enumerate(words):
                        # Skip common non-food words
                        if word in ['i', 'want', 'like', 'get', 'have', 'order', 'the', 'a', 'an', 'some', 'please', 'would', 'could', 'can']:
                            continue
                        
                        # Try single words and two-word combinations
                        potential_items = [word]
                        if i < len(words) - 1:
                            two_word = f"{word} {words[i+1]}"
                            potential_items.append(two_word)
                        
                        # Try to match each potential food word with menu items using fuzzy matching
                        for potential_item in potential_items:
                            menu_item = self._find_menu_item_fuzzy(potential_item)
                            if menu_item:
                                quantity = 1  # Default quantity
                                
                                # Try to find quantity near the food word
                                patterns_to_check = [
                                    rf'(\d+)\s*{re.escape(potential_item)}',
                                    rf'{re.escape(potential_item)}\s*(\d+)',
                                    rf'(\w+)\s*{re.escape(potential_item)}',
                                    rf'{re.escape(potential_item)}\s*(\w+)',
                                ]
                                
                                for qty_pattern in patterns_to_check:
                                    match = re.search(qty_pattern, conversation_text)
                                    if match:
                                        qty_text = match.group(1).lower()
                                        if qty_text.isdigit():
                                            quantity = int(qty_text)
                                        elif qty_text in quantity_patterns:
                                            quantity = quantity_patterns[qty_text]
                                        break
                                
                                extracted_items.append({
                                    'name': menu_item.name,  # Use corrected name
                                    'quantity': quantity
                                })
                                if menu_item.name.lower() != potential_item.lower():
                                    print(f"🔍 Found menu item via fuzzy match: '{potential_item}' -> '{menu_item.name}' x{quantity}")
                                else:
                                    print(f"🔍 Found menu item '{menu_item.name}' x{quantity}")
                                break
                        
                        if extracted_items:  # Stop after finding first match
                            break
                
                return extracted_items
                
        except Exception as e:
            print(f"Error extracting order from conversation: {e}")
            return []

    def _suggest_drink_for_food(self, food_items):
        """Suggest complementary drinks based on food items ordered"""
        try:
            # Import Flask app and models locally
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import MenuItem
            
            with app.app_context():
                # Get available drinks
                drinks = MenuItem.query.filter_by(category='drinks', is_available=True).all()
                if not drinks:
                    return None
                
                # Food-to-drink pairing suggestions
                food_drink_pairings = {
                    # Appetizers
                    'buffalo wings': ['Beer', 'Iced Tea', 'Lemonade', 'Pepsi', 'Mountain Dew'],
                    'bruschetta': ['White Wine', 'Sparkling Water', 'Italian Soda', 'Sierra Mist'],
                    'stuffed mushrooms': ['Red Wine', 'Sparkling Water'],
                    'mozzarella sticks': ['Beer', 'Soda', 'Iced Tea', 'Pepsi', 'Coca-Cola'],
                    'calamari': ['White Wine', 'Beer', 'Lemonade', 'Sierra Mist'],
                    
                    # Main courses
                    'grilled salmon': ['White Wine', 'Sparkling Water', 'Lemonade', 'Sierra Mist'],
                    'ribeye steak': ['Red Wine', 'Beer', 'Iced Tea', 'Pepsi'],
                    'chicken parmesan': ['Red Wine', 'Italian Soda', 'Iced Tea', 'Pepsi'],
                    'pasta': ['Red Wine', 'Italian Soda', 'Sparkling Water', 'Sierra Mist'],
                    'burger': ['Beer', 'Soda', 'Milkshake', 'Pepsi', 'Coca-Cola', 'Mountain Dew'],
                    'pizza': ['Beer', 'Soda', 'Italian Soda', 'Pepsi', 'Coca-Cola', 'Mountain Dew'],
                    'fish': ['White Wine', 'Lemonade', 'Sparkling Water', 'Sierra Mist'],
                    'chicken': ['White Wine', 'Iced Tea', 'Lemonade', 'Diet Pepsi'],
                    'beef': ['Red Wine', 'Beer', 'Iced Tea', 'Pepsi'],
                    'pork': ['Beer', 'Apple Cider', 'Iced Tea', 'Pepsi'],
                    
                    # Desserts
                    'cheesecake': ['Coffee', 'Dessert Wine', 'Milk'],
                    'chocolate': ['Coffee', 'Milk', 'Hot Chocolate'],
                    'ice cream': ['Coffee', 'Milk', 'Hot Chocolate'],
                    'tiramisu': ['Coffee', 'Dessert Wine'],
                    'cake': ['Coffee', 'Milk', 'Tea']
                }
                
                # Find the best drink suggestion based on food items
                suggested_drinks = set()
                for food_item in food_items:
                    food_name = food_item['name'].lower()
                    
                    # Check for exact matches first
                    for food_key, drink_suggestions in food_drink_pairings.items():
                        if food_key in food_name:
                            suggested_drinks.update(drink_suggestions)
                            break
                
                # If no specific pairing found, suggest based on category
                if not suggested_drinks:
                    # Default suggestions for different meal types
                    has_appetizer = any('appetizer' in food_item.get('category', '').lower() for food_item in food_items)
                    has_main = any('main' in food_item.get('category', '').lower() for food_item in food_items)
                    has_dessert = any('dessert' in food_item.get('category', '').lower() for food_item in food_items)
                    
                    if has_dessert:
                        suggested_drinks.update(['Coffee', 'Milk', 'Tea'])
                    elif has_main:
                        suggested_drinks.update(['Iced Tea', 'Soda', 'Water'])
                    elif has_appetizer:
                        suggested_drinks.update(['Beer', 'Soda', 'Iced Tea'])
                    else:
                        suggested_drinks.update(['Water', 'Soda', 'Iced Tea'])
                
                # Find available drinks that match suggestions
                available_suggested_drinks = []
                for drink in drinks:
                    for suggestion in suggested_drinks:
                        if suggestion.lower() in drink.name.lower():
                            available_suggested_drinks.append(drink)
                            break
                
                # Return the first available suggested drink
                return available_suggested_drinks[0] if available_suggested_drinks else drinks[0]
                
        except Exception as e:
            print(f"Error suggesting drink for food: {e}")
            return None

    def _send_order_sms(self, order_data, phone_number):
        """Send SMS confirmation for order"""
        try:
            # Convert time to 12-hour format for SMS
            try:
                time_obj = datetime.strptime(str(order_data['target_time']), '%H:%M')
                time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
            except (ValueError, TypeError):
                time_12hr = str(order_data['target_time'])
            
            sms_body = f"🍽️ Bobby's Table Order Confirmed!\n\n"
            sms_body += f"Order #{order_data['id']} for {order_data['person_name']}\n"
            sms_body += f"📱 Phone: {phone_number}\n\n"
            sms_body += f"📋 Items Ordered:\n"
            
            for item in order_data['items']:
                sms_body += f"   • {item}\n"
            
            sms_body += f"\n💰 Total: ${order_data['total_amount']:.2f}\n"
            sms_body += f"📦 Type: {order_data['order_type'].title()}\n"
            
            if order_data['order_type'] == 'pickup':
                sms_body += f"⏰ Ready for pickup: {time_12hr}\n"
                sms_body += f"📍 Please come to Bobby's Table to collect your order.\n"
            else:
                sms_body += f"🚚 Estimated delivery: {time_12hr}\n"
                if order_data.get('customer_address'):
                    sms_body += f"📍 Delivery address: {order_data['customer_address']}\n"
            
            if order_data.get('special_instructions'):
                sms_body += f"📝 Special instructions: {order_data['special_instructions']}\n"
            
            sms_body += f"\nThank you for choosing Bobby's Table! We'll have your delicious order ready right on time."
            sms_body += f"\nCall us anytime to check on your order status using order #{order_data['id']}."
            sms_body += f"\nReply STOP to stop."
            
            # Send SMS using SignalWire Agents SDK
            sms_function_result = SwaigFunctionResult().send_sms(
                to_number=phone_number,
                from_number=self.signalwire_from_number,
                body=sms_body
            )
            
            return {'success': True, 'sms_sent': True, 'result': sms_function_result}
            
        except Exception as e:
            print(f"❌ SMS Error: Failed to send SMS to {phone_number}: {e}")
            return {'success': False, 'sms_sent': False, 'error': str(e)}

    def _add_item_to_order_handler(self, args, raw_data):
        """Handler for add_item_to_order tool - used for building orders incrementally"""
        try:
            # This is a helper function that doesn't actually create orders
            # It's used to acknowledge additional items and suggest next steps
            
            items = args.get('items', [])
            if not items:
                return SwaigFunctionResult("I didn't catch what you'd like to add. Could you please tell me which items you'd like to add to your order?")
            
            # Acknowledge the additional items
            item_list = []
            for item in items:
                quantity = item.get('quantity', 1)
                item_list.append(f"{quantity}x {item['name']}")
            
            message = f"Great! I'll add {', '.join(item_list)} to your order. "
            
            # Ask if they want anything else
            message += "Would you like to add anything else to your order, or shall I finalize it for you?"
            
            return SwaigFunctionResult(message)
            
        except Exception as e:
            return SwaigFunctionResult(f"Sorry, there was an error adding items to your order: {str(e)}")

    def _finalize_order_handler(self, args, raw_data):
        """Handler for finalize_order tool - completes the order with all items"""
        try:
            # This calls create_order with skip_suggestions=True to bypass the suggestion phase
            args['skip_suggestions'] = True
            return self._create_order_handler(args, raw_data)
            
        except Exception as e:
            return SwaigFunctionResult(f"Sorry, there was an error finalizing your order: {str(e)}")

    def _create_order_handler(self, args, raw_data):
        """Handler for create_order tool"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            import random
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import db, Order, OrderItem, MenuItem, Reservation
            
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
                
                # Handle phone number with priority: user-provided > conversation-extracted > caller ID
                user_provided_phone = args.get('customer_phone')
                conversation_phone = self._extract_phone_from_conversation(raw_data.get('call_log', []) if raw_data else [])
                
                # Determine which phone number to use
                if user_provided_phone:
                    # User explicitly provided a phone number
                    normalized_phone = self._normalize_phone_number(user_provided_phone, caller_phone)
                    args['customer_phone'] = normalized_phone
                    print(f"🔄 Using user-provided phone number: {normalized_phone}")
                elif conversation_phone:
                    # Phone number extracted from conversation
                    args['customer_phone'] = conversation_phone
                    print(f"🔄 Using phone number from conversation: {conversation_phone}")
                elif caller_phone:
                    # Default to caller ID
                    normalized_phone = self._normalize_phone_number(caller_phone)
                    args['customer_phone'] = normalized_phone
                    print(f"🔄 Using caller ID as phone number: {normalized_phone}")
                else:
                    print("⚠️  No phone number available")
                
                # Try to extract customer name from conversation if not provided
                if not args.get('customer_name'):
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    for entry in call_log:
                        if entry.get('role') == 'user' and entry.get('content'):
                            content = entry['content'].lower()
                            # Look for patterns like "put this under the name X" or "name is X"
                            if 'name' in content:
                                import re
                                # Pattern to extract name after "name" keyword
                                name_patterns = [
                                    r'name\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)*)',
                                    r'under(?:neath)?\s+(?:the\s+)?name\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)*)',
                                    r'put\s+(?:this\s+)?under(?:neath)?\s+(?:the\s+)?name\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)*)'
                                ]
                                
                                for pattern in name_patterns:
                                    match = re.search(pattern, content)
                                    if match:
                                        extracted_name = match.group(1).strip().title()
                                        args['customer_name'] = extracted_name
                                        print(f"🔄 Extracted customer name from conversation: {extracted_name}")
                                        break
                                
                                if args.get('customer_name'):
                                    break
                
                # Try to get customer name from recent reservation if still not provided
                if not args.get('customer_name') and caller_phone:
                    recent_reservation = Reservation.query.filter(
                        Reservation.phone_number.like(f"%{caller_phone}%")
                    ).order_by(Reservation.date.desc()).first()
                    
                    if recent_reservation:
                        args['customer_name'] = recent_reservation.name
                        print(f"🔄 Auto-filled customer name from recent reservation: {recent_reservation.name}")
                
                # Try to extract order information from conversation context if items not provided
                if not args.get('items'):
                    # Look at the conversation history to extract order information
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    
                    # Get recent user messages to extract order intent
                    recent_user_messages = []
                    order_confirmed = False
                    
                    # First pass: collect all user messages and check for confirmation
                    all_user_messages = []
                    for entry in call_log:
                        if entry.get('role') == 'user' and entry.get('content'):
                            content = entry['content'].lower()
                            all_user_messages.append(content)
                            
                            # Check if user confirmed an order or wants to finalize
                            confirmation_phrases = ['yes', 'yes.', 'confirm', 'confirmed', 'place order', 'place the order', 'finalize my order', 'finalize order', 'finalize', 'complete my order', 'complete order', 'okay', 'ok']
                            if any(phrase in content for phrase in confirmation_phrases):
                                order_confirmed = True
                                # If user explicitly said "finalize", set skip_suggestions to True
                                if 'finalize' in content or 'complete' in content:
                                    args['skip_suggestions'] = True
                                # Also check if user said "yes" after being asked about finalizing
                                elif content.strip() in ['yes', 'yes.', 'okay', 'ok']:
                                    # This might be a confirmation to finalize
                                    args['skip_suggestions'] = True
                                    print(f"🔄 User confirmed with '{content}' - treating as finalization")
                    
                    # Second pass: look for buffalo wings mentions and extract quantity
                    for entry in call_log:
                        if entry.get('role') == 'assistant' and entry.get('content'):
                            # Check if assistant mentioned specific items
                            content = entry['content'].lower()
                            if 'buffalo wings' in content:
                                # Extract quantity - check ALL user messages for quantity
                                quantity = 1  # default
                                
                                # Check user messages for quantity mentions, but only in food-related contexts
                                for user_msg in all_user_messages:
                                    # Skip messages that are clearly about reservations, not food orders
                                    if 'reservation' in user_msg.lower() or 'check on' in user_msg.lower():
                                        continue
                                    
                                    # Only look for quantities in messages that mention food or ordering
                                    if any(food_word in user_msg.lower() for food_word in ['wings', 'order', 'want', 'like', 'get', 'buffalo', 'chicken', 'food']):
                                        words = user_msg.lower().split()
                                        if 'two' in words or 'two.' in words or '2' in words:
                                            quantity = 2
                                            print(f"🔢 Found user said 'two' in food context: '{user_msg}' - setting quantity to 2")
                                            break
                                        elif 'three' in words or 'three.' in words or '3' in words:
                                            quantity = 3
                                            print(f"🔢 Found user said 'three' in food context: '{user_msg}' - setting quantity to 3")
                                            break
                                        elif 'four' in words or 'four.' in words or '4' in words:
                                            quantity = 4
                                            print(f"🔢 Found user said 'four' in food context: '{user_msg}' - setting quantity to 4")
                                            break
                                        elif 'one' in words or 'one.' in words or '1' in words:
                                            quantity = 1
                                            print(f"🔢 Found user said 'one' in food context: '{user_msg}' - setting quantity to 1")
                                            break
                                
                                # Fallback to assistant message if no user quantity found
                                if quantity == 1:
                                    if 'two' in content or '2x' in content or '2 ' in content:
                                        quantity = 2
                                    elif 'one' in content or '1x' in content or '1 ' in content:
                                        quantity = 1
                                
                                # Assistant mentioned buffalo wings, user likely confirmed
                                if order_confirmed:
                                    args['items'] = [{'name': 'Buffalo Wings', 'quantity': quantity}]
                                    print(f"🤖 Extracted confirmed order from conversation: Buffalo Wings x{quantity}")
                                    break
                    
                    # Set recent_user_messages for fallback extraction
                    recent_user_messages = all_user_messages[-5:] if all_user_messages else []
                    
                    # If no confirmed order found, try to extract from user messages
                    if not args.get('items'):
                        extracted_items = self._extract_order_from_conversation(recent_user_messages)
                        
                        if extracted_items:
                            args['items'] = extracted_items
                            print(f"🤖 Extracted order from conversation: {extracted_items}")
                        else:
                            # If we still can't extract items, provide helpful guidance
                            return SwaigFunctionResult("I'd be happy to help you place an order! What would you like to order today? You can just tell me the items you want, like 'I'd like the salmon' or 'I want the cheesecake'.")
                
                # Check if this is the initial order creation (not skipping suggestions)
                skip_suggestions = args.get('skip_suggestions', False)
                
                # If we have items but haven't asked about drinks/additional items yet, do that first
                if args.get('items') and not skip_suggestions:
                    # Calculate current order total for display
                    current_items = []
                    current_total = 0
                    
                    for item_data in args['items']:
                        menu_item = MenuItem.query.filter_by(name=item_data['name'], is_available=True).first()
                        if menu_item:
                            quantity = item_data.get('quantity', 1)
                            current_items.append(f"{quantity}x {menu_item.name}")
                            current_total += menu_item.price * quantity
                    
                    if current_items:
                        # Suggest a complementary drink
                        suggested_drink = self._suggest_drink_for_food(args['items'])
                        
                        message = f"Great! So far I have {', '.join(current_items)} for ${current_total:.2f}. "
                        
                        if suggested_drink:
                            message += f"Would you like to add a {suggested_drink.name} for ${suggested_drink.price:.2f}? It pairs perfectly with your order. "
                        
                        message += "Or would you like to add any other items to your order? If you're all set, just say 'finalize my order' and I'll complete it for you."
                        
                        return SwaigFunctionResult(message)
                
                # Check for required information
                missing_info = []
                if not args.get('customer_name'):
                    missing_info.append("your name")
                if not args.get('customer_phone'):
                    missing_info.append("your phone number")
                if not args.get('items') or len(args.get('items', [])) == 0:
                    missing_info.append("items to order")
                
                # Check if delivery address is needed
                order_type = args.get('order_type', 'pickup').lower()
                if order_type == 'delivery' and not args.get('customer_address'):
                    missing_info.append("your delivery address")
                
                if missing_info:
                    missing_text = " and ".join(missing_info)
                    return SwaigFunctionResult(f"I need {missing_text} to complete your order. Could you please provide that information?")
                
                # Validate order type
                if order_type not in ['pickup', 'delivery']:
                    return SwaigFunctionResult("Order type must be either 'pickup' or 'delivery'.")
                
                # Check if a similar order was recently created to avoid duplicates
                from datetime import datetime, timedelta
                now = datetime.now()
                recent_cutoff = now - timedelta(minutes=5)  # Check last 5 minutes
                
                if caller_phone:
                    recent_order = Order.query.filter(
                        Order.customer_phone.like(f"%{caller_phone}%"),
                        Order.created_at >= recent_cutoff
                    ).first()
                    
                    if recent_order:
                        return SwaigFunctionResult(f"I see you recently placed order #{recent_order.id}. Would you like to check the status of that order or place a new one?")
                
                # Generate random estimated time (10-45 minutes)
                estimated_minutes = random.randint(10, 45)
                estimated_ready_time = now + timedelta(minutes=estimated_minutes)
                
                # Create the order without requiring a reservation (matching Flask route structure)
                order = Order(
                    order_number=self._generate_order_number(),
                    person_name=args['customer_name'],
                    status='pending',
                    target_date=str(now.date()),
                    target_time=estimated_ready_time.strftime('%H:%M'),
                    order_type=order_type,
                    customer_phone=args['customer_phone'],
                    customer_address=args.get('customer_address', ''),
                    special_instructions=args.get('special_instructions', ''),
                    reservation_id=None  # No reservation required
                )
                
                db.session.add(order)
                db.session.flush()  # Get order ID
                
                total_amount = 0
                order_summary = []
                
                # Add order items
                for item_data in args['items']:
                    # Find menu item by name with fuzzy matching
                    menu_item = self._find_menu_item_fuzzy(item_data['name'])
                    if not menu_item:
                        return SwaigFunctionResult(f"Sorry, '{item_data['name']}' is not available on our menu.")
                    
                    # Log if we corrected the spelling
                    if menu_item.name.lower() != item_data['name'].lower():
                        print(f"🔄 Corrected '{item_data['name']}' to '{menu_item.name}'")
                    
                    quantity = item_data.get('quantity', 1)
                    
                    order_item = OrderItem(
                        order_id=order.id,
                        menu_item_id=menu_item.id,
                        quantity=quantity,
                        price_at_time=menu_item.price
                    )
                    
                    db.session.add(order_item)
                    total_amount += menu_item.price * quantity
                    order_summary.append(f"{quantity}x {menu_item.name}")  # Use corrected name
                
                # Round total amount to 2 decimal places to avoid floating-point precision issues
                total_amount = round(total_amount, 2)
                order.total_amount = total_amount
                db.session.commit()
                
                # Convert estimated ready time to 12-hour format
                ready_time_12hr = estimated_ready_time.strftime('%I:%M %p').lstrip('0')
                
                # Prepare order data for SMS
                order_data = {
                    'id': order.id,
                    'person_name': order.person_name,
                    'target_time': order.target_time,
                    'items': order_summary,
                    'total_amount': order.total_amount,
                    'order_type': order.order_type,
                    'customer_address': order.customer_address,
                    'special_instructions': order.special_instructions
                }
                
                # Send SMS confirmation
                sms_result = self._send_order_sms(order_data, args['customer_phone'])
                
                # Check if payment preference was specified
                payment_preference = args.get('payment_preference', 'pickup')  # Default to pay at pickup
                
                # Update order payment status based on preference
                if payment_preference == 'now':
                    order.payment_status = 'pending'  # Will be updated after payment processing
                else:
                    order.payment_status = 'unpaid'  # Pay at pickup/delivery
                
                db.session.commit()
                
                # Create comprehensive order confirmation
                message = f"🍽️ ORDER CONFIRMED! 🍽️\n\n"
                message += f"Order #{order.order_number} for {args['customer_name']}\n"
                message += f"📱 Phone: {args['customer_phone']}\n\n"
                message += f"📋 Items Ordered:\n"
                for item in order_summary:
                    message += f"   • {item}\n"
                message += f"\n💰 Total: ${total_amount:.2f}\n"
                message += f"📦 Type: {order_type.title()}\n"
                
                if order_type == 'pickup':
                    message += f"⏰ Ready for pickup: {ready_time_12hr}\n"
                    message += f"📍 Please come to Bobby's Table to collect your order.\n"
                else:
                    message += f"🚚 Estimated delivery: {ready_time_12hr}\n"
                    if args.get('customer_address'):
                        message += f"📍 Delivery address: {args['customer_address']}\n"
                
                if args.get('special_instructions'):
                    message += f"📝 Special instructions: {args['special_instructions']}\n"
                
                # Add SMS confirmation status to the message
                if sms_result.get('sms_sent'):
                    message += f"\n📱 A confirmation SMS has been sent to your phone. "
                
                # Prepare meta_data for payment processing
                order_meta_data = {
                    'order_id': order.id,
                    'order_number': order.order_number,
                    'customer_name': args['customer_name'],
                    'customer_phone': args['customer_phone'],
                    'order_total': total_amount,
                    'order_type': order_type,
                    'payment_needed': True,
                    'payment_amount': total_amount,
                    'cardholder_name': args['customer_name'],  # Default cardholder name
                    'order_items': order_summary,
                    'special_instructions': args.get('special_instructions', ''),
                    'customer_address': args.get('customer_address', '')
                }
                
                print(f"🔄 Setting order meta_data: {order_meta_data}")
                
                # Handle payment preference
                if payment_preference == 'now':
                    message += f"\n💳 You chose to pay now. I'll collect your payment information next."
                    message += f"\nThank you for choosing Bobby's Table! We'll have your delicious order ready right on time. "
                    message += f"You can call us anytime to check on your order status using order #{order.order_number}."
                    
                    # Return result with payment action and meta_data
                    result = SwaigFunctionResult(message)
                    result = result.set_metadata(order_meta_data)
                    
                    # Add payment collection using the pay verb
                    import os
                    
                    # Get payment connector URL - try to auto-detect ngrok URL
                    # Get payment connector URL from environment or auto-detect
                    base_url = os.getenv('SIGNALWIRE_PAYMENT_CONNECTOR_URL')
                    
                    if base_url:
                        # Use environment variable and ensure it has the correct endpoint
                        if not base_url.endswith('/api/payment-processor'):
                            payment_connector_url = f"{base_url.rstrip('/')}/api/payment-processor"
                        else:
                            payment_connector_url = base_url
                        print(f"🔗 Using payment connector URL from environment: {payment_connector_url}")
                    else:
                        print("🔗 SIGNALWIRE_PAYMENT_CONNECTOR_URL not set, using auto-detection")
                        # Fallback to dynamic URL detection
                        try:
                            from flask import request
                            if request and request.headers.get('Host'):
                                host = request.headers.get('Host')
                                payment_connector_url = f"https://{host}/api/payment-processor"
                            else:
                                payment_connector_url = 'http://localhost:8080/api/payment-processor'
                        except:
                            payment_connector_url = 'http://localhost:8080/api/payment-processor'
                    
                    print(f"🔗 Using payment connector URL: {payment_connector_url}")
                    
                    # Check if URL is localhost (will cause issues with SignalWire)
                    if 'localhost' in payment_connector_url or '127.0.0.1' in payment_connector_url:
                        print("⚠️  WARNING: Payment connector URL is localhost - SignalWire won't be able to reach this!")
                        print("   Make sure SIGNALWIRE_PAYMENT_CONNECTOR_URL is set to your ngrok URL")
                    
                    # Add payment collection with proper prompts and pound key terminators
                    status_url = payment_connector_url.replace('/api/payment-processor', '/api/signalwire/payment-callback')
                    result = result.pay(
                        payment_connector_url=payment_connector_url,
                        status_url=status_url,
                        input_method="dtmf",
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
                        description=f"Bobby's Table Order #{order.order_number}",
                        valid_card_types="visa mastercard amex discover",
                        prompts=[
                            {
                                "name": "card_number",
                                "text": "Please enter your 16-digit card number followed by the pound key."
                            },
                            {
                                "name": "expiration_date",
                                "text": "Please enter your card's expiration date as 4 digits, month and year, followed by the pound key."
                            },
                            {
                                "name": "security_code",
                                "text": "Please enter your 3 or 4 digit security code followed by the pound key."
                            },
                            {
                                "name": "postal_code",
                                "text": "Please enter your 5-digit ZIP code followed by the pound key."
                            }
                        ],
                        parameters=self._build_payment_parameters(
                            order_id=str(order.id),
                            order_number=order.order_number,
                            customer_name=args['customer_name'],
                            phone_number=args['customer_phone'],
                            payment_type="order",
                            call_id=raw_data.get('call_id') if raw_data else None
                        )
                    )
                    
                    return result
                else:
                    message += f"\n💰 Payment: You'll pay when you {order_type} your order."
                    message += f"\nThank you for choosing Bobby's Table! We'll have your delicious order ready right on time. "
                    message += f"You can call us anytime to check on your order status using order #{order.order_number}."
                    message += f"\n💳 If you'd like to pay now instead, just say 'I want to pay for my order' and I'll help you process the payment."
                    
                    # Return result with meta_data for future payment
                    result = SwaigFunctionResult(message)
                    result = result.set_metadata(order_meta_data)
                    
                    return result
                
        except Exception as e:
            return SwaigFunctionResult(f"Sorry, there was an error creating your order: {str(e)}")
    
    def _get_order_status_handler(self, args, raw_data):
        """Handler for get_order_status tool"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import Order
            from datetime import datetime
            
            with app.app_context():
                # First check if order_number is provided directly
                if args.get('order_number'):
                    order = Order.query.filter_by(order_number=args['order_number']).first()
                    if order:
                        args['order_id'] = order.id
                        print(f"🔍 Found order by number {args['order_number']}: ID {order.id}")
                    else:
                        return SwaigFunctionResult(f"Order number {args['order_number']} not found.")
                
                # Try to extract order number/ID from conversation if not provided in args
                elif not args.get('order_id') and not args.get('reservation_id'):
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    
                    # Extract order number/ID from conversation
                    import re
                    order_number = None
                    order_id = None
                    
                    for entry in call_log:
                        if entry.get('content'):
                            content = entry['content'].lower()
                            
                            # First try to find 6-digit order numbers (be more specific to avoid reservation numbers)
                            order_number_patterns = [
                                r'order number\s+is\s+(\d{6})',  # "order number is 123456"
                                r'order\s+(\d{6})',              # "order 123456"
                                r'order\s+number\s+(\d{6})',     # "order number 123456"
                                # Removed the overly broad r'(\d{6})' pattern that matches any 6-digit number
                            ]
                            
                            for pattern in order_number_patterns:
                                match = re.search(pattern, content)
                                if match:
                                    order_number = match.group(1)
                                    print(f"🔍 Extracted order number from conversation: {order_number}")
                                    break
                            
                            # If no 6-digit number found, try shorter order IDs
                            if not order_number:
                                order_id_patterns = [
                                    r'order\s+(?:number\s+)?(\d+)',
                                    r'order\s+(?:number\s+)?(nineteen|eighteen|seventeen|sixteen|fifteen|fourteen|thirteen|twelve|eleven|ten|nine|eight|seven|six|five|four|three|two|one)',
                                    r'(?:check\s+)?(?:my\s+)?order\s+(?:number\s+)?(\d+)',
                                    r'(?:check\s+)?(?:my\s+)?order\s+(?:number\s+)?(nineteen|eighteen|seventeen|sixteen|fifteen|fourteen|thirteen|twelve|eleven|ten|nine|eight|seven|six|five|four|three|two|one)',
                                    r'#(\d+)'
                                ]
                                
                                for pattern in order_id_patterns:
                                    order_match = re.search(pattern, content)
                                    if order_match:
                                        order_num = order_match.group(1)
                                        # Convert word numbers to digits
                                        word_to_num = {
                                            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
                                            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
                                            'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14,
                                            'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18,
                                            'nineteen': 19, 'twenty': 20
                                        }
                                        if order_num in word_to_num:
                                            order_id = word_to_num[order_num]
                                        else:
                                            order_id = int(order_num)
                                        print(f"🔍 Found order ID {order_id} from: '{content}'")
                                        break
                            
                            if order_number or order_id:
                                break
                    
                    # Try to find by order number first (preferred)
                    if order_number:
                        order = Order.query.filter_by(order_number=order_number).first()
                        if order:
                            args['order_id'] = order.id
                            print(f"🔍 Found order by extracted number {order_number}: ID {order.id}")
                        else:
                            # If not found as order number, check if it's a reservation number
                            from models import Reservation
                            reservation = Reservation.query.filter_by(reservation_number=order_number).first()
                            if reservation:
                                print(f"🔍 Number {order_number} is a reservation number, looking for associated orders")
                                # Find orders associated with this reservation
                                reservation_orders = Order.query.filter_by(reservation_id=reservation.id).all()
                                if reservation_orders:
                                    # Show all orders for this reservation
                                    message = f"Found {len(reservation_orders)} order(s) for reservation #{order_number} ({reservation.name}):\n\n"
                                    for order in reservation_orders:
                                        # Convert target time to 12-hour format
                                        if order.target_time:
                                            time_obj = datetime.strptime(order.target_time, '%H:%M')
                                            time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                                        else:
                                            time_12hr = "Not specified"
                                        
                                        status_messages = {
                                            'pending': 'Order is pending and will be started soon.',
                                            'preparing': 'Order is currently being prepared in the kitchen.',
                                            'ready': f'Order is ready for {order.order_type}!',
                                            'completed': 'Order has been completed.'
                                        }
                                        
                                        message += f"🍽️ Order #{order.order_number} for {order.person_name}\n"
                                        message += f"   Status: {order.status.title()}\n"
                                        message += f"   {status_messages.get(order.status, 'Status unknown')}\n"
                                        message += f"   Scheduled for: {time_12hr} on {order.target_date}\n"
                                        message += f"   Total: ${order.total_amount:.2f}\n"
                                        message += f"   Payment: {order.payment_status.title()}\n\n"
                                    
                                    return SwaigFunctionResult(message.strip())
                                else:
                                    return SwaigFunctionResult(f"Reservation #{order_number} found for {reservation.name}, but no orders have been placed yet. Would you like to place an order?")
                            else:
                                return SwaigFunctionResult(f"Order number {order_number} not found.")
                    elif order_id:
                        args['order_id'] = order_id
                
                # If still no order ID found and no reservation ID, try to find by caller phone
                if not args.get('order_id') and not args.get('reservation_id'):
                    caller_phone = None
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
                        # Find the most recent order for this phone number
                        recent_order = Order.query.filter(
                            Order.customer_phone.like(f"%{caller_phone}%")
                        ).order_by(Order.created_at.desc()).first()
                        
                        if recent_order:
                            args['order_id'] = recent_order.id
                            print(f"🔍 Found recent order {recent_order.id} for caller {caller_phone}")
                
                # If still no order ID, show recent orders
                if not args.get('order_id') and not args.get('reservation_id'):
                    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
                    if not recent_orders:
                        return SwaigFunctionResult("No orders found in the system.")
                    
                    message = f"Here are the {len(recent_orders)} most recent orders:\n"
                    for order in recent_orders:
                        message += f"• Order #{order.order_number} - {order.person_name} - Status: {order.status}\n"
                    return SwaigFunctionResult(message)
                
                if args.get('order_id'):
                    order = Order.query.get(args['order_id'])
                elif args.get('reservation_id'):
                    order = Order.query.filter_by(reservation_id=args['reservation_id']).order_by(Order.created_at.desc()).first()
                else:
                    return SwaigFunctionResult("Please provide either an order ID or reservation ID to check order status.")
                
                if not order:
                    return SwaigFunctionResult("I couldn't find that order. Please check the order ID or phone number.")
                
                # Convert target time to 12-hour format
                if order.target_time:
                    time_obj = datetime.strptime(order.target_time, '%H:%M')
                    time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                else:
                    time_12hr = "Not specified"
                
                status_messages = {
                    'pending': 'Your order is pending and will be started soon.',
                    'preparing': 'Your order is currently being prepared in the kitchen.',
                    'ready': f'Your order is ready for {order.order_type}!',
                    'completed': 'Your order has been completed.'
                }
                
                message = f"Order #{order.order_number} for {order.person_name}\n"
                message += f"Status: {order.status.title()}\n"
                message += f"{status_messages.get(order.status, 'Status unknown')}\n"
                message += f"Scheduled for: {time_12hr} on {order.target_date}\n"
                message += f"Total: ${order.total_amount:.2f}\n"
                message += f"Type: {order.order_type.title() if order.order_type else 'Not specified'}"
                
                if order.order_type == 'delivery' and order.customer_address:
                    message += f"\nDelivery address: {order.customer_address}"
                
                return SwaigFunctionResult(message)
                
        except Exception as e:
            return SwaigFunctionResult(f"Sorry, there was an error checking your order status: {str(e)}")
    
    def _update_order_status_handler(self, args, raw_data):
        """Handler for update_order_status tool"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import db, Order
            
            with app.app_context():
                # First check if order_number is provided
                if args.get('order_number'):
                    order = Order.query.filter_by(order_number=args['order_number']).first()
                    if order:
                        args['order_id'] = order.id
                        print(f"🔍 Found order by number {args['order_number']}: ID {order.id}")
                    else:
                        return SwaigFunctionResult(f"Order number {args['order_number']} not found.")
                elif not args.get('order_id'):
                    # Try to extract from conversation
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    
                    import re
                    order_number = None
                    order_id = None
                    
                    for entry in call_log:
                        if entry.get('content'):
                            content = entry['content'].lower()
                            
                            # Look for 6-digit order numbers first (be more specific)
                            order_number_patterns = [
                                r'order number\s+is\s+(\d{6})',
                                r'order\s+(\d{6})',
                                r'order\s+number\s+(\d{6})',
                                # Removed overly broad patterns that match any 6-digit number
                            ]
                            
                            for pattern in order_number_patterns:
                                match = re.search(pattern, content)
                                if match:
                                    order_number = match.group(1)
                                    break
                            
                            # If no 6-digit number, try order IDs
                            if not order_number:
                                order_id_patterns = [
                                    r'order\s+(?:number\s+)?(\d+)',
                                    r'update\s+order\s+(\d+)',
                                    r'#(\d+)'
                                ]
                                
                                for pattern in order_id_patterns:
                                    match = re.search(pattern, content)
                                    if match:
                                        order_id = int(match.group(1))
                                        break
                            
                            if order_number or order_id:
                                break
                    
                    if order_number:
                        order = Order.query.filter_by(order_number=order_number).first()
                        if order:
                            args['order_id'] = order.id
                        else:
                            return SwaigFunctionResult(f"Order number {order_number} not found.")
                    elif order_id:
                        args['order_id'] = order_id
                    else:
                        return SwaigFunctionResult("I need an order number or order ID to update the status. Please provide the order number or say something like 'Update order 123456 status to ready'.")
                
                # Check for status parameter
                if not args.get('status'):
                    return SwaigFunctionResult("I need to know what status to update the order to. Please specify the new status (pending, preparing, ready, completed, cancelled).")
                
                order = Order.query.get(args['order_id'])
                
                if not order:
                    return SwaigFunctionResult(f"Order #{args['order_id']} not found.")
                
                valid_statuses = ['pending', 'preparing', 'ready', 'completed', 'cancelled']
                new_status = args['status'].lower()
                
                if new_status not in valid_statuses:
                    return SwaigFunctionResult(f"Invalid status. Valid statuses are: {', '.join(valid_statuses)}")
                
                # Check if order can be modified based on current status
                current_status = order.status.lower()
                
                # Define which status transitions are allowed
                allowed_transitions = {
                    'pending': ['preparing', 'cancelled'],  # Pending orders can only go to preparing or be cancelled
                    'preparing': ['ready', 'cancelled'],    # Preparing orders can only go to ready or be cancelled
                    'ready': ['completed', 'cancelled'],    # Ready orders can only be completed or cancelled
                    'completed': [],                        # Completed orders cannot be changed
                    'cancelled': []                         # Cancelled orders cannot be changed
                }
                
                if new_status not in allowed_transitions.get(current_status, []):
                    if current_status in ['completed', 'cancelled']:
                        return SwaigFunctionResult(f"Order #{order.id} is {current_status} and cannot be modified.")
                    else:
                        valid_next = ', '.join(allowed_transitions.get(current_status, []))
                        return SwaigFunctionResult(f"Order #{order.id} is currently {current_status}. It can only be updated to: {valid_next}")
                
                old_status = order.status
                order.status = new_status
                db.session.commit()
                
                return SwaigFunctionResult(f"Order #{order.order_number} status updated from {old_status} to {new_status}.")
                
        except Exception as e:
            return SwaigFunctionResult(f"Sorry, there was an error updating the order status: {str(e)}")
    
    def _update_pending_order_handler(self, args, raw_data):
        """Handler for update_pending_order tool - modify items in pending orders only"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import db, Order, OrderItem, MenuItem
            
            with app.app_context():
                # Try to extract information from conversation if not provided in args
                if not args.get('order_id') or not args.get('action') or not args.get('items'):
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    
                    # Extract order ID from conversation
                    if not args.get('order_id'):
                        import re
                        for entry in call_log:
                            if entry.get('content'):
                                content = entry['content'].lower()
                                # Look for order number mentions in both user and assistant messages
                                order_patterns = [
                                    r'order\s+(?:number\s+)?(\d+)',
                                    r'order\s+(?:number\s+)?(nineteen|eighteen|seventeen|sixteen|fifteen|fourteen|thirteen|twelve|eleven|ten|nine|eight|seven|six|five|four|three|two|one)',
                                    r'(?:to\s+)?order\s+(\d+)',
                                    r'#(\d+)'
                                ]
                                
                                for pattern in order_patterns:
                                    order_match = re.search(pattern, content)
                                    if order_match:
                                        order_num = order_match.group(1)
                                        # Convert word numbers to digits
                                        word_to_num = {
                                            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
                                            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
                                            'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14,
                                            'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18,
                                            'nineteen': 19, 'twenty': 20
                                        }
                                        if order_num in word_to_num:
                                            args['order_id'] = word_to_num[order_num]
                                        else:
                                            args['order_id'] = int(order_num)
                                        print(f"🔍 Found order ID {args['order_id']} from: '{content}'")
                                        break
                                if args.get('order_id'):
                                    break
                    
                    # Extract action and items from conversation
                    if not args.get('action') or not args.get('items'):
                        for entry in call_log:
                            if entry.get('role') == 'user' and entry.get('content'):
                                content = entry['content'].lower()
                                
                                # Detect add action
                                if any(phrase in content for phrase in ['add', 'include', 'also get', 'also want']):
                                    args['action'] = 'add'
                                    
                                    # Extract items to add
                                    items = []
                                    if 'pepsi' in content:
                                        items.append({'name': 'Pepsi', 'quantity': 1})
                                    elif 'coke' in content:
                                        items.append({'name': 'Coke', 'quantity': 1})
                                    elif 'buffalo wings' in content:
                                        items.append({'name': 'Buffalo Wings', 'quantity': 1})
                                    elif 'cheesecake' in content:
                                        items.append({'name': 'Cheesecake', 'quantity': 1})
                                    elif 'salmon' in content:
                                        items.append({'name': 'Grilled Salmon', 'quantity': 1})
                                    
                                    if items:
                                        args['items'] = items
                                        print(f"🔄 Extracted from conversation: action={args['action']}, items={items}")
                                        break
                                
                                # Detect remove action
                                elif any(phrase in content for phrase in ['remove', 'take off', 'cancel', 'delete']):
                                    args['action'] = 'remove'
                                    # Similar item extraction logic for removal
                
                # If we still don't have order_id but we have caller phone, try to find the most recent pending order
                if not args.get('order_id') and raw_data.get('caller_id_number'):
                    caller_phone = raw_data['caller_id_number']
                    recent_order = Order.query.filter_by(
                        customer_phone=caller_phone,
                        status='pending'
                    ).order_by(Order.id.desc()).first()
                    
                    if recent_order:
                        args['order_id'] = recent_order.id
                        print(f"🔍 Found recent pending order {recent_order.id} for caller {caller_phone}")
                
                # Auto-fill customer phone from caller ID if not provided
                if not args.get('customer_phone') and raw_data.get('caller_id_number'):
                    args['customer_phone'] = raw_data['caller_id_number']
                
                # Check for required parameters after extraction
                action = args.get('action', '').lower()
                
                # Different required fields based on action
                if action == 'update_info':
                    required_fields = ['order_id', 'action']
                else:
                    required_fields = ['order_id', 'action', 'items']
                
                missing_fields = [field for field in required_fields if not args.get(field)]
                
                if missing_fields:
                    missing_text = ", ".join(missing_fields)
                    if action == 'update_info':
                        return SwaigFunctionResult(f"I need some more information to update the order. Please provide: {missing_text}. For example, say 'Update order 19 name to John Smith' or 'Change order 19 to delivery'.")
                    else:
                        return SwaigFunctionResult(f"I need some more information to update the order. Please provide: {missing_text}. For example, say 'Add a Pepsi to order 19' or 'Remove the salad from order 15'.")
                
                order = Order.query.get(args['order_id'])
                
                if not order:
                    return SwaigFunctionResult(f"Order #{args['order_id']} not found.")
                
                # Verify customer phone if provided (but skip verification for update_info action)
                if args.get('customer_phone') and action != 'update_info':
                    if order.customer_phone != args['customer_phone']:
                        return SwaigFunctionResult(f"Phone number doesn't match the order. Please verify your information.")
                
                # Check if order is still pending
                if order.status.lower() != 'pending':
                    return SwaigFunctionResult(f"Order #{order.id} is currently {order.status} and cannot be modified. Only pending orders can be changed.")
                
                action = args['action'].lower()
                items_to_process = args.get('items', [])
                
                if action == 'add':
                    # Add new items to the order
                    added_items = []
                    total_added = 0
                    
                    for item_data in items_to_process:
                        menu_item = MenuItem.query.filter_by(name=item_data['name'], is_available=True).first()
                        if not menu_item:
                            return SwaigFunctionResult(f"Sorry, '{item_data['name']}' is not available on our menu.")
                        
                        quantity = item_data.get('quantity', 1)
                        
                        # Check if item already exists in order
                        existing_item = OrderItem.query.filter_by(
                            order_id=order.id,
                            menu_item_id=menu_item.id
                        ).first()
                        
                        if existing_item:
                            existing_item.quantity += quantity
                        else:
                            new_order_item = OrderItem(
                                order_id=order.id,
                                menu_item_id=menu_item.id,
                                quantity=quantity,
                                price_at_time=menu_item.price
                            )
                            db.session.add(new_order_item)
                        
                        added_items.append(f"{quantity}x {menu_item.name}")
                        total_added += menu_item.price * quantity
                    
                    # Update order total
                    order.total_amount += total_added
                    db.session.commit()
                    
                    return SwaigFunctionResult(f"Added {', '.join(added_items)} to order #{order.id}. Additional cost: ${total_added:.2f}. New total: ${order.total_amount:.2f}")
                
                elif action == 'remove':
                    # Remove items from the order
                    removed_items = []
                    total_removed = 0
                    
                    for item_data in items_to_process:
                        menu_item = MenuItem.query.filter_by(name=item_data['name']).first()
                        if not menu_item:
                            continue
                        
                        order_item = OrderItem.query.filter_by(
                            order_id=order.id,
                            menu_item_id=menu_item.id
                        ).first()
                        
                        if order_item:
                            removed_items.append(f"{order_item.quantity}x {menu_item.name}")
                            total_removed += order_item.price_at_time * order_item.quantity
                            db.session.delete(order_item)
                    
                    if not removed_items:
                        return SwaigFunctionResult(f"None of the specified items were found in order #{order.id}.")
                    
                    # Update order total
                    order.total_amount -= total_removed
                    if order.total_amount < 0:
                        order.total_amount = 0
                    
                    db.session.commit()
                    
                    return SwaigFunctionResult(f"Removed {', '.join(removed_items)} from order #{order.id}. Refund: ${total_removed:.2f}. New total: ${order.total_amount:.2f}")
                
                elif action == 'change_quantity':
                    # Change quantity of existing items
                    changed_items = []
                    total_change = 0
                    
                    for item_data in items_to_process:
                        menu_item = MenuItem.query.filter_by(name=item_data['name']).first()
                        if not menu_item:
                            continue
                        
                        new_quantity = item_data.get('quantity', 1)
                        
                        order_item = OrderItem.query.filter_by(
                            order_id=order.id,
                            menu_item_id=menu_item.id
                        ).first()
                        
                        if order_item:
                            old_quantity = order_item.quantity
                            quantity_diff = new_quantity - old_quantity
                            price_diff = order_item.price_at_time * quantity_diff
                            
                            if new_quantity <= 0:
                                # Remove item if quantity is 0 or negative
                                changed_items.append(f"Removed {menu_item.name}")
                                total_change -= order_item.price_at_time * old_quantity
                                db.session.delete(order_item)
                            else:
                                order_item.quantity = new_quantity
                                changed_items.append(f"Changed {menu_item.name} from {old_quantity} to {new_quantity}")
                                total_change += price_diff
                    
                    if not changed_items:
                        return SwaigFunctionResult(f"None of the specified items were found in order #{order.id}.")
                    
                    # Update order total
                    order.total_amount += total_change
                    if order.total_amount < 0:
                        order.total_amount = 0
                    
                    db.session.commit()
                    
                    change_text = f"${abs(total_change):.2f} {'added' if total_change >= 0 else 'refunded'}"
                    return SwaigFunctionResult(f"Updated order #{order.id}: {', '.join(changed_items)}. {change_text}. New total: ${order.total_amount:.2f}")
                
                elif action == 'update_info':
                    # Update order information fields
                    updated_fields = []
                    
                    # Update customer name
                    if args.get('person_name'):
                        old_name = order.person_name
                        order.person_name = args['person_name']
                        updated_fields.append(f"customer name from '{old_name}' to '{args['person_name']}'")
                    
                    # Update customer phone
                    if args.get('customer_phone') and args['customer_phone'] != order.customer_phone:
                        # Normalize the new phone number
                        normalized_phone = self._normalize_phone_number(args['customer_phone'])
                        old_phone = order.customer_phone
                        order.customer_phone = normalized_phone
                        updated_fields.append(f"phone number from '{old_phone}' to '{normalized_phone}'")
                    
                    # Update target date
                    if args.get('target_date'):
                        # Validate date format
                        try:
                            from datetime import datetime
                            datetime.strptime(args['target_date'], '%Y-%m-%d')
                            old_date = order.target_date
                            order.target_date = args['target_date']
                            updated_fields.append(f"order date from '{old_date}' to '{args['target_date']}'")
                        except ValueError:
                            return SwaigFunctionResult(f"Invalid date format '{args['target_date']}'. Please use YYYY-MM-DD format.")
                    
                    # Update target time
                    if args.get('target_time'):
                        # Validate time format
                        try:
                            from datetime import datetime
                            datetime.strptime(args['target_time'], '%H:%M')
                            old_time = order.target_time
                            order.target_time = args['target_time']
                            updated_fields.append(f"order time from '{old_time}' to '{args['target_time']}'")
                        except ValueError:
                            return SwaigFunctionResult(f"Invalid time format '{args['target_time']}'. Please use HH:MM format (24-hour).")
                    
                    # Update order type
                    if args.get('order_type'):
                        old_type = order.order_type
                        order.order_type = args['order_type']
                        updated_fields.append(f"order type from '{old_type}' to '{args['order_type']}'")
                        
                        # If changing to delivery, require address
                        if args['order_type'] == 'delivery' and not args.get('customer_address') and not order.customer_address:
                            return SwaigFunctionResult("Delivery address is required for delivery orders. Please provide a customer_address.")
                    
                    # Update customer address
                    if args.get('customer_address'):
                        old_address = order.customer_address or "none"
                        order.customer_address = args['customer_address']
                        updated_fields.append(f"delivery address from '{old_address}' to '{args['customer_address']}'")
                    
                    # Update special instructions
                    if args.get('special_instructions'):
                        old_instructions = order.special_instructions or "none"
                        order.special_instructions = args['special_instructions']
                        updated_fields.append(f"special instructions from '{old_instructions}' to '{args['special_instructions']}'")
                    
                    if not updated_fields:
                        return SwaigFunctionResult(f"No fields were provided to update for order #{order.id}. Please specify what you'd like to change.")
                    
                    db.session.commit()
                    
                    return SwaigFunctionResult(f"Updated order #{order.id}: {', '.join(updated_fields)}.")
                
                else:
                    return SwaigFunctionResult(f"Invalid action '{action}'. Valid actions are: add, remove, change_quantity, update_info")
                
        except Exception as e:
            return SwaigFunctionResult(f"Sorry, there was an error updating the order: {str(e)}")
    
    def _get_kitchen_orders_handler(self, args, raw_data):
        """Handler for get_kitchen_orders tool"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import db, Order, OrderItem
            
            with app.app_context():
                # Set default filters
                filter_date = args.get('date', datetime.now().strftime('%Y-%m-%d'))
                start_time = args.get('start_time', '00:00')
                end_time = args.get('end_time', '23:59')
                status_filter = args.get('status', 'all')
                
                # Build query
                query = Order.query.filter(
                    Order.target_date == filter_date,
                    Order.target_time >= start_time,
                    Order.target_time <= end_time
                )
                
                if status_filter != 'all':
                    query = query.filter(Order.status == status_filter)
                
                orders = query.order_by(Order.target_time).all()
                
                format_type = args.get('format', 'text')
                
                if format_type == 'json':
                    # Return structured data for kitchen dashboard
                    orders_data = []
                    for order in orders:
                        # Only include essential info: order number, name, phone
                        customer_info = order.person_name if order.person_name else order.customer_phone
                        orders_data.append({
                            'order_id': order.id,
                            'customer_info': customer_info,
                            'target_time': order.target_time
                        })
                    
                    return SwaigFunctionResult(
                        f"Found {len(orders)} kitchen orders for {filter_date}",
                        data={
                            'orders': orders_data,
                            'total_count': len(orders)
                        }
                    )
                
                else:
                    # Return text format for voice
                    if not orders:
                        filter_text = f"for {filter_date}"
                        if status_filter != 'all':
                            filter_text += f" with status '{status_filter}'"
                        return SwaigFunctionResult(f"No kitchen orders found {filter_text}.")
                    
                    # Format date nicely
                    date_obj = datetime.strptime(filter_date, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%A, %B %d, %Y')
                    
                    response = f"🍳 Kitchen Orders for {formatted_date}:\n\n"
                    
                    if status_filter != 'all':
                        response += f"Showing {status_filter} orders only\n\n"
                    
                    for order in orders:
                        # Convert time to 12-hour format
                        time_obj = datetime.strptime(order.target_time, '%H:%M')
                        time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                        
                        # Extract first/last name or use phone if name not available
                        customer_info = order.person_name if order.person_name else order.customer_phone
                        
                        response += f"🕐 {time_12hr} - Order #{order.id} - {customer_info}\n"
                    
                    return SwaigFunctionResult(response.strip())
                
        except Exception as e:
            return SwaigFunctionResult(f"Error retrieving kitchen orders: {str(e)}")
    
    def _get_order_queue_handler(self, args, raw_data):
        """Handler for get_order_queue tool"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import db, Order
            
            with app.app_context():
                # Get target date (default to today)
                target_date = args.get('date', datetime.now().strftime('%Y-%m-%d'))
                
                # Query orders by status for the target date
                base_query = Order.query.filter_by(target_date=target_date)
                
                pending_orders = base_query.filter_by(status='pending').order_by(Order.target_time).all()
                preparing_orders = base_query.filter_by(status='preparing').order_by(Order.target_time).all()
                ready_orders = base_query.filter_by(status='ready').order_by(Order.target_time).all()
                
                format_type = args.get('format', 'text')
                
                if format_type == 'json':
                    return SwaigFunctionResult(
                        f"Order queue for {target_date}",
                        data={
                            'date': target_date,
                            'pending': [order.to_dict() for order in pending_orders],
                            'preparing': [order.to_dict() for order in preparing_orders],
                            'ready': [order.to_dict() for order in ready_orders],
                            'counts': {
                                'pending': len(pending_orders),
                                'preparing': len(preparing_orders),
                                'ready': len(ready_orders),
                                'total': len(pending_orders) + len(preparing_orders) + len(ready_orders)
                            }
                        }
                    )
                
                else:
                    # Return text format for voice
                    date_obj = datetime.strptime(target_date, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%A, %B %d, %Y')
                    
                    total_orders = len(pending_orders) + len(preparing_orders) + len(ready_orders)
                    
                    if total_orders == 0:
                        return SwaigFunctionResult(f"No orders in the queue for {formatted_date}.")
                    
                    response = f"🍳 Kitchen Order Queue for {formatted_date}:\n\n"
                    response += f"📊 Summary: {total_orders} total orders\n"
                    response += f"   • Pending: {len(pending_orders)}\n"
                    response += f"   • Preparing: {len(preparing_orders)}\n"
                    response += f"   • Ready: {len(ready_orders)}\n\n"
                    
                    # Pending orders
                    if pending_orders:
                        response += f"⏳ PENDING ORDERS ({len(pending_orders)}):\n"
                        for order in pending_orders:
                            time_obj = datetime.strptime(order.target_time, '%H:%M')
                            time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                            customer_info = order.person_name if order.person_name else order.customer_phone
                            response += f"   • Order #{order.id} - {customer_info} - {time_12hr}\n"
                        response += "\n"
                    
                    # Preparing orders
                    if preparing_orders:
                        response += f"👨‍🍳 PREPARING ORDERS ({len(preparing_orders)}):\n"
                        for order in preparing_orders:
                            time_obj = datetime.strptime(order.target_time, '%H:%M')
                            time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                            customer_info = order.person_name if order.person_name else order.customer_phone
                            response += f"   • Order #{order.id} - {customer_info} - {time_12hr}\n"
                        response += "\n"
                    
                    # Ready orders
                    if ready_orders:
                        response += f"✅ READY ORDERS ({len(ready_orders)}):\n"
                        for order in ready_orders:
                            time_obj = datetime.strptime(order.target_time, '%H:%M')
                            time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
                            customer_info = order.person_name if order.person_name else order.customer_phone
                            response += f"   • Order #{order.id} - {customer_info} - {time_12hr}\n"
                    
                    return SwaigFunctionResult(response.strip())
                
        except Exception as e:
            return SwaigFunctionResult(f"Error retrieving order queue: {str(e)}")
    
    def _get_kitchen_summary_handler(self, args, raw_data):
        """Handler for get_kitchen_summary tool"""
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
            from models import db, Order, OrderItem
            
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
                
                # Query orders in range
                orders = Order.query.filter(
                    Order.target_date >= start_date,
                    Order.target_date <= end_date
                ).all()
                
                format_type = args.get('format', 'text')
                
                # Calculate summary statistics
                total_orders = len(orders)
                total_revenue = sum(order.total_amount or 0 for order in orders)
                
                # Status distribution
                status_counts = defaultdict(int)
                order_type_counts = defaultdict(int)
                hourly_distribution = defaultdict(int)
                
                # Popular items
                item_counts = defaultdict(int)
                
                for order in orders:
                    status_counts[order.status] += 1
                    order_type_counts[order.order_type] += 1
                    
                    # Group by hour
                    try:
                        hour = int(order.target_time.split(':')[0])
                        time_period = f"{hour}:00"
                        hourly_distribution[time_period] += 1
                    except (ValueError, AttributeError):
                        pass
                    
                    # Count items
                    for item in order.items:
                        if item.menu_item:
                            item_counts[item.menu_item.name] += item.quantity
                
                if format_type == 'json':
                    # Get top 5 popular items
                    popular_items = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                    
                    summary_data = {
                        'date_range': {'start': start_date, 'end': end_date},
                        'total_orders': total_orders,
                        'total_revenue': round(total_revenue, 2),
                        'average_order_value': round(total_revenue / total_orders, 2) if total_orders > 0 else 0,
                        'status_distribution': dict(status_counts),
                        'order_type_distribution': dict(order_type_counts),
                        'hourly_distribution': dict(hourly_distribution),
                        'popular_items': [{'name': name, 'count': count} for name, count in popular_items],
                        'orders': [order.to_dict() for order in orders]
                    }
                    return SwaigFunctionResult(f"Kitchen summary {date_range_text}", data=summary_data)
                
                else:
                    # Text format for voice
                    if total_orders == 0:
                        return SwaigFunctionResult(f"No kitchen orders found {date_range_text}.")
                    
                    avg_order_value = total_revenue / total_orders
                    
                    response = f"🍳 Kitchen Summary {date_range_text}:\n\n"
                    response += f"📈 Overview:\n"
                    response += f"  • Total orders: {total_orders}\n"
                    response += f"  • Total revenue: ${total_revenue:.2f}\n"
                    response += f"  • Average order value: ${avg_order_value:.2f}\n\n"
                    
                    if status_counts:
                        response += f"📊 Order Status:\n"
                        for status, count in sorted(status_counts.items()):
                            percentage = (count / total_orders) * 100
                            response += f"  • {status.title()}: {count} ({percentage:.1f}%)\n"
                        response += "\n"
                    
                    if order_type_counts:
                        response += f"📦 Order Types:\n"
                        for order_type, count in sorted(order_type_counts.items()):
                            percentage = (count / total_orders) * 100
                            response += f"  • {order_type.title()}: {count} ({percentage:.1f}%)\n"
                        response += "\n"
                    
                    if hourly_distribution:
                        response += f"🕐 Hourly Distribution:\n"
                        for time_slot in sorted(hourly_distribution.keys()):
                            count = hourly_distribution[time_slot]
                            # Convert to 12-hour format
                            hour = int(time_slot.split(':')[0])
                            time_12hr = datetime.strptime(time_slot, '%H:%M').strftime('%I:%M %p').lstrip('0')
                            response += f"  • {time_12hr}: {count} order{'s' if count != 1 else ''}\n"
                        response += "\n"
                    
                    if item_counts:
                        # Show top 5 popular items
                        popular_items = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                        response += f"🍽️ Popular Items:\n"
                        for i, (item_name, count) in enumerate(popular_items, 1):
                            response += f"  {i}. {item_name}: {count} ordered\n"
                    
                    return SwaigFunctionResult(response.strip())
                
        except Exception as e:
            return SwaigFunctionResult(f"Error generating kitchen summary: {str(e)}")
    
    def _process_reservation_payment(self, reservation, total_amount, caller_phone, raw_data):
        """Process payment for a reservation using SWML pay verb"""
        try:
            # Round total amount to 2 decimal places to avoid floating-point precision issues
            total_amount = round(total_amount, 2)
            
            print(f"💳 Processing reservation payment for #{reservation.reservation_number}")
            print(f"💰 Total amount: ${total_amount:.2f}")
            
            # Get payment connector URL from environment or auto-detect
            base_url = os.getenv('SIGNALWIRE_PAYMENT_CONNECTOR_URL')
            
            if base_url:
                # Use environment variable and ensure it has the correct endpoint
                if not base_url.endswith('/api/payment-processor'):
                    payment_connector_url = f"{base_url.rstrip('/')}/api/payment-processor"
                else:
                    payment_connector_url = base_url
            else:
                # Auto-detect payment connector URL
                if raw_data and 'global_data' in raw_data:
                    # Try to get host from request headers or global data
                    host = None
                    try:
                        from flask import request
                        if hasattr(request, 'headers'):
                            host = request.headers.get('Host')
                    except:
                        pass
                    
                    if host and 'ngrok' in host:
                        payment_connector_url = f"https://{host}/api/payment-processor"
                    else:
                        payment_connector_url = 'http://localhost:8080/api/payment-processor'
                else:
                    payment_connector_url = 'http://localhost:8080/api/payment-processor'
            
            print(f"🔗 Using payment connector URL: {payment_connector_url}")
            
            # Check for localhost warning
            if 'localhost' in payment_connector_url or '127.0.0.1' in payment_connector_url:
                print("⚠️ Using localhost payment connector URL - this won't work for real calls")
                print("   Make sure SIGNALWIRE_PAYMENT_CONNECTOR_URL is set to your ngrok URL")
            
            # Configure SWML pay verb for reservation payment
            result = SwaigFunctionResult(
                f"💳 Processing payment for Reservation #{reservation.reservation_number}\n"
                f"Customer: {reservation.name}\n"
                f"Amount: ${total_amount:.2f}\n\n"
                f"I'll now collect your credit card information securely."
            )
            
            # Configure SWML pay verb - always use payment connector approach
            # Add status URL for payment result callback
            status_url = payment_connector_url.replace('/api/payment-processor', '/api/signalwire/payment-callback')
            
            result = result.pay(
                payment_connector_url=payment_connector_url,
                status_url=status_url,
                input_method="dtmf",
                payment_method="credit-card",
                timeout=10,
                max_attempts=3,
                security_code=True,
                postal_code=True,
                min_postal_code_length=5,
                token_type="one-time",
                currency="usd",
                language="en-US",
                voice="woman",
                valid_card_types="visa mastercard amex discover",
                charge_amount=f"{total_amount:.2f}",
                description=f"Bobby's Table Reservation #{reservation.reservation_number}",
                parameters=[
                    {"name": "reservation_number", "value": reservation.reservation_number},
                    {"name": "customer_name", "value": reservation.name},
                    {"name": "phone_number", "value": caller_phone or reservation.phone_number},
                    {"name": "payment_type", "value": "reservation"}
                ] + ([{"name": "call_id", "value": raw_data.get('call_id')}] if raw_data and raw_data.get('call_id') and raw_data.get('call_id').strip() else [])
            )
            
            # Set metadata for payment tracking
            result.set_metadata({
                "payment_step": "collecting_payment",
                "payment_type": "reservation",
                "reservation_number": reservation.reservation_number,
                "amount": total_amount,
                "customer_name": reservation.name,
                "phone_number": caller_phone or reservation.phone_number
            })
            
            print(f"✅ Payment collection configured for ${total_amount} - Reservation #{reservation.reservation_number}")
            return result
            
        except Exception as e:
            print(f"❌ Error in _process_reservation_payment: {str(e)}")
            import traceback
            traceback.print_exc()
            
            result = SwaigFunctionResult(
                f"Sorry, there was an error processing your payment request: {str(e)}"
            )
            result.set_metadata({
                "payment_step": "error",
                "error": str(e)
            })
            return result

    def _pay_order_handler(self, args, raw_data):
        """Handler for pay_order tool"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import db, Order, Reservation
            from flask import current_app
            
            with app.app_context():
                # Extract meta_data for session management
                meta_data = raw_data.get('meta_data', {}) if raw_data else {}
                print(f"🔍 Current meta_data: {meta_data}")
                
                # Get call_id for payment session checking - raw_data is the full SWAIG request
                call_id = raw_data.get('call_id') if raw_data else None
                print(f"🔍 Call ID: {call_id}")
                print(f"🔍 Raw data keys: {list(raw_data.keys()) if raw_data else 'None'}")
                print(f"🔍 Raw data type: {type(raw_data)}")
                
                # Debug: Show first few keys to understand the structure
                if raw_data and isinstance(raw_data, dict):
                    print(f"🔍 First 10 raw_data keys: {list(raw_data.keys())[:10]}")
                    if 'call_id' in raw_data:
                        print(f"🔍 Found call_id in raw_data: {raw_data['call_id']}")
                    else:
                        print(f"🔍 call_id not found in raw_data, checking other possible keys...")
                        for key in ['ai_session_id', 'session_id', 'id']:
                            if key in raw_data:
                                print(f"   Found {key}: {raw_data[key]}")
                else:
                    print(f"🔍 raw_data is not a dict or is None")
                
                # Check if there's an active payment session - now passed from main app
                session_data = raw_data.get('_payment_session') if raw_data else None
                print(f"🔍 Payment session data from main app: {session_data}")
                
                if session_data and session_data.get('reservation_number'):
                    reservation_number = session_data.get('reservation_number')
                    print(f"🔍 Found active payment session for reservation {reservation_number}")
                    
                    # Get reservation details to provide context
                    reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
                    if reservation:
                        # IMPORTANT: Instead of redirecting, automatically proceed with reservation payment
                        print(f"✅ Auto-proceeding with reservation payment for #{reservation_number}")
                        
                        # Calculate total amount from associated orders
                        total_bill = sum(order.total_amount or 0 for order in reservation.orders)
                        
                        # Check if reservation has amount due
                        if not total_bill or total_bill <= 0:
                            result = SwaigFunctionResult(
                                f"Reservation #{reservation_number} for {reservation.name} has no amount due. "
                                "Please contact the restaurant if you believe this is an error."
                            )
                            result.set_metadata({
                                "payment_step": "no_amount_due",
                                "reservation_number": reservation_number
                            })
                            return result
                        
                        # Check if already paid
                        if reservation.payment_status == 'paid':
                            result = SwaigFunctionResult(
                                f"Reservation #{reservation_number} has already been paid. "
                                f"Your confirmation number is {reservation.confirmation_number}."
                            )
                            result.set_metadata({
                                "payment_step": "already_paid",
                                "reservation_number": reservation_number
                            })
                            return result
                        
                        # Get caller phone for payment processing
                        caller_phone = None
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
                        
                        # Normalize phone number
                        if caller_phone:
                            caller_phone = self._normalize_phone_number(caller_phone)
                            print(f"🔍 Using caller ID: {caller_phone}")
                        
                        # Proceed with payment collection for the reservation
                        return self._process_reservation_payment(
                            reservation=reservation,
                            total_amount=total_bill,
                            caller_phone=caller_phone,
                            raw_data=raw_data
                        )
                    else:
                        # Reservation not found, clear the session
                        print(f"🧹 Reservation {reservation_number} not found, continuing with order payment")
                
                if not session_data and call_id:
                    # Fallback: try to access payment sessions directly
                    try:
                        print(f"🔍 Fallback: Checking payment session for call_id: {call_id}")
                        current_app_instance = app._get_current_object() if hasattr(app, '_get_current_object') else app
                        
                        if hasattr(current_app_instance, 'payment_sessions'):
                            payment_sessions = current_app_instance.payment_sessions
                            print(f"🔍 Found payment_sessions with {len(payment_sessions)} active sessions")
                            
                            if call_id in payment_sessions:
                                session_data = payment_sessions[call_id]
                                print(f"✅ Found payment session data via fallback: {session_data}")
                            else:
                                print(f"❌ Call ID {call_id} not found in payment sessions")
                        else:
                            print(f"❌ No payment_sessions attribute found on app instance")
                            
                    except Exception as e:
                        print(f"❌ Error accessing payment session: {e}")
                        session_data = None
                    

                
                # Check if there's an active payment session for a reservation in meta_data (fallback)
                if meta_data.get('payment_session_active') and meta_data.get('verified_reservation'):
                    verified_reservation = meta_data.get('verified_reservation')
                    reservation_number = verified_reservation.get('reservation_number')
                    print(f"🔍 Found active payment session in meta_data for reservation {reservation_number}")
                    
                    # IMPORTANT: If there's an active payment session for a reservation,
                    # redirect to pay_reservation instead of trying to pay individual orders
                    result = SwaigFunctionResult(
                        f"I see you have an active payment session for reservation #{reservation_number}. "
                        f"Let me help you pay for that reservation instead. "
                        f"Please say 'pay reservation {reservation_number}' to continue with the reservation payment."
                    )
                    result.set_metadata({
                        "payment_step": "redirect_to_reservation",
                        "active_reservation_session": verified_reservation
                    })
                    return result
                
                # Get caller phone number from raw_data
                caller_phone = None
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
                
                print(f"🔍 pay_order called with caller_phone: {caller_phone}")
                print(f"🔍 pay_order args: {args}")
                
                # AUTO-DETECT: Check if this is for a newly created order from session metadata
                order_number = args.get('order_number')
                if not order_number:
                    # Check meta_data for recently created order
                    order_created = meta_data.get('order_created')
                    session_order_number = meta_data.get('order_number')
                    
                    if order_created and session_order_number:
                        order_number = session_order_number
                        print(f"🔍 Auto-detected new order from session: #{order_number}")
                    else:
                        # Try to detect from conversation history
                        call_log = raw_data.get('call_log', []) if raw_data else []
                        for entry in reversed(call_log[-10:]):  # Check last 10 entries
                            if (entry.get('role') == 'assistant' and 
                                entry.get('content') and 
                                'order confirmed' in entry.get('content', '').lower()):
                                
                                # Try to extract order number from the assistant's message
                                import re
                                content = entry.get('content', '')
                                order_match = re.search(r'Order #(\d{6})', content)
                                if order_match:
                                    order_number = order_match.group(1)
                                    print(f"🔍 Auto-detected order from conversation: #{order_number}")
                                    break
                
                # Check if we already have verified order data in meta_data
                verified_order = meta_data.get('verified_order')
                if verified_order:
                    print(f"✅ Using verified order from meta_data: {verified_order}")
                    order_id = verified_order.get('order_id')
                    order = Order.query.get(order_id) if order_id else None
                    if order:
                        print(f"🔍 Found verified order: Order #{order.order_number}")
                    else:
                        # Clear invalid meta_data
                        result = SwaigFunctionResult("I need to verify your order information again.")
                        result.set_metadata({})
                        return result
                else:
                    # Find the order
                    order = None
                    
                    # Try to find by order number first (preferred)
                    if order_number:
                        order = Order.query.filter_by(order_number=order_number).first()
                        if order:
                            print(f"🔍 Found order by number {order_number}: ID {order.id}")
                        else:
                            result = SwaigFunctionResult(f"Order number {order_number} not found.")
                            result.set_metadata({
                                "payment_step": "error",
                                "error": "order_not_found"
                            })
                            return result
                    
                    # Try to find by order ID
                    elif args.get('order_id'):
                        order = Order.query.get(args['order_id'])
                        if order:
                            print(f"🔍 Found order by ID {args['order_id']}")
                        else:
                            result = SwaigFunctionResult(f"Order ID {args['order_id']} not found.")
                            result.set_metadata({
                                "payment_step": "error",
                                "error": "order_not_found"
                            })
                            return result
                    
                    # Try to extract order number from conversation if not provided
                    elif raw_data and 'call_log' in raw_data:
                        order_number = self._extract_order_number_from_conversation(raw_data['call_log'])
                        
                        # Try to find by extracted order number
                        if order_number:
                            order = Order.query.filter_by(order_number=order_number).first()
                            if order:
                                print(f"🔍 Found order by extracted number {order_number}: ID {order.id}")
                            else:
                                result = SwaigFunctionResult(f"Order number {order_number} not found.")
                                result.set_metadata({
                                    "payment_step": "error",
                                    "error": "order_not_found"
                                })
                                return result
                    
                    # If still no order found, try to find by phone number matching as fallback
                    if not order and caller_phone:
                        print(f"🔍 No order found by number/ID, searching by phone number: {caller_phone}")
                        
                        # Normalize the caller phone for better matching
                        normalized_caller = self._normalize_phone_number(caller_phone)
                        print(f"🔍 Normalized caller phone: {normalized_caller}")
                        
                        # Try multiple phone number formats for matching
                        phone_patterns = [
                            caller_phone,  # Original format
                            normalized_caller,  # Normalized format
                            caller_phone.replace('+1', ''),  # Without +1
                            caller_phone.replace('+', ''),   # Without +
                            caller_phone[-10:] if len(caller_phone) >= 10 else caller_phone,  # Last 10 digits
                        ]
                        
                        # Remove duplicates while preserving order
                        phone_patterns = list(dict.fromkeys(phone_patterns))
                        print(f"🔍 Trying phone patterns: {phone_patterns}")
                        
                        recent_orders = []
                        for pattern in phone_patterns:
                            if pattern:
                                orders = Order.query.filter(
                                    Order.customer_phone.like(f"%{pattern}%"),
                                    Order.payment_status.in_(['unpaid', 'pending'])
                                ).order_by(Order.created_at.desc()).limit(3).all()
                                recent_orders.extend(orders)
                        
                        # Remove duplicates
                        seen_ids = set()
                        unique_orders = []
                        for order_obj in recent_orders:
                            if order_obj.id not in seen_ids:
                                unique_orders.append(order_obj)
                                seen_ids.add(order_obj.id)
                        
                        recent_orders = unique_orders[:3]  # Limit to 3
                        
                        print(f"🔍 Found {len(recent_orders)} orders by phone matching")
                        for order_obj in recent_orders:
                            print(f"   Order #{order_obj.order_number}: Phone={order_obj.customer_phone}, Status={order_obj.payment_status}")
                        
                        if len(recent_orders) == 1:
                            order = recent_orders[0]
                            print(f"🔍 Found single unpaid order for caller: Order #{order.order_number}")
                        elif len(recent_orders) > 1:
                            # Multiple orders found, ask user to specify
                            order_list = []
                            for o in recent_orders:
                                order_list.append(f"Order #{o.order_number} for ${o.total_amount:.2f}")
                            
                            result = SwaigFunctionResult(
                                f"I found {len(recent_orders)} unpaid orders for your phone number: {', '.join(order_list)}. "
                                f"Which order would you like to pay for? Please tell me the order number."
                            )
                            result.set_metadata({
                                "payment_step": "need_order_selection",
                                "available_orders": [{"order_number": o.order_number, "amount": o.total_amount} for o in recent_orders]
                            })
                            return result
                        else:
                            # No orders found - provide helpful message
                            print("🔍 No unpaid orders found for caller")
                            
                            # Check if there are any orders at all for this phone
                            all_orders_for_phone = []
                            for pattern in phone_patterns:
                                if pattern:
                                    orders = Order.query.filter(
                                        Order.customer_phone.like(f"%{pattern}%")
                                    ).all()
                                    all_orders_for_phone.extend(orders)
                            
                            if all_orders_for_phone:
                                result = SwaigFunctionResult(
                                    "I found orders for your phone number, but they are all already paid. "
                                    "If you have a new order to pay for, please provide the order number."
                                )
                            else:
                                result = SwaigFunctionResult(
                                    "I couldn't find any orders for your phone number. "
                                    "Could you please provide your order number?"
                                )
                            
                            result.set_metadata({
                                "payment_step": "need_order_number"
                            })
                            return result
                
                if not order:
                    result = SwaigFunctionResult(
                        "I need your order number to process payment. "
                        "Could you please provide your 6-digit order number?"
                    )
                    result.set_metadata({
                        "payment_step": "need_order_number"
                    })
                    return result
                
                # Verify customer name if provided
                if args.get('customer_name'):
                    if order.person_name and order.person_name.lower() != args['customer_name'].lower():
                        result = SwaigFunctionResult(
                            f"The name '{args['customer_name']}' doesn't match our records for order #{order.order_number}. "
                            f"Please verify the order number and customer name."
                        )
                        result.set_metadata({
                            "payment_step": "error",
                            "error": "name_mismatch"
                        })
                        return result
                
                # Check if order is already paid
                if order.payment_status == 'paid':
                    result = SwaigFunctionResult(
                        f"Order #{order.order_number} has already been paid. "
                        f"The payment amount was ${order.payment_amount:.2f}."
                    )
                    result.set_metadata({
                        "payment_step": "already_paid",
                        "order_number": order.order_number
                    })
                    return result
                
                # Check if order can be paid (not cancelled)
                if order.status == 'cancelled':
                    result = SwaigFunctionResult(
                        f"Order #{order.order_number} has been cancelled and cannot be paid."
                    )
                    result.set_metadata({
                        "payment_step": "error",
                        "error": "order_cancelled"
                    })
                    return result
                
                # Get payment amount
                payment_amount = order.total_amount or 0.0
                if payment_amount <= 0:
                    result = SwaigFunctionResult(
                        f"Order #{order.order_number} has no amount due. Please contact the restaurant for assistance."
                    )
                    result.set_metadata({
                        "payment_step": "error",
                        "error": "no_amount_due"
                    })
                    return result
                
                # Update order payment status to pending
                order.payment_status = 'pending'
                db.session.commit()
                
                # Use phone number from args or caller ID
                phone_number = args.get('phone_number') or caller_phone or order.customer_phone
                
                # Store verified order data in meta_data
                verified_data = {
                    "payment_step": "processing_payment",
                    "verified_order": {
                        "order_id": order.id,
                        "order_number": order.order_number,
                        "customer_name": order.person_name or "",
                        "phone_number": phone_number or "",
                        "total_amount": payment_amount
                    },
                    "payment_session_active": True
                }
                
                # Create payment confirmation message
                message = f"💳 Processing payment for Order #{order.order_number}\n"
                message += f"Customer: {order.person_name}\n"
                message += f"Amount: ${payment_amount:.2f}\n\n"
                message += f"I'll now collect your credit card information securely."
                
                # Create result with payment action
                result = SwaigFunctionResult(message)
                
                # Store session data in meta_data BEFORE payment collection
                result.set_metadata(verified_data)
                
                # Add payment collection using the pay verb
                import os
                
                # Get payment connector URL from environment or auto-detect
                base_url = os.getenv('SIGNALWIRE_PAYMENT_CONNECTOR_URL')
                
                if base_url:
                    # Use environment variable and ensure it has the correct endpoint
                    if not base_url.endswith('/api/payment-processor'):
                        payment_connector_url = f"{base_url.rstrip('/')}/api/payment-processor"
                    else:
                        payment_connector_url = base_url
                    print(f"🔗 Using payment connector URL from environment: {payment_connector_url}")
                else:
                    print("🔗 SIGNALWIRE_PAYMENT_CONNECTOR_URL not set, using auto-detection")
                    # Fallback to dynamic URL detection
                    try:
                        from flask import request
                        if request and request.headers.get('Host'):
                            host = request.headers.get('Host')
                            payment_connector_url = f"https://{host}/api/payment-processor"
                        else:
                            payment_connector_url = 'http://localhost:8080/api/payment-processor'
                    except:
                        payment_connector_url = 'http://localhost:8080/api/payment-processor'
                
                print(f"💳 Using payment connector URL: {payment_connector_url}")
                
                # Check if URL is localhost (will cause issues with SignalWire)
                if 'localhost' in payment_connector_url or '127.0.0.1' in payment_connector_url:
                    print("⚠️  WARNING: Payment connector URL is localhost - SignalWire won't be able to reach this!")
                    print("   Make sure SIGNALWIRE_PAYMENT_CONNECTOR_URL is set to your ngrok URL")
                
                # Use our payment processor endpoint (which handles Stripe integration internally)
                result = result.pay(
                    payment_connector_url=payment_connector_url,
                    status_url=f"{payment_connector_url.replace('/api/payment-processor', '/api/signalwire/payment-callback')}",
                    input_method="dtmf",
                    payment_method="credit-card",
                    timeout=10,
                    max_attempts=3,
                    security_code=True,
                    postal_code=True,
                    min_postal_code_length=5,
                    token_type="one-time",
                    charge_amount=f"{payment_amount:.2f}",
                    currency="usd",
                    language="en-US",
                    voice="woman",
                    description=f"Bobby's Table Order #{order.order_number}",
                    valid_card_types="visa mastercard amex discover",
                    prompts=[
                        {
                            "name": "card_number",
                            "text": "Please enter your 16-digit card number followed by the pound key."
                        },
                        {
                            "name": "expiration_date",
                            "text": "Please enter your card's expiration date as 4 digits, month and year, followed by the pound key."
                        },
                        {
                            "name": "security_code",
                            "text": "Please enter your 3 or 4 digit security code followed by the pound key."
                        },
                        {
                            "name": "postal_code",
                            "text": "Please enter your 5-digit ZIP code followed by the pound key."
                        }
                    ],
                    parameters=[
                        {"name": "order_id", "value": str(order.id)},
                        {"name": "order_number", "value": order.order_number},
                        {"name": "customer_name", "value": order.person_name or ""},
                        {"name": "phone_number", "value": phone_number or ""},
                        {"name": "payment_type", "value": "order"}
                    ] + ([{"name": "call_id", "value": raw_data.get('call_id')}] if raw_data and raw_data.get('call_id') and raw_data.get('call_id').strip() else [])
                )
                
                return result
                
        except Exception as e:
            result = SwaigFunctionResult(f"Sorry, there was an error processing your payment request: {str(e)}")
            result.set_metadata({
                "payment_step": "error",
                "error": str(e)
            })
            return result

    def _pay_for_order_handler(self, args, raw_data):
        """Handler for pay_for_order tool - uses meta_data from create_order"""
        try:
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import db, Order
            
            print(f"🔍 pay_for_order called with args: {args}")
            print(f"🔍 Raw data keys: {list(raw_data.keys()) if raw_data else 'None'}")
            
            # Get meta_data from raw_data
            meta_data = raw_data.get('meta_data', {}) if raw_data else {}
            print(f"🔍 Current meta_data: {meta_data}")
            
            # Check if we have order information in meta_data
            if not meta_data.get('order_id') and not meta_data.get('order_number'):
                return SwaigFunctionResult("I don't have the order information available. Please provide the order number you'd like to pay for.")
            
            # Get order information from meta_data
            order_id = meta_data.get('order_id')
            order_number = meta_data.get('order_number')
            order_total = meta_data.get('order_total') or meta_data.get('payment_amount', 0)
            customer_name = meta_data.get('customer_name')
            customer_phone = meta_data.get('customer_phone')
            
            print(f"🔍 Order info from meta_data:")
            print(f"   Order ID: {order_id}")
            print(f"   Order Number: {order_number}")
            print(f"   Total: ${order_total}")
            print(f"   Customer: {customer_name}")
            print(f"   Phone: {customer_phone}")
            
            # Verify customer name matches
            if args.get('customer_name') and customer_name:
                if args['customer_name'].lower() != customer_name.lower():
                    return SwaigFunctionResult(f"The customer name doesn't match the order. Please verify your information.")
            
            # Get cardholder name (use provided or default to customer name)
            cardholder_name = args.get('cardholder_name') or customer_name or args.get('customer_name')
            
            with app.app_context():
                # Verify order exists and get details
                order = None
                if order_id:
                    order = Order.query.get(order_id)
                elif order_number:
                    order = Order.query.filter_by(order_number=order_number).first()
                
                if not order:
                    return SwaigFunctionResult(f"Order not found. Please check the order number and try again.")
                
                # Check if order is already paid
                if order.payment_status == 'paid':
                    return SwaigFunctionResult(f"Order #{order.order_number} has already been paid. No additional payment is needed.")
                
                # Use order total from database if meta_data doesn't have it
                if not order_total:
                    order_total = order.total_amount
                
                # Round order total to 2 decimal places to avoid floating-point precision issues
                order_total = round(order_total, 2)
                
                # Check for affirmative response in conversation
                call_log = raw_data.get('call_log', []) if raw_data else []
                wants_to_pay = self._detect_affirmative_response(call_log, "payment")
                
                if not wants_to_pay:
                    # Ask for confirmation
                    message = f"I can process payment for your order #{order.order_number} totaling ${order_total:.2f}. "
                    message += f"Would you like to pay now with a credit card? Just say 'yes' or 'sure' and I'll collect your payment information."
                    return SwaigFunctionResult(message)
                
                # Process payment
                phone_number = customer_phone or raw_data.get('caller_id_number', '')
                
                # Normalize phone number
                if phone_number:
                    phone_number = self._normalize_phone_number(phone_number)
                
                # Create payment message
                message = f"Perfect! I'll process payment for order #{order.order_number} totaling ${order_total:.2f}. "
                message += f"Please have your credit card ready. I'll collect your card information now."
                
                # Create result with payment action
                result = SwaigFunctionResult(message)
                
                # Set meta_data for payment processing
                payment_meta_data = {
                    'order_id': order.id,
                    'order_number': order.order_number,
                    'customer_name': customer_name,
                    'customer_phone': phone_number,
                    'cardholder_name': cardholder_name,
                    'payment_amount': order_total,
                    'payment_type': 'order'
                }
                
                result = result.set_metadata(payment_meta_data)
                
                # Add payment collection using the pay verb
                import os
                
                # Get payment connector URL
                base_url = os.getenv('SIGNALWIRE_PAYMENT_CONNECTOR_URL')
                
                if base_url:
                    if not base_url.endswith('/api/payment-processor'):
                        payment_connector_url = f"{base_url.rstrip('/')}/api/payment-processor"
                    else:
                        payment_connector_url = base_url
                    print(f"🔗 Using payment connector URL from environment: {payment_connector_url}")
                else:
                    print("🔗 SIGNALWIRE_PAYMENT_CONNECTOR_URL not set, using auto-detection")
                    try:
                        from flask import request
                        if request and request.headers.get('Host'):
                            host = request.headers.get('Host')
                            payment_connector_url = f"https://{host}/api/payment-processor"
                        else:
                            payment_connector_url = 'http://localhost:8080/api/payment-processor'
                    except:
                        payment_connector_url = 'http://localhost:8080/api/payment-processor'
                
                print(f"🔗 Using payment connector URL: {payment_connector_url}")
                
                # Add payment collection
                status_url = payment_connector_url.replace('/api/payment-processor', '/api/signalwire/payment-callback')
                result = result.pay(
                    payment_connector_url=payment_connector_url,
                    status_url=status_url,
                    input_method="dtmf",
                    payment_method="credit-card",
                    timeout=10,
                    max_attempts=3,
                    security_code=True,
                    postal_code=True,
                    min_postal_code_length=5,
                    token_type="one-time",
                    charge_amount=f"{order_total:.2f}",
                    currency="usd",
                    language="en-US",
                    voice="woman",
                    description=f"Bobby's Table Order #{order.order_number}",
                    valid_card_types="visa mastercard amex discover",
                    prompts=[
                        {
                            "name": "card_number",
                            "text": "Please enter your 16-digit card number followed by the pound key."
                        },
                        {
                            "name": "expiration_date",
                            "text": "Please enter your card's expiration date as 4 digits, month and year, followed by the pound key."
                        },
                        {
                            "name": "security_code",
                            "text": "Please enter your 3 or 4 digit security code followed by the pound key."
                        },
                        {
                            "name": "postal_code",
                            "text": "Please enter your 5-digit ZIP code followed by the pound key."
                        }
                    ],
                    parameters=[
                        {"name": "order_id", "value": str(order.id)},
                        {"name": "order_number", "value": order.order_number},
                        {"name": "customer_name", "value": customer_name or ""},
                        {"name": "phone_number", "value": phone_number or ""},
                        {"name": "payment_type", "value": "order"}
                    ] + ([{"name": "call_id", "value": raw_data.get('call_id')}] if raw_data and raw_data.get('call_id') and raw_data.get('call_id').strip() else [])
                )
                
                return result
                
        except Exception as e:
            return SwaigFunctionResult(f"Sorry, there was an error processing your payment: {str(e)}")

    def _send_payment_receipt_handler(self, args, raw_data):
        """Send payment receipt SMS using SWML send_sms action"""
        try:
            from signalwire_agents.core.function_result import SwaigFunctionResult
            from models import Reservation

            # Extract parameters from args (args is a list of parsed arguments)
            if isinstance(args, list) and len(args) > 0:
                params = args[0]  # First element contains the parameters
            else:
                params = args
            
            reservation_number = params.get('reservation_number')
            phone_number = params.get('phone_number')
            amount = params.get('amount')
            confirmation_number = params.get('confirmation_number')

            print(f"📱 VERBOSE: Sending payment receipt SMS")
            print(f"   📋 Full args received: {json.dumps(args, indent=2) if args else 'None'}")
            print(f"   📋 Full raw_data received: {json.dumps(raw_data, indent=2) if raw_data else 'None'}")
            print(f"   📋 Extracted parameters:")
            print(f"      - Reservation: {reservation_number}")
            print(f"      - Phone: {phone_number}")
            print(f"      - Amount: ${amount}")
            print(f"      - Confirmation: {confirmation_number}")
            
            # Get reservation details
            reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
            if not reservation:
                return SwaigFunctionResult(f"Reservation {reservation_number} not found")
            
            # Convert time to 12-hour format for SMS
            try:
                time_obj = datetime.strptime(str(reservation.time), '%H:%M')
                time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
            except (ValueError, TypeError):
                time_12hr = str(reservation.time)
            
            # Build SMS body with proper escaping for SWML
            # Build SMS body (using normal line breaks - the SDK will handle SWML formatting)
            sms_body = f"💳 Bobby's Table Payment Receipt\n\n"
            sms_body += f"✅ Payment Successful!\n\n"
            sms_body += f"🎫 CONFIRMATION: {confirmation_number}\n\n"
            sms_body += f"Reservation Details:\n"
            sms_body += f"• Name: {reservation.name}\n"
            sms_body += f"• Date: {reservation.date}\n"
            sms_body += f"• Time: {time_12hr}\n"
            party_text = "person" if reservation.party_size == 1 else "people"
            sms_body += f"• Party Size: {reservation.party_size} {party_text}\n"
            sms_body += f"• Reservation #: {reservation.reservation_number}\n\n"
            sms_body += f"Payment Information:\n"
            sms_body += f"• Amount Paid: ${amount:.2f}\n"
            sms_body += f"• Payment Date: {datetime.now().strftime('%m/%d/%Y %I:%M %p')}\n\n"
            sms_body += f"Thank you for your payment!\n"
            sms_body += f"We look forward to serving you.\n\n"
            sms_body += f"Bobby's Table Restaurant\n"
            sms_body += f"Reply STOP to stop."
            
            # Get SignalWire phone number from environment
            import os
            signalwire_from_number = os.getenv('SIGNALWIRE_FROM_NUMBER', '+14126127565')
            
            print(f"📤 VERBOSE: Using SignalWire Agents SDK send_sms method")
            print(f"   📋 SMS Parameters:")
            print(f"      - From: {signalwire_from_number}")
            print(f"      - To: {phone_number}")
            print(f"      - Region: us")
            print(f"   📋 SMS Body (full):")
            print(f"      {repr(sms_body)}")
            print(f"   📋 SMS Body (formatted):")
            print(sms_body)
            
            # Use the updated SignalWire Agents SDK send_sms method
            result = SwaigFunctionResult()
            result = result.send_sms(
                to_number=phone_number,
                from_number=signalwire_from_number,
                body=sms_body,
                region="us"
            )
            
            # Set a response message
            result.set_response(f"📱 Payment receipt SMS will be sent to {phone_number} for reservation {reservation_number} with confirmation {confirmation_number}")
            
            print(f"✅ VERBOSE: SWML SMS action created successfully")
            print(f"   📋 Result type: {type(result)}")
            print(f"   📋 Result object: {result}")
            if hasattr(result, 'to_dict'):
                print(f"   📋 Result dict: {json.dumps(result.to_dict(), indent=2)}")
            
            return result
            
        except Exception as e:
            print(f"❌ Error creating SMS receipt: {e}")
            return SwaigFunctionResult(f"Failed to send SMS receipt: {str(e)}")

    def _payment_completed_handler(self, args, raw_data):
        """Handle payment completion and provide confirmation number to customer"""
        try:
            from signalwire_agents.core.function_result import SwaigFunctionResult
            
            payment_type = args.get('payment_type')
            confirmation_number = args.get('confirmation_number')
            amount = args.get('amount')
            reservation_number = args.get('reservation_number')
            order_number = args.get('order_number')
            
            print(f"🎉 Payment completed handler called")
            print(f"   Type: {payment_type}")
            print(f"   Confirmation: {confirmation_number}")
            print(f"   Amount: ${amount}")
            print(f"   Reservation: {reservation_number}")
            print(f"   Order: {order_number}")
            
            # Create appropriate response based on payment type
            if payment_type == 'reservation' and reservation_number:
                message = f"🎉 Great news! Your payment has been processed successfully!\n\n"
                message += f"💳 Payment Details:\n"
                message += f"• Amount: ${amount:.2f}\n"
                message += f"• Reservation: #{reservation_number}\n"
                message += f"• Confirmation Number: {confirmation_number}\n\n"
                message += f"📱 You'll receive an SMS receipt shortly with all the details.\n\n"
                message += f"Thank you for your payment! We look forward to serving you at Bobby's Table. "
                message += f"Is there anything else I can help you with today?"
                
            elif payment_type == 'order' and order_number:
                message = f"🎉 Excellent! Your payment has been processed successfully!\n\n"
                message += f"💳 Payment Details:\n"
                message += f"• Amount: ${amount:.2f}\n"
                message += f"• Order: #{order_number}\n"
                message += f"• Confirmation Number: {confirmation_number}\n\n"
                message += f"📱 You'll receive an SMS receipt with all the details.\n\n"
                message += f"Thank you for your order! We'll have it ready for you soon. "
                message += f"Is there anything else I can help you with?"
                
            else:
                # Generic payment completion message
                message = f"🎉 Payment processed successfully!\n\n"
                message += f"💳 Payment Details:\n"
                message += f"• Amount: ${amount:.2f}\n"
                message += f"• Confirmation Number: {confirmation_number}\n\n"
                message += f"Thank you for your payment! Is there anything else I can help you with today?"
            
            result = SwaigFunctionResult(message)
            
            # Set metadata to indicate payment is complete
            result.set_metadata({
                "payment_completed": True,
                "payment_type": payment_type,
                "confirmation_number": confirmation_number,
                "amount": amount,
                "reservation_number": reservation_number,
                "order_number": order_number
            })
            
            return result
            
        except Exception as e:
            print(f"❌ Error in payment completed handler: {e}")
            return SwaigFunctionResult(f"Payment was processed, but there was an error providing the details: {str(e)}")

    def _send_test_sms_handler(self, args, raw_data):
        """Send a test SMS message to verify SMS functionality"""
        try:
            from signalwire_agents.core.function_result import SwaigFunctionResult
            import os
            
            # Extract parameters
            if isinstance(args, list) and len(args) > 0:
                params = args[0]
            else:
                params = args
            
            phone_number = params.get('phone_number')
            custom_message = params.get('message')
            
            print(f"📱 VERBOSE: Sending test SMS")
            print(f"   📋 Full args received: {json.dumps(args, indent=2) if args else 'None'}")
            print(f"   📋 Full raw_data received: {json.dumps(raw_data, indent=2) if raw_data else 'None'}")
            print(f"   📋 Extracted parameters:")
            print(f"      - Phone: {phone_number}")
            print(f"      - Custom Message: {custom_message}")
            
            if not phone_number:
                return SwaigFunctionResult("❌ Phone number is required for test SMS")
            
            # Create test message
            if custom_message:
                sms_body = custom_message
            else:
                sms_body = f"🧪 Test SMS from Bobby's Table\n\n"
                sms_body += f"This is a test message to verify SMS functionality.\n\n"
                sms_body += f"✅ If you received this message, SMS is working correctly!\n\n"
                sms_body += f"Sent at: {datetime.now().strftime('%m/%d/%Y %I:%M %p')}\n\n"
                sms_body += f"Bobby's Table Restaurant\n"
                sms_body += f"Reply STOP to stop."
            
            # Get SignalWire phone number from environment
            signalwire_from_number = os.getenv('SIGNALWIRE_FROM_NUMBER', '+14126127565')
            
            print(f"📤 VERBOSE: Using SignalWire Agents SDK send_sms method for test")
            print(f"   📋 SMS Parameters:")
            print(f"      - From: {signalwire_from_number}")
            print(f"      - To: {phone_number}")
            print(f"      - Region: us")
            print(f"   📋 SMS Body (full):")
            print(f"      {repr(sms_body)}")
            print(f"   📋 SMS Body (formatted):")
            print(sms_body)
            
            # Use the SignalWire Agents SDK send_sms method
            result = SwaigFunctionResult()
            result = result.send_sms(
                to_number=phone_number,
                from_number=signalwire_from_number,
                body=sms_body,
                region="us"
            )
            
            # Set a response message
            result.set_response(f"📱 Test SMS will be sent to {phone_number}")
            
            print(f"✅ VERBOSE: Test SMS action created successfully")
            print(f"   📋 Result type: {type(result)}")
            print(f"   📋 Result object: {result}")
            if hasattr(result, 'to_dict'):
                print(f"   📋 Result dict: {json.dumps(result.to_dict(), indent=2)}")
            
            return result
            
        except Exception as e:
            print(f"❌ Error creating test SMS: {e}")
            return SwaigFunctionResult(f"Failed to send test SMS: {str(e)}")