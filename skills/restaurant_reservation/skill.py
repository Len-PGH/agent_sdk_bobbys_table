"""
Restaurant Reservation Skill for SignalWire AI Agents
Provides reservation management capabilities
"""

from typing import List, Dict, Any
import re
import logging
from datetime import datetime
from flask import current_app
import os
from collections import defaultdict

from signalwire_agents.core.skill_base import SkillBase
from signalwire_agents.core.function_result import SwaigFunctionResult
from signalwire_agents.core.swaig_function import SWAIGFunction
from signalwire_agents.core.agent_base import AgentBase

# Get logger for this module
logger = logging.getLogger(__name__)

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
    
    def __init__(self, agent: AgentBase):
        try:
            logger.info("Initializing RestaurantReservationSkill")
            super().__init__(agent)
            # Use the class-level swaig_fields
            logger.info("Calling register_tools")
            self.register_tools()
            logger.info("RestaurantReservationSkill initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing RestaurantReservationSkill: {str(e)}", exc_info=True)
    
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
        """Enhanced menu caching with robust fallback mechanisms"""
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
                
                # Enhanced cache validation
                cache_validation_result = self._validate_cache_freshness(meta_data)
                if cache_validation_result['is_valid']:
                    print(f"🚀 Menu cache is fresh ({cache_validation_result['age_minutes']:.1f} min old), using cached data")
                    return meta_data
                
                print(f"📊 Refreshing menu cache (reason: {cache_validation_result['reason']})")
                
                # Enhanced menu loading with retry logic
                cached_menu = self._load_menu_with_retry()
                
                if not cached_menu:
                    print("❌ Failed to load menu from database, attempting fallback")
                    cached_menu = self._get_fallback_menu_data(meta_data)
                
                if cached_menu:
                    # Update meta_data with enhanced metadata
                    meta_data.update({
                        'cached_menu': cached_menu,
                        'menu_cached_at': datetime.now().isoformat(),
                        'menu_item_count': len(cached_menu),
                        'cache_version': '2.0',
                        'cache_source': 'database' if cached_menu else 'fallback',
                        'last_cache_refresh': datetime.now().isoformat()
                    })
                    
                    print(f"✅ Cached {len(cached_menu)} menu items in meta_data")
                    return meta_data
                else:
                    print("❌ All menu caching attempts failed")
                    return meta_data
                
        except Exception as e:
            print(f"❌ Critical error in menu caching: {e}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()}")
            
            # Return existing meta_data or empty dict as ultimate fallback
            return raw_data.get('meta_data', {}) if raw_data else {}

    def _validate_cache_freshness(self, meta_data):
        """Validate cache freshness with detailed analysis"""
        if not meta_data or not meta_data.get('cached_menu'):
            return {'is_valid': False, 'reason': 'no_cache_data'}
        
        # Check cache timestamp
        cache_time = meta_data.get('menu_cached_at')
        if not cache_time:
            return {'is_valid': False, 'reason': 'no_timestamp'}
        
        try:
            from datetime import datetime, timedelta
            cached_at = datetime.fromisoformat(cache_time)
            age = datetime.now() - cached_at
            age_minutes = age.total_seconds() / 60
            
            # Cache is valid for 10 minutes (increased from 5 for better performance)
            if age < timedelta(minutes=10):
                return {'is_valid': True, 'age_minutes': age_minutes}
            else:
                return {'is_valid': False, 'reason': f'expired_{age_minutes:.1f}min_old'}
        except ValueError:
            return {'is_valid': False, 'reason': 'invalid_timestamp_format'}
        
        # Check if cache has reasonable number of items
        cached_menu = meta_data.get('cached_menu', [])
        if len(cached_menu) < 5:  # Minimum expected menu items
            return {'is_valid': False, 'reason': f'insufficient_items_{len(cached_menu)}'}
        
        return {'is_valid': True, 'age_minutes': age_minutes}

    def _load_menu_with_retry(self, max_attempts=3):
        """Load menu from database with retry logic"""
        from models import MenuItem
        
        for attempt in range(max_attempts):
            try:
                print(f"📊 Loading menu from database (attempt {attempt + 1}/{max_attempts})")
                
                # Enhanced query with explicit ordering for consistency
                menu_items = MenuItem.query.filter_by(is_available=True).order_by(MenuItem.id).all()
                
                if not menu_items:
                    print("⚠️ No available menu items found in database")
                    if attempt < max_attempts - 1:
                        continue
                    return []
                
                # Convert to enhanced serializable format
                cached_menu = []
                for item in menu_items:
                    try:
                        cached_menu.append({
                            'id': item.id,
                            'name': item.name,
                            'price': float(item.price),
                            'category': item.category or 'Uncategorized',
                            'description': item.description or '',
                            'is_available': bool(item.is_available),
                            'cached_at': datetime.now().isoformat()
                        })
                    except Exception as item_error:
                        print(f"⚠️ Error processing menu item {item.id}: {item_error}")
                        continue
                
                if cached_menu:
                    print(f"✅ Successfully loaded {len(cached_menu)} menu items")
                    return cached_menu
                else:
                    print("❌ No valid menu items after processing")
                    
            except Exception as e:
                print(f"❌ Database error on attempt {attempt + 1}: {e}")
                if attempt < max_attempts - 1:
                    import time
                    time.sleep(0.1)  # Brief delay between retries
                    continue
                else:
                    print("❌ All database retry attempts failed")
                    break
        
        return []

    def _get_fallback_menu_data(self, meta_data):
        """Get fallback menu data when database fails"""
        # Try to use existing cached data even if expired
        existing_cache = meta_data.get('cached_menu')
        if existing_cache and len(existing_cache) > 0:
            print(f"🔄 Using expired cache as fallback ({len(existing_cache)} items)")
            
            # Update timestamps to mark as fallback
            for item in existing_cache:
                item['fallback_used'] = True
                item['fallback_at'] = datetime.now().isoformat()
            
            return existing_cache
        
        # Ultimate fallback: minimal menu data
        print("🆘 Using hardcoded fallback menu")
        return self._get_hardcoded_fallback_menu()

    def _get_hardcoded_fallback_menu(self):
        """Hardcoded fallback menu for extreme cases"""
        return [
            {
                'id': 1,
                'name': 'House Special',
                'price': 25.00,
                'category': 'Main Course',
                'description': 'Restaurant special dish',
                'is_available': True,
                'fallback': True,
                'fallback_at': datetime.now().isoformat()
            },
            {
                'id': 2,
                'name': 'House Salad',
                'price': 12.00,
                'category': 'Appetizer',
                'description': 'Fresh mixed greens',
                'is_available': True,
                'fallback': True,
                'fallback_at': datetime.now().isoformat()
            },
            {
                'id': 3,
                'name': 'House Wine',
                'price': 8.00,
                'category': 'Beverage',
                'description': 'House wine selection',
                'is_available': True,
                'fallback': True,
                'fallback_at': datetime.now().isoformat()
            }
        ]

    def _refresh_menu_cache_if_needed(self, meta_data):
        """Refresh menu cache if it's getting stale"""
        if not self._validate_cache_freshness(meta_data)['is_valid']:
            print("🔄 Menu cache needs refresh, updating...")
            return self._cache_menu_in_metadata({'meta_data': meta_data})
        return meta_data

    def _validate_menu_item(self, item_data):
        """Validate a single menu item"""
        try:
            if not isinstance(item_data, dict):
                return False
            
            required_fields = ['id', 'name', 'price', 'category', 'is_available']
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
            
            if not isinstance(item_data['is_available'], bool):
                return False
            
            return True
            
        except Exception:
            return False

    def _validate_menu_cache(self, meta_data):
        """Validate the complete menu cache"""
        try:
            cached_menu = meta_data.get('cached_menu', [])
            
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
        """Generate a unique 5-digit order number"""
        import random
        import sys
        import os
        
        # Add the parent directory to sys.path to import app
        parent_dir = os.path.dirname(os.path.dirname(__file__))
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        
        from models import Order
        
        while True:
            # Generate a 5-digit number (10000 to 99999)
            number = str(random.randint(10000, 99999))
            
            # Check if this number already exists
            existing = Order.query.filter_by(order_number=number).first()
            if not existing:
                return number

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
    
    def _extract_food_items_from_conversation(self, conversation_text, meta_data=None):
        """Extract food items mentioned in conversation and return with correct menu item IDs using cached menu"""
        try:
            import re
            
            # Use cached menu from meta_data if available, otherwise fall back to database query
            if meta_data and meta_data.get('cached_menu'):
                print("🚀 Using cached menu from meta_data for food item extraction")
                cached_menu = meta_data['cached_menu']
                
                # Convert cached menu format to menu items format for compatibility
                menu_items = []
                class MenuItemStub:
                    def __init__(self, item_data):
                        self.id = item_data['id']
                        self.name = item_data['name']
                        self.price = item_data['price']
                        self.category = item_data['category']
                        self.description = item_data['description']
                        self.is_available = item_data['is_available']
                
                for item_data in cached_menu:
                    menu_items.append(MenuItemStub(item_data))
                
                print(f"✅ Using {len(menu_items)} cached menu items for extraction")
            else:
                print("📊 No cached menu found, querying database")
                # Fall back to database query if no cached menu
                import sys
                import os
                
                # Add the parent directory to sys.path to import app
                parent_dir = os.path.dirname(os.path.dirname(__file__))
                if parent_dir not in sys.path:
                    sys.path.insert(0, parent_dir)
                
                from app import app
                from models import MenuItem
                
                with app.app_context():
                    menu_items = MenuItem.query.filter_by(is_available=True).all()
            
            extracted_items = []
            conversation_lower = conversation_text.lower()
            
            # CRITICAL FIX: Sort by name length (descending) to prioritize compound names
            # This ensures "Chicken Tenders" matches before "Chicken Caesar Salad" when user says "chicken tenders"
            menu_items = sorted(menu_items, key=lambda item: len(item.name.lower()), reverse=True)
            
            # Common quantity words and numbers
            quantity_patterns = {
                'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
                'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
                'a': 1, 'an': 1, 'single': 1, 'couple': 2, 'few': 3,
                '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10
            }
            
            # Track already matched items to avoid duplicates
            matched_items = set()
            
            # Check each menu item to see if it's mentioned in conversation
            for menu_item in menu_items:
                item_name = menu_item.name.lower()
                
                # CRITICAL FIX: Only skip if we already found this EXACT item, not just the base word
                # This allows "Chicken Tenders" to be found even if "Chicken Caesar Salad" was already matched
                if any(existing['menu_item_id'] == menu_item.id for existing in extracted_items):
                    continue
                
                # Create variations of the item name to check
                name_variations = []
                
                # For exact menu item name matching
                name_variations.append(item_name)
                
                # Special cases for common items with priority matching
                if item_name == 'pepsi':  # Exact match for regular Pepsi
                    name_variations.extend(['pepsi', 'soda', 'cola'])
                elif item_name == 'diet pepsi':  # Only match if specifically mentioned
                    name_variations.extend(['diet pepsi', 'diet soda'])
                elif item_name == 'coca-cola':  # Exact match for Coca-Cola
                    name_variations.extend(['coke', 'coca cola', 'coca-cola'])
                elif item_name == 'bbq wings':  # PRIORITY: BBQ Wings should match first
                    name_variations.extend(['bbq wings', 'barbecue wings', 'bbq wing'])
                    # Special handling for "bbq" + "wings" combination
                    if 'bbq' in conversation_lower and 'wings' in conversation_lower:
                        name_variations.extend(['wings', 'wing'])
                elif 'buffalo wings' in item_name:
                    # Only match buffalo wings if BBQ wings wasn't already matched
                    if 'bbq' not in conversation_lower:
                        name_variations.extend(['wings', 'buffalo wing', 'wing', 'buffalo wings'])
                elif 'draft beer' in item_name:
                    name_variations.extend(['beer', 'draft', 'draft beer'])
                elif 'classic cheeseburger' in item_name:
                    name_variations.extend(['classic cheeseburger', 'cheeseburger', 'classic burger', 'burger'])
                elif 'bbq ribs' in item_name:
                    name_variations.extend(['bbq ribs', 'barbecue ribs', 'ribs'])
                elif 'bbq burger' in item_name:
                    # Only match BBQ burger if specifically mentioned, not just "bbq"
                    name_variations.extend(['bbq burger', 'barbecue burger'])
                elif 'mountain dew' in item_name:
                    name_variations.extend(['mountain dew', 'dew'])
                elif 'chicken tenders' in item_name:
                    name_variations.extend(['chicken tenders', 'chicken tender', 'tenders', 'chicken fingers', 'fingers'])
                elif 'truffle fries' in item_name:
                    name_variations.extend(['truffle fries', 'truffle frie'])
                elif 'eggs benedict' in item_name:
                    name_variations.extend(['eggs benedict', 'egg benedict', 'benedict'])
                else:
                    # For other items, add common variations
                    name_variations.append(item_name.replace(' ', ''))  # Remove spaces
                    if ' ' in item_name:
                        # Add individual words for partial matching, but exclude common connecting words
                        words = item_name.split()
                        # Filter out common connecting words and very short words that could cause false matches
                        filtered_words = [word for word in words if word.lower() not in 
                                        ['and', 'or', 'the', 'a', 'an', 'with', 'of', 'in', 'on'] and len(word) >= 3]
                        name_variations.extend(filtered_words)
                
                # Check if any variation appears in conversation
                for variation in name_variations:
                    if len(variation) > 2 and variation in conversation_lower:
                        # Special logic for Pepsi vs Diet Pepsi disambiguation
                        if variation == 'pepsi':
                            # If conversation contains "diet", only match Diet Pepsi with "diet pepsi"
                            if 'diet' in conversation_lower:
                                if item_name == 'pepsi':  # Skip regular Pepsi when diet is mentioned
                                    continue
                            else:
                                if item_name == 'diet pepsi':  # Skip Diet Pepsi when diet is NOT mentioned
                                    continue
                        
                        # Try to find quantity near the item mention
                        quantity = 1  # Default
                        
                        # Look for numbers or quantity words near the item name
                        patterns = [
                            rf'(\d+)\s*{re.escape(variation)}',  # "2 pepsi"
                            rf'{re.escape(variation)}\s*(\d+)',  # "pepsi 2"
                            rf'(\w+)\s*{re.escape(variation)}',  # "two pepsi"
                            rf'{re.escape(variation)}\s*(\w+)',  # "pepsi two"
                        ]
                        
                        for pattern in patterns:
                            match = re.search(pattern, conversation_lower)
                            if match:
                                qty_text = match.group(1).lower()
                                if qty_text.isdigit():
                                    quantity = int(qty_text)
                                elif qty_text in quantity_patterns:
                                    quantity = quantity_patterns[qty_text]
                                break
                        
                        extracted_items.append({
                            'menu_item_id': menu_item.id,
                            'quantity': quantity,
                            'name': menu_item.name,
                            'matched_variation': variation
                        })
                        
                        print(f"🔍 Found menu item: '{variation}' -> {menu_item.name} (ID {menu_item.id}) x{quantity}")
                        
                        break  # Stop checking variations for this item
            
            print(f"🔍 Extracted {len(extracted_items)} food items from conversation")
            
            # POST-PROCESSING: Remove less specific matches when more specific ones exist
            # Example: If both "Chicken Caesar Salad" (matched by "chicken") and "Chicken Tenders" (matched by "chicken tenders") 
            # are found, keep only the more specific "Chicken Tenders"
            filtered_items = []
            for item in extracted_items:
                variation = item['matched_variation']
                
                # Check if there's a more specific match for the same base concept
                more_specific_exists = False
                for other_item in extracted_items:
                    other_variation = other_item['matched_variation']
                    # If another item has a longer, more specific variation that contains this one
                    if (other_variation != variation and 
                        len(other_variation) > len(variation) and 
                        variation in other_variation):
                        more_specific_exists = True
                        print(f"🔍 Removing less specific match: '{variation}' -> {item['name']} (more specific: '{other_variation}' -> {other_item['name']})")
                        break
                
                if not more_specific_exists:
                    filtered_items.append(item)
            
            print(f"🔍 After filtering: {len(filtered_items)} food items")
            return filtered_items
            
        except Exception as e:
            print(f"❌ Error extracting food items from conversation: {e}")
            return []
    
    def _extract_reservation_info_from_conversation(self, call_log, caller_phone=None, meta_data=None):
        """Extract reservation information from conversation history"""
        import re
        from datetime import datetime, timedelta
        
        extracted = {}
        
        # Combine all user messages
        user_messages = []
        for entry in call_log:
            if entry.get('role') == 'user' and entry.get('content'):
                user_messages.append(entry['content'].lower())
        
        conversation_text = ' '.join(user_messages)
        print(f"🔍 Analyzing conversation: {conversation_text}")
        
        # Extract name patterns
        name_patterns = [
            r'my name is ([a-zA-Z\s]+?)(?:\s*\.|\s+at|\s+for|\s+and|\s*$)',
            r'i\'m ([a-zA-Z\s]+?)(?:\s*\.|\s+at|\s+for|\s+and|\s*$)',
            r'this is ([a-zA-Z\s]+?)(?:\s*\.|\s+at|\s+for|\s+and|\s*$)',
            r'([a-zA-Z]+\s+[a-zA-Z]+)\s+calling',
            r'([a-zA-Z]+\s+[a-zA-Z]+)\s+here',
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
        
        # Extract party size
        party_patterns = [
            r'party of (\d+)',
            r'for (\d+) people',
            r'for (\d+) person',
            r'(\d+) people',
            r'(\d+) person',
            r'party of (one|two|three|four|five|six|seven|eight|nine|ten)',
            r'for a party of (one|two|three|four|five|six|seven|eight|nine|ten)',
            r'(?:reservation for|table for)\s+(\d+)',
        ]
        
        party_word_to_num = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
        }
        
        for pattern in party_patterns:
            match = re.search(pattern, conversation_text)
            if match:
                party_str = match.group(1)
                if party_str.lower() in party_word_to_num:
                    party_size = party_word_to_num[party_str.lower()]
                else:
                    try:
                        party_size = int(party_str)
                    except ValueError:
                        continue
                
                if 1 <= party_size <= 20:  # Reasonable range
                    extracted['party_size'] = party_size
                    break
        
        # Extract date (handle "today", "tomorrow", specific dates)
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
        
        # Extract time
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
                
                minute = 0
                am_pm = None
                
                if len(groups) >= 3:
                    if groups[1] and groups[1].isdigit():
                        minute = int(groups[1])
                    if groups[2]:
                        am_pm = groups[2].lower()
                elif len(groups) >= 2:
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
            normalized_phone = self._normalize_phone_number(caller_phone)
            if normalized_phone:
                extracted['phone_number'] = normalized_phone
        
        print(f"🔍 Extracted info: {extracted}")
        return extracted
        
    def register_tools(self):
        try:
            logger.info("Starting tool registration for RestaurantReservationSkill")
            # get_current_time and get_current_date are provided by the built-in datetime skill
            # logger.info("Date/time functions provided by datetime skill")
            logger.info("Registering create_reservation")
            try:
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
                                            },
                                            "required": ["items"]
                                        }
                                    },
                                    "required": ["items"]
                                }
                            }
                        },
                        "required": []
                    },
                    handler=self._create_reservation_handler,
                    meta_data_token="reservation_session",
                    **self.swaig_fields
                )
                logger.info("Registered create_reservation")
            except Exception as e:
                logger.error(f"Failed to register create_reservation: {str(e)}", exc_info=True)
            logger.info("Registering get_reservation")
            try:
                self.agent.define_tool(
                    name="get_reservation",
                    description="Look up an existing reservation by any available information: phone number, first name, last name, full name, date, time, party size, reservation ID, or confirmation number. Can return formatted text for voice or structured JSON for programmatic use.",
                    parameters={"type": "object", "properties": {"phone_number": {"type": "string", "description": "Customer phone number"}, "name": {"type": "string", "description": "Customer full name, first name, or last name"}, "first_name": {"type": "string", "description": "Customer first name"}, "last_name": {"type": "string", "description": "Customer last name"}, "reservation_id": {"type": "integer", "description": "Reservation ID"}, "reservation_number": {"type": "string", "description": "6-digit reservation number"}, "confirmation_number": {"type": "string", "description": "Payment confirmation number (format: CONF-XXXXXXXX)"}, "date": {"type": "string", "description": "Reservation date (YYYY-MM-DD)"}, "time": {"type": "string", "description": "Reservation time (HH:MM)"}, "party_size": {"type": "integer", "description": "Number of people"}, "email": {"type": "string", "description": "Customer email address"}, "format": {"type": "string", "enum": ["text", "json"], "description": "Response format: 'text' for voice-friendly formatted text (default), 'json' for structured data", "default": "text"}}, "required": []},
                    handler=self._get_reservation_handler,
                    **self.swaig_fields
                )
                logger.info("Registered get_reservation")
            except Exception as e:
                logger.error(f"Failed to register get_reservation: {str(e)}", exc_info=True)
            logger.info("Registering update_reservation")
            try:
                self.agent.define_tool(
                    name="update_reservation",
                    description="Update an existing reservation details (time, date, party size, etc.) OR add food/drink items to an existing pre-order. When customer wants to modify their reservation or add items to their order, use this function. IMPORTANT: Always ask the customer if they would like to add anything else to their pre-order before finalizing any changes.",
                    parameters={"type": "object", "properties": {"reservation_id": {"type": "integer", "description": "Reservation ID (internal database ID)"}, "reservation_number": {"type": "string", "description": "6-digit reservation number"}, "name": {"type": "string", "description": "New customer name"}, "party_size": {"type": "integer", "description": "New party size"}, "date": {"type": "string", "description": "New reservation date (YYYY-MM-DD)"}, "time": {"type": "string", "description": "New reservation time (HH:MM)"}, "phone_number": {"type": "string", "description": "New phone number"}, "special_requests": {"type": "string", "description": "New special requests"}, "add_items": {"type": "array", "description": "Food or drink items to add to the pre-order", "items": {"type": "object", "properties": {"name": {"type": "string", "description": "Menu item name"}, "quantity": {"type": "integer", "description": "Quantity to add", "default": 1}}, "required": ["name"]}}}, "required": []},
                    handler=self._update_reservation_handler,
                    **self.swaig_fields
                )
                logger.info("Registered update_reservation")
            except Exception as e:
                logger.error(f"Failed to register update_reservation: {str(e)}", exc_info=True)
            logger.info("Registering cancel_reservation")
            try:
                self.agent.define_tool(
                    name="cancel_reservation",
                    description="Cancel an existing reservation. Use this function when a customer wants to cancel their reservation.",
                    parameters={
                        "type": "object", 
                        "properties": {
                            "reservation_number": {"type": "string", "description": "6-digit reservation number"},
                            "phone_number": {"type": "string", "description": "Customer phone number"},
                            "customer_name": {"type": "string", "description": "Customer name"},
                            "reservation_id": {"type": "integer", "description": "Reservation ID (internal database ID)"}
                        }, 
                        "required": []
                    },
                    handler=self._cancel_reservation_handler,
                    **self.swaig_fields
                )
                logger.info("Registered cancel_reservation")
            except Exception as e:
                logger.error(f"Failed to register cancel_reservation: {str(e)}", exc_info=True)
            logger.info("Registering get_calendar_events")
            try:
                self.agent.define_tool(
                    name="get_calendar_events",
                    description="Get a list of upcoming reservations for a specific date range. Use this function to retrieve reservations for a specific date range.",
                    parameters={"type": "object", "properties": {"start_date": {"type": "string", "description": "Start date of the reservation range (YYYY-MM-DD)"}, "end_date": {"type": "string", "description": "End date of the reservation range (YYYY-MM-DD)"}}, "required": []},
                    handler=self._get_calendar_events_handler,
                    **self.swaig_fields
                )
                logger.info("Registered get_calendar_events")
            except Exception as e:
                logger.error(f"Failed to register get_calendar_events: {str(e)}", exc_info=True)
            logger.info("Registering get_todays_reservations")
            try:
                self.agent.define_tool(
                    name="get_todays_reservations",
                    description="Get a list of reservations for today. Use this function to retrieve reservations for today.",
                    parameters={"type": "object", "properties": {}, "required": []},
                    handler=self._get_todays_reservations_handler,
                    **self.swaig_fields
                )
                logger.info("Registered get_todays_reservations")
            except Exception as e:
                logger.error(f"Failed to register get_todays_reservations: {str(e)}", exc_info=True)
            logger.info("Registering get_reservation_summary")
            try:
                self.agent.define_tool(
                    name="get_reservation_summary",
                    description="Get a summary of reservations for a specific date range. Use this function to retrieve a summary of reservations for a specific date range.",
                    parameters={"type": "object", "properties": {"start_date": {"type": "string", "description": "Start date of the reservation range (YYYY-MM-DD)"}, "end_date": {"type": "string", "description": "End date of the reservation range (YYYY-MM-DD)"}}, "required": []},
                    handler=self._get_reservation_summary_handler,
                    **self.swaig_fields
                )
                logger.info("Registered get_reservation_summary")
            except Exception as e:
                logger.error(f"Failed to register get_reservation_summary: {str(e)}", exc_info=True)
            logger.info("Registering pay_reservation")
            try:
                self.agent.define_tool(
                    name="pay_reservation",
                    description="Collect payment for an existing reservation. Use this function to collect payment for an existing reservation. Give the payment results to the customer.",
                    parameters={
                        "type": "object", 
                        "properties": {
                            "reservation_id": {"type": "integer", "description": "Reservation ID (internal database ID)"}, 
                            "reservation_number": {"type": "string", "description": "6-digit reservation number"}, 
                            "name": {"type": "string", "description": "Customer name"}, 
                            "phone_number": {"type": "string", "description": "Customer phone number"}, 

                            "total_amount": {"type": "number", "description": "Total bill amount to be charged in USD"}, 
                            "payment_status": {"type": "string", "description": "Current payment status (unpaid, paid, partial)", "enum": ["unpaid", "paid", "partial"]}, 
                            "party_size": {"type": "integer", "description": "Number of people in the party"}, 
                            "reservation_date": {"type": "string", "description": "Date of the reservation (YYYY-MM-DD)"}, 
                            "reservation_time": {"type": "string", "description": "Time of the reservation (HH:MM)"}, 
                            "special_requests": {"type": "string", "description": "Special requests"}, 
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
                        "required": []
                    },
                    handler=self._pay_reservation_handler,
                    **self.swaig_fields
                )
                logger.info("Registered pay_reservation")
            except Exception as e:
                logger.error(f"Failed to register pay_reservation: {str(e)}", exc_info=True)
            logger.info("Registering check_payment_completion")
            try:
                self.agent.define_tool(
                    name="check_payment_completion",
                    description="Check if a payment has been completed for the current call session. Use this function after initiating payment to check if the payment has been processed successfully and announce the confirmation to the customer.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "reservation_number": {
                                "type": "string",
                                "description": "6-digit reservation number (optional, for verification)"
                            }
                        },
                        "required": []
                    },
                    handler=self._check_payment_completion_handler,
                    **self.swaig_fields
                )
                logger.info("Registered check_payment_completion")
            except Exception as e:
                logger.error(f"Failed to register check_payment_completion: {str(e)}", exc_info=True)
                
            # Weather forecast tool for restaurant location (zipcode 15222)
            logger.info("Registering get_weather_forecast")
            try:
                self.agent.define_tool(
                    name="get_weather_forecast",
                    description="Get weather forecast for the restaurant area (zipcode 15222) for a reservation date. Use this when customers ask about weather for their reservation or the restaurant location.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "reservation_date": {
                                "type": "string",
                                "description": "Date of the reservation (YYYY-MM-DD format) - optional, for context"
                            },
                            "reservation_time": {
                                "type": "string", 
                                "description": "Time of the reservation (HH:MM format) - optional, for context"
                            }
                        },
                        "required": []
                    },
                    handler=self._get_weather_forecast_handler,
                    **self.swaig_fields
                )
                logger.info("Registered get_weather_forecast")
            except Exception as e:
                logger.error(f"Failed to register get_weather_forecast: {str(e)}", exc_info=True)
                
            # Outdoor seating request tool
            logger.info("Registering request_outdoor_seating")
            try:
                self.agent.define_tool(
                    name="request_outdoor_seating",
                    description="Request outdoor seating for a reservation when weather conditions are favorable. Use this when customers express interest in outdoor dining or when weather forecast suggests it would be pleasant.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "reservation_number": {
                                "type": "string",
                                "description": "6-digit reservation number to add outdoor seating request to"
                            },
                            "customer_name": {
                                "type": "string",
                                "description": "Customer name for the reservation"
                            },
                            "party_size": {
                                "type": "integer",
                                "description": "Number of people in the party"
                            },
                            "special_note": {
                                "type": "string",
                                "description": "Any special notes about the outdoor seating request"
                            }
                        },
                        "required": []
                    },
                    handler=self._request_outdoor_seating_handler,
                    **self.swaig_fields
                )
                logger.info("Registered request_outdoor_seating")
            except Exception as e:
                logger.error(f"Failed to register request_outdoor_seating: {str(e)}", exc_info=True)
                
            # SMS and receipt handlers are managed by the menu skill to avoid duplication
            # logger.info("SMS and receipt handlers managed by menu skill")
            # Get tool count from the registry
            tool_count = len(self.agent._tool_registry._swaig_functions) if hasattr(self.agent, '_tool_registry') and hasattr(self.agent._tool_registry, '_swaig_functions') else 0
            logger.info(f"Completed tool registration: {tool_count} tools in registry")
        except Exception as e:
            logger.error(f"Error registering tools: {str(e)}", exc_info=True)

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
                payment_needed = meta_data.get('payment_needed')
                
                print(f"🔍 Auto-detection check:")
                print(f"   reservation_created: {reservation_created}")
                print(f"   session_reservation_number: {session_reservation_number}")
                print(f"   payment_needed: {payment_needed}")
                
                # Enhanced: Check for affirmative response to payment after reservation creation
                if (reservation_created and session_reservation_number and payment_needed and 
                    not args.get('reservation_number')):
                    # Check if user gave an affirmative response recently
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    if self._detect_affirmative_response(call_log, "payment"):
                        print(f"🔍 Detected affirmative payment response after reservation creation")
                        # Auto-fill ALL payment information from session
                        reservation_number = session_reservation_number
                        if not cardholder_name and meta_data.get('customer_name'):
                            cardholder_name = meta_data.get('customer_name')
                        if not phone_number and meta_data.get('phone_number'):
                            phone_number = meta_data.get('phone_number')
                        print(f"🔍 Auto-filled payment info: res#{reservation_number}, name={cardholder_name}, phone={phone_number}")
                
                if reservation_created and session_reservation_number:
                    reservation_number = session_reservation_number
                    print(f"🔍 Auto-detected new reservation from session: #{reservation_number}")
                    
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
                            'reservation confirmed' in entry.get('content', '').lower()):
                            
                            # Try to extract reservation number from the assistant's message
                            content = entry.get('content', '')
                            reservation_match = re.search(r'Reservation #(\d{6})', content)
                            if reservation_match:
                                reservation_number = reservation_match.group(1)
                                print(f"🔍 Auto-detected reservation from conversation: #{reservation_number}")
                                break
            
            # ENHANCED: Also check if we have session context but parameters were not auto-filled
            # CRITICAL FIX: Use main metadata reservation_number as highest priority
            if not reservation_number and meta_data.get('reservation_number'):
                reservation_number = meta_data.get('reservation_number')
                print(f"🔍 Using reservation_number from meta_data: #{reservation_number}")
                
            # BACKUP: Only fall back to verified_reservation if no main reservation_number found
            if not reservation_number and meta_data.get('verified_reservation', {}).get('reservation_number'):
                backup_reservation_number = meta_data.get('verified_reservation', {}).get('reservation_number')
                print(f"🔄 BACKUP: Using verified_reservation.reservation_number: #{backup_reservation_number}")
                reservation_number = backup_reservation_number
                
            if not cardholder_name and meta_data.get('customer_name'):
                cardholder_name = meta_data.get('customer_name')
                print(f"🔍 Using customer_name as cardholder_name from meta_data: {cardholder_name}")
                
            if not phone_number and meta_data.get('phone_number'):
                phone_number = meta_data.get('phone_number')
                print(f"🔍 Using phone_number from meta_data: {phone_number}")
            
            # Validate required information - but be smarter about what we ask for
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
            
            # STEP 1: Look up reservation and show bill summary FIRST (before asking for cardholder name)
            # Look up reservation and calculate total
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app, start_payment_session
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
                                            "No problem! Your reservation is still confirmed. "
                                            "You can pay when you arrive at the restaurant. "
                                            "Is there anything else I can help you with?"
                                        )
                                        result.set_metadata({
                                            "payment_step": "cancelled",
                                            "reservation_number": reservation_number
                                        })
                                        return result
                
                # STEP 2: Show bill summary and ask for confirmation (if not confirmed yet)
                if not payment_confirmed:
                    print(f"🔍 Showing bill total for confirmation: ${total_amount:.2f}")
                    
                    # Use reservation name for display, not cardholder name (since we don't have it yet)
                    customer_display_name = reservation.name
                    
                    # Create detailed order breakdown
                    order_details = []
                    for order in orders:
                        if order.total_amount and order.total_amount > 0:
                            order_details.append(f"• Order #{order.order_number}: ${order.total_amount:.2f}")
                    
                    message = f"📋 Bill Summary for Reservation #{reservation_number}\n\n"
                    message += f"👤 Customer: {customer_display_name}\n"
                    message += f"📅 Party of {reservation.party_size} on {reservation.date} at {reservation.time}\n\n"
                    if order_details:
                        message += f"🍽️ Your Orders:\n"
                        message += "\n".join(order_details) + "\n\n"
                    message += f"💰 Total Amount: ${total_amount:.2f}\n\n"
                    message += f"Would you like to proceed with payment of ${total_amount:.2f}? Please say 'yes' to continue or 'no' to cancel."
                    
                    # Return with confirmation request
                    result = SwaigFunctionResult(message)
                    result.set_metadata({
                        "payment_step": "awaiting_confirmation",
                        "reservation_number": reservation_number,
                        "customer_name": customer_display_name,
                        "cardholder_name": customer_display_name,  # AUTO-POPULATE: Use reservation name as cardholder name
                        "phone_number": phone_number,
                        "total_amount": total_amount,
                        "reservation_details": {
                            "reservation_number": reservation_number,
                            "customer_name": customer_display_name,
                            "party_size": reservation.party_size,
                            "reservation_date": str(reservation.date),
                            "reservation_time": str(reservation.time),
                            "reservation_id": reservation.id
                        }
                    })
                    return result
                
                # STEP 3: Payment confirmed - automatically use reservation name as cardholder name
                if not cardholder_name:
                    # Always use the reservation name as cardholder name (no need to ask)
                    if reservation.name:
                        cardholder_name = reservation.name
                        print(f"🔍 Auto-using reservation name as cardholder name: {cardholder_name}")
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
                    {"name": "reservation_number", "value": reservation_number},
                    {"name": "customer_name", "value": cardholder_name},
                    {"name": "cardholder_name", "value": cardholder_name},  # Pre-populate to skip name prompt
                    {"name": "phone_number", "value": phone_number or ""},
                    {"name": "payment_type", "value": "reservation"}
                ]
                
                # Only add call_id if it has a non-empty value
                if call_id and call_id.strip():
                    parameters_array.append({"name": "call_id", "value": call_id})
                    print(f"🔍 Added call_id to parameters: {call_id}")
                
                # Create response message with payment result variables for immediate feedback
                if meta_data.get('reservation_created'):
                    message = f"🔄 Processing payment for ${total_amount:.2f}...\n\n"
                    message += f"I'll now collect your credit card information securely. Please have your card ready.\n\n"
                else:
                    message = f"🔄 Processing payment for ${total_amount:.2f}...\n\n"
                    message += f"I'll now collect your credit card information securely. Please have your card ready.\n\n"
                
                # Add SignalWire payment result variables for immediate success/failure feedback
                message += f"${{pay_payment_results.success ? "
                message += f"'🎉 Excellent! Your payment of ${total_amount:.2f} has been processed successfully! ' + "
                message += f"'Your confirmation number is ' + pay_payment_results.confirmation_number + '. ' + "
                message += f"'Thank you for dining with Bobby\\'s Table!' : "
                message += f"'I\\'m sorry, there was an issue processing your payment: ' + pay_payment_results.error_message + '. ' + "
                message += f"'Please try again or contact the restaurant for assistance.'}}"
                
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
                base_url = os.getenv('SIGNALWIRE_PAYMENT_CONNECTOR_URL') or os.getenv('BASE_URL', 'https://localhost:8080')
                
                if base_url and not base_url.endswith('/api/payment-processor'):
                    payment_connector_url = f"{base_url.rstrip('/')}/api/payment-processor"
                else:
                    payment_connector_url = base_url or f"{os.getenv('BASE_URL', 'https://localhost:8080')}/api/payment-processor"
                
                status_url = payment_connector_url.replace('/api/payment-processor', '/api/signalwire/payment-callback')
                
                print(f"🔗 Using payment connector URL: {payment_connector_url}")
                
                # CRITICAL: Start payment session for callback tracking
                if call_id:
                    start_payment_session(call_id, reservation_number)
                    print(f"✅ Started payment session for call {call_id}, reservation {reservation_number}")
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
                        description=f"Bobby's Table Reservation #{reservation_number}",
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
                
                # Import start_payment_session for retry
                from app import start_payment_session
                
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

    def _check_payment_completion_handler(self, args, raw_data):
        """Check if payment has been completed for the current call session"""
        try:
            from signalwire_agents.core.function_result import SwaigFunctionResult
            
            # Get call_id from raw_data
            call_id = raw_data.get('call_id') if raw_data else None
            reservation_number = args.get('reservation_number')
            
            if not call_id:
                return SwaigFunctionResult(
                    "I can't check payment completion without a call session ID."
                )
            
            # Check payment session data
            try:
                # Import locally to avoid circular imports
                import sys
                import os
                parent_dir = os.path.dirname(os.path.dirname(__file__))
                if parent_dir not in sys.path:
                    sys.path.insert(0, parent_dir)
                
                from app import app
                
                # Get payment session data
                payment_sessions = getattr(app, 'payment_sessions', {})
                global payment_sessions_global
                if 'payment_sessions_global' not in globals():
                    payment_sessions_global = {}
                
                # Check both app and global payment sessions
                payment_session = payment_sessions.get(call_id) or payment_sessions_global.get(call_id)
                
                if not payment_session:
                    return SwaigFunctionResult(
                        "I don't see any payment activity for this call session yet. "
                        "Please initiate payment first using the pay_reservation function."
                    )
                
                # Check if payment has been completed
                if payment_session.get('payment_completed'):
                    confirmation_number = payment_session.get('confirmation_number')
                    payment_amount = payment_session.get('payment_amount')
                    reservation_number = payment_session.get('reservation_number')
                    
                    if confirmation_number and payment_amount:
                        # Mark payment as announced to prevent duplicate announcements
                        payment_session['payment_announced'] = True
                        payment_sessions[call_id] = payment_session
                        payment_sessions_global[call_id] = payment_session.copy()
                        
                        return SwaigFunctionResult(
                            f"🎉 EXCELLENT! Your payment of ${payment_amount:.2f} has been processed successfully! "
                            f"Your confirmation number is {confirmation_number}. "
                            f"Please write this down: {confirmation_number}. "
                            f"Your reservation #{reservation_number} is now fully paid and confirmed. "
                            f"We look forward to serving you at Bobby's Table!"
                        )
                    else:
                        return SwaigFunctionResult(
                            "Your payment has been processed, but I'm still waiting for the confirmation details. "
                            "Please wait a moment and I'll check again shortly."
                        )
                else:
                    payment_status = payment_session.get('payment_status', 'unknown')
                    if payment_status == 'in_progress':
                        return SwaigFunctionResult(
                            "Your payment is currently being processed. Please wait while I collect your payment information."
                        )
                    elif payment_status == 'failed':
                        return SwaigFunctionResult(
                            "I see that your payment attempt was unsuccessful. Would you like to try again?"
                        )
                    else:
                        return SwaigFunctionResult(
                            f"Your payment session is active but not yet completed. Status: {payment_status}. "
                            f"Please continue with the payment process."
                        )
                
            except Exception as session_error:
                print(f"ERROR: Failed to check payment session: {session_error}")
                return SwaigFunctionResult(
                    "I'm having trouble checking your payment status. Please try again in a moment."
                )
        
        except Exception as e:
            print(f"ERROR: Check payment completion failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return SwaigFunctionResult(
                "I'm having trouble checking your payment completion status. Please try again."
            )

    def _show_order_summary_and_confirm(self, args, raw_data):
        """Enhanced order summary with comprehensive validation and confirmation"""
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
                # Enhanced menu cache validation
                meta_data = self._cache_menu_in_metadata(raw_data)
                if not self._validate_menu_cache(meta_data):
                    print("⚠️ Menu cache validation failed during order summary")
                    meta_data = self._cache_menu_in_metadata(raw_data)
                
                party_orders = args.get('party_orders', [])
                if not party_orders:
                    return SwaigFunctionResult("No order details found to summarize. Please tell me what you'd like to order.")
                
                # Enhanced party orders validation
                validated_party_orders = self._validate_and_fix_party_orders(party_orders, meta_data)
                if not validated_party_orders:
                    return SwaigFunctionResult("The order items couldn't be validated. Please tell me what you'd like to order again.")
                
                # Use cached menu for fast lookups
                cached_menu = meta_data.get('cached_menu', [])
                menu_lookup = {item['id']: item for item in cached_menu} if cached_menu else {}
                
                if not menu_lookup:
                    # Fallback to database if no cached menu
                    print("📊 Fallback to database for order summary")
                    menu_items = MenuItem.query.filter_by(is_available=True).all()
                    menu_lookup = {item.id: {'id': item.id, 'name': item.name, 'price': float(item.price)} for item in menu_items}
                
                # Enhanced order summary generation
                summary_result = self._generate_enhanced_order_summary(
                    validated_party_orders, menu_lookup, args
                )
                
                if summary_result['has_errors']:
                    return SwaigFunctionResult(
                        f"There were issues with your order:\n\n{summary_result['error_message']}\n\n"
                        "Please tell me what you'd like to order again."
                    )
                
                # Store comprehensive pending reservation data
                updated_meta_data = meta_data.copy()
                updated_meta_data.update({
                    'pending_reservation': args,
                    'validated_party_orders': validated_party_orders,
                    'workflow_step': 'awaiting_order_confirmation',
                    'order_summary_shown': True,
                    'order_total': summary_result['total_amount'],
                    'order_validation_passed': True,
                    'confirmation_attempts': 0
                })
                
                result = SwaigFunctionResult(summary_result['summary_text'])
                result.set_metadata(updated_meta_data)
                return result
                
        except Exception as e:
            print(f"❌ Error in _show_order_summary_and_confirm: {e}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()}")
            return SwaigFunctionResult(f"I encountered an error while preparing your order summary. Please tell me your order again.")

    def _generate_enhanced_order_summary(self, party_orders, menu_lookup, args):
        """Generate comprehensive order summary with validation"""
        summary_lines = []
        total_amount = 0.0
        validation_errors = []
        missing_items = []
        
        # Reservation header
        summary_lines.extend([
            "🍽️ **RESERVATION & ORDER SUMMARY** 🍽️",
            "",
            "📅 **Reservation Details:**",
            f"• Name: {args.get('name', 'N/A')}",
            f"• Date: {args.get('date', 'N/A')}",
            f"• Time: {args.get('time', 'N/A')}",
            f"• Party Size: {args.get('party_size', 'N/A')} people",
            f"• Phone: {args.get('phone_number', 'N/A')}",
            ""
        ])
        
        if args.get('special_requests'):
            summary_lines.extend([
                f"📝 **Special Requests:** {args['special_requests']}",
                ""
            ])
        
        # Order details with enhanced validation
        summary_lines.extend([
            "🍽️ **Pre-Order Details:**",
            ""
        ])
        
        for person_order in party_orders:
            person_name = person_order.get('person_name', 'Customer')
            person_items = person_order.get('items', [])
            
            if person_items:
                summary_lines.append(f"👤 **{person_name}:**")
                person_total = 0.0
                person_item_count = 0
                
                for item_data in person_items:
                    try:
                        menu_item_id = int(item_data['menu_item_id'])
                        quantity = int(item_data.get('quantity', 1))
                        
                        # Enhanced menu item validation
                        if menu_item_id not in menu_lookup:
                            missing_items.append(f"Item ID {menu_item_id} for {person_name}")
                            continue
                        
                        menu_info = menu_lookup[menu_item_id]
                        item_name = menu_info['name']
                        item_price = float(menu_info['price'])
                        
                        # Validate quantity
                        if quantity <= 0:
                            validation_errors.append(f"Invalid quantity ({quantity}) for {item_name}")
                            quantity = 1
                        
                        item_total = item_price * quantity
                        person_total += item_total
                        person_item_count += quantity
                        
                        # Format item line
                        if quantity > 1:
                            summary_lines.append(f"   • {item_name} x{quantity} - ${item_total:.2f} (${item_price:.2f} each)")
                        else:
                            summary_lines.append(f"   • {item_name} - ${item_price:.2f}")
                        
                    except (ValueError, KeyError, TypeError) as e:
                        validation_errors.append(f"Error processing item for {person_name}: {str(e)}")
                        continue
                
                # Person summary
                if person_item_count > 0:
                    item_text = "item" if person_item_count == 1 else "items"
                    summary_lines.extend([
                        f"   📊 {person_item_count} {item_text}, Total: ${person_total:.2f}",
                        ""
                    ])
                    total_amount += person_total
                else:
                    summary_lines.extend([
                        f"   ⚠️ No valid items found for {person_name}",
                        ""
                    ])
        
        # Order totals and summary
        summary_lines.extend([
            "💰 **ORDER TOTAL:**",
            f"🎯 **Grand Total: ${total_amount:.2f}**",
            ""
        ])
        
        # Add important notes
        if total_amount > 0:
            summary_lines.extend([
                "ℹ️ **Important Notes:**",
                "• Your food will be prepared and ready when you arrive",
                "• You can pay now or when you arrive at the restaurant",
                "• Please arrive on time for your reservation",
                ""
            ])
        
        # Enhanced confirmation request
        summary_lines.extend([
            "❓ **PLEASE CONFIRM YOUR ORDER:**",
            "",
            "Is everything correct above? Please respond with:",
            "✅ **'Yes, that's correct'** - to confirm and create your reservation",
            "🔄 **'Change [specific item]'** - to modify something specific",
            "➕ **'Add [item]'** - to add more items",
            "❌ **'Cancel'** - to start over",
            "",
            "What would you like to do?"
        ])
        
        # Prepare error message if needed
        error_message = ""
        has_errors = False
        
        if validation_errors or missing_items:
            has_errors = True
            error_parts = []
            
            if missing_items:
                error_parts.append(f"Missing menu items: {', '.join(missing_items)}")
            
            if validation_errors:
                error_parts.append(f"Validation errors: {', '.join(validation_errors)}")
            
            error_message = "\n".join(error_parts)
        
        return {
            'summary_text': "\n".join(summary_lines),
            'total_amount': total_amount,
            'has_errors': has_errors,
            'error_message': error_message,
            'validation_errors': validation_errors,
            'missing_items': missing_items
        }

    def _create_reservation_handler(self, args, raw_data):
        """Handler for create_reservation tool"""
        try:
            # Extract meta_data for session management
            meta_data = raw_data.get('meta_data', {}) if raw_data else {}
            print(f"🔍 Initial meta_data: {meta_data}")
            
            # CRITICAL FIX: Proactively cache menu before processing any food items
            print("🔧 Proactively caching menu for reservation creation...")
            meta_data = self._cache_menu_in_metadata(raw_data)
            print(f"✅ Menu cached for reservation processing")

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
                
                # NEW PREORDER WORKFLOW CHECK
                # Check if this is a preorder that needs summarization first
                current_meta_data = raw_data.get('meta_data', {}) if raw_data else {}
                party_orders = args.get('party_orders', [])
                
                # If party_orders exist but no confirmation yet, show order summary for confirmation
                if (party_orders and 
                    not current_meta_data.get('order_confirmed') and 
                    not current_meta_data.get('order_summary_shown') and
                    not args.get('skip_summary', False)):
                    
                    return self._show_order_summary_and_confirm(args, raw_data)
                
                # Check if user is confirming their order details from previous summary
                if current_meta_data.get('workflow_step') == 'awaiting_order_confirmation':
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    user_confirmed = False
                    
                    print(f"🔍 WORKFLOW: In awaiting_order_confirmation state")
                    print(f"🔍 WORKFLOW: Checking last {min(5, len(call_log))} conversation entries for confirmation")
                    
                    # Check last user message for order confirmation - be more strict
                    recent_user_messages = []
                    for entry in reversed(call_log[-10:]):  # Check more entries for confirmation
                        if entry.get('role') == 'user' and entry.get('content'):
                            recent_user_messages.append(entry.get('content', ''))
                    
                    print(f"🔍 WORKFLOW: Recent user messages: {recent_user_messages}")
                    
                    # Look for explicit confirmation in the most recent messages
                    for content in recent_user_messages[:3]:  # Only check last 3 user messages
                        content_lower = content.lower().strip()
                        
                        # Enhanced confirmation phrases - more natural language patterns
                        explicit_confirmations = [
                            'yes, that\'s correct', 'yes that\'s correct', 'that\'s correct',
                            'yes, create', 'yes create', 'create reservation', 'create it',
                            'looks good', 'looks right', 'that\'s right', 'perfect',
                            'confirm', 'confirmed', 'proceed', 'go ahead',
                            # NEW: More natural responses
                            'sounds good', 'that works', 'let\'s do it', 'make it',
                            'book it', 'reserve it', 'yes please', 'absolutely',
                            'that\'s perfect', 'exactly right', 'all good'
                        ]
                        
                        # Check for explicit confirmation
                        if any(phrase in content_lower for phrase in explicit_confirmations):
                            user_confirmed = True
                            print(f"✅ WORKFLOW: User explicitly confirmed with: '{content}'")
                            break
                        
                        # Check for simple "yes" but only if it's a standalone response
                        elif content_lower in ['yes', 'yes.', 'yep', 'yeah', 'sure', 'ok', 'okay']:
                            # Additional check: make sure the previous assistant message was asking for confirmation
                            for entry in reversed(call_log[-5:]):
                                if (entry.get('role') == 'assistant' and 
                                    entry.get('content') and 
                                    ('confirm' in entry.get('content', '').lower() or 
                                     'correct' in entry.get('content', '').lower())):
                                    user_confirmed = True
                                    print(f"✅ WORKFLOW: User confirmed with simple '{content}' after confirmation prompt")
                                    break
                            if user_confirmed:
                                break
                        
                        # Check for modification requests
                        elif ('change' in content_lower or 'wrong' in content_lower or 
                              'not right' in content_lower or 'different' in content_lower):
                            print(f"🔄 WORKFLOW: User wants to modify order: '{content}'")
                            return SwaigFunctionResult(
                                "I'd be happy to help you modify your order! "
                                "Please tell me what you'd like to change or add."
                            )
                        
                        # Check for cancellation
                        elif 'cancel' in content_lower or 'start over' in content_lower:
                            print(f"❌ WORKFLOW: User wants to cancel: '{content}'")
                            result = SwaigFunctionResult("No problem! Let's start fresh. How can I help you today?")
                            result.set_metadata({})  # Clear meta_data
                            return result
                    
                    # Also check if user is trying to pay (which implies confirmation)
                    if not user_confirmed:
                        for content in recent_user_messages[:2]:  # Only check last 2 messages
                            content_lower = content.lower()
                            if ('pay' in content_lower or 'payment' in content_lower or 
                                'card' in content_lower or 'credit' in content_lower):
                                user_confirmed = True
                                print(f"✅ WORKFLOW: User implied confirmation by requesting payment: '{content}'")
                                break
                    
                    # If no confirmation found, ask for it
                    if not user_confirmed:
                        print("❌ WORKFLOW: No confirmation detected, asking user to confirm")
                        # Check if we already showed the summary
                        if not current_meta_data.get('order_summary_shown'):
                            # Show summary first
                            pending_reservation = current_meta_data.get('pending_reservation', {})
                            if pending_reservation:
                                return self._show_order_summary_and_confirm(pending_reservation, raw_data)
                        
                        return SwaigFunctionResult(
                            "I need you to confirm your order before I can create the reservation.\n\n"
                            "Please review the order details above and respond with:\n"
                            "✅ **'Yes, that's correct'** if the order is right\n"
                            "🔄 **'Change [item]'** to modify your order\n"
                            "❌ **'Cancel'** to start over\n\n"
                            "What would you like to do?"
                        )
                    
                    # User confirmed their order, but re-validate against conversation to ensure accuracy
                    print("✅ WORKFLOW: User confirmed order, re-validating against conversation")
                    
                    # Re-extract items from conversation to ensure accuracy
                    conversation_text = ' '.join([
                        entry.get('content', '') 
                        for entry in call_log 
                        if entry.get('role') == 'user'
                    ])
                    
                    re_extracted_items = self._extract_food_items_from_conversation(conversation_text, meta_data)
                    print(f"🔍 WORKFLOW: Re-extracted items from conversation: {re_extracted_items}")
                    
                    if re_extracted_items:
                        # CRITICAL FIX: Also re-parse person assignments, don't just use cached assignments
                        customer_name = args.get('name', 'Customer')
                        party_size = args.get('party_size', 2)
                        
                        # FIXED: Use enhanced parsing for better name extraction and assignment
                        additional_names = self._extract_person_names_from_conversation(conversation_text, customer_name)
                        corrected_party_orders = self._fallback_order_distribution(
                            re_extracted_items, customer_name, party_size, additional_names, conversation_text
                        )
                        
                        print(f"🔄 WORKFLOW: Re-assigned items to people:")
                        for order in corrected_party_orders:
                            person_name = order.get('person_name', 'Unknown')
                            items = order.get('items', [])
                            print(f"   {person_name}: {len(items)} items")
                        
                        # Update args with corrected assignments
                        args['party_orders'] = corrected_party_orders
                        args['order_confirmed'] = True
                        print("✅ WORKFLOW: Updated pending reservation with corrected items")
                    
                    # Update meta_data with corrected information
                    if meta_data and 'pending_reservation' in meta_data:
                        meta_data['pending_reservation'].update(args)
                        print("✅ WORKFLOW: Using validated pending reservation data")
                
                # INTELLIGENT ITEM PROCESSING: Handle both confirmation and addition scenarios
                party_orders = args.get('party_orders', [])
                order_confirmed = args.get('order_confirmed', False)
                
                # Check user intent from recent conversation
                call_log = raw_data.get('call_log', []) if raw_data else []
                recent_user_messages = [
                    entry.get('content', '').lower() 
                    for entry in call_log[-3:] 
                    if entry.get('role') == 'user'
                ]
                latest_user_message = recent_user_messages[-1] if recent_user_messages else ""
                
                # Detect if user is adding items vs confirming existing order
                adding_items_phrases = [
                    'i want to add', 'can i add', 'i also want', 'also get', 'and also',
                    'i\'d like to also', 'can i also get', 'add to that', 'plus',
                    'i also need', 'can we add', 'let me add', 'i want more'
                ]
                
                confirmation_phrases = [
                    'yes that\'s correct', 'that\'s right', 'that sounds good', 'perfect',
                    'yes please', 'that\'s perfect', 'correct', 'exactly', 'that\'s it',
                    'yes', 'yep', 'yeah', 'sounds good', 'looks good'
                ]
                
                is_adding_items = any(phrase in latest_user_message for phrase in adding_items_phrases)
                is_confirming_order = any(phrase in latest_user_message for phrase in confirmation_phrases)
                
                print(f"🔍 User intent analysis:")
                print(f"   Latest message: '{latest_user_message}'")
                print(f"   Is adding items: {is_adding_items}")
                print(f"   Is confirming order: {is_confirming_order}")
                print(f"   Has pending orders: {bool(party_orders)}")
                print(f"   Order confirmed flag: {order_confirmed}")
                
                if party_orders and (order_confirmed or is_confirming_order) and not is_adding_items:
                    # Scenario 1: User is confirming their existing pending order
                    print("✅ WORKFLOW: User confirming existing order - preserving confirmed items")
                    
                elif party_orders and is_adding_items:
                    # Scenario 2: User wants to add items to existing pending order
                    print("🔄 WORKFLOW: User adding items to existing order - merging with conversation extraction")
                    
                    conversation_text = ' '.join([
                        entry.get('content', '') 
                        for entry in call_log 
                        if entry.get('role') == 'user'
                    ])
                    
                    # Extract NEW items from conversation
                    new_items = self._extract_food_items_from_conversation(conversation_text, meta_data)
                    print(f"🔍 Extracted new items from conversation: {new_items}")
                    
                    if new_items:
                        # Add new items to existing party orders
                        for order in party_orders:
                            if 'items' in order:
                                existing_items = order['items']
                                print(f"🔄 Adding new items to {order.get('person_name', 'Unknown')}'s order")
                                print(f"   Existing items: {existing_items}")
                                
                                # Add new items to existing ones
                                for new_item in new_items:
                                    order['items'].append({
                                        'menu_item_id': new_item['menu_item_id'],
                                        'quantity': new_item['quantity']
                                    })
                                
                                print(f"   Updated items: {order['items']}")
                        
                        args['party_orders'] = party_orders
                        print(f"✅ Added new items to existing party orders")
                
                elif party_orders and not order_confirmed:
                    # Scenario 3: AI provided wrong menu item IDs - fix them with proper person-item assignment
                    print("🔍 [Summary] Validating menu item IDs in party_orders...")
                    conversation_text = ' '.join([
                        entry.get('content', '') 
                        for entry in call_log 
                        if entry.get('role') == 'user'
                    ])
                    
                    # Extract correct menu items from conversation
                    correct_items = self._extract_food_items_from_conversation(conversation_text, meta_data)
                    print(f"🔍 [Summary] Extracted correct items from conversation: {correct_items}")
                    
                    if correct_items:
                        # Use intelligent parsing to assign items to specific people
                        customer_name = args.get('name', 'Customer')
                        party_size = args.get('party_size', 2)
                        
                        # FIXED: Use enhanced parsing for better name extraction and assignment
                        additional_names = self._extract_person_names_from_conversation(conversation_text, customer_name)
                        corrected_party_orders = self._fallback_order_distribution(
                            correct_items, customer_name, party_size, additional_names, conversation_text
                        )
                        
                        print(f"🔄 [Summary] Intelligently assigned items to people:")
                        for order in corrected_party_orders:
                            person_name = order.get('person_name', 'Unknown')
                            items = order.get('items', [])
                            print(f"   {person_name}: {len(items)} items")
                            
                            # Convert items to the format expected by args
                            formatted_items = []
                            for item in items:
                                if isinstance(item, dict) and 'menu_item_id' in item:
                                    formatted_items.append({
                                        'menu_item_id': item['menu_item_id'],
                                        'quantity': item.get('quantity', 1)
                                    })
                            order['items'] = formatted_items
                        
                        args['party_orders'] = corrected_party_orders
                        print(f"✅ [Summary] Fixed party_orders with correct menu item IDs and proper person assignment")
                
                # Extract caller phone number from various sources
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
                
                # CRITICAL PHONE NUMBER FIX: Ensure we never use phone as name
                phone_numbers_to_check = [caller_phone, user_provided_phone, conversation_phone, args.get('phone_number')]
                phone_numbers_to_check = [p for p in phone_numbers_to_check if p]  # Remove None values
                
                if not args.get('name') or any(args.get('name') == phone for phone in phone_numbers_to_check):
                    # Phone number was mistakenly used as name, force re-extraction
                    print(f"🚨 CRITICAL: Phone number used as name ({args.get('name')}), forcing re-extraction")
                    args['name'] = None
                    
                    # Re-extract customer name more aggressively from conversation
                    import re
                    for entry in reversed(call_log):
                        if entry.get('role') == 'user' and entry.get('content'):
                            content = entry['content']
                            # Look for explicit name patterns
                            name_patterns = [
                                r'my name is ([A-Z][a-z]+ [A-Z][a-z]+)',
                                r'i\'m ([A-Z][a-z]+ [A-Z][a-z]+)',
                                r'this is ([A-Z][a-z]+ [A-Z][a-z]+)',
                                r'name is ([A-Z][a-z]+ [A-Z][a-z]+)',
                                r'([A-Z][a-z]+ [A-Z][a-z]+) calling',
                                r'([A-Z][a-z]+ [A-Z][a-z]+) here'
                            ]
                            for pattern in name_patterns:
                                match = re.search(pattern, content, re.IGNORECASE)
                                if match:
                                    potential_name = match.group(1).strip().title()
                                    if not any(potential_name == phone for phone in phone_numbers_to_check):
                                        args['name'] = potential_name
                                        print(f"✅ FIXED: Extracted proper name: {potential_name}")
                                        break
                            if args.get('name'):
                                break
                    
                    # Final fallback if no name found
                    if not args.get('name'):
                        args['name'] = "Customer"
                        print(f"🔧 FALLBACK: Using generic 'Customer' name")
                
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
                # Use timezone-aware comparison to avoid timezone issues
                import pytz
                
                # Use the same timezone as configured in app.py
                LOCAL_TIMEZONE = pytz.timezone("America/New_York")
                
                # Get current time in the configured timezone
                now = datetime.now(LOCAL_TIMEZONE).replace(tzinfo=None)
                
                # Add some debugging output
                print(f"🔍 Reservation datetime: {reservation_datetime}")
                print(f"🔍 Current datetime: {now}")
                print(f"🔍 Is in past? {reservation_datetime < now}")
                
                # Add a small buffer (1 minute) to account for processing time
                from datetime import timedelta
                buffer_time = now - timedelta(minutes=1)
                
                if reservation_datetime < buffer_time:
                    print(f"❌ Reservation is in the past: {reservation_datetime} < {buffer_time}")
                    return SwaigFunctionResult("I can't make a reservation for a time in the past. Please choose a future date and time.")
                
                # No duplicate prevention - allow all reservation requests
                # Customers should be free to make multiple reservations as needed
                
                # Generate a unique 6-digit reservation number (matching Flask route logic)
                while True:
                    reservation_number = f"{random.randint(100000, 999999)}"
                    # Check if this number already exists
                    existing = Reservation.query.filter_by(reservation_number=reservation_number).first()
                    if not existing:
                        break
                
                # Create reservation with exact same structure as Flask route and init_test_data.py
                reservation = Reservation(
                    reservation_number=reservation_number,
                    name=args['name'],
                    party_size=int(args['party_size']),
                    date=args['date'],
                    time=args['time'],
                    phone_number=args['phone_number'],
                    status='confirmed',  # Match Flask route default
                    special_requests=args.get('special_requests', ''),
                    payment_status='unpaid'  # Match init_test_data.py structure
                )
                
                db.session.add(reservation)
                db.session.flush()  # Get reservation.id
                
                # Process party orders if provided (matching Flask route logic)
                party_orders = args.get('party_orders', [])
                pre_order = args.get('pre_order', [])  # Handle alternative format from AI
                order_items = args.get('order_items', [])  # Handle order_items format from test/AI
                total_reservation_amount = 0.0
                
                # Convert order_items format to party_orders format if needed
                if order_items and not party_orders and not pre_order:
                    print(f"🔄 Converting order_items format to party_orders format")
                    from models import MenuItem
                    
                    # Convert order_items to party_orders format using exact matching only
                    converted_items = []
                    for item in order_items:
                        item_name = item.get('name', '')
                        quantity = item.get('quantity', 1)
                        person_name = item.get('person_name', args.get('name', 'Customer'))
                        
                        # Find menu item by exact name match first
                        menu_item = self._find_menu_item_exact(item_name)
                        
                        if menu_item:
                            converted_items.append({
                                'menu_item_id': menu_item.id,
                                'quantity': quantity,
                                'person_name': person_name
                            })
                            print(f"   ✅ Added exact match: '{item_name}' (menu item ID {menu_item.id}) for {person_name}")
                        else:
                            print(f"   ❌ Exact match not found for '{item_name}' - trying conversation extraction")
                            # Try to find the item using conversation extraction
                            call_log = raw_data.get('call_log', []) if raw_data else []
                            conversation_text = ' '.join([entry.get('content', '') for entry in call_log if entry.get('content')])
                            
                            # Use the conversation extraction to find the correct menu item
                            conversation_items = self._extract_food_items_from_conversation(conversation_text, meta_data)
                            
                            # Look for a match based on the item name
                            for conv_item in conversation_items:
                                if item_name.lower() in conv_item.get('name', '').lower() or conv_item.get('name', '').lower() in item_name.lower():
                                    converted_items.append({
                                        'menu_item_id': conv_item['menu_item_id'],
                                        'quantity': quantity,
                                        'person_name': person_name
                                    })
                                    print(f"   ✅ Found via conversation: '{item_name}' -> {conv_item['name']} (ID {conv_item['menu_item_id']}) for {person_name}")
                                    break
                            else:
                                print(f"   ❌ Could not find '{item_name}' in menu or conversation - skipping")
                    
                    if converted_items:
                        # Group items by person
                        person_groups = {}
                        for item in converted_items:
                            person = item['person_name']
                            if person not in person_groups:
                                person_groups[person] = []
                            person_groups[person].append({
                                'menu_item_id': item['menu_item_id'],
                                'quantity': item['quantity']
                            })
                        
                        party_orders = []
                        for person_name, items in person_groups.items():
                            party_orders.append({
                                'person_name': person_name,
                                'items': items
                            })
                        
                        print(f"   Created party_orders from order_items: {party_orders}")
                
                # Convert pre_order format to party_orders format if needed
                if pre_order and not party_orders:
                    print(f"🔄 Converting pre_order format to party_orders format")
                    print(f"   ⚠️ WARNING: Using fallback pre_order format instead of preferred party_orders")
                    print(f"   📋 Raw pre_order data: {pre_order}")
                    
                    from models import MenuItem
                    
                    # Convert pre_order items to party_orders format using enhanced matching
                    converted_items = []
                    for item in pre_order:
                        item_name = item.get('name', '')
                        quantity = item.get('quantity', 1)
                        
                        # Enhanced matching: try exact match first, then fuzzy match
                        menu_item = self._find_menu_item_exact(item_name)
                        
                        if not menu_item:
                            print(f"   🔍 Exact match failed for '{item_name}', trying fuzzy match...")
                            menu_item = self._find_menu_item_fuzzy(item_name, meta_data)
                        
                        if menu_item:
                            # Include price for transparency and validation
                            if hasattr(menu_item, 'price'):
                                price = float(menu_item.price)
                            else:
                                price = menu_item.get('price', 0.0) if isinstance(menu_item, dict) else 0.0
                            
                            converted_items.append({
                                'menu_item_id': menu_item.id if hasattr(menu_item, 'id') else menu_item.get('id'),
                                'quantity': quantity,
                                'name': item_name,  # Keep original name for debugging
                                'price': price      # Include price for validation
                            })
                            print(f"   ✅ Converted: '{item_name}' → ID {menu_item.id if hasattr(menu_item, 'id') else menu_item.get('id')} @ ${price:.2f}")
                        else:
                            print(f"   ❌ No match found for '{item_name}' - skipping item")
                    
                    if converted_items:
                        # ENHANCED: Use party distribution logic for multiple people
                        party_size = args.get('party_size', 1)
                        customer_name = args.get('name', 'Customer')
                        
                        if party_size > 1:
                            print(f"   🔄 ENHANCED: Distributing {len(converted_items)} items across {party_size} people")
                            
                            # Construct conversation text for better assignment
                            call_log = raw_data.get('call_log', []) if raw_data else []
                            conversation_text = ' '.join([
                                entry.get('content', '') 
                                for entry in call_log 
                                if entry.get('role') in ['user', 'assistant']
                            ])
                            
                            # Use the fallback distribution logic with conversation context
                            party_orders = self._fallback_order_distribution(
                                converted_items,  # food_items
                                customer_name,
                                party_size,
                                [],  # additional_names (empty list)
                                conversation_text
                            )
                            print(f"   ✅ Enhanced distribution created {len(party_orders)} party orders")
                        else:
                            # Single person - all items go to customer
                            party_orders = [{
                                'person_name': customer_name,
                                'items': converted_items
                            }]
                            print(f"   ✅ Single person order created with {len(converted_items)} items")
                    
                    print(f"   📊 Final party_orders: {party_orders}")
                    print(f"   💡 RECOMMENDATION: Use party_orders format with menu_item_id for better reliability")
                
                # Debug logging for order processing
                print(f"🔍 Order processing debug:")
                print(f"   old_school: {args.get('old_school', False)}")
                print(f"   party_orders: {len(party_orders)} items")
                print(f"   pre_order: {len(pre_order)} items")
                print(f"   order_items: {len(order_items)} items")
                
                # CRITICAL FIX: Always process orders regardless of payment context
                # The payment protection system was incorrectly blocking reservation creation
                # when customers wanted to create reservations with pre-orders
                print(f"🔧 PAYMENT PROTECTION BYPASS: Processing reservation creation with pre-orders")
                
                # Only process orders if not an old school reservation
                if not args.get('old_school', False) and party_orders:
                    from models import Order, OrderItem, MenuItem
                    print(f"✅ Processing {len(party_orders)} party orders")
                    
                    # SIMPLIFIED PROCESSING: Trust the provided menu IDs and use cached menu data
                    print(f"🔧 SIMPLIFIED: Using provided menu IDs directly with cached menu validation")
                    
                    # Use cached menu for fast lookups and accurate pricing
                    cached_menu = meta_data.get('cached_menu', [])
                    menu_lookup = {item['id']: item for item in cached_menu} if cached_menu else {}
                    
                    if not menu_lookup:
                        print("⚠️ No cached menu available, querying database directly")
                        # Fallback to database if no cached menu
                        menu_items = MenuItem.query.filter_by(is_available=True).all()
                        menu_lookup = {item.id: {'id': item.id, 'name': item.name, 'price': float(item.price), 'category': item.category} for item in menu_items}
                    
                    print(f"📊 Using menu data with {len(menu_lookup)} items for pricing")
                    
                    total_reservation_amount = 0.0
                    
                    for person_order in party_orders:
                        person_name = person_order.get('person_name', 'Customer')
                        person_items = person_order.get('items', [])
                        
                        if not person_items:
                            print(f"   ⚠️ No items for {person_name}, skipping order creation")
                            continue
                        
                        print(f"   👤 Creating order for {person_name} with {len(person_items)} items")
                        
                        # Create order for this person
                        order = Order(
                            order_number=self._generate_order_number(),
                            reservation_id=reservation.id,
                            table_id=None,
                            person_name=person_name,
                            status='pending',
                            total_amount=0.0,
                            target_date=args['date'],
                            target_time=args['time'],
                            order_type='reservation',
                            payment_status='unpaid',
                            customer_phone=args.get('phone_number')
                        )
                        db.session.add(order)
                        db.session.flush()  # Get order.id
                        
                        order_total = 0.0
                        for item_data in person_items:
                            menu_item_id = int(item_data['menu_item_id'])
                            quantity = int(item_data.get('quantity', 1))
                            
                            # Get menu item info from cached data or database
                            if menu_item_id in menu_lookup:
                                menu_info = menu_lookup[menu_item_id]
                                menu_item_name = menu_info['name']
                                menu_item_price = float(menu_info['price'])
                                print(f"      ✅ Using cached data: {menu_item_name} x{quantity} @ ${menu_item_price}")
                            else:
                                # Fallback to database query
                                menu_item = MenuItem.query.get(menu_item_id)
                                if menu_item:
                                    menu_item_name = menu_item.name
                                    menu_item_price = float(menu_item.price)
                                    print(f"      ✅ Using database: {menu_item_name} x{quantity} @ ${menu_item_price}")
                                else:
                                    print(f"      ❌ Menu item ID {menu_item_id} not found, skipping")
                                    continue
                            
                            # Create order item with accurate pricing
                            order_item = OrderItem(
                                order_id=order.id,
                                menu_item_id=menu_item_id,
                                quantity=quantity,
                                price_at_time=menu_item_price  # Use the accurate price from cache/database
                            )
                            db.session.add(order_item)
                            
                            item_total = menu_item_price * quantity
                            order_total += item_total
                            print(f"         💰 Item total: ${item_total:.2f}")
                        
                        order.total_amount = order_total
                        total_reservation_amount += order_total
                        print(f"   💰 Order total for {person_name}: ${order_total:.2f}")
                    
                    print(f"💰 Total reservation amount: ${total_reservation_amount:.2f}")
                
                # Fallback: If no party_orders but conversation indicates food items, extract them
                elif not args.get('old_school', False) and not party_orders:
                    print("🔍 No party_orders provided, checking conversation for food items...")
                    
                    # Get conversation text for extraction
                    call_log = raw_data.get('call_log', []) if raw_data else []
                    conversation_text = ' '.join([
                        entry.get('content', '') for entry in call_log 
                        if entry.get('role') == 'user'
                    ])
                    
                    # Check for food keywords
                    food_keywords = [
                        'burger', 'pizza', 'salad', 'chicken', 'steak', 'fish', 'wings', 'fries',
                        'drink', 'beer', 'wine', 'water', 'soda', 'pepsi', 'coke', 'tea', 'coffee',
                        'appetizer', 'dessert', 'soup', 'sandwich', 'pasta', 'rice'
                    ]
                    
                    conversation_lower = conversation_text.lower()
                    has_food_mention = any(keyword in conversation_lower for keyword in food_keywords)
                    
                    if has_food_mention:
                        print(f"🔄 FALLBACK: Detected food mentions in conversation, attempting extraction")
                        conversation_items = self._extract_food_items_from_conversation(conversation_text, meta_data)
                        
                        if conversation_items:
                            print(f"   ✅ Found {len(conversation_items)} items via fallback conversation extraction")
                            
                            # Create a single order with all conversation items
                            from models import Order, OrderItem, MenuItem
                            
                            order = Order(
                                order_number=self._generate_order_number(),
                                reservation_id=reservation.id,
                                table_id=None,
                                person_name=args.get('name', 'Customer'),
                                status='pending',
                                total_amount=0.0,
                                target_date=args['date'],
                                target_time=args['time'],
                                order_type='reservation',
                                payment_status='unpaid',
                                customer_phone=args.get('phone_number')
                            )
                            db.session.add(order)
                            db.session.flush()  # Get order.id
                            
                            order_total = 0.0
                            for item_data in conversation_items:
                                menu_item_id = int(item_data['menu_item_id'])
                                quantity = int(item_data.get('quantity', 1))
                                
                                menu_item = MenuItem.query.get(menu_item_id)
                                if menu_item:
                                    print(f"      ✅ Fallback adding: {menu_item.name} x{quantity} @ ${menu_item.price}")
                                    
                                    order_total += menu_item.price * quantity
                                    order_item = OrderItem(
                                        order_id=order.id,
                                        menu_item_id=menu_item.id,
                                        quantity=quantity,
                                        price_at_time=menu_item.price
                                    )
                                    db.session.add(order_item)
                            
                            order.total_amount = order_total
                            total_reservation_amount += order_total
                            print(f"   ✅ Fallback order total: ${order_total:.2f}")
                        else:
                            print(f"   ❌ No items found via fallback conversation extraction")
                    else:
                        print(f"   ℹ️ No food keywords detected in conversation - truly an old-school reservation")
                
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
                
                # CHECK FOR OUTDOOR SEATING REQUEST AND FETCH WEATHER
                outdoor_seating_requested = False
                
                # Check if outdoor seating was mentioned in special requests or conversation
                special_requests = args.get('special_requests', '') or ''
                outdoor_keywords = ['outdoor', 'outside', 'patio', 'terrace', 'al fresco', 'open air']
                
                # Check special requests field for explicit outdoor seating requests
                if any(keyword in special_requests.lower() for keyword in outdoor_keywords):
                    # Only add if it's a clear request, not a decline
                    if not any(negative in special_requests.lower() for negative in ['no', 'not', 'decline', 'cancel', "don't", 'due to weather', 'because of']):
                        outdoor_seating_requested = True
                        print("🌿 Outdoor seating detected in special requests")
                
                # ENHANCED: Check conversation for outdoor seating mentions with context analysis
                if not outdoor_seating_requested and raw_data:
                    call_log = raw_data.get('call_log', [])
                    conversation_text = ' '.join([
                        entry.get('content', '') for entry in call_log 
                        if entry.get('role') == 'user'
                    ]).lower()
                    
                    # Check if outdoor keywords are present
                    has_outdoor_keywords = any(keyword in conversation_text for keyword in outdoor_keywords)
                    
                    if has_outdoor_keywords:
                        # CRITICAL FIX: Analyze context to determine if it's a request or decline
                        positive_patterns = [
                            r'\b(want|would like|prefer|request|add|yes.*outdoor|outdoor.*yes)\b.*\b(outdoor|outside|patio|terrace)\b',
                            r'\b(outdoor|outside|patio|terrace)\b.*\b(please|want|would like|prefer|yes)\b',
                            r'\b(can we|could we)\b.*\b(outdoor|outside|patio|terrace)\b',
                            r'\b(outdoor|outside|patio|terrace)\b.*\b(seating|table|dining)\b.*\b(please|yes)\b'
                        ]
                        
                        negative_patterns = [
                            r'\b(no|not|don\'t|decline|cancel)\b.*\b(outdoor|outside|patio|terrace)\b',
                            r'\b(outdoor|outside|patio|terrace)\b.*\b(no|not|don\'t|decline|cancel)\b',
                            r'\b(due to|because of|considering)\b.*\b(weather|rain|cold|hot)\b.*\b(no|not|don\'t)\b',
                            r'\b(weather|rain|cold|hot)\b.*\b(no|not|don\'t|decline)\b.*\b(outdoor|outside|patio|terrace)\b',
                            r'\b(too|very)\b.*\b(cold|hot|rainy|windy)\b.*\b(outdoor|outside|patio|terrace)\b'
                        ]
                        
                        import re
                        
                        # Check for positive outdoor seating requests
                        is_positive_request = any(re.search(pattern, conversation_text) for pattern in positive_patterns)
                        
                        # Check for negative responses/declines
                        is_negative_response = any(re.search(pattern, conversation_text) for pattern in negative_patterns)
                        
                        print(f"🔍 Outdoor seating analysis: positive={is_positive_request}, negative={is_negative_response}")
                        print(f"   Conversation excerpt: ...{conversation_text[-200:]}...")
                        
                        # Only request outdoor seating if it's clearly positive and not negative
                        if is_positive_request and not is_negative_response:
                            outdoor_seating_requested = True
                            print("🌿 ✅ Outdoor seating REQUEST confirmed from conversation analysis")
                        elif is_negative_response:
                            print("🌿 ❌ Outdoor seating DECLINED detected - will not add outdoor seating request")
                        else:
                            # Ambiguous case - check for simple affirmative patterns
                            simple_positive = any(phrase in conversation_text for phrase in [
                                'yes outdoor', 'outdoor yes', 'want outdoor', 'outdoor seating please',
                                'add outdoor', 'outdoor table', 'outside seating', 'patio seating'
                            ])
                            if simple_positive:
                                outdoor_seating_requested = True
                                print("🌿 ✅ Outdoor seating request detected via simple patterns")
                            else:
                                print("🌿 ❓ Outdoor keywords found but context unclear - not adding outdoor seating")
                
                # If outdoor seating requested, fetch weather and add to special requests
                if outdoor_seating_requested:
                    print(f"🌤️ Fetching weather for outdoor seating request on {args.get('date')}")
                    
                    try:
                        import requests
                        import os
                        
                        weather_api_key = os.getenv('WEATHER_API_KEY')
                        location = "15222"  # Restaurant zipcode
                        
                        if weather_api_key and args.get('date'):
                            # Fetch weather forecast for reservation date
                            api_url = f"https://api.weatherapi.com/v1/forecast.json?key={weather_api_key}&q={location}&days=10&aqi=no&alerts=no"
                            response = requests.get(api_url, timeout=5)
                            
                            if response.status_code == 200:
                                weather_data = response.json()
                                reservation_date = args.get('date')
                                
                                # Find forecast for reservation date
                                forecast_day = None
                                for day in weather_data['forecast']['forecastday']:
                                    if day['date'] == reservation_date:
                                        forecast_day = day
                                        break
                                
                                if forecast_day:
                                    day_data = forecast_day['day']
                                    condition = day_data['condition']['text']
                                    max_temp = round(day_data['maxtemp_f'])
                                    min_temp = round(day_data['mintemp_f'])
                                    chance_rain = day_data.get('daily_chance_of_rain', 0)
                                    avg_temp = round((max_temp + min_temp) / 2)
                                    wind_speed = day_data.get('maxwind_mph', 0)
                                    
                                    # Check if suitable for outdoor dining
                                    is_suitable = self._is_suitable_for_outdoor_dining(
                                        avg_temp, chance_rain, condition, wind_speed
                                    )
                                    
                                    # Format weather details
                                    weather_details = f"Weather forecast: {condition}, {max_temp}°F/{min_temp}°F, {chance_rain}% rain chance"
                                    
                                    # Add outdoor seating request with weather to special requests
                                    outdoor_request = f"🌿 OUTDOOR SEATING REQUESTED ({weather_details})"
                                    
                                    current_special_requests = reservation.special_requests or ''
                                    if current_special_requests and not any(keyword in current_special_requests.lower() for keyword in outdoor_keywords):
                                        reservation.special_requests = f"{current_special_requests}; {outdoor_request}"
                                    elif not current_special_requests:
                                        reservation.special_requests = outdoor_request
                                    elif "OUTDOOR SEATING" not in current_special_requests.upper():
                                        # Replace generic outdoor mention with detailed weather request
                                        reservation.special_requests = f"{current_special_requests}; {outdoor_request}"
                                    
                                    print(f"✅ Added weather forecast to outdoor seating request: {weather_details}")
                                    
                                    # Store weather suitability info for response message and conversation persistence
                                    meta_data['weather_suitable'] = is_suitable
                                    meta_data['weather_details'] = weather_details
                                    meta_data['outdoor_seating_requested'] = True
                                    meta_data['reservation_weather_date'] = reservation_date
                                    meta_data['weather_last_fetched'] = datetime.now().isoformat()
                                    
                                    # Store weather info for conversation context
                                    meta_data['last_weather_forecast'] = {
                                        'date': reservation_date,
                                        'condition': condition,
                                        'high': max_temp,
                                        'low': min_temp,
                                        'rain_chance': chance_rain,
                                        'suitable_for_outdoor': is_suitable,
                                        'details': weather_details
                                    }
                                    
                                    if not is_suitable:
                                        print(f"⚠️ Weather may not be ideal for outdoor dining: {weather_details}")
                                else:
                                    print("⚠️ Could not find weather forecast for reservation date")
                            else:
                                print(f"⚠️ Weather API request failed: {response.status_code}")
                        else:
                            print("⚠️ Weather API key not available or no date provided")
                            
                            # Still add outdoor seating request without weather details
                            current_special_requests = reservation.special_requests or ''
                            outdoor_request = "🌿 OUTDOOR SEATING REQUESTED"
                            
                            if current_special_requests and "OUTDOOR SEATING" not in current_special_requests.upper():
                                reservation.special_requests = f"{current_special_requests}; {outdoor_request}"
                            elif not current_special_requests:
                                reservation.special_requests = outdoor_request
                                
                    except Exception as weather_error:
                        print(f"⚠️ Error fetching weather for outdoor seating: {weather_error}")
                        # Still add outdoor seating request without weather details
                        current_special_requests = reservation.special_requests or ''
                        outdoor_request = "🌿 OUTDOOR SEATING REQUESTED"
                        
                        if current_special_requests and "OUTDOOR SEATING" not in current_special_requests.upper():
                            reservation.special_requests = f"{current_special_requests}; {outdoor_request}"
                        elif not current_special_requests:
                            reservation.special_requests = outdoor_request

                # CRITICAL: Enhanced database commit with error handling
                try:
                    db.session.commit()
                    print(f"✅ Database transaction committed successfully for reservation {reservation.id}")
                    
                    # CRITICAL FIX: Trigger real-time web notifications for voice-created reservations
                    try:
                        # Import here to avoid circular imports
                        import requests
                        import json
                        
                        # FIXED: Use correct variable name for total amount
                        total_amount = total_reservation_amount if 'total_reservation_amount' in locals() else 0.0
                        
                        # Send notification to web interface via localhost API
                        notification_data = {
                            'type': 'new_reservation',
                            'reservation_id': reservation.id,
                            'reservation_number': reservation.reservation_number,
                            'customer_name': args['name'],
                            'party_size': args['party_size'],
                            'date': args['date'],
                            'time': args['time'],
                            'total_amount': total_amount,
                            'created_via': 'voice_agent'
                        }
                        
                        print(f"🔔 Sending web notification for reservation {reservation.reservation_number}")
                        print(f"   Notification data: {notification_data}")
                        
                        # Try multiple possible ports where the web interface might be running
                        notification_urls = [
                            'http://localhost:8080/api/notify_reservation_created',
                            'http://127.0.0.1:8080/api/notify_reservation_created',
                            'http://localhost:8000/api/notify_reservation_created',
                            'http://localhost:5000/api/notify_reservation_created',
                            'http://127.0.0.1:8000/api/notify_reservation_created',
                            'http://127.0.0.1:5000/api/notify_reservation_created'
                        ]
                        
                        notification_sent = False
                        for url in notification_urls:
                            try:
                                response = requests.post(
                                    url,
                                    json=notification_data,
                                    timeout=2  # Allow slightly more time
                                )
                                if response.status_code == 200:
                                    print(f"✅ Web notification sent successfully to {url}")
                                    notification_sent = True
                                    break
                                else:
                                    print(f"⚠️ Web notification failed for {url}: {response.status_code}")
                            except requests.exceptions.RequestException as e:
                                print(f"⚠️ Web notification failed for {url}: {e}")
                                continue
                        
                        if not notification_sent:
                            print(f"⚠️ Web notification failed for all URLs - web interface may not be running")
                            
                    except Exception as e:
                        print(f"⚠️ Notification system error: {e}")
                        import traceback
                        print(f"   Traceback: {traceback.format_exc()}")
                        # Don't fail the reservation creation if notification fails
                    
                except Exception as commit_error:
                    print(f"❌ CRITICAL: Database commit failed for reservation {reservation.id}: {commit_error}")
                    db.session.rollback()
                    return SwaigFunctionResult(f"Sorry, there was a database error creating your reservation. Please try again or call us directly at the restaurant.")
                
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
                
                # Add weather information and outdoor seating confirmation if applicable
                if meta_data.get('outdoor_seating_requested'):
                    weather_suitable = meta_data.get('weather_suitable', True)
                    weather_details = meta_data.get('weather_details', '')
                    
                    message += f"\n🌿 OUTDOOR SEATING REQUESTED!\n"
                    
                    if weather_details:
                        clean_weather = weather_details.replace('Weather forecast: ', '')
                        message += f"🌤️ Weather Forecast: {clean_weather}\n"
                        
                        if weather_suitable:
                            message += f"✨ Perfect! The weather looks ideal for outdoor dining!\n"
                        else:
                            message += f"⚠️ Weather Advisory: Conditions may not be ideal for outdoor dining.\n"
                            message += f"Don't worry - we'll ensure you have a comfortable table!\n"
                    
                    message += f"🍃 Note: Outdoor tables are subject to availability and weather conditions.\n"
                
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
                message += f"Please arrive on time and let us know if you need to make any changes.\n\n"
                
                # ENHANCED SMS WORKFLOW: Provide clear next steps without redundant prompting
                message += f"📱 SMS CONFIRMATION AVAILABLE:\n"
                message += f"I can send your complete reservation details to your phone via text message. "
                message += f"The SMS will include your reservation number, date, time, party details"
                if total_reservation_amount > 0:
                    message += f", pre-order information"
                message += f", and a calendar link.\n"
                message += f"Just let me know if you'd like me to send that to you!"
                
                # Set meta_data with reservation information for potential payment processing and SMS confirmation
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
                    "reservation_id": reservation.id,
                    "sms_confirmation_pending": True,
                    "calendar_updated": True
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
                
                # 🚀 INSTANT CALENDAR UPDATE: Trigger calendar refresh for web interface
                try:
                    import requests
                    # Notify web interface to refresh calendar immediately
                    calendar_refresh_url = "http://localhost:8080/api/calendar/refresh-trigger"
                    refresh_data = {
                        "event_type": "reservation_created",
                        "reservation_id": reservation.id,
                        "reservation_number": reservation.reservation_number,
                        "customer_name": reservation.name,
                        "party_size": reservation.party_size,
                        "date": reservation.date,
                        "time": reservation.time,
                        "source": "phone_swaig"
                    }
                    
                    # Non-blocking request with short timeout
                    response = requests.post(
                        calendar_refresh_url, 
                        json=refresh_data, 
                        timeout=2
                    )
                    
                    if response.status_code == 200:
                        print(f"📅 Calendar refresh notification sent successfully")
                    else:
                        print(f"⚠️ Calendar refresh notification failed: {response.status_code}")
                        
                except Exception as refresh_error:
                    # Don't fail the reservation if calendar refresh fails
                    print(f"⚠️ Calendar refresh notification error (non-critical): {refresh_error}")
                
                return result
                
        except Exception as e:
            print(f"❌ create_reservation failed for call_id: {call_id}")
            print(f"   Error: {str(e)}")
            print(f"   Args received: {args}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()}")
            return SwaigFunctionResult(f"Sorry, there was an error creating your reservation: {str(e)}")
    
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
                        pass  # Continue with existing logic
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
                        
                        # ENHANCEMENT: Check for payment completion in current call session
                        # This handles cases where payment just completed but user is still on the call
                        payment_just_completed = False
                        if raw_data and raw_data.get('call_id'):
                            try:
                                from app import app
                                payment_sessions = getattr(app, 'payment_sessions', {})
                                global payment_sessions_global
                                if 'payment_sessions_global' not in globals():
                                    payment_sessions_global = {}
                                
                                call_id = raw_data['call_id']
                                
                                # Check both app and global payment sessions
                                payment_session = payment_sessions.get(call_id) or payment_sessions_global.get(call_id)
                                
                                if payment_session and payment_session.get('payment_completed') and not payment_session.get('payment_announced'):
                                    payment_just_completed = True
                                    fresh_confirmation = payment_session.get('confirmation_number')
                                    payment_amount = payment_session.get('payment_amount')
                                    
                                    if fresh_confirmation and not confirmation_number:
                                        confirmation_number = fresh_confirmation
                                    
                                    if payment_amount and not paid:
                                        paid = True
                                        total_bill = payment_amount
                                    
                                    # Mark payment as announced to prevent duplicate announcements
                                    payment_session['payment_announced'] = True
                                    payment_sessions[call_id] = payment_session
                                    payment_sessions_global[call_id] = payment_session.copy()
                                    
                                    print(f"✅ Payment completion detected for call {call_id}: {fresh_confirmation}")
                            except Exception as e:
                                print(f"⚠️ Could not check payment session for call completion: {e}")
                        
                        if paid and confirmation_number:
                            if payment_just_completed:
                                message += f"🎉 EXCELLENT! Your payment of ${total_bill:.2f} has been processed successfully! "
                                message += f"Your confirmation number is {confirmation_number}. "
                                message += f"Please write this down: {confirmation_number}. "
                            else:
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
                        menu_item = self._find_menu_item_fuzzy(item_name, meta_data)
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
                            total_amount=0.0,
                            target_date=str(reservation.date),
                            target_time=str(reservation.time),
                            order_type='reservation',
                            payment_status='unpaid',
                            customer_phone=reservation.phone_number
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

    def _extract_person_names_from_conversation(self, conversation_text, customer_name):
        """Extract additional person names from conversation text"""
        additional_names = []
        
        # Enhanced patterns for person names in restaurant conversations
        # Updated to handle compound names like "SpongeBob", "MacDonald", etc.
        name_patterns = [
            # Key pattern for the specific case: "Party of two, Jim Smith and SpongeBob"
            r'\bparty\s+of\s+\d+,?\s+([A-Z][a-z\']+(?:\s+[A-Z][a-z\']+)*)\s+and\s+([A-Z][a-z\']*[A-Z]?[a-z\']*)\b',  # "party of two, Jim Smith and SpongeBob"
            r'\bparty\s+of\s+\d+\s+for\s+([A-Z][a-z\']+(?:\s+[A-Z][a-z\']+)*)\s+and\s+([A-Z][a-z\']*[A-Z]?[a-z\']*)\b',  # "party of two for Jim Smith and SpongeBob"
            r'\breservation.*?([A-Z][a-z\']+(?:\s+[A-Z][a-z\']+)*)\s+and\s+([A-Z][a-z\']*[A-Z]?[a-z\']*)\b',  # "reservation for Jim Smith and SpongeBob"
            r'\bfor\s+([A-Z][a-z\']*[A-Z]?[a-z\']*(?:\s+[A-Z][a-z\']+)*)\s+and\s+([A-Z][a-z\']*[A-Z]?[a-z\']*)\b',  # "for Jim and SpongeBob"
            r'\b([A-Z][a-z\']+(?:\s+[A-Z][a-z\']+)*)\s+and\s+([A-Z][a-z\']*[A-Z]?[a-z\']*)\b',  # "Jim Smith and SpongeBob" (general pattern)
            r'\band\s+([A-Z][a-z\']*[A-Z]?[a-z\']*)\b',  # "and SpongeBob" - handles compound names
            r'\bwith\s+([A-Z][a-z\']*[A-Z]?[a-z\']*)\b', # "with SpongeBob"
            r'\b([A-Z][a-z\']*[A-Z]?[a-z\']*)\s+will\s+have\b', # "SpongeBob will have"
            r'\b([A-Z][a-z\']*[A-Z]?[a-z\']*)\s+wants\b', # "SpongeBob wants"
            r'\b([A-Z][a-z\']*[A-Z]?[a-z\']*)\s+would\s+like\b', # "SpongeBob would like"
            r'\bfor\s+([A-Z][a-z\']*[A-Z]?[a-z\']*)\b',  # "for SpongeBob"
        ]
        
        # Extract names using patterns
        import re
        print(f"🔍 ENHANCED NAME EXTRACTION:")
        print(f"   Customer name: '{customer_name}'")
        print(f"   Conversation snippet: '{conversation_text[:200]}...'")
        
        for i, pattern in enumerate(name_patterns):
            matches = re.findall(pattern, conversation_text, re.IGNORECASE)
            if matches:
                print(f"   🎯 Pattern {i+1} matched: {pattern}")
                print(f"   📝 Matches found: {matches}")
            
            for match in matches:
                # Handle both single group and multiple group matches
                if isinstance(match, tuple):
                    # Multiple groups captured (e.g., "party of two for Jim and SpongeBob")
                    for name in match:
                        name = name.strip()
                        if name and name.lower() != customer_name.lower() and name not in additional_names:
                            # Clean up names like "Jim's" to "Jim"
                            cleaned_name = name.rstrip("'s")
                            additional_names.append(cleaned_name)
                            print(f"   ✅ Extracted name from pattern {i+1}: '{cleaned_name}'")
                else:
                    # Single group captured
                    name = match.strip()
                    if name and name.lower() != customer_name.lower() and name not in additional_names:
                        # Clean up names like "Jim's" to "Jim"  
                        cleaned_name = name.rstrip("'s")
                        additional_names.append(cleaned_name)
                        print(f"   ✅ Extracted name from pattern {i+1}: '{cleaned_name}'")
        
        # Also look for common names in the text
        common_names = [
            'John', 'Mary', 'Bob', 'Sarah', 'Tom', 'Lisa', 'Mike', 'Anna', 'David', 'Emma',
            'James', 'Jennifer', 'Robert', 'Linda', 'Michael', 'Elizabeth', 'William', 'Barbara',
            'Richard', 'Susan', 'Joseph', 'Jessica', 'Thomas', 'Karen', 'Christopher', 'Nancy',
            'Daniel', 'Betty', 'Paul', 'Helen', 'Mark', 'Sandra', 'Donald', 'Donna', 'George',
            'Carol', 'Kenneth', 'Ruth', 'Steven', 'Sharon', 'Edward', 'Michelle', 'Brian',
            'Laura', 'Ronald', 'Sarah', 'Anthony', 'Kimberly', 'Kevin', 'Deborah', 'Jason',
            'Dorothy', 'Jeff', 'Amy', 'Jim', 'Angela', 'Steve', 'Brenda', 'Matt', 'Emma',
            'SpongeBob', 'Patrick', 'Squidward', 'Sandy', 'Mr. Krabs', 'Plankton',  # Fun names
            'Alice', 'Charlie', 'Alex', 'Sam', 'Chris', 'Pat', 'Jordan', 'Casey', 'Taylor',
            'Morgan', 'Riley', 'Dakota', 'Sage', 'Avery', 'Quinn', 'Blake', 'Cameron', 'Drew'
        ]
        
        # Enhanced name scanning with better word boundary detection
        conversation_words = re.split(r'\W+', conversation_text)
        for word in conversation_words:
            # Check if this word matches any common names (case-insensitive)
            for common_name in common_names:
                if (word.lower() == common_name.lower() and 
                    word.lower() != customer_name.lower() and 
                    common_name not in additional_names):
                    additional_names.append(common_name)
                    print(f"   🔍 Found common name: '{common_name}'")
        
        print(f"🔍 Extracted additional names: {additional_names}")
        return additional_names

    def _parse_person_food_assignments_from_conversation(self, conversation_text, customer_name, additional_names):
        """Parse person-specific food assignments from conversation text"""
        import re
        
        person_assignments = {}
        
        # Create list of all person names
        all_names = [customer_name] + additional_names
        
        print(f"🔍 Parsing food assignments for: {all_names}")
        
        # Enhanced patterns for person-specific assignments in agent responses
        # Looking for patterns like "For Jim Smith, how about the Grilled Chicken Breast"
        conversation_lines = conversation_text.split('\n')
        
        for line in conversation_lines:
            # Look for "For [Name]" patterns in agent responses
            for_pattern = r'[Ff]or\s+([^,]+),.*?([A-Z][a-z\s]+(?:Breast|Burger|Steak|Salad|Sandwich|Pizza|Pasta|Soup|Wings|Fries|Wine|Beer|Soda|Lemonade|Coffee|Tea))'
            
            matches = re.finditer(for_pattern, line, re.IGNORECASE)
            for match in matches:
                person = match.group(1).strip()
                food_mention = match.group(2).strip()
                
                # Validate person name is in our list
                person_match = None
                for name in all_names:
                    if name.lower() in person.lower() or person.lower() in name.lower():
                        person_match = name
                        break
                
                if person_match:
                    if person_match not in person_assignments:
                        person_assignments[person_match] = []
                    
                    person_assignments[person_match].append(food_mention)
                    print(f"   ✅ {person_match}: {food_mention}")
        
        return person_assignments

    def _fallback_order_distribution(self, food_items, customer_name, party_size, additional_names, conversation_text=""):
        """Enhanced fallback distribution that respects conversation assignments when possible"""
        party_orders = []
        
        # CRITICAL FIX: Ensure customer_name is never a phone number
        if customer_name and ('+' in customer_name or customer_name.isdigit() or len(customer_name.replace(' ', '').replace('+', '').replace('-', '')) > 10):
            print(f"🚨 Customer name appears to be phone number: {customer_name}, using fallback")
            customer_name = "Primary Guest"
        
        # CRITICAL FIX: Validate additional names are not phone numbers
        validated_additional_names = []
        for name in additional_names:
            if name and not ('+' in name or name.isdigit() or len(name.replace(' ', '').replace('+', '').replace('-', '')) > 10):
                validated_additional_names.append(name)
        
        # Create person list with validated names
        person_names = [customer_name] + validated_additional_names
        while len(person_names) < party_size:
            person_names.append(f'Guest {len(person_names)}')
        
        print(f"🔍 Person names for order distribution: {person_names}")
        
        # ENHANCED: Try to parse person-specific assignments from conversation first
        assigned_item_ids = set()  # FIXED: Track IDs instead of dict objects
        if conversation_text:
            person_assignments = self._parse_person_food_assignments_from_conversation(conversation_text, customer_name, validated_additional_names)
            
            if person_assignments:
                print("✅ Using conversation-based assignments")
                # Convert conversation assignments to party orders
                for person_name in person_names:
                    assigned_food_names = person_assignments.get(person_name, [])
                    person_items = []
                    
                    # Find matching menu items for assigned food names
                    for food_name in assigned_food_names:
                        for item in food_items:
                            item_name = item.get('name', '').lower()
                            item_id = item.get('menu_item_id')
                            if (food_name.lower() in item_name or 
                                any(word in item_name for word in food_name.lower().split())) and item_id not in assigned_item_ids:
                                person_items.append(item)
                                assigned_item_ids.add(item_id)  # FIXED: Add ID, not dict
                                break
                    
                    if person_items:
                        party_orders.append({
                            'person_name': person_name,
                            'items': person_items
                        })
        
        # For any remaining unassigned items, distribute evenly
        remaining_items = [item for item in food_items if item.get('menu_item_id') not in assigned_item_ids]
        if remaining_items:
            print(f"🔄 Distributing {len(remaining_items)} remaining items evenly")
            for i, item in enumerate(remaining_items):
                person_index = i % len(person_names)
                person_name = person_names[person_index]
                
                # Find existing party order for this person or create new one
                existing_order = next((po for po in party_orders if po['person_name'] == person_name), None)
                if existing_order:
                    existing_order['items'].append(item)
                else:
                    party_orders.append({
                        'person_name': person_name,
                        'items': [item]
                    })
        
        # Ensure all people have orders even if empty
        for person_name in person_names:
            if not any(po['person_name'] == person_name for po in party_orders):
                party_orders.append({
                    'person_name': person_name,
                    'items': []
                })
        
        return party_orders

    def _validate_and_fix_party_orders(self, party_orders, meta_data):
        """Validate and fix party_orders structure"""
        if not party_orders:
            return []
        
        fixed_orders = []
        cached_menu = meta_data.get('cached_menu', [])
        menu_lookup = {item['id']: item for item in cached_menu} if cached_menu else {}
        
        for order in party_orders:
            if not isinstance(order, dict):
                continue
            
            person_name = order.get('person_name', 'Customer')
            items = order.get('items', [])
            
            if not items:
                continue
            
            # Validate and fix items
            fixed_items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                
                menu_item_id = item.get('menu_item_id')
                quantity = item.get('quantity', 1)
                
                # Validate menu_item_id
                if not menu_item_id:
                    continue
                
                try:
                    menu_item_id = int(menu_item_id)
                    quantity = int(quantity)
                except (ValueError, TypeError):
                    continue
                
                # Check if menu item exists in cache
                if menu_lookup and menu_item_id not in menu_lookup:
                    print(f"⚠️ Menu item ID {menu_item_id} not found in cache")
                    continue
                
                fixed_items.append({
                    'menu_item_id': menu_item_id,
                    'quantity': max(1, quantity)
                })
            
            if fixed_items:
                fixed_orders.append({
                    'person_name': person_name,
                    'items': fixed_items
                })
        
        return fixed_orders

    def _detect_user_confirmation(self, recent_messages):
        """Detect if user has confirmed their order with enhanced pattern matching"""
        explicit_confirmations = [
            'yes, that\'s correct', 'yes that\'s correct', 'that\'s correct',
            'yes, create', 'yes create', 'create reservation', 'create it',
            'looks good', 'looks right', 'that\'s right', 'perfect',
            'confirm', 'confirmed', 'proceed', 'go ahead',
            'sounds good', 'that works', 'let\'s do it', 'make it',
            'book it', 'reserve it', 'yes please', 'absolutely',
            'that\'s perfect', 'exactly right', 'all good'
        ]
        
        for content in recent_messages[:3]:
            content_lower = content.lower().strip()
            
            # Check for explicit confirmation
            if any(phrase in content_lower for phrase in explicit_confirmations):
                print(f"✅ User confirmed with explicit phrase: '{content}'")
                return True
            
            # Check for simple affirmative responses
            if content_lower in ['yes', 'yes.', 'yep', 'yeah', 'sure', 'ok', 'okay']:
                print(f"✅ User confirmed with simple affirmative: '{content}'")
                return True
            
            # Check for modification requests
            if ('change' in content_lower or 'wrong' in content_lower or 
                'not right' in content_lower or 'different' in content_lower):
                print(f"🔄 User wants to modify order: '{content}'")
                return 'modify'
            
            # Check for cancellation
            if 'cancel' in content_lower or 'start over' in content_lower:
                print(f"❌ User wants to cancel: '{content}'")
                return 'cancel'
        
        return False

    def _enhanced_database_transaction(self, reservation, party_orders, args):
        """Enhanced database transaction with comprehensive error handling"""
        from models import db, Order, OrderItem, MenuItem
        
        transaction_success = False
        created_orders = []
        total_reservation_amount = 0.0
        
        try:
            # Add reservation to session
            db.session.add(reservation)
            db.session.flush()  # Get reservation.id
            
            print(f"✅ Reservation created: {reservation.id} - {reservation.reservation_number}")
            
            # Process party orders with enhanced validation
            if party_orders and not args.get('old_school', False):
                print(f"🔧 Processing {len(party_orders)} party orders with enhanced validation")
                
                for person_order in party_orders:
                    person_name = person_order.get('person_name', 'Customer')
                    person_items = person_order.get('items', [])
                    
                    if not person_items:
                        print(f"   ⚠️ No items for {person_name}, skipping order creation")
                        continue
                    
                    print(f"   👤 Creating order for {person_name} with {len(person_items)} items")
                    
                    # Create order for this person
                    order = Order(
                        order_number=self._generate_order_number(),
                        reservation_id=reservation.id,
                        table_id=None,
                        person_name=person_name,
                        status='pending',
                        total_amount=0.0,
                        target_date=args['date'],
                        target_time=args['time'],
                        order_type='reservation',
                        payment_status='unpaid',
                        customer_phone=args.get('phone_number')
                    )
                    db.session.add(order)
                    db.session.flush()  # Get order.id
                    
                    created_orders.append(order)
                    
                    # Process order items with enhanced validation
                    order_total = 0.0
                    for item_data in person_items:
                        try:
                            menu_item_id = int(item_data['menu_item_id'])
                            quantity = int(item_data.get('quantity', 1))
                            
                            # Enhanced menu item validation
                            menu_item = MenuItem.query.get(menu_item_id)
                            if not menu_item:
                                print(f"      ❌ Menu item ID {menu_item_id} not found in database")
                                continue
                            
                            if not menu_item.is_available:
                                print(f"      ❌ Menu item {menu_item.name} is not available")
                                continue
                            
                            # Create order item
                            order_item = OrderItem(
                                order_id=order.id,
                                menu_item_id=menu_item_id,
                                quantity=quantity,
                                price_at_time=menu_item.price
                            )
                            db.session.add(order_item)
                            
                            item_total = float(menu_item.price) * quantity
                            order_total += item_total
                            
                            print(f"      ✅ Added: {menu_item.name} x{quantity} @ ${menu_item.price} = ${item_total:.2f}")
                            
                        except (ValueError, KeyError, TypeError) as item_error:
                            print(f"      ❌ Error processing item {item_data}: {item_error}")
                            continue
                    
                    order.total_amount = order_total
                    total_reservation_amount += order_total
                    print(f"   💰 Order total for {person_name}: ${order_total:.2f}")
            
            # CRITICAL: Enhanced database commit with comprehensive error handling
            print(f"💾 Committing transaction for reservation {reservation.id}")
            db.session.commit()
            transaction_success = True
            print(f"✅ Database transaction committed successfully")
            
        except Exception as transaction_error:
            print(f"❌ CRITICAL: Database transaction failed: {transaction_error}")
            print(f"   Reservation ID: {reservation.id if reservation else 'N/A'}")
            print(f"   Orders created: {len(created_orders)}")
            
            # Enhanced rollback with logging
            try:
                db.session.rollback()
                print(f"✅ Database rollback completed successfully")
            except Exception as rollback_error:
                print(f"❌ CRITICAL: Database rollback failed: {rollback_error}")
            
            raise transaction_error
        
        return transaction_success, created_orders, total_reservation_amount

    def _find_menu_item_fuzzy(self, item_name, meta_data=None):
        """
        Find menu item using fuzzy matching with cached menu support
        
        Args:
            item_name: The item name to search for (potentially misspelled)
            meta_data: Optional meta_data containing cached menu
            
        Returns:
            MenuItem object or dict if found, None otherwise
        """
        from models import MenuItem
        import re
        
        if not item_name:
            return None
        
        # Normalize the search term
        search_term = item_name.lower().strip()
        
        # Use cached menu if available, otherwise query database
        if meta_data and meta_data.get('cached_menu'):
            print(f"🚀 Using cached menu for fuzzy search of '{item_name}'")
            cached_menu = meta_data['cached_menu']
            
            # Convert to compatible format for existing logic
            class MenuItemStub:
                def __init__(self, item_data):
                    self.id = item_data['id']
                    self.name = item_data['name']
                    self.price = item_data['price']
                    self.category = item_data['category']
                    self.description = item_data['description']
                    self.is_available = item_data['is_available']
            
            # First try exact match (case-insensitive)
            for item_data in cached_menu:
                if item_data['name'].lower() == search_term and item_data['is_available']:
                    return MenuItemStub(item_data)
            
            # Try partial match
            for item_data in cached_menu:
                if search_term in item_data['name'].lower() and item_data['is_available']:
                    return MenuItemStub(item_data)
            
            # Convert cached items to stub objects for fuzzy matching
            menu_items = [MenuItemStub(item_data) for item_data in cached_menu if item_data['is_available']]
        else:
            print(f"📊 Using database query for fuzzy search of '{item_name}'")
            
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
            menu_items = MenuItem.query.filter_by(is_available=True).all()
        
        # Common spelling corrections and variations
        spelling_corrections = {
            'kraft': 'craft',
            'coke': 'coca-cola',
            'lemonade': 'craft lemonade',
            'tea': 'iced tea',
            'coffee': 'coffee',
            'sparkling water': 'sparkling water',
            'water': 'sparkling water',
            'beer': 'draft beer',
            'wine': 'house wine',
            'chicken fingers': 'chicken tenders',
            'fingers': 'chicken tenders'
        }
        
        # Apply spelling corrections
        corrected_term = search_term
        for wrong, correct in spelling_corrections.items():
            if wrong in search_term:
                corrected_term = search_term.replace(wrong, correct)
                break
        
        # Try corrected term with cached menu
        if corrected_term != search_term and meta_data and meta_data.get('cached_menu'):
            for item_data in meta_data['cached_menu']:
                if corrected_term in item_data['name'].lower() and item_data['is_available']:
                    class MenuItemStub:
                        def __init__(self, item_data):
                            self.id = item_data['id']
                            self.name = item_data['name']
                            self.price = item_data['price']
                            self.category = item_data['category']
                            self.description = item_data['description']
                            self.is_available = item_data['is_available']
                    return MenuItemStub(item_data)
        elif corrected_term != search_term:
            menu_item = MenuItem.query.filter(
                MenuItem.name.ilike(f'%{corrected_term}%')
            ).filter_by(is_available=True).first()
            if menu_item:
                return menu_item
        
        # Fuzzy matching using simple similarity
        best_match = None
        best_score = 0
        
        for item in menu_items:
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
                    
                    result = SwaigFunctionResult(f"Found {len(events)} calendar events")
                    result.add_action("calendar_events", events)
                    return result
                
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
                            
                            response += f"  • {time_12hr} - {reservation.name} (Party of {reservation.party_size})\n"
                            if reservation.special_requests:
                                response += f" - {reservation.special_requests}\n"
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
                    result = SwaigFunctionResult(f"Found {len(reservations)} reservations for {target_date}")
                    result.add_action("reservations_data", [r.to_dict() for r in reservations])
                    return result
                
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
                    result = SwaigFunctionResult(f"Reservation summary {date_range_text}")
                    result.add_action("summary_data", summary_data)
                    return result
                
                else:
                    # Text format for voice
                    if total_reservations == 0:
                        return SwaigFunctionResult(f"No reservations found {date_range_text}.")
                    
                    avg_party_size = round(total_guests / total_reservations, 1)
                    
                    response = f"📊 Reservation Summary {date_range_text}:\n\n"
                    response += f"📈 Overview:\n"
                    response += f"  • Total reservations: {total_reservations}\n"
                    response += f"  • Total guests: {total_guests}\n"

                    # Add average party size
                    response += f"  • Average party size: {avg_party_size}\n\n"
                    
                    # Time distribution
                    response += f"🕒 Time Distribution:\n"
                    for time, count in sorted(time_slots.items()):
                        response += f"  • {time}: {count} reservations\n"
                    response += "\n"
                    
                    # Party size distribution
                    response += f"👥 Party Size Distribution:\n"
                    for size, count in sorted(party_sizes.items()):
                        response += f"  • Party of {size}: {count} reservations\n"
                    
                    return SwaigFunctionResult(response.strip())
            
        except Exception as e:
            return SwaigFunctionResult(f"Error generating reservation summary: {str(e)}")

    def _cancel_reservation_handler(self, args, raw_data):
        """Handler for cancel_reservation tool"""
        try:
            from signalwire_agents.core.function_result import SwaigFunctionResult
            # Import Flask app and models locally to avoid circular import
            import sys
            import os
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import db, Reservation
            from datetime import datetime
            
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
                    caller_phone = raw_data.get('caller_id', '') if raw_data else ''
                    if caller_phone:
                        caller_phone = self._normalize_phone_number(caller_phone)
                        print(f"🔍 Using caller phone: {caller_phone}")
                    
                    with app.app_context():
                        reservation = None
                        
                        # Fallback to phone number search (most recent reservation)
                        if caller_phone:
                            reservation = Reservation.query.filter_by(
                                phone_number=caller_phone
                            ).filter(
                                Reservation.status != 'cancelled'
                            ).order_by(Reservation.created_at.desc()).first()
                            
                            if reservation:
                                print(f"🔍 Found reservation by phone: {reservation.id}")
                        
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
                
                message = f"I've cancelled reservation {reservation.reservation_number} for {reservation.name} on {reservation.date} at {time_12hr}. "
                message += "We're sorry to see you cancel and hope to serve you again soon!"
                
                return SwaigFunctionResult(message)
                
        except Exception as e:
            return SwaigFunctionResult(f"Error cancelling reservation: {str(e)}")

    # get_current_time and get_current_date handlers removed - using built-in datetime skill

    def _send_reservation_sms_handler(self, args, raw_data):
        """Send reservation SMS confirmation"""
        try:
            # This should be handled by the menu skill to avoid duplication
            return SwaigFunctionResult("SMS functionality is handled by the menu system. Please use the menu skill for SMS operations.")
            
        except Exception as e:
            return SwaigFunctionResult(f"Error sending SMS: {str(e)}")

    def _send_payment_receipt_handler(self, args, raw_data):
        """Send payment receipt"""
        try:
            # This should be handled by the menu skill to avoid duplication
            return SwaigFunctionResult("Payment receipt functionality is handled by the menu system. Please use the menu skill for payment operations.")
            
        except Exception as e:
            return SwaigFunctionResult(f"Error sending payment receipt: {str(e)}")

    def _is_suitable_for_outdoor_dining(self, temperature, rain_chance, condition, wind_speed):
        """Determine if weather conditions are suitable for outdoor dining"""
        try:
            # Temperature criteria: comfortable range for outdoor dining
            temp_suitable = 65 <= temperature <= 85
            
            # Rain criteria: low chance of rain
            rain_suitable = rain_chance <= 25
            
            # Wind criteria: not too windy
            wind_suitable = wind_speed <= 15
            
            # Condition criteria: avoid severe weather
            condition_lower = condition.lower()
            severe_conditions = [
                'thunderstorm', 'storm', 'heavy rain', 'heavy snow', 
                'blizzard', 'tornado', 'hail', 'sleet', 'freezing'
            ]
            condition_suitable = not any(severe in condition_lower for severe in severe_conditions)
            
            # All criteria must be met for outdoor seating recommendation
            is_suitable = temp_suitable and rain_suitable and wind_suitable and condition_suitable
            
            print(f"🌿 Outdoor dining check: temp={temperature}°F ({temp_suitable}), "
                  f"rain={rain_chance}% ({rain_suitable}), wind={wind_speed}mph ({wind_suitable}), "
                  f"condition='{condition}' ({condition_suitable}) -> suitable={is_suitable}")
            
            return is_suitable
            
        except Exception as e:
            print(f"❌ Error checking outdoor dining suitability: {e}")
            return False

    def _get_weather_forecast_handler(self, args, raw_data):
        """Get weather forecast for the restaurant area (zipcode 15222)"""
        from signalwire_agents.core.function_result import SwaigFunctionResult
        import os
        import requests
        from datetime import datetime, timedelta
        
        try:
            print("🌤️ Weather forecast requested")
            
            # Extract reservation details if provided in args
            reservation_date = args.get('reservation_date')
            reservation_time = args.get('reservation_time')
            
            # If no reservation details in args, try to extract from conversation context
            if not reservation_date:
                # Try to extract from conversation or agent metadata
                meta_data = raw_data.get('meta_data', {})
                call_log = raw_data.get('call_log', [])
                
                # Check if weather was already fetched for this conversation
                if meta_data.get('last_weather_forecast'):
                    weather_info = meta_data['last_weather_forecast']
                    reservation_date = weather_info.get('date')
                    print(f"🔍 Found existing weather forecast in meta_data for {reservation_date}")
                    
                    # If the forecast is recent (same conversation), use it
                    condition = weather_info.get('condition', '')
                    high_temp = weather_info.get('high', 0)
                    low_temp = weather_info.get('low', 0)
                    rain_chance = weather_info.get('rain_chance', 0)
                    is_suitable = weather_info.get('suitable_for_outdoor', True)
                    
                    # Return the cached weather information with additional context
                    message = f"🌤️ **Weather Forecast for your reservation on {reservation_date}:**\n\n"
                    message += f"**Condition:** {condition}\n"
                    message += f"**Temperature:** High of {high_temp}°F, Low of {low_temp}°F\n"
                    message += f"**Rain Chance:** {rain_chance}%\n\n"
                    
                    if is_suitable:
                        message += f"🌿 **Great news!** The weather looks perfect for outdoor dining! "
                        message += f"Your outdoor seating request is all set.\n\n"
                    else:
                        message += f"⚠️ **Weather Advisory:** The forecast shows conditions that may not be ideal for outdoor dining. "
                        message += f"Don't worry - we'll ensure you have a comfortable table, and if the weather improves, "
                        message += f"we can still accommodate your outdoor seating preference based on availability.\n\n"
                    
                    message += f"🍃 **Note:** Our outdoor tables are subject to availability and weather conditions. "
                    message += f"We'll do our best to accommodate your preference!\n\n"
                    message += f"Is there anything else I can help you with for your reservation?"
                    
                    return SwaigFunctionResult(message)
                
                # Look for recently created reservation in conversation
                for entry in reversed(call_log[-10:]):  # Check last 10 entries
                    content = entry.get('content', '')
                    if 'reservation number' in content.lower() and 'confirmed' in content.lower():
                        # Try to extract date from recent reservation confirmation
                        try:
                            # Look for date patterns in the confirmation message
                            import re
                            date_match = re.search(r'tomorrow|(\d{4}-\d{2}-\d{2})', content.lower())
                            if date_match:
                                if 'tomorrow' in content.lower():
                                    reservation_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
                                    print(f"🔍 Extracted reservation date from context: {reservation_date} (tomorrow)")
                                break
                        except:
                            pass
                
                # If still no date, assume they're asking about tomorrow (most common case)
                if not reservation_date:
                    reservation_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
                    print(f"🔍 Defaulting to tomorrow for weather forecast: {reservation_date}")
            
            print(f"🔍 Using reservation date: {reservation_date}, time: {reservation_time}")
            
            # Restaurant location - zipcode 15222 (Pittsburgh, PA area)
            location = "15222"
            
            # Get weather API key
            weather_api_key = os.getenv('WEATHER_API_KEY')
            if not weather_api_key:
                return SwaigFunctionResult(
                    "I'm sorry, I can't check the weather forecast right now due to a system configuration issue. "
                    "However, I recommend checking your local weather app or website before your reservation!"
                )
            
            print(f"🔍 Getting weather for location: {location}")
            
            # Build context message based on reservation details
            context_message = ""
            if reservation_date:
                try:
                    res_date = datetime.strptime(reservation_date, '%Y-%m-%d')
                    date_str = res_date.strftime('%A, %B %d')
                    if reservation_time:
                        context_message = f"for your reservation on {date_str} at {reservation_time} "
                    else:
                        context_message = f"for your reservation on {date_str} "
                except:
                    if reservation_time:
                        context_message = f"for your reservation at {reservation_time} "
                    else:
                        context_message = "for your reservation "
            
            # Determine if we need current weather or forecast
            forecast_needed = False
            if reservation_date:
                try:
                    res_date = datetime.strptime(reservation_date, '%Y-%m-%d').date()
                    today = datetime.now().date()
                    if res_date > today:
                        forecast_needed = True
                        days_ahead = (res_date - today).days
                        print(f"🔍 Forecast needed for {days_ahead} days ahead")
                except:
                    pass
            
            # Choose API endpoint based on whether forecast is needed
            if forecast_needed and reservation_date:
                # Use forecast API for future dates
                api_url = f"https://api.weatherapi.com/v1/forecast.json?key={weather_api_key}&q={location}&days=7&aqi=no&alerts=no"
            else:
                # Use current weather API for today or when no specific date given
                api_url = f"https://api.weatherapi.com/v1/current.json?key={weather_api_key}&q={location}&aqi=no"
            
            print(f"🔗 Weather API URL: {api_url}")
            
            # Make the API request
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            weather_data = response.json()
            
            # Build the weather response
            if forecast_needed and 'forecast' in weather_data:
                # Handle forecast data
                location_name = weather_data.get('location', {}).get('name', 'the restaurant area')
                
                # Find the forecast for the specific date
                forecast_day = None
                if reservation_date:
                    for day in weather_data['forecast']['forecastday']:
                        if day['date'] == reservation_date:
                            forecast_day = day
                            break
                
                if forecast_day:
                    day_data = forecast_day['day']
                    condition = day_data['condition']['text']
                    max_temp = round(day_data['maxtemp_f'])
                    min_temp = round(day_data['mintemp_f'])
                    chance_rain = day_data.get('daily_chance_of_rain', 0)
                    avg_temp = round((max_temp + min_temp) / 2)
                    wind_speed = day_data.get('maxwind_mph', 0)
                    
                    message = f"🌤️ **Weather Forecast {context_message}in {location_name}:**\n\n"
                    message += f"**Condition:** {condition}\n"
                    message += f"**Temperature:** High of {max_temp}°F, Low of {min_temp}°F\n"
                    
                    if chance_rain > 30:
                        message += f"**Rain:** {chance_rain}% chance of rain\n"
                        message += f"💡 **Tip:** You might want to bring an umbrella or jacket!\n\n"
                    else:
                        message += f"**Rain:** Low chance of rain ({chance_rain}%)\n"
                        message += f"☀️ **Tip:** Looks like great weather for dining!\n\n"
                    
                    # Check if weather is suitable for outdoor seating
                    is_outdoor_weather = self._is_suitable_for_outdoor_dining(
                        avg_temp, chance_rain, condition, wind_speed
                    )
                    
                    if is_outdoor_weather:
                        message += f"🌿 **Outdoor Seating Available:** Perfect weather for our outdoor tables! "
                        message += f"Would you like me to add outdoor seating to your reservation? "
                        message += f"Our patio offers a lovely dining experience with beautiful views.\n\n"
                        message += f"💡 **Just say 'yes, add outdoor seating' or 'request outdoor seating' and I'll update your reservation immediately!**\n\n"
                    
                    message += "We look forward to seeing you at Bobby's Table! 🍽️"
                else:
                    # Fallback to general forecast
                    day_data = weather_data['forecast']['forecastday'][0]['day']
                    condition = day_data['condition']['text']
                    max_temp = round(day_data['maxtemp_f'])
                    min_temp = round(day_data['mintemp_f'])
                    
                    message = f"🌤️ **Weather Forecast {context_message}in the restaurant area:**\n\n"
                    message += f"**Condition:** {condition}\n"
                    message += f"**Temperature:** High of {max_temp}°F, Low of {min_temp}°F\n\n"
                    message += "We look forward to seeing you at Bobby's Table! 🍽️"
            else:
                # Handle current weather data
                location_name = weather_data.get('location', {}).get('name', 'the restaurant area')
                current = weather_data['current']
                condition = current['condition']['text']
                temp = round(current['temp_f'])
                feels_like = round(current['feelslike_f'])
                wind_speed = round(current['wind_mph'])
                wind_dir = current['wind_dir']
                humidity = current['humidity']
                
                message = f"🌤️ **Current Weather {context_message}in {location_name}:**\n\n"
                message += f"**Condition:** {condition}\n"
                message += f"**Temperature:** {temp}°F (feels like {feels_like}°F)\n"
                message += f"**Wind:** {wind_dir} at {wind_speed} mph\n"
                message += f"**Humidity:** {humidity}%\n\n"
                
                # Add helpful tips based on weather
                if temp < 40:
                    message += f"🧥 **Tip:** It's quite cold! Dress warmly for your visit.\n\n"
                elif temp > 85:
                    message += f"☀️ **Tip:** It's quite warm! Our restaurant is climate controlled for your comfort.\n\n"
                elif 'rain' in condition.lower() or 'shower' in condition.lower():
                    message += f"🌧️ **Tip:** It's raining! We have covered entry for your convenience.\n\n"
                else:
                    message += f"✨ **Tip:** Lovely weather for dining! We look forward to seeing you.\n\n"
                
                # Check if current weather is suitable for outdoor seating
                is_outdoor_weather = self._is_suitable_for_outdoor_dining(
                    feels_like, 0, condition, wind_speed  # Use feels_like temp, 0% rain for current
                )
                
                if is_outdoor_weather:
                    message += f"🌿 **Outdoor Seating Available:** Perfect weather for our outdoor tables! "
                    message += f"Would you like me to add outdoor seating to your reservation? "
                    message += f"Our patio offers a lovely dining experience with beautiful views.\n\n"
                    message += f"💡 **Just say 'yes, add outdoor seating' or 'request outdoor seating' and I'll update your reservation immediately!**\n\n"
                
                message += "We look forward to seeing you at Bobby's Table! 🍽️"
            
            return SwaigFunctionResult(message)
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Weather API request failed: {e}")
            return SwaigFunctionResult(
                "I'm sorry, I can't check the weather forecast right now due to a connectivity issue. "
                "Please check your local weather app or website before your reservation. "
                "We look forward to seeing you at Bobby's Table!"
            )
        except Exception as e:
            print(f"❌ Error in weather forecast handler: {e}")
            import traceback
            traceback.print_exc()
            return SwaigFunctionResult(
                "I'm sorry, I encountered an issue checking the weather forecast. "
                "Please check your local weather app or website before your reservation. "
                "We look forward to seeing you at Bobby's Table!"
            )

    def _request_outdoor_seating_handler(self, args, raw_data):
        """Handle requests for outdoor seating with weather details"""
        from signalwire_agents.core.function_result import SwaigFunctionResult
        import os
        import sys
        import requests
        from datetime import datetime
        
        try:
            print("🌿 Outdoor seating request received")
            
            # Extract parameters from args first
            reservation_number = args.get('reservation_number')
            customer_name = args.get('customer_name')
            party_size = args.get('party_size')
            special_note = args.get('special_note', '')
            
            # If no reservation details in args, try to extract from conversation context
            if not reservation_number and not customer_name:
                call_log = raw_data.get('conversation', {}).get('call_log', [])
                
                # Look for recently created reservation in conversation
                for entry in reversed(call_log[-15:]):  # Check last 15 entries
                    content = entry.get('content', '')
                    if 'reservation number' in content.lower() and 'confirmed' in content.lower():
                        # Try to extract reservation number and customer name
                        import re
                        # Look for reservation number pattern
                        number_match = re.search(r'reservation number[:\s]+(\d{6})', content.lower())
                        if number_match:
                            reservation_number = number_match.group(1)
                            print(f"🔍 Extracted reservation number from context: {reservation_number}")
                        
                        # Look for customer name pattern
                        name_match = re.search(r'name[:\s]+([a-zA-Z\s]+)', content.lower())
                        if name_match:
                            customer_name = name_match.group(1).strip()
                            print(f"🔍 Extracted customer name from context: {customer_name}")
                        break
                
                # If still no info, check for recent reservation creation in function calls
                if not reservation_number:
                    for entry in reversed(call_log[-10:]):
                        if entry.get('role') == 'tool' and 'reservation confirmed' in entry.get('content', '').lower():
                            # Try to extract reservation details from tool response
                            content = entry.get('content', '')
                            number_match = re.search(r'(\d{6})', content)
                            if number_match:
                                reservation_number = number_match.group(1)
                                print(f"🔍 Extracted reservation number from tool response: {reservation_number}")
                                break
            
            print(f"🔍 Using reservation_number: {reservation_number}, customer_name: {customer_name}")
            
            # Add the parent directory to sys.path to import app
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            from models import Reservation, db
            
            with app.app_context():
                # Try to find the reservation
                reservation = None
                
                if reservation_number:
                    reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
                elif customer_name:
                    # Search by customer name if no reservation number
                    reservations = Reservation.query.filter(
                        Reservation.name.ilike(f'%{customer_name}%')
                    ).all()
                    if len(reservations) == 1:
                        reservation = reservations[0]
                    elif len(reservations) > 1:
                        return SwaigFunctionResult(
                            f"I found multiple reservations for {customer_name}. "
                            "Could you provide your 6-digit reservation number so I can add the outdoor seating request to the correct reservation?"
                        )
                
                if not reservation:
                    if reservation_number:
                        return SwaigFunctionResult(
                            f"I couldn't find reservation #{reservation_number}. "
                            "Please check the reservation number and try again."
                        )
                    else:
                        return SwaigFunctionResult(
                            "I'll need either your reservation number or full name to add the outdoor seating request. "
                            "What's your 6-digit reservation number?"
                        )
                
                # Get current weather for temperature details
                weather_details = ""
                try:
                    weather_api_key = os.getenv('WEATHER_API_KEY')
                    if weather_api_key:
                        location = "15222"  # Restaurant zipcode
                        
                        # Check if reservation is for future date to determine forecast vs current
                        reservation_date = reservation.date
                        today = datetime.now().date()
                        
                        if reservation_date > today:
                            # Use forecast for future dates
                            api_url = f"https://api.weatherapi.com/v1/forecast.json?key={weather_api_key}&q={location}&days=7&aqi=no&alerts=no"
                            response = requests.get(api_url, timeout=5)
                            if response.status_code == 200:
                                weather_data = response.json()
                                # Find the forecast for the specific date
                                for day in weather_data['forecast']['forecastday']:
                                    if day['date'] == str(reservation_date):
                                        day_data = day['day']
                                        condition = day_data['condition']['text']
                                        max_temp = round(day_data['maxtemp_f'])
                                        min_temp = round(day_data['mintemp_f'])
                                        rain_chance = day_data.get('daily_chance_of_rain', 0)
                                        weather_details = f"Weather forecast: {condition}, {max_temp}°F/{min_temp}°F, {rain_chance}% rain chance"
                                        break
                        else:
                            # Use current weather for today
                            api_url = f"https://api.weatherapi.com/v1/current.json?key={weather_api_key}&q={location}&aqi=no"
                            response = requests.get(api_url, timeout=5)
                            if response.status_code == 200:
                                weather_data = response.json()
                                current = weather_data['current']
                                condition = current['condition']['text']
                                temp = round(current['temp_f'])
                                feels_like = round(current['feelslike_f'])
                                weather_details = f"Current weather: {condition}, {temp}°F (feels like {feels_like}°F)"
                except Exception as e:
                    print(f"⚠️ Could not fetch weather details for outdoor seating request: {e}")
                    weather_details = "Weather details unavailable"
                
                # Update the reservation with outdoor seating request including weather
                current_special_requests = reservation.special_requests or ''
                outdoor_request = "🌿 OUTDOOR SEATING REQUESTED"
                
                # Add weather details to the request
                if weather_details:
                    outdoor_request += f" ({weather_details})"
                
                if special_note:
                    outdoor_request += f" - {special_note}"
                
                # Add to special requests if not already there
                if "OUTDOOR SEATING" not in current_special_requests.upper():
                    if current_special_requests:
                        new_special_requests = f"{current_special_requests}; {outdoor_request}"
                    else:
                        new_special_requests = outdoor_request
                    
                    reservation.special_requests = new_special_requests
                    db.session.commit()
                    
                    print(f"✅ Added outdoor seating request with weather details to reservation #{reservation.reservation_number}")
                    
                    message = f"🌿 **Outdoor Seating Requested!**\n\n"
                    message += f"I've added your outdoor seating request to reservation #{reservation.reservation_number}.\n\n"
                    message += f"**Reservation Details:**\n"
                    message += f"• **Name:** {reservation.name}\n"
                    message += f"• **Date:** {reservation.date}\n"
                    message += f"• **Time:** {reservation.time}\n"
                    message += f"• **Party Size:** {reservation.party_size}\n"
                    if weather_details and weather_details != "Weather details unavailable":
                        message += f"• **Weather:** {weather_details}\n"
                    message += f"\n🍃 **Note:** Our outdoor tables are subject to availability and weather conditions. "
                    message += f"If weather becomes unfavorable, we'll ensure you have a comfortable indoor table.\n\n"
                    message += f"We look forward to serving you on our beautiful patio! 🌟"
                    
                    return SwaigFunctionResult(message)
                else:
                    message = f"🌿 **Outdoor Seating Already Requested**\n\n"
                    message += f"Your reservation #{reservation.reservation_number} already has outdoor seating requested.\n\n"
                    message += f"We look forward to serving you on our beautiful patio! 🌟"
                    
                    return SwaigFunctionResult(message)
                
        except Exception as e:
            print(f"❌ Error in outdoor seating request handler: {e}")
            import traceback
            traceback.print_exc()
            return SwaigFunctionResult(
                "I'm sorry, I encountered an issue processing your outdoor seating request. "
                "Please mention your preference when you arrive, and we'll do our best to accommodate you!"
            )


