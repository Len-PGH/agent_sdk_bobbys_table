
# Bobby's Table Restaurant Management System

A comprehensive restaurant management system with integrated web and voice interfaces powered by SignalWire Agents Python SDK. Features advanced real-time notifications, configurable audio alerts, and seamless voice-to-web synchronization.

## 🚀 Quick Start

### Run on Replit

Click the button below to import and run this project on Replit:

[![Run on Replit](https://replit.com/badge?theme=dark&variant=small)](https://replit.com/new/github/Len-PGH/agent_sdk_bobbys_table)

### Start the Integrated Service

```bash
# Start the integrated web and voice interface
python start_agents.py
```

This will start a single service on port 8080 with:
- **Web Interface**: http://localhost:8080 (Full restaurant management)
- **Voice Interface**: http://localhost:8080/receptionist (Phone-based ordering and reservations)
- **Kitchen Dashboard**: http://localhost:8080/kitchen (Order management)
- **Calendar View**: http://localhost:8080/calendar (Real-time reservation management)

## 🔊 Audio Notification System

Bobby's Table features a comprehensive, configurable notification system for real-time alerts:

### **Notification Types**
- **chime**: Pleasant chime sound (default)
- **dink**: Short dink sound
- **bell**: Bell-like ring
- **soft**: Quiet soft chime
- **generated**: Computer-generated two-tone chime (no file needed)
- **off**: No sound notifications

### **Environment Configuration**
```bash
# Notification Sound Configuration
NOTIFICATION_SOUND_TYPE=generated    # Sound type (see above options)
NOTIFICATION_VOLUME=0.7             # Volume level (0.0 to 1.0)
NOTIFICATION_FALLBACK=off           # TTS fallback (speech/off)
```

### **Browser Policy Handling**
- **Auto-detection** of user interaction for audio permissions
- **Graceful fallback** when audio is blocked
- **Visual prompts** to enable audio notifications
- **Smart toast positioning** to avoid UI interference

## 🏗️ Core Files Documentation

### Application Core

#### `app.py` - Main Flask Application
The central Flask application that provides both web interface and SWAIG integration.

**Key Features:**
- **Web Routes**: Restaurant management interface, calendar, menu, kitchen dashboard
- **SWAIG Integration**: `/receptionist` endpoint for voice interactions
- **Payment Processing**: Stripe integration with `/api/payment-processor` endpoint
- **Function Validation**: Advanced validation system for speech recognition errors
- **Session Management**: Payment session tracking and callback handling
- **Notification Config**: Environment-driven notification system injection

**Important Functions:**
- `validate_and_correct_function_call()` - Corrects AI routing mistakes and speech recognition errors
- `payment_processor()` - Handles Stripe payment processing
- `signalwire_payment_callback()` - Processes payment callbacks
- `inject_notification_config()` - Injects notification settings into all templates
- `notify_reservation_created()` - Real-time notification endpoint for voice reservations
- `check_voice_reservations()` - Dual-detection system for voice reservation notifications

#### `start_agents.py` - Application Launcher
Unified startup script that initializes the integrated Flask app with SWAIG capabilities.

**Features:**
- Environment configuration validation
- Database initialization
- SignalWire agent setup
- Graceful shutdown handling

#### `swaig_agents.py` - SignalWire Agent Management
Contains the SignalWire agent configuration and skills registration.

**Key Components:**
- `ReceptionistAgent` class with comprehensive restaurant skills
- Skills registration and configuration
- Agent persona and behavior definitions
- Error handling and logging

### Database Layer

#### `models.py` - Database Models
SQLAlchemy models defining the restaurant's data structure.

**Models:**
- `Reservation` - Customer reservations with pre-order support
- `MenuItem` - Menu items with categories and pricing
- `Order` - Customer orders (pickup/delivery)
- `OrderItem` - Individual items within orders
- `PartyOrder` - Pre-orders linked to reservations

**Key Features:**
- Relationship definitions between models
- Validation methods for data integrity
- Utility methods for common operations

#### `schema.sql` - Database Schema
SQL schema definition for restaurant database structure.

**Tables:**
- Reservations, menu items, orders, order items, party orders
- Proper indexing for performance
- Foreign key constraints for data integrity

#### `init_test_data.py` - Sample Data
Populates the database with sample menu items, reservations, and orders for testing.

### Skills Architecture

#### `skills/restaurant_reservation/skill.py` - Reservation Management
Comprehensive reservation management skill for voice interactions.

**Core Functions:**
- `create_reservation()` - Make new reservations with pre-ordering
- `get_reservation()` - Search reservations by multiple criteria
- `pay_reservation()` - Process payments for reservations
- `cancel_reservation()` - Cancel reservations with verification
- `update_reservation()` - Modify existing reservations

**Advanced Features:**
- Fuzzy name matching and phone number normalization
- Speech recognition digit duplication handling
- Context-aware function routing
- SMS confirmation and receipt sending
- Real-time web notification triggers

#### `skills/restaurant_menu/skill.py` - Menu and Ordering
Handles all menu browsing and order placement functionality.

**Core Functions:**
- `get_menu()` - Browse menu with intelligent categorization
- `get_surprise_selections()` - Generate random menu selections for surprise orders
- `create_order()` - Place orders with natural language item extraction
- `pay_order()` - Process payments for orders
- `get_order_status()` - Check order preparation status
- `update_order_status()` - Update order status (kitchen use)

**Advanced Features:**
- Natural language item parsing and fuzzy matching
- Random surprise order generation with pricing
- Drink suggestions based on food orders
- Order modification and cancellation
- Kitchen dashboard integration

#### `skills/utils.py` - Shared Utilities
Common utility functions used across skills.

**Utilities:**
- Phone number normalization
- Date/time parsing and validation
- SMS sending functions
- Database query helpers

### Configuration and Deployment

#### `environment.template` - Environment Configuration
Template for environment variables with detailed documentation.

**Notification Settings:**
- Sound type configuration with all available options
- Volume control and fallback behavior
- Detailed comments explaining each setting

#### `prompt.md` - Agent Prompts
Contains the detailed prompts and instructions for the SignalWire agent.

**Sections:**
- Agent persona and behavior
- Function descriptions and usage
- Error handling guidelines
- Voice interaction best practices
- Surprise order capabilities

#### `requirements.txt` - Dependencies
Complete list of Python packages required for the application.

**Key Dependencies:**
- Flask (web framework)
- SQLAlchemy (database ORM)
- SignalWire Agents SDK
- Stripe (payment processing)
- Requests (HTTP client)

#### `number_utils.py` - Phone Number Processing
Specialized utilities for phone number handling and validation.

**Features:**
- Phone number normalization across multiple formats
- Validation for US phone numbers
- Parsing from various input formats

### User Interface

#### `templates/` - HTML Templates
Jinja2 templates for the web interface with notification config injection.

**Key Templates:**
- `base.html` - Common layout and notification configuration
- `index.html` - Main dashboard
- `calendar.html` - Reservation calendar interface with real-time updates
- `menu.html` - Menu browsing and ordering
- `kitchen.html` - Kitchen dashboard with configurable notifications

#### `static/` - Static Assets
CSS, JavaScript, and image files for the web interface.

**Structure:**
- `css/` - Custom stylesheets
- `js/` - JavaScript for interactive features and notification system
- `sounds/` - Audio notification files (chime, dink, bell, soft-chime)
- `bootstrap/` - Bootstrap CSS framework
- `fontawesome/` - Icon fonts
- `fullcalendar/` - Calendar widget

**Key JavaScript Files:**
- `calendar.js` - Real-time reservation notifications, audio handling, browser policy management
- `cart.js` - Shopping cart functionality
- `menu.js` - Menu browsing and ordering

### Testing and Debugging

#### `test_swaig_functions.py` - Function Testing
Comprehensive testing suite for SWAIG functions.

**Test Categories:**
- Reservation management tests
- Menu and ordering tests
- Payment processing tests
- Error handling validation

## 🔧 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Flask Application (app.py)               │
├─────────────────────────────────────────────────────────────┤
│  Web Interface     │  SWAIG Endpoint    │  Payment Processor │
│  (HTML/CSS/JS)     │  (/receptionist)   │  (Stripe)         │
│  + Notifications   │  + Voice Alerts    │  + SMS Receipts   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                SignalWire Agent (swaig_agents.py)           │
├─────────────────────────────────────────────────────────────┤
│  Reservation Skill  │  Menu Skill       │  Shared Utils     │
│  (reservations)     │  (ordering +      │  (phone, SMS,     │
│  + Web Notifications│   surprise)       │   notifications)  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Database Layer (models.py)               │
├─────────────────────────────────────────────────────────────┤
│  Reservations  │  Menu Items  │  Orders  │  Party Orders    │
│  (SQLAlchemy)  │  (SQLAlchemy)│  (SQLAlchemy)│  (SQLAlchemy)│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Real-time Notification System                  │
├─────────────────────────────────────────────────────────────┤
│  Voice → Web Sync  │  Configurable Audio │  Browser Policy  │
│  Dual Detection    │  Environment Config │  Smart Fallbacks │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Deployment on Replit

### Environment Configuration

1. **Set environment variables in Replit Secrets**:
   ```bash
   # Flask Configuration
   FLASK_ENV=production
   SECRET_KEY=a1b2c3d4super7h8i9j0k1l2m3n4osecret8s9t0u1vkeyx4y5z6
   DEBUG=False
   
   # Database Configuration
   DATABASE_URL=sqlite:///instance/restaurant.db
   
   # SignalWire Configuration (Voice & SMS)
   SIGNALWIRE_PROJECT_ID=12345678-1234-5678-9abc-123456789def
   SIGNALWIRE_TOKEN=PTxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   SIGNALWIRE_SPACE=subdomainname
   SIGNALWIRE_FROM_NUMBER=+15551234567
   
   # Stripe Payment Configuration
   STRIPE_PUBLISHABLE_KEY=pk_test_51234567890abcdefghijklmnopqrstuvwxyzABCDEF
   STRIPE_API_KEY=sk_test_51234567890abcdefghijklmnopqrstuvwxyzABCDEF

   
   # Application Configuration
   APP_HOST=0.0.0.0
   APP_PORT=8080
   APP_DOMAIN=https://your-repl-name.your-username.repl.co
   SIGNALWIRE_PAYMENT_CONNECTOR_URL=https://your-repl-name.your-username.repl.co
   BASE_URL=https://your-repl-name.your-username.repl.co
   
   # Logging Configuration
   LOG_LEVEL=DEBUG
   LOG_FILE=logs/app.log
   
   
   # Notification Sound Configuration
   NOTIFICATION_SOUND_TYPE=generated
   NOTIFICATION_VOLUME=0.7
   NOTIFICATION_FALLBACK=off

   # Available NOTIFICATION_SOUND_TYPE options:
   # - chime: Pleasant chime sound (default)
   # - dink: Short dink sound
   # - bell: Bell-like ring
   # - soft: Quiet soft chime
   # - generated: Computer-generated two-tone chime (no file needed)
   # - off: No sound notifications

   ```

2. **Configure webhook URLs**:
   - Use your Replit app URL for a debug webhook
   - Example: `https://your-repl-name.your-username.repl.co/webhook-debug-console`

### SignalWire Configuration

1. Create SignalWire project
2. Configure phone numbers
3. Set webhook URLs:
   - Voice: `https://your-repl-name.your-username.repl.co/receptionist`
   - SMS: `https://your-repl-name.your-username.repl.co/receptionist`

## 🛠️ Installation

### Prerequisites

- Python 3.9+
- SignalWire account (for voice features)
- Stripe account (for payment processing)

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd bobbystable
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Initialize database**
   ```bash
   python init_db.py
   python init_test_data.py  # Optional: Add sample data
   ```

4. **Configure environment**
   ```bash
   # Copy template and configure
   cp environment.template .env
   # Edit .env with your credentials and preferences
   
   # Example .env configuration:
   FLASK_ENV=production
   SECRET_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
   SIGNALWIRE_PROJECT_ID=12345678-1234-5678-9abc-123456789def
   SIGNALWIRE_TOKEN=PTxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   SIGNALWIRE_SPACE=example-space.signalwire.com
   SIGNALWIRE_FROM_NUMBER=+15551234567
   STRIPE_PUBLISHABLE_KEY=pk_test_51234567890abcdefghijklmnopqrstuvwxyzABCDEF
   STRIPE_SECRET_KEY=sk_test_51234567890abcdefghijklmnopqrstuvwxyzABCDEF
   STRIPE_API_KEY=sk_test_51234567890abcdefghijklmnopqrstuvwxyzABCDEF
   NOTIFICATION_SOUND_TYPE=generated
   NOTIFICATION_VOLUME=0.7
   NOTIFICATION_FALLBACK=off
   ```

## 🧪 Testing

### Run All Tests

```bash
# Test SWAIG functions
python test_swaig_functions.py

# Test individual components
python -c "from models import *; print('Models imported successfully')"
python -c "from skills.restaurant_reservation.skill import RestaurantReservationSkill; print('Reservation skill imported')"
python -c "from skills.restaurant_menu.skill import RestaurantMenuSkill; print('Menu skill imported')"
```

### Test Notification System

```bash
# Test in browser console (calendar page)
playNotificationSound()              # Test configured sound
testGeneratedChime()                # Test generated tone
window.notificationConfig           # View current config
```

## 🌟 Key Features

### Advanced Voice-to-Web Synchronization
- **Dual Detection System**: Primary notification + database fallback for 100% reliability
- **Real-time Updates**: Voice reservations appear instantly in web interface
- **Smart Session Management**: Prevents duplicate notifications
- **Cross-platform Persistence**: Notifications work across multiple browser tabs

### Intelligent Audio Management
- **Browser Policy Compliance**: Handles modern browser autoplay restrictions
- **User Interaction Detection**: Automatically enables audio after first click
- **Graceful Degradation**: Visual prompts when audio is unavailable
- **Environment-driven Configuration**: Easily customizable via .env variables

### Advanced Speech Recognition Handling
- **Digit Duplication Detection**: Automatically corrects speech recognition errors
- **Context-Aware Routing**: Routes function calls based on conversation context
- **Confidence Scoring**: Only applies corrections when highly confident
- **Surprise Order Generation**: AI can create random menu selections with pricing

### Comprehensive Payment Integration
- **Stripe Processing**: Secure credit card processing via SignalWire
- **Payment Session Management**: Tracks payment states across conversations
- **SMS Receipts**: Automatic confirmation messages
- **Retry Logic**: Handles failed payments gracefully

### Real-time Kitchen Operations
- **Live Order Updates**: Kitchen dashboard updates in real-time
- **Configurable Notifications**: Sound alerts for new orders
- **Visual Indicators**: Flash notifications and browser notifications
- **Cross-platform Compatibility**: Works on web and voice simultaneously

---

**Bobby's Table** - Where technology meets hospitality! 🍽️📞🔊
