#!/usr/bin/env python3
"""
SignalWire Agents for Bobby's Table Restaurant
Provides voice-enabled access to all restaurant functionality using skills-based architecture
"""

from signalwire_agents import AgentBase
from signalwire_agents.core.function_result import SwaigFunctionResult
from signalwire_agents.core.state import StateManager, FileStateManager
from signalwire_agents.core.contexts import ContextBuilder, Context, create_simple_context
from datetime import datetime, timedelta
import os
import json
from dotenv import load_dotenv
import requests

load_dotenv()

# SignalWire configuration for SMS
SIGNALWIRE_FROM_NUMBER = os.getenv('SIGNALWIRE_FROM_NUMBER', '+15551234567')

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
            self.state_manager = FileStateManager("restaurant_agent_state.json")
            print("✅ State manager initialized")
        except Exception as e:
            print(f"⚠️ Could not initialize state manager: {e}")
            self.state_manager = None
        
        # Add pre-built skills for enhanced functionality
        try:
            # Add datetime skill for time/date queries
            self.add_skill("datetime")
            print("✅ Added datetime skill")
        except Exception as e:
            print(f"⚠️ Could not add datetime skill: {e}")
        
        try:
            # Add weather skill if API key is available
            weather_api_key = os.getenv('WEATHER_API_KEY')
            if weather_api_key:
                self.add_skill("weather_api", {
                    "tool_name": "get_weather",
                    "api_key": weather_api_key,
                    "temperature_unit": "fahrenheit"
                })
                print("✅ Added weather skill")
            else:
                print("⚠️ Weather API key not found, skipping weather skill")
        except Exception as e:
            print(f"⚠️ Could not add weather skill: {e}")
        
        try:
            # Add web search skill if API key is available
            search_api_key = os.getenv('SEARCH_API_KEY')
            if search_api_key:
                self.add_skill("web_search", {
                    "tool_name": "search_web",
                    "api_key": search_api_key
                })
                print("✅ Added web search skill")
            else:
                print("⚠️ Search API key not found, skipping web search skill")
        except Exception as e:
            print(f"⚠️ Could not add web search skill: {e}")

        # Add restaurant-specific skills using local imports
        try:
            # Import and add reservation management skill
            from skills.restaurant_reservation.skill import RestaurantReservationSkill
            
            skill_params = {
                "swaig_fields": {
                    "secure": True,
                    "fillers": {
                        "en-US": [
                            "Let me check our reservation system...",
                            "Looking up your reservation...",
                            "Processing your reservation request...",
                            "Checking availability..."
                        ]
                    }
                }
            }
            
            reservation_skill = RestaurantReservationSkill(self, skill_params)
            if reservation_skill.setup():
                reservation_skill.register_tools()
                print("✅ Added restaurant reservation skill")
            else:
                print("⚠️ Restaurant reservation skill setup failed")
        except Exception as e:
            print(f"⚠️ Could not add restaurant reservation skill: {e}")

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
                menu_skill.register_tools()
                print("✅ Added restaurant menu skill")
            else:
                print("⚠️ Restaurant menu skill setup failed")
        except Exception as e:
            print(f"⚠️ Could not add restaurant menu skill: {e}")
        
        # Set up the agent's capabilities
        self.set_params({
            "end_of_speech_timeout": 500,
            "silence_timeout": 500,
            "max_speech_timeout": 15000
        })
        
        # Add the agent's prompt with enhanced capabilities
        self.prompt_add_section("System", """
You are Bobby, the friendly receptionist for Bobby's Table, an upscale restaurant. You can help customers with:

1. Making new reservations (including "old school" table-only reservations)
2. Checking existing reservations
3. Modifying or canceling reservations
4. Browsing our menu and placing orders for pickup or delivery
5. Checking order status
6. Processing bill payments with secure credit card collection
7. Providing current time and date information
8. Checking weather conditions (if customers ask about outdoor seating)
9. General information searches (if needed)

Always be warm, professional, and helpful. When customers call, greet them and ask how you can help them today.

**RESERVATION SYSTEM FEATURES:**

**Unique Reservation Numbers:**
- Every reservation gets a unique 6-digit reservation number (e.g., 123456)
- These numbers are automatically generated and included in confirmations
- Customers can use these numbers to reference their reservations
- Always mention the reservation number when confirming or discussing reservations

**SMS Confirmations:**
- All reservations automatically send SMS confirmations to the customer's phone
- SMS includes reservation details: name, date, time, party size, reservation number, and special requests
- Cancellations and updates also send SMS notifications
- If SMS fails, the reservation is still created successfully

**IMPORTANT CONVERSATION CONTEXT HANDLING:**

**For reservation lookups:**
- **ALWAYS ASK FOR RESERVATION NUMBER FIRST** - This is the fastest and most accurate way to find reservations
- When customers want to check their reservation, ask: "Do you have your reservation number? It's a 6-digit number we sent you when you made the reservation."
- If they don't have the reservation number, then ask for their name or phone number as backup
- The system can search using ANY information: reservation number (preferred), name, phone number, date, or party size
- If the customer doesn't provide specific search criteria, you can call get_reservation with no parameters to show recent reservations
- The system will automatically use the caller's phone number and extract names from conversation
- When customers mention reservation numbers, handle spoken numbers like "seven eight nine zero one two" which becomes "789012"
- Reservation numbers are the most reliable search method - always try this first!

**For reservation updates:**
- When updating reservations, the system will automatically find the reservation using conversation context
- If a customer mentions a name (like "Rob Zombie") and wants to change the time, you can call update_reservation even without the reservation ID
- The system will extract the customer name and time change request from the conversation
- Always confirm the changes before finalizing
- Updated reservations automatically send new SMS confirmations

**For orders:**
- When creating orders, the system will automatically extract order items from the conversation
- If a customer says "I want two Buffalo Wings" and then confirms "Yes", you can call create_order with empty parameters
- The system will analyze the conversation to understand what they want to order
- It will also auto-fill customer information from the caller's phone number and recent reservations
- Always confirm the order details before finalizing
- Orders also send SMS confirmations with pickup/delivery times

**Enhanced Ordering Process:**
1. **Initial Order**: When a customer orders food items, use create_order to start the order
2. **Drink Suggestions**: The system will automatically suggest complementary drinks based on the food ordered
3. **Additional Items**: Ask if they want to add anything else to their order
4. **Order Finalization**: When they're ready to complete the order, use finalize_order to process it
5. **Random Timing**: Each order gets a random pickup/delivery time between 10-45 minutes for realism
6. **Comprehensive Confirmation**: Provide detailed order confirmation with emojis and clear formatting
7. **SMS Notifications**: Orders automatically send SMS confirmations with all details

**Ordering Flow Example:**
- Customer: "I want two Buffalo Wings"
- You: Call create_order → System suggests drinks and asks for additional items
- Customer: "Add a Coke and that's it"
- You: Call finalize_order → System creates the complete order with random timing and sends SMS

**Function Call Strategy:**
- Even if you don't have all the required parameters, you can still call the functions
- The system will use conversation context to fill in missing information
- This makes the conversation more natural and reduces the need to ask for information repeatedly
- Trust the system to extract context from the conversation history
- **IMPORTANT**: When you decide to call a function, call it immediately without announcing what you're going to do
- Don't say "Let me check..." or "One moment please..." - just call the function and let the results speak for themselves
- The system will handle the processing time automatically

**For new reservations, you'll need:**
- Customer name
- Party size (number of people)
- Preferred date and time
- Phone number
- Any special requests

**We offer two types of reservations:**
1. **Regular reservations** - Reserve a table and pre-order food and drinks
2. **Old school reservations** - Just reserve the table, browse menu and order when you arrive

**For orders, you can help them browse our menu categories:**
- Breakfast items
- Appetizers  
- Main courses
- Desserts
- Drinks

**For bill payments:**
- When customers want to pay their bill, use the pay_reservation function
- The system will look up their reservation and calculate the total amount due from their orders
- It will securely collect their credit card information (card number, expiration, CVV, ZIP code)
- Process the payment through our secure payment system
- Send them an SMS receipt upon successful payment
- Guide them step-by-step through the payment process conversationally
- You'll need their reservation number and the name on their credit card

**Additional Features:**
- If customers ask about the weather (for outdoor seating decisions) or need to know the current time/date, you can help with that too
- All reservations and orders are automatically saved to our database
- SMS confirmations are sent for all transactions
- Reservation numbers make it easy for customers to reference their bookings

Always confirm details before finalizing any reservation or order, and always mention the reservation number when confirming reservations.
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
        
        print("✅ SignalWire agent initialized successfully")

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
            print(f"📞 TRANSFER REQUEST:")
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
            print(f"📅 CALLBACK REQUEST:")
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

    def pay_reservation_by_phone(self, reservation_number=None, order_id=None, phone_number=None, cardholder_name=None, email=None):
        """
        SWAIG function to collect payment for a reservation/order via SignalWire Pay verb and Stripe.
        Args:
            reservation_number (str): Reservation number to pay for.
            order_id (str): Order ID to pay for (alternative to reservation_number).
            phone_number (str): Phone number to send SMS receipt to.
            cardholder_name (str): Name on the credit card.
            email (str): Optional email for receipt.
        Returns:
            dict: Result with success/failure and details.
        """
        from flask import current_app
        from models import Reservation, Order
        import os
        import requests
        import json
        from signalwire_agents.core.function_result import SwaigFunctionResult

        print(f"🔍 pay_reservation_by_phone called with:")
        print(f"   reservation_number: {reservation_number}")
        print(f"   order_id: {order_id}")
        print(f"   phone_number: {phone_number}")
        print(f"   cardholder_name: {cardholder_name}")

        # Ensure we're in Flask app context
        try:
            # Try to get the current app context
            current_app.logger.info("Using existing Flask app context")
        except RuntimeError:
            # No app context, need to create one
            print("🔧 Creating Flask app context...")
            import sys
            import os
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from app import app
            with app.app_context():
                return self._pay_reservation_with_context(reservation_number, order_id, phone_number, cardholder_name, email)
        
        # We're already in app context, proceed normally
        return self._pay_reservation_with_context(reservation_number, order_id, phone_number, cardholder_name, email)
    
    def _pay_reservation_with_context(self, reservation_number=None, order_id=None, phone_number=None, cardholder_name=None, email=None):
        """Helper method that runs within Flask app context"""
        from models import Reservation, Order
        from signalwire_agents.core.function_result import SwaigFunctionResult
        import os

        # 1. Lookup reservation/order
        reservation = None
        if reservation_number:
            print(f"🔍 Looking up reservation by number: {reservation_number}")
            reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
            if reservation:
                print(f"✅ Found reservation: ID {reservation.id}, Name: {reservation.name}")
            else:
                print(f"❌ No reservation found with number: {reservation_number}")
                # Try to find any reservations to debug
                all_reservations = Reservation.query.limit(5).all()
                print(f"🔍 Sample reservations in database:")
                for res in all_reservations:
                    print(f"   ID: {res.id}, Number: {res.reservation_number}, Name: {res.name}")
        elif order_id:
            print(f"🔍 Looking up reservation by order ID: {order_id}")
            reservation = Reservation.query.filter_by(id=order_id).first()
            if reservation:
                print(f"✅ Found reservation by order ID: {reservation.id}")
            else:
                print(f"❌ No reservation found with ID: {order_id}")
        
        if not reservation:
            return {"success": False, "error": "Reservation/order not found."}

        # 2. Calculate total amount due from orders
        total_amount = 0.0
        orders = Order.query.filter_by(reservation_id=reservation.id).all()
        print(f"🔍 Found {len(orders)} orders for reservation {reservation.id}")
        for order in orders:
            order_amount = order.total_amount or 0.0
            total_amount += order_amount
            print(f"   Order ID {order.id}: ${order_amount}")
        
        print(f"🔍 Total amount due: ${total_amount}")
        
        if total_amount <= 0:
            # If no orders exist, create a default amount for testing
            print("⚠️ No amount due found, using default amount for testing")
            total_amount = 50.00  # Default amount for testing
        
        # 3. Use SignalWire Pay verb (SWML) to collect payment
        try:
            # Get SignalWire configuration
            # Get payment connector URL - try to auto-detect ngrok URL
            payment_connector_url = os.getenv('SIGNALWIRE_PAYMENT_CONNECTOR_URL')
            if payment_connector_url:
                # If environment variable is set, ensure it has the correct endpoint path
                if not payment_connector_url.endswith('/api/signalwire/payment-callback'):
                    if payment_connector_url.endswith('/'):
                        payment_connector_url = payment_connector_url + 'api/signalwire/payment-callback'
                    else:
                        payment_connector_url = payment_connector_url + '/api/signalwire/payment-callback'
            else:
                # Try to auto-detect ngrok URL from request headers
                try:
                    from flask import request
                    if request and request.headers.get('Host'):
                        host = request.headers.get('Host')
                        if 'ngrok' in host or 'tunnel' in host:
                            payment_connector_url = f"https://{host}/api/signalwire/payment-callback"
                        else:
                            payment_connector_url = 'http://localhost:8080/api/signalwire/payment-callback'
                    else:
                        payment_connector_url = 'http://localhost:8080/api/signalwire/payment-callback'
                except:
                    payment_connector_url = 'http://localhost:8080/api/signalwire/payment-callback'
            
            print(f"🔗 Using payment connector URL: {payment_connector_url}")
            print(f"🔗 URL length: {len(payment_connector_url)} characters")
            print(f"🔗 URL ends with: '{payment_connector_url[-50:]}'")
            
            # Check if URL is localhost (will cause issues with SignalWire)
            if 'localhost' in payment_connector_url or '127.0.0.1' in payment_connector_url:
                print("⚠️  WARNING: Payment connector URL is localhost - SignalWire won't be able to reach this!")
                print("   Make sure SIGNALWIRE_PAYMENT_CONNECTOR_URL is set to your ngrok URL")
            
            # Create payment description
            description = f"Bobby's Table Reservation #{reservation_number}"
            
            # Create SWML Pay action using SwaigFunctionResult
            result = SwaigFunctionResult()
            
            # Add a brief message before payment collection
            result = result.say(f"Perfect! I'll now collect payment for ${total_amount:.2f}. Please have your credit card ready. After payment, I'll provide you with a confirmation number.")
            
            # Add the Pay verb to collect credit card details
            print(f"🔗 About to call result.pay() with URL: {payment_connector_url}")
            result = result.pay(
                payment_connector_url=payment_connector_url,
                input_method="dtmf",  # Use DTMF for card entry
                payment_method="credit-card",
                timeout=10,  # 10 seconds between digits
                max_attempts=3,  # Allow 3 attempts
                security_code=True,  # Collect CVV
                postal_code=True,  # Collect ZIP code
                min_postal_code_length=5,  # Minimum ZIP length
                token_type="one-time",  # One-time payment
                charge_amount=str(total_amount),  # Amount to charge
                currency="usd",
                language="en-US",
                voice="woman",
                description=description,
                valid_card_types="visa mastercard amex discover",
                parameters=[
                    {"name": "reservation_number", "value": reservation_number},
                    {"name": "cardholder_name", "value": cardholder_name or ""},
                    {"name": "phone_number", "value": phone_number or reservation.phone_number},
                    {"name": "email", "value": email or ""}
                ]
            )
            
            print(f"✅ Payment collection setup successful for ${total_amount}")
            
            # Return the SWML result to execute payment collection
            return {
                "success": True, 
                "message": "Payment collection initiated",
                "swml_result": result,
                "amount": total_amount,
                "reservation_number": reservation_number
            }
            
        except Exception as e:
            print(f"❌ Error setting up payment collection: {e}")
            return {"success": False, "error": f"Failed to initiate payment collection: {str(e)}"}

    def generate_swml_pay_payload(self, amount, reservation_number, phone_number, action_url, description=None, currency='usd', cardholder_name=None, email=None):
        """
        Generate a SWML JSON payload for SignalWire Pay verb with Stripe.
        Args:
            amount (float): Amount to charge.
            reservation_number (str): Reservation or order number.
            phone_number (str): Phone number for receipt (optional, for context).
            action_url (str): Webhook URL for payment result.
            description (str): Description for payment.
            currency (str): Currency code (default 'usd').
            cardholder_name (str): Name on the credit card.
            email (str): Optional email for receipt.
        Returns:
            dict: SWML JSON payload.
        """
        if not description:
            description = f"Bobby's Table Reservation #{reservation_number}"
        pay_action = {
            "amount": amount,
            "action_url": action_url,
            "payment_processor": "stripe",
            "payment_processor_account": "your_stripe_account_id",
            "currency": currency,
            "description": description
        }
        if cardholder_name:
            pay_action["cardholder_name"] = cardholder_name
        if email:
            pay_action["email"] = email
        return {
            "actions": [
                {"say": {"text": "Please enter your card number, expiration, and CVC to pay your bill."}},
                {"pay": pay_action}
            ]
        }

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

def pay_reservation_by_phone(reservation_number=None, order_id=None, phone_number=None, cardholder_name=None, email=None):
    """
    Standalone SWAIG function to collect payment for a reservation/order via SignalWire Pay verb and Stripe.
    Args:
        reservation_number (str): Reservation number to pay for.
        order_id (str): Order ID to pay for (alternative to reservation_number).
        phone_number (str): Phone number to send SMS receipt to.
        cardholder_name (str): Name on the credit card.
        email (str): Optional email for receipt.
    Returns:
        dict: Result with success/failure and details.
    """
    from flask import current_app
    from models import Reservation, Order
    import os
    import requests
    import json
    from signalwire_agents.core.function_result import SwaigFunctionResult

    print(f"🔍 standalone pay_reservation_by_phone called with:")
    print(f"   reservation_number: {reservation_number}")
    print(f"   order_id: {order_id}")
    print(f"   phone_number: {phone_number}")
    print(f"   cardholder_name: {cardholder_name}")

    # Ensure we're in Flask app context
    try:
        # Try to get the current app context
        current_app.logger.info("Using existing Flask app context")
    except RuntimeError:
        # No app context, need to create one
        print("🔧 Creating Flask app context...")
        import sys
        import os
        parent_dir = os.path.dirname(os.path.abspath(__file__))
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        
        from app import app
        with app.app_context():
            return _pay_reservation_with_context_standalone(reservation_number, order_id, phone_number, cardholder_name, email)
    
    # We're already in app context, proceed normally
    return _pay_reservation_with_context_standalone(reservation_number, order_id, phone_number, cardholder_name, email)

def _pay_reservation_with_context_standalone(reservation_number=None, order_id=None, phone_number=None, cardholder_name=None, email=None):
    """Helper function that runs within Flask app context"""
    from models import Reservation, Order
    from signalwire_agents.core.function_result import SwaigFunctionResult
    import os

    # 1. Lookup reservation/order
    reservation = None
    if reservation_number:
        print(f"🔍 Looking up reservation by number: {reservation_number}")
        reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
        if reservation:
            print(f"✅ Found reservation: ID {reservation.id}, Name: {reservation.name}")
        else:
            print(f"❌ No reservation found with number: {reservation_number}")
            # Try to find any reservations to debug
            all_reservations = Reservation.query.limit(5).all()
            print(f"🔍 Sample reservations in database:")
            for res in all_reservations:
                print(f"   ID: {res.id}, Number: {res.reservation_number}, Name: {res.name}")
    elif order_id:
        print(f"🔍 Looking up reservation by order ID: {order_id}")
        reservation = Reservation.query.filter_by(id=order_id).first()
        if reservation:
            print(f"✅ Found reservation by order ID: {reservation.id}")
        else:
            print(f"❌ No reservation found with ID: {order_id}")
    
    if not reservation:
        return {"success": False, "error": "Reservation/order not found."}

    # 2. Calculate total amount due from orders
    total_amount = 0.0
    orders = Order.query.filter_by(reservation_id=reservation.id).all()
    print(f"🔍 Found {len(orders)} orders for reservation {reservation.id}")
    for order in orders:
        order_amount = order.total_amount or 0.0
        total_amount += order_amount
        print(f"   Order ID {order.id}: ${order_amount}")
    
    print(f"🔍 Total amount due: ${total_amount}")
    
    if total_amount <= 0:
        # If no orders exist, create a default amount for testing
        print("⚠️ No amount due found, using default amount for testing")
        total_amount = 50.00  # Default amount for testing
    
    # 3. Use SignalWire Pay verb (SWML) to collect payment
    try:
        # Get SignalWire configuration
        # Get payment connector URL - try to auto-detect ngrok URL
        payment_connector_url = os.getenv('SIGNALWIRE_PAYMENT_CONNECTOR_URL')
        if payment_connector_url:
            # If environment variable is set, ensure it has the correct endpoint path
            if not payment_connector_url.endswith('/api/signalwire/payment-callback'):
                if payment_connector_url.endswith('/'):
                    payment_connector_url = payment_connector_url + 'api/signalwire/payment-callback'
                else:
                    payment_connector_url = payment_connector_url + '/api/signalwire/payment-callback'
        else:
            # Try to auto-detect ngrok URL from request headers
            try:
                from flask import request
                if request and request.headers.get('Host'):
                    host = request.headers.get('Host')
                    if 'ngrok' in host or 'tunnel' in host:
                        payment_connector_url = f"https://{host}/api/signalwire/payment-callback"
                    else:
                        payment_connector_url = 'http://localhost:8080/api/signalwire/payment-callback'
                else:
                    payment_connector_url = 'http://localhost:8080/api/signalwire/payment-callback'
            except:
                payment_connector_url = 'http://localhost:8080/api/signalwire/payment-callback'
        
        print(f"🔗 Using payment connector URL: {payment_connector_url}")
        print(f"🔗 URL length: {len(payment_connector_url)} characters")
        print(f"🔗 URL ends with: '{payment_connector_url[-50:]}'")
        
        # Check if URL is localhost (will cause issues with SignalWire)
        if 'localhost' in payment_connector_url or '127.0.0.1' in payment_connector_url:
            print("⚠️  WARNING: Payment connector URL is localhost - SignalWire won't be able to reach this!")
            print("   Make sure SIGNALWIRE_PAYMENT_CONNECTOR_URL is set to your ngrok URL")
        
        # Create payment description
        description = f"Bobby's Table Reservation #{reservation_number}"
        
        # Create SWML Pay action using SwaigFunctionResult
        result = SwaigFunctionResult()
        
        # Add a brief message before payment collection
        result = result.say(f"Perfect! I'll now collect payment for ${total_amount:.2f}. Please have your credit card ready.")
        
        # Add the Pay verb to collect credit card details
        print(f"🔗 About to call result.pay() with URL: {payment_connector_url}")
        result = result.pay(
            payment_connector_url=payment_connector_url,
            input_method="dtmf",  # Use DTMF for card entry
            payment_method="credit-card",
            timeout=10,  # 10 seconds between digits
            max_attempts=3,  # Allow 3 attempts
            security_code=True,  # Collect CVV
            postal_code=True,  # Collect ZIP code
            min_postal_code_length=5,  # Minimum ZIP length
            token_type="one-time",  # One-time payment
            charge_amount=str(total_amount),  # Amount to charge
            currency="usd",
            language="en-US",
            voice="woman",
            description=description,
            valid_card_types="visa mastercard amex discover",
            parameters=[
                {"name": "reservation_number", "value": reservation_number},
                {"name": "cardholder_name", "value": cardholder_name or ""},
                {"name": "phone_number", "value": phone_number or reservation.phone_number},
                {"name": "email", "value": email or ""}
            ]
        )
        
        print(f"✅ Payment collection setup successful for ${total_amount}")
        
        # Return the SWML result to execute payment collection
        return {
            "success": True, 
            "message": "Payment collection initiated",
            "swml_result": result,
            "amount": total_amount,
            "reservation_number": reservation_number
        }
        
    except Exception as e:
        print(f"❌ Error setting up payment collection: {e}")
        return {"success": False, "error": f"Failed to initiate payment collection: {str(e)}"}

 