#!/usr/bin/env python3
"""
SignalWire Agents for Bobby's Table Restaurant
Provides voice-enabled access to all restaurant functionality using skills-based architecture
"""

from signalwire_agents import AgentBase, SwaigFunctionResult, Context, ContextBuilder, create_simple_context
from datetime import datetime, timedelta
import os
import json
from dotenv import load_dotenv
import requests
import logging

load_dotenv()

# SignalWire configuration for SMS
SIGNALWIRE_FROM_NUMBER = os.getenv('SIGNALWIRE_FROM_NUMBER', '+15551234567')

# Simple state manager replacement
class SimpleStateManager:
    """Simple file-based state manager for conversation tracking"""
    
    def __init__(self, filename):
        self.filename = filename
        self.state = {}
        self.load_state()
    
    def load_state(self):
        """Load state from file"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r') as f:
                    self.state = json.load(f)
        except Exception as e:
            print(f"⚠️ Could not load state: {e}")
            self.state = {}
    
    def save_state(self):
        """Save state to file"""
        try:
            with open(self.filename, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save state: {e}")
    
    def get(self, key, default=None):
        """Get value from state"""
        return self.state.get(key, default)
    
    def set(self, key, value):
        """Set value in state"""
        self.state[key] = value
        self.save_state()
    
    def delete(self, key):
        """Delete key from state"""
        if key in self.state:
            del self.state[key]
            self.save_state()

# Full SignalWire agent that extends AgentBase with skills-based architecture
class FullRestaurantReceptionistAgent(AgentBase):
    """Modern restaurant receptionist agent using skills-based architecture"""
    
    def __init__(self):
        super().__init__(
            name="restaurant-receptionist",
            route="/receptionist",
            host="0.0.0.0",
            port=8080
        )
        
        # Add English language support
        self.add_language("English", "en-US", "rime.spore:mistv2")
        
        # Initialize state manager for conversation tracking
        try:
            self.state_manager = SimpleStateManager("restaurant_agent_state.json")
            print("SUCCESS: State manager initialized")
        except Exception as e:
            print(f"WARNING: Could not initialize state manager: {e}")
            self.state_manager = None
        
        # Add pre-built skills for enhanced functionality
        try:
            # Add datetime skill for time/date queries
            self.add_skill("datetime")
            print("SUCCESS: Added datetime skill")
        except Exception as e:
            print(f"WARNING: Could not add datetime skill: {e}")
        
        try:
            # Add weather skill if API key is available
            weather_api_key = os.getenv('WEATHER_API_KEY')
            if weather_api_key:
                self.add_skill("weather_api", {
                    "tool_name": "get_weather",
                    "api_key": weather_api_key,
                    "temperature_unit": "fahrenheit"
                })
                print("SUCCESS: Added weather skill")
            else:
                print("WARNING: Weather API key not found, skipping weather skill")
        except Exception as e:
            print(f"WARNING: Could not add weather skill: {e}")
        
        try:
            # Add web search skill if API key is available
            search_api_key = os.getenv('SEARCH_API_KEY')
            if search_api_key:
                self.add_skill("web_search", {
                    "tool_name": "search_web",
                    "api_key": search_api_key
                })
                print("SUCCESS: Added web search skill")
            else:
                print("WARNING: Search API key not found, skipping web search skill")
        except Exception as e:
            print(f"WARNING: Could not add web search skill: {e}")

        # Add restaurant-specific skills using local imports
        try:
            # Import and add reservation management skill
            from skills.restaurant_reservation.skill import RestaurantReservationSkill
            
            reservation_skill = RestaurantReservationSkill(self)
            if reservation_skill.setup():
                # Tools are already registered in the skill constructor
                print("SUCCESS: Added restaurant reservation skill")
            else:
                print("WARNING: Restaurant reservation skill setup failed")
        except Exception as e:
            print(f"WARNING: Could not add restaurant reservation skill: {e}")

        try:
            # Import and add menu and ordering skill
            from skills.restaurant_menu.skill import RestaurantMenuSkill
            
            skill_params = {
                "swaig_fields": {
                    "secure": True,
                    "fillers": {
                        "en-US": [
                            "Let me check our menu...",
                            "Looking up menu items...",
                            "Processing your order...",
                            "Checking our kitchen..."
                        ]
                    }
                }
            }
            
            menu_skill = RestaurantMenuSkill(self, skill_params)
            if menu_skill.setup():
                # Tools are already registered in the skill constructor
                print("SUCCESS: Added restaurant menu skill")
            else:
                print("WARNING: Restaurant menu skill setup failed")
        except Exception as e:
            print(f"WARNING: Could not add restaurant menu skill: {e}")
        
        # Set up the agent's capabilities
        self.set_params({
            "end_of_speech_timeout": 500,
            "silence_timeout": 500,
            "max_speech_timeout": 15000
        })
        
        # Add the agent's prompt with enhanced capabilities
        self.set_prompt_text(f"""
