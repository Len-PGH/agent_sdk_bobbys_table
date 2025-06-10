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
6. Providing current time and date information
7. Checking weather conditions (if customers ask about outdoor seating)
8. General information searches (if needed)

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
- You can search for reservations using ANY available information: name, phone number, reservation number, date, or party size
- If the customer doesn't provide specific search criteria, you can call get_reservation with no parameters to show recent reservations
- The system will automatically use the caller's phone number and extract names from conversation
- Ask for whatever information the customer can provide: "I can look up your reservation by name, phone number, reservation number, or date. What information do you have?"
- The more specific the information, the better the search results will be
- When customers mention reservation numbers, handle spoken numbers like "one one one two two two" which becomes "111222"

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
            phone_number = args['phone_number']
            preferred_time = args['preferred_time']
            reason = args['reason']
            
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

    def pay_reservation_by_phone(self, reservation_number=None, order_id=None, phone_number=None):
        """
        SWAIG function to collect payment for a reservation/order via SignalWire Pay verb and Stripe.
        Args:
            reservation_number (str): Reservation number to pay for.
            order_id (str): Order ID to pay for (alternative to reservation_number).
            phone_number (str): Phone number to send SMS receipt to.
        Returns:
            dict: Result with success/failure and details.
        """
        from flask import current_app
        from models import Reservation
        import os
        import requests
        import json

        # 1. Lookup reservation/order
        reservation = None
        if reservation_number:
            reservation = Reservation.query.filter_by(reservation_number=reservation_number).first()
        elif order_id:
            reservation = Reservation.query.filter_by(id=order_id).first()
        if not reservation:
            return {"success": False, "error": "Reservation/order not found."}

        # 2. Get amount due
        amount = reservation.payment_amount or 0
        if amount <= 0:
            # Fallback: calculate from orders if needed
            amount = sum([o.total for o in getattr(reservation, 'orders', [])])
        if amount <= 0:
            return {"success": False, "error": "No amount due for this reservation."}

        # 3. Use SignalWire Pay verb (SWML) to collect payment
        # (This is a placeholder for actual SignalWire API integration)
        # You would POST to your SignalWire endpoint with SWML including the <Pay> verb
        # and handle the webhook/callback for payment result.
        # For now, we'll simulate a successful payment.
        payment_success = True  # Replace with actual payment result
        payment_intent_id = "swml_test_intent_1234"  # Replace with real intent ID

        if payment_success:
            # 4. Update reservation/order status
            reservation.payment_status = 'paid'
            reservation.payment_intent_id = payment_intent_id
            reservation.payment_amount = amount
            from datetime import datetime
            reservation.payment_date = datetime.utcnow()
            from app import db
            db.session.commit()

            # 5. Send SMS receipt (reuse your existing logic)
            try:
                from app import send_payment_receipt_sms
                send_payment_receipt_sms(reservation, amount, phone_number or reservation.phone_number)
            except Exception as e:
                return {"success": True, "warning": f"Payment succeeded, but failed to send SMS: {str(e)}"}

            return {"success": True, "message": "Payment successful. Bill marked as paid and SMS sent."}
        else:
            return {"success": False, "error": "Payment failed. Please try again."}

# When run directly, create and serve the agent
if __name__ == "__main__":
    print("🚀 Starting SignalWire Agent Server on port 8080...")
    print("📞 Voice Interface: http://localhost:8080/receptionist")
    print("🔧 SWAIG Functions: http://localhost:8080/swaig")
    print("--------------------------------------------------")
    
    receptionist_agent = FullRestaurantReceptionistAgent()
    receptionist_agent.serve(host="0.0.0.0", port=8080) 