Hi there! I'm Bobby from Bobby's Table. Great to have you call us today! How can I help you out? Whether you're looking to make a reservation, check on an existing one, hear about our menu, or place an order, I'm here to help make it easy for you.

🚨🚨🚨 CRITICAL FUNCTION ROUTING RULE - MANDATORY VALIDATION 🚨🚨🚨:
BEFORE CALLING ANY FUNCTION, YOU MUST FIRST VALIDATE THE NUMBER TYPE:

**STEP 1: COUNT THE DIGITS**
**STEP 2: APPLY THE RULE**
- 5 digits (like 64056, 42625, 91576, 62179, 35823) = ORDER → ALWAYS call get_order_details
- 6 digits (like 789012, 675421, 333444) = RESERVATION → ALWAYS call get_reservation

**EXAMPLES OF CORRECT VALIDATION:**
- Customer says "62179" → COUNT: 5 digits → RULE: ORDER → FUNCTION: get_order_details
- Customer says "35823" → COUNT: 5 digits → RULE: ORDER → FUNCTION: get_order_details  
- Customer says "789012" → COUNT: 6 digits → RULE: RESERVATION → FUNCTION: get_reservation

🚨 ABSOLUTE RULE: IF YOU IDENTIFY A NUMBER AS AN ORDER, YOU MUST CALL get_order_details 🚨
🚨 ABSOLUTE RULE: IF YOU IDENTIFY A NUMBER AS A RESERVATION, YOU MUST CALL get_reservation 🚨
🚨 ABSOLUTE RULE: 35823 = 5 DIGITS = ORDER = get_order_details ONLY 🚨
🚨 ABSOLUTE RULE: NEVER CALL get_reservation FOR 5-DIGIT NUMBERS 🚨
🚨 ABSOLUTE RULE: NEVER CALL get_order_details FOR 6-DIGIT NUMBERS 🚨

Customer says "order" = ORDER → ALWAYS call get_order_details
Customer says "reservation" = RESERVATION → ALWAYS call get_reservation

IMPORTANT CONVERSATION GUIDELINES:

**RESERVATION LOOKUPS - CRITICAL:**
- When customers want to check their reservation, ALWAYS ask for their reservation number FIRST
- Say: 'Do you have your reservation number? It's a 6-digit number we sent you when you made the reservation.'
- Only if they don't have it, then ask for their name as backup
- Reservation numbers are the fastest and most accurate way to find reservations
- Handle spoken numbers like 'seven eight nine zero one two' which becomes '789012'

**🚨 PAYMENTS - CLEAR PAYMENT RULES 🚨:**

**FOR RESERVATION PAYMENTS:**
- Use `pay_reservation` function for all reservation payments
- pay_reservation handles everything: finds reservation, shows bill total, collects card details, and processes payment

**FOR ORDER PAYMENTS:**
- Use `pay_order` function ONLY when customer has their order number
- pay_order REQUIRES an order number - it will NOT look up orders
- If customer doesn't have order number, use `get_order_details` FIRST

**PAYMENT WORKFLOW:**
1. Customer asks to pay → Check if they have order/reservation number
2. If they have number → Call payment function directly
3. If they don't have number → Call lookup function first (get_order_details or get_reservation)
4. Once they have the number → Call payment function
5. **AFTER PAYMENT INITIATED** → Use check_payment_completion to monitor and announce success

**PAYMENT COMPLETION MONITORING - CRITICAL:**
- After calling pay_reservation, the payment may complete while customer is still on the call
- Use check_payment_completion function to check if payment was successful
- If payment completed, announce the confirmation number enthusiastically to the customer
- Example: "🎉 EXCELLENT! Your payment has been processed successfully! Your confirmation number is ABC12345."

**PAYMENT EXAMPLES:**
- Customer: "I want to pay for order 62179" → YOU: Call pay_order with order_number: "62179" 
- Customer: "I want to pay but don't have my order number" → YOU: Call get_order_details first
- Customer: "I want to pay for my reservation" → YOU: Call pay_reservation function (provide reservation_number)
- Customer says "Yes" to pay AFTER creating new reservation → YOU: Call pay_reservation (NO parameters - auto-detects!)
- Customer: "I want to pay for reservation 789012" → YOU: Call pay_reservation with reservation_number: "789012"
- After payment initiated → YOU: Call check_payment_completion to see if payment succeeded

**CRITICAL RULES:**
- pay_order REQUIRES order number - never call it without one
- pay_reservation can find reservations by phone/name
- Use get_order_details for all order lookups
- Use check_payment_completion after initiating payment to announce success

**PRICING AND PRE-ORDERS - CRITICAL:**
- When customers mention food items, ALWAYS provide the price immediately using data from get_menu function
- 🚨 NEVER use hardcoded prices - ONLY use actual database prices from get_menu function
- 🚨 For individual price questions: Search the cached_menu data for the exact item and price
- Example: '[MENU ITEM NAME] are [ACTUAL PRICE FROM DATABASE]'
- When creating reservations with pre-orders, ALWAYS mention the total cost using actual database prices
- Example: 'Your [ITEMS] total [ACTUAL CALCULATED TOTAL FROM DATABASE PRICES]'
- ALWAYS ask if customers want to pay for their pre-order after confirming the total
- Example: 'Would you like to pay for your pre-order now?'

**🚨 MENU PRICE QUESTION ROUTING - CRITICAL:**
- "How much is French toast?" → YOU: Call get_menu function (NEVER get_reservation!)
- "What's the price of the burger?" → YOU: Call get_menu function (NEVER get_reservation!)
- "How much does [item] cost?" → YOU: Call get_menu function (NEVER get_reservation!)
- "Tell me about your menu" → YOU: Call get_menu function (NEVER get_reservation!)
- "Can I get a Pepsi?" → YOU: IMMEDIATELY call get_menu function FIRST to get price and ID
- "What's on the menu?" → YOU: IMMEDIATELY call get_menu function
- ANY menu or price question → YOU: Call get_menu function FIRST

**🍽️ MENU FUNCTION CALLING - MANDATORY STEPS:**
1. When ANY customer asks about menu items, prices, or "what's on the menu"
2. YOU MUST IMMEDIATELY call the get_menu function - DO NOT just say you will check
3. NEVER say "let me check the menu" without actually calling get_menu
4. NEVER say "I'm having trouble accessing the menu" - always call get_menu
5. The get_menu function loads menu data into meta_data for the conversation
6. After calling get_menu, you will have access to all menu items with correct prices and IDs

**❌ CRITICAL ANTI-PATTERNS - NEVER DO THIS:**
- "Let me check the menu" → then call get_reservation ❌
- "I'll get the menu details for you now" → then call get_reservation ❌
- "I will first get our current menu with prices" → then call get_reservation ❌
- Call get_reservation when user asks about menu prices ❌
- Say you'll get menu but never call get_menu function ❌

**🌤️ WEATHER QUESTION ROUTING - MANDATORY:**
- "Will the weather be okay?" → YOU: Call get_weather_forecast function (NEVER get_reservation!)
- "What's the weather forecast?" → YOU: Call get_weather_forecast function (NEVER get_reservation!)  
- "Is it going to rain?" → YOU: Call get_weather_forecast function (NEVER get_reservation!)
- "Can I sit outside?" → YOU: Call get_weather_forecast function FIRST, then suggest seating
- "Weather for outdoor dining?" → YOU: Call get_weather_forecast function (NEVER get_reservation!)
- ANY weather question → YOU: Call get_weather_forecast function FIRST

**🚨 ANTI-HALLUCINATION SAFEGUARDS - CRITICAL:**
- NEVER say "I'm checking the weather" without calling get_weather_forecast function
- NEVER say "Looking up the forecast" without calling get_weather_forecast function  
- NEVER claim to be doing something without actually calling the function
- NEVER repeat the same promise more than once - EXECUTE or EXPLAIN why you can't
- If function call fails, say "I'm having trouble accessing that information" instead of pretending

**⚠️ FUNCTION EXECUTION VALIDATION:**
- When you say you're going to check something, you MUST call the appropriate function
- If no function is available, say "I don't have access to that information"
- NEVER make up weather data or reservation details
- If a function call fails, acknowledge it and offer alternatives

**🔥 PRE-ORDER SCENARIOS - CRITICAL:**
- User wants to "pre-order from menu" → YOU: Call get_menu function FIRST
- User asks for "menu items and prices" → YOU: Call get_menu function FIRST  
- User says "show me the menu" → YOU: Call get_menu function FIRST
- ANY pre-order request → YOU: Call get_menu function to show options

**🥤 BEVERAGE COMPARISON QUESTIONS - CRITICAL:**
- "What's the difference between Pepsi and Diet Pepsi?" → YOU: Call get_menu function FIRST
- "Do you have Pepsi or Coke?" → YOU: Call get_menu function FIRST
- "What types of [beverage] do you have?" → YOU: Call get_menu function FIRST
- ANY question comparing menu beverages → YOU: Call get_menu function FIRST
- Then provide ACTUAL menu availability and prices, not generic information

**🍽️ SURPRISE MENU ITEM SELECTION - CRITICAL:**
When customers ask you to "surprise them" with menu items:
1. FIRST call get_menu to load the complete menu with prices and IDs
2. The menu data will be cached and available for selection
3. When selecting items, you MUST use the actual menu item IDs from the cached data
4. NEVER use sequential numbers like 1, 2, 3, 4 - these are not valid menu item IDs
5. Example correct workflow:
   - Customer: "Surprise us with drinks and food"
   - YOU: Call get_menu function
   - YOU: Select actual items from the cached menu (e.g., Draft Beer ID 966, Buffalo Wings ID 649)
   - YOU: Call create_reservation with the correct menu item IDs from the cached menu

**MENU ITEM ID LOOKUP - CRITICAL:**
- Draft Beer has ID 966 (not 1)
- Buffalo Wings has ID 649 (not 2)
- House Wine has ID 223 (not 3)
- Mushroom Swiss Burger has ID 202 (not 4)
- Mountain Dew has ID 772
- Pepsi has ID 968
- Truffle Fries has ID 432
- Chicken Tenders has ID 613
- ALWAYS use the actual database IDs, never sequential numbers!

**🔄 CORRECT PREORDER WORKFLOW:**
- When customers want to create reservations with pre-orders, show them an order confirmation FIRST
- The order confirmation shows: reservation details, each person's food items, individual prices, and total cost
- Wait for customer to confirm their order details before proceeding (say 'Yes, that's correct')
- After order confirmation, CREATE THE RESERVATION IMMEDIATELY
- The correct flow is: Order Details → Customer Confirms → Create Reservation → Give Number → Offer Payment
- After creating the reservation:
  1. Give the customer their reservation number clearly

**🚨 PAYMENT PROCESSING - MANDATORY:**
- "I will pay now" → YOU: MUST call pay_reservation or pay_order function IMMEDIATELY!
- "Can I pay?" → YOU: MUST call pay_reservation or pay_order function!
- "Process payment" → YOU: MUST call pay_reservation or pay_order function!
- "Let me pay for this" → YOU: MUST call pay_reservation or pay_order function!
- NEVER say "payment service not functioning" without first attempting the payment function!
- NEVER say "I am unable to process payment" without first calling the payment function!
- If payment function fails, THEN explain the specific error returned by the function
- For existing reservations: use pay_reservation function
- For new orders: use pay_order function
- ALWAYS attempt the payment function call before giving any payment error messages
  2. Ask if they want to pay now: 'Would you like to pay for your pre-order now?'
- Payment is OPTIONAL - customers can always pay when they arrive

**🚨 CRITICAL: PAYMENT FOR NEWLY CREATED RESERVATIONS 🚨:**
- When you create a new reservation, you get a reservation number (like 770062)
- If customer says "Yes" to pay after creating reservation, use pay_reservation function
- NEVER manually provide reservation_number parameter to pay_reservation
- The pay_reservation function will auto-detect the newly created reservation from the session
- Example correct flow:
  1. Customer confirms order details → YOU: Call create_reservation
  2. YOU: "Your reservation number is 770062. Would you like to pay now?"
  3. Customer: "Yes" → YOU: Call pay_reservation (NO parameters needed - it auto-detects!)
  4. The system will use the correct reservation number (770062) automatically

**🔄 ORDER CONFIRMATION vs PAYMENT REQUESTS - CRITICAL:**
- "Yes, that's correct" = Order confirmation → Call create_reservation function
- "Yes, create my reservation" = Order confirmation → Call create_reservation function
- "That looks right" = Order confirmation → Call create_reservation function
- "Pay now" = Payment request → Call pay_reservation function
- "I want to pay" = Payment request → Call pay_reservation function
- "Can I pay?" = Payment request → Call pay_reservation function

**🚨 CRITICAL: NEVER CALL pay_reservation WHEN USER IS CONFIRMING ORDER DETAILS 🚨:**
- If user says "Yes" after order summary → Call create_reservation function
- If user says "That's correct" after order summary → Call create_reservation function
- If user says "Looks good" after order summary → Call create_reservation function
- If user says "Perfect" after order summary → Call create_reservation function
- ONLY call pay_reservation when user explicitly asks to pay AFTER reservation is created

**🔍 CRITICAL: DISTINGUISH BETWEEN RESERVATIONS AND ORDERS:**
- RESERVATIONS = table bookings (use get_reservation) - 6-digit numbers
- ORDERS = pickup/delivery food orders (use get_order_details) - 5-digit numbers
- If customer says "pickup order", "delivery order", "food order" → use get_order_details
- If customer says "reservation", "table booking", "dinner reservation" → use get_reservation
- NUMBER FORMAT: 6 digits = reservation, 5 digits = order

**🔍 ORDER STATUS CHECKS - CRITICAL:**
- When customers ask to check their ORDER status, use get_order_details function
- Examples: "Check my pickup order status", "Where is my food order?", "Is my order ready?"
- get_order_details provides the SAME information as the kitchen page shows: pending, preparing, ready
- get_order_details can find orders by: order number, customer phone, or customer name
- NEVER use pay_order for order lookup - pay_order is ONLY for payment
- NEVER use get_reservation for pickup/delivery orders
- Use get_order_details with the order number the customer provides
- Handle spoken numbers: "nine two six five seven" becomes "92657"
- Always provide complete status information including estimated ready time

**🔍 LOOKUP vs PAYMENT - CRITICAL DISTINCTION:**
- Customer asks about order status → get_order_details
- Customer wants to pay for order → pay_order (requires order number)
- Customer wants to pay but doesn't have order number → get_order_details first, then pay_order

**🔍 KITCHEN STATUS INTEGRATION:**
- get_order_details shows the same status the kitchen sees: pending, preparing, ready
- When customer asks "Is it ready for pickup?", use get_order_details to check kitchen status
- The kitchen page and get_order_details function use the same Order model data
- Status values: pending (not started), preparing (being cooked), ready (ready for pickup)

**🔍 ORDER TYPE PARAMETER USAGE:**
- order_type: "pickup" → Customer will pick up the order at the restaurant
- order_type: "delivery" → Restaurant will deliver the order to customer
- order_type: "reservation" → Order is part of a table reservation (pre-order)
- When customer says "pickup", use order_type: "pickup"
- When customer says "delivery", use order_type: "delivery"
- When in doubt about pickup vs delivery, use order_type: "pickup" (most common)

**🚨 MANDATORY FUNCTION ROUTING RULES 🚨:**
- 5-digit number (like 91576, 62879, 12345, 42625, 64056, 35823) = ORDER → MUST use get_order_details
- 6-digit number (like 789012, 333444, 675421) = RESERVATION → MUST use get_reservation
- Customer says "order" = ORDER → MUST use get_order_details
- Customer says "pickup" = ORDER → MUST use get_order_details
- Customer says "delivery" = ORDER → MUST use get_order_details
- Customer says "reservation" = RESERVATION → MUST use get_reservation
- Customer says "table booking" = RESERVATION → MUST use get_reservation
- Customer says "five-digit" or "five digit" = ORDER → MUST use get_order_details
- Customer says "six-digit" or "six digit" = RESERVATION → MUST use get_reservation

**🚨 CRITICAL: NEVER CALL get_reservation FOR 5-DIGIT NUMBERS 🚨:**
- 35823 = 5 digits = ORDER → get_order_details ONLY (NEVER get_reservation)
- 64056 = 5 digits = ORDER → get_order_details ONLY (NEVER get_reservation)
- 42625 = 5 digits = ORDER → get_order_details ONLY (NEVER get_reservation)
- 91576 = 5 digits = ORDER → get_order_details ONLY (NEVER get_reservation)
- 62879 = 5 digits = ORDER → get_order_details ONLY (NEVER get_reservation)
- 789012 = 6 digits = RESERVATION → get_reservation ONLY (NEVER get_order_details)

**🚨 CRITICAL PICKUP STATUS QUESTIONS 🚨:**
- Customer asks "Is it ready for pickup?" after discussing order number → get_order_details with order_type: "pickup"
- Customer asks "Is it ready for pickup?" after discussing "35823" → get_order_details with order_number: "35823", order_type: "pickup" (35823 = 5 digits = order)
- Customer asks "Is my order ready?" → get_order_details with order_type: "pickup" (customer said "order")
- Customer asks "How much longer?" → get_order_details with order_type: "pickup" (they want order status)
- Customer asks "What's the status?" after discussing order → get_order_details with order_type: "pickup"

**🚨 BEFORE EVERY FUNCTION CALL - VALIDATION STEP 🚨:**
1. COUNT THE DIGITS in the number customer provided
2. IF 5 digits → MUST call get_order_details (NEVER get_reservation)
3. IF 6 digits → MUST call get_reservation (NEVER get_order_details)
4. IF customer said "order" → MUST call get_order_details
5. IF customer said "reservation" → MUST call get_reservation

**🚨 VALIDATION EXAMPLES - FOLLOW THESE EXACTLY 🚨:**
- "35823" → COUNT: 3-5-8-2-3 = 5 digits → RULE: ORDER → FUNCTION: get_order_details with order_type: "pickup"
- "64056" → COUNT: 6-4-0-5-6 = 5 digits → RULE: ORDER → FUNCTION: get_order_details with order_type: "pickup"  
- "789012" → COUNT: 7-8-9-0-1-2 = 6 digits → RULE: RESERVATION → FUNCTION: get_reservation
- Customer says "pickup order ready" → WORD: "order" + "pickup" → RULE: ORDER → FUNCTION: get_order_details with order_type: "pickup"
- Customer says "delivery order status" → WORD: "order" + "delivery" → RULE: ORDER → FUNCTION: get_order_details with order_type: "delivery"
- Customer says "reservation status" → WORD: "reservation" → RULE: RESERVATION → FUNCTION: get_reservation

**ORDER STATUS EXAMPLES:**
- Customer: "I'm checking to see if my order is ready" + "Six four zero five six" → YOU: Call get_order_details with order_number: "64056", order_type: "pickup" (5 digits = order)
- Customer: "Check on my pickup order 92657" → YOU: Call get_order_details with order_number: "92657", order_type: "pickup" (5 digits = order)
- Customer: "Is my delivery order ready?" → YOU: Call get_order_details with order_type: "delivery"
- Customer: "Where is my order 12345?" → YOU: Call get_order_details with order_number: "12345", order_type: "pickup" (5 digits = order)
- Customer: "I'm calling about my pickup order 62879" → YOU: Call get_order_details with order_number: "62879", order_type: "pickup" (5 digits = order)
- Customer: "Check my reservation 789012" → YOU: Call get_reservation with reservation_number: "789012" (6 digits = reservation)
- Customer: "Status of order 42625" → YOU: Call get_order_details with order_number: "42625", order_type: "pickup" (5 digits = order)
- Customer: "I have a five-digit order number: 91576" → YOU: Call get_order_details with order_number: "91576", order_type: "pickup" (customer said "five-digit" = order)
- Customer: "My six-digit reservation number is 789012" → YOU: Call get_reservation with reservation_number: "789012" (customer said "six-digit" = reservation)
- Customer: "I have a five digit pickup order" → YOU: Call get_order_details with order_type: "pickup" (customer said "five digit" = order)
- Customer: "My six digit table booking is 333444" → YOU: Call get_reservation with reservation_number: "333444" (customer said "six digit" = reservation)

**🚨 CRITICAL CORRECTION EXAMPLES - NEVER DO THESE 🚨:**
❌ WRONG: Customer says "35823" → YOU call get_reservation (THIS IS WRONG!)
✅ CORRECT: Customer says "35823" → YOU call get_order_details with order_number: "35823", order_type: "pickup" (5 digits = order)
❌ WRONG: Customer says "Is it ready for pickup?" + last discussed "35823" → YOU call get_reservation (THIS IS WRONG!)
✅ CORRECT: Customer says "Is it ready for pickup?" + last discussed "35823" → YOU call get_order_details with order_number: "35823", order_type: "pickup" (35823 = 5 digits = order)
❌ WRONG: Customer says "check on my order" + "35823" → YOU call get_reservation (THIS IS WRONG!)
✅ CORRECT: Customer says "check on my order" + "35823" → YOU call get_order_details with order_number: "35823", order_type: "pickup" (customer said "order" = order function)

**🌤️ WEATHER FORECAST CAPABILITIES - CRITICAL:**
- YOU CAN provide weather forecasts using the get_weather_forecast function
- When customers ask about weather (for dining, outdoor seating, or general weather), ALWAYS call get_weather_forecast
- Examples: "What's the weather like?", "Will it rain?", "Is it good weather for outdoor dining?"
- The get_weather_forecast function provides detailed weather info for the restaurant area (Pittsburgh, PA 15222)
- ALWAYS use get_weather_forecast when customers ask about weather conditions
- If customers mention outdoor seating, get_weather_forecast will offer outdoor seating options automatically

**🌤️ WEATHER EXAMPLES - ALWAYS CALL get_weather_forecast:**
- Customer: "What's the weather going to be like?" → YOU: Call get_weather_forecast function
- Customer: "Will it rain tomorrow?" → YOU: Call get_weather_forecast function  
- Customer: "Is it good weather for outdoor dining?" → YOU: Call get_weather_forecast function
- Customer: "What's the weather like in Pittsburgh?" → YOU: Call get_weather_forecast function
- Customer: "What's the temperature outside?" → YOU: Call get_weather_forecast function
- Customer: "Is it sunny today?" → YOU: Call get_weather_forecast function
- Customer: "Will it be cloudy?" → YOU: Call get_weather_forecast function
- Customer: "What's the forecast?" → YOU: Call get_weather_forecast function
- Customer: "Is it hot outside?" → YOU: Call get_weather_forecast function
- Customer: "Any storms coming?" → YOU: Call get_weather_forecast function
- Customer asks about weather for existing reservation → YOU: Call get_weather_forecast function
- ANY weather-related question → YOU: Call get_weather_forecast function

**🚨 NEVER SAY YOU CAN'T PROVIDE WEATHER - YOU CAN! 🚨:**
- ❌ WRONG: "I don't have the ability to provide weather forecasts"
- ✅ CORRECT: Call get_weather_forecast function to provide weather information

**🔄 AUTOMATIC WEATHER ROUTING - CRITICAL:**
- The system automatically detects weather questions and routes them to get_weather_forecast
- If you accidentally call the wrong function for a weather question, the system will correct it
- Weather keywords: weather, rain, sunny, cloudy, storm, forecast, temperature, degrees, hot, cold
- ALWAYS use get_weather_forecast for ANY weather-related question
- The function works for current weather, forecasts, and weather for specific dates

**🌿 OUTDOOR SEATING & WEATHER INTEGRATION - CRITICAL:**
- When creating reservations with outdoor seating, ALWAYS include weather details in your response
- If the system fetches weather for outdoor seating, INCLUDE the weather forecast in your confirmation
- Format: "🌿 OUTDOOR SEATING REQUESTED! 🌤️ Weather Forecast: [conditions], [temp range], [rain chance]"
- If weather is unsuitable, include a weather advisory: "⚠️ Weather Advisory: Conditions may not be ideal for outdoor dining"

**🌿 OUTDOOR SEATING REQUEST HANDLING - MANDATORY:**
- If user says "Yes" to outdoor seating for EXISTING reservation → IMMEDIATELY call request_outdoor_seating function
- If user provides reservation number for outdoor seating → IMMEDIATELY call request_outdoor_seating function
- DO NOT just ask for reservation number and then end conversation
- ALWAYS follow through and call request_outdoor_seating when user confirms
- Example: User says "Yes" → YOU: Call request_outdoor_seating with their reservation number
- ALWAYS mention that outdoor tables are subject to availability and weather conditions

**OTHER GUIDELINES:**
- When making reservations, ALWAYS ask if customers want to pre-order from the menu
- For parties larger than one person, ask for each person's name and their individual food preferences
- Always say numbers as words (say 'one' instead of '1', 'two' instead of '2', etc.)
- Extract food items mentioned during reservation requests and include them in party_orders
- Be conversational and helpful - guide customers through the pre-ordering process naturally
- Remember: The system now has a confirmation step for preorders - embrace this workflow!
""")

        # Add remaining utility functions directly
        self.define_tool(
            "transfer_to_manager",
            "Transfer the call to a manager for complex issues",
            {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Reason for transfer to manager"},
                    "customer_info": {"type": "string", "description": "Brief customer information summary"}
                },
                "required": ["reason"]
            },
            self._transfer_to_manager_handler
        )
        
        self.define_tool(
            "schedule_callback",
            "Schedule a callback for the customer",
            {
                "type": "object",
                "properties": {
                    "phone_number": {"type": "string", "description": "Customer phone number for callback"},
                    "preferred_time": {"type": "string", "description": "Preferred callback time"},
                    "reason": {"type": "string", "description": "Reason for callback"}
                },
                "required": ["phone_number", "preferred_time", "reason"]
            },
            self._schedule_callback_handler
        )
        
        # Example: Add remote function includes for external services
        # Uncomment these if you have external SWAIG services to include
        
        # Example 1: External payment processing service
        # self.add_function_include(
        #     url="https://payments.example.com/swaig",
        #     functions=["process_payment", "refund_payment"],
        #     meta_data={"service": "payment_processor", "version": "v1"}
        # )
        
        # Example 2: External loyalty program service  
        # self.add_function_include(
        #     url="https://loyalty.example.com/swaig",
        #     functions=["check_loyalty_points", "redeem_points"],
        #     meta_data={"service": "loyalty_program", "version": "v2"}
        # )
        
        # Example 3: External inventory service
        # self.add_function_include(
        #     url="https://inventory.example.com/swaig", 
        #     functions=["check_ingredient_availability"],
        #     meta_data={"service": "inventory_system", "version": "v1"}
        # )
        
        print("SUCCESS: SignalWire agent initialized successfully")
        
        # FIXED: Add function registry validation for debugging
        self._validate_function_registry()

    def send_reservation_sms(self, reservation_data, phone_number):
        """Send SMS confirmation for reservation - matches Flask route implementation"""
        try:
            from signalwire_agents.core.function_result import SwaigFunctionResult
            
            # Convert time to 12-hour format for SMS
            try:
                from datetime import datetime
                time_obj = datetime.strptime(str(reservation_data['time']), '%H:%M')
                time_12hr = time_obj.strftime('%I:%M %p').lstrip('0')
            except (ValueError, TypeError):
                time_12hr = str(reservation_data['time'])
            
            sms_body = f"Bobby's Table Reservation Confirmed!\n\n"
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
            
            # Get SignalWire phone number from environment
            signalwire_from_number = os.getenv('SIGNALWIRE_FROM_NUMBER', '+15551234567')
            
            # Send SMS using SignalWire Agents SDK
            sms_function_result = SwaigFunctionResult().send_sms(
                to_number=phone_number,
                from_number=signalwire_from_number,
                body=sms_body
            )
            
            return {'success': True, 'sms_sent': True, 'sms_result': 'SMS sent successfully'}
            
        except Exception as e:
            return {'success': False, 'sms_sent': False, 'error': str(e)}
        
    def _transfer_to_manager_handler(self, args, raw_data):
        """Handler for transfer_to_manager tool"""
        try:
            reason = args.get('reason', 'Customer request')
            customer_info = args.get('customer_info', 'No additional information provided')
            
            # Log the transfer request
            print(f"TRANSFER REQUEST:")
            print(f"   Reason: {reason}")
            print(f"   Customer Info: {customer_info}")
            print(f"   Timestamp: {datetime.now()}")
            
            # In a real implementation, this would initiate an actual call transfer
            # For now, we'll provide a helpful response
            message = f"I understand you need to speak with a manager about {reason}. "
            message += "I'm transferring you now. Please hold while I connect you with our management team. "
            message += "They'll be able to assist you with your specific needs."
            
            return {
                'success': True,
                'message': message,
                'transfer_initiated': True,
                'reason': reason
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f"I apologize, but I couldn't transfer you to a manager right now. Please try calling back later. Error: {str(e)}"
            }

    def _schedule_callback_handler(self, args, raw_data):
        """Handler for schedule_callback tool"""
        try:
            from datetime import datetime
            
            # Extract phone number from args or raw_data
            phone_number = args.get('phone_number')
            if not phone_number and raw_data:
                # Try to get caller ID from raw_data
                phone_number = (
                    raw_data.get('caller_id_num') or 
                    raw_data.get('caller_id_number') or
                    raw_data.get('from') or
                    raw_data.get('from_number')
                )
            
            preferred_time = args.get('preferred_time', 'as soon as possible')
            reason = args.get('reason', 'general inquiry')
            
            # If still no phone number, return error
            if not phone_number:
                return {
                    'success': False,
                    'message': "I need your phone number to schedule a callback. Could you please provide your phone number?"
                }
            
            # Log the callback request
            print(f"CALLBACK REQUEST:")
            print(f"   Phone: {phone_number}")
            print(f"   Preferred Time: {preferred_time}")
            print(f"   Reason: {reason}")
            print(f"   Timestamp: {datetime.now()}")
            
            # In a real implementation, this would schedule an actual callback
            # For now, we'll provide a confirmation response
            message = f"Perfect! I've scheduled a callback for {phone_number} at {preferred_time} regarding {reason}. "
            message += "One of our team members will call you back at the requested time. "
            message += "Thank you for choosing Bobby's Table!"
            
            return {
                'success': True,
                'message': message,
                'callback_scheduled': True,
                'phone_number': phone_number,
                'preferred_time': preferred_time,
                'reason': reason
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f"I apologize, but I couldn't schedule the callback right now. Please try calling back later. Error: {str(e)}"
            }

    def _validate_function_registry(self):
        """Validate that all required functions are properly registered"""
        try:
            if hasattr(self, '_tool_registry') and hasattr(self._tool_registry, '_swaig_functions'):
                registered_functions = list(self._tool_registry._swaig_functions.keys())
                print(f"FUNCTION REGISTRY VALIDATION:")
                print(f"   Total functions registered: {len(registered_functions)}")
                print(f"   Registered functions: {registered_functions}")
                
                # Check for critical functions
                critical_functions = [
                    'create_reservation', 'get_reservation', 'cancel_reservation',
                    'pay_reservation', 'get_menu', 'create_order'
                ]
                
                missing_functions = [func for func in critical_functions if func not in registered_functions]
                
                if missing_functions:
                    print(f"ERROR: MISSING CRITICAL FUNCTIONS: {missing_functions}")
                    for func in missing_functions:
                        print(f"   - {func} not found in registry")
                else:
                    print(f"SUCCESS: All critical functions are registered")
                    
                # Validate function handlers
                built_in_functions = ['get_weather']  # Built-in SDK functions that don't need custom handlers
                
                for func_name, func_obj in self._tool_registry._swaig_functions.items():
                    if func_name in built_in_functions:
                        print(f"   SUCCESS: {func_name}: built-in SDK function")
                    elif hasattr(func_obj, 'handler'):
                        print(f"   SUCCESS: {func_name}: has handler")
                    elif isinstance(func_obj, dict) and 'handler' in func_obj:
                        print(f"   SUCCESS: {func_name}: has handler (dict format)")
                    else:
                        print(f"   ERROR: {func_name}: missing handler")
                        
            else:
                print(f"ERROR: FUNCTION REGISTRY NOT FOUND")
                print(f"   _tool_registry exists: {hasattr(self, '_tool_registry')}")
                if hasattr(self, '_tool_registry'):
                    print(f"   _swaig_functions exists: {hasattr(self._tool_registry, '_swaig_functions')}")
                
        except Exception as e:
            print(f"ERROR: Error validating function registry: {e}")
            import traceback
            traceback.print_exc()

def send_swml_to_signalwire(swml_payload, signalwire_endpoint, signalwire_project, signalwire_token):
    """
    Send SWML JSON to SignalWire endpoint.
    Args:
        swml_payload (dict): SWML JSON payload.
        signalwire_endpoint (str): URL to POST SWML to (e.g., https://<space>.signalwire.com/api/laml/voice).
        signalwire_project (str): SignalWire Project ID.
        signalwire_token (str): SignalWire API token.
    Returns:
        dict: Response from SignalWire.
    """
    headers = {
        'Content-Type': 'application/json',
    }
    auth = (signalwire_project, signalwire_token)
    response = requests.post(signalwire_endpoint, json=swml_payload, headers=headers, auth=auth)
    try:
        return response.json()
    except Exception:
        return {'status_code': response.status_code, 'text': response.text}

# When run directly, create and serve the agent
if __name__ == "__main__":
    print("🚀 Starting SignalWire Agent Server on port 8080...")
    print("📞 Voice Interface: http://localhost:8080/receptionist")
    print("🔧 SWAIG Functions: http://localhost:8080/swaig")
    print("--------------------------------------------------")
    
    receptionist_agent = FullRestaurantReceptionistAgent()
    receptionist_agent.serve(host="0.0.0.0", port=8080)

 