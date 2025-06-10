# Bobby's Table Reservation System

A comprehensive restaurant management system with integrated web and voice interfaces powered by SignalWire Agents.

## 🚀 Quick Start

### Start the Integrated Service

```bash
# Start the integrated web and voice interface
python start_agents.py
```

This will start a single service on port 8080 with:
- **Web Interface**: http://localhost:8080 (Full restaurant management)
- **Voice Interface**: http://localhost:8080/receptionist (Phone-based ordering and reservations)
- **Kitchen Dashboard**: http://localhost:8080/kitchen (Order management)

### Test Voice Functions

```bash
# Test all SWAIG voice functions via HTTP
python test_swaig_functions.py
```

## 🎯 SWAIG Integration

Bobby's Table integrates with SignalWire's AI Gateway (SWAIG) to provide voice-enabled restaurant services. The system uses a skills-based architecture for modular functionality.

### 📞 Voice Interface

**Primary SWAIG Endpoint**: `/receptionist`
- **URL**: `http://localhost:8080/receptionist`
- **Authentication**: Basic Auth (admin/admin)
- **Purpose**: Main voice interface for all restaurant functions

### 🛠️ Available Functions

The voice assistant can handle 12 different functions:

#### Reservation Management
- **`create_reservation`** - Make new reservations with full details
- **`get_reservation`** - Search reservations by any criteria (name, phone, ID, date, party size)
- **`update_reservation`** - Modify existing reservations
- **`cancel_reservation`** - Cancel reservations with verification

#### Menu & Ordering
- **`get_menu`** - Browse menu items by category or view complete menu
- **`create_order`** - Place orders for pickup or delivery
- **`get_order_status`** - Check order preparation status
- **`update_order_status`** - Update order status (kitchen use)

#### Utility Functions
- **`get_current_time`** - Get current time
- **`get_current_date`** - Get current date
- **`transfer_to_manager`** - Transfer complex issues to management
- **`schedule_callback`** - Schedule customer callbacks

## 🌐 Web Interface Features

The web interface provides a complete restaurant management dashboard:

- **Reservation Calendar**: Visual calendar with drag-and-drop functionality
- **Menu Management**: Browse and order from categorized menu items
- **Shopping Cart**: Add items to cart with quantity management
- **Order Tracking**: Real-time order status updates
- **Kitchen Dashboard**: Three-column workflow (Pending → Preparing → Ready)
- **Time Filtering**: Filter orders by date and time ranges

## 🏗️ Integrated Architecture

```
┌─────────────────┐    ┌─────────────────────────────────────┐
│   SignalWire    │    │         Flask App (Port 8080)       │
│   Platform      │◄──►│  ┌─────────────┐ ┌─────────────────┐ │
└─────────────────┘    │  │ Web Routes  │ │ SWAIG Functions │ │
                       │  │             │ │ (/receptionist) │ │
                       │  └─────────────┘ └─────────────────┘ │
                       │              │                      │
                       │              ▼                      │
                       │         ┌─────────────────┐         │
                       │         │   SQLite DB     │         │
                       │         │   (Shared)      │         │
                       │         └─────────────────┘         │
                       └─────────────────────────────────────┘
```

## 📋 Table of Contents

1. [Installation](#installation)
2. [Configuration](#configuration)
3. [Usage](#usage)
4. [API Endpoints](#api-endpoints)
5. [SWAIG Functions](#swaig-functions)
6. [Development](#development)
7. [Deployment](#deployment)

## 🛠️ Installation

### Prerequisites

- Python 3.8+
- Node.js (for frontend dependencies)
- SignalWire account (for voice features)

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd bobbystable
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   npm install  # For frontend dependencies
   ```

4. **Initialize database**
   ```bash
   python init_db.py
   python init_test_data.py  # Optional: Add sample data
   ```

5. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your SignalWire credentials
   ```

## ⚙️ Configuration

Create a `.env` file with the following variables:

```env
# SignalWire Configuration
SIGNALWIRE_PROJECT_ID=your_project_id
SIGNALWIRE_TOKEN=your_token
SIGNALWIRE_SPACE_URL=your_space_url

# Flask Configuration
FLASK_ENV=development
SECRET_KEY=your_secret_key

# Database
DATABASE_URL=sqlite:///instance/restaurant.db
```

## 🚀 Usage

### Start the Integrated Service

```bash
# Start the integrated web and voice interface
python start_agents.py
```

### Alternative: Start Flask App Directly

```bash
# Start Flask app with integrated SWAIG functions
python app.py
```

### Access the Application

- **Web Interface**: http://localhost:8080
- **Voice Interface**: http://localhost:8080/receptionist
- **Kitchen Dashboard**: http://localhost:8080/kitchen

## 🔌 API Endpoints

### Reservations

- `GET /api/reservations` - List all reservations
- `POST /api/reservations` - Create new reservation
- `GET /api/reservations/<id>` - Get specific reservation
- `PUT /api/reservations/<id>` - Update reservation
- `DELETE /api/reservations/<id>` - Delete reservation
- `GET /api/reservations/calendar` - Get calendar events

### Menu Items

- `GET /api/menu_items` - List all menu items
- `GET /api/menu_items/<id>` - Get specific menu item

### Orders

- `GET /api/orders` - List all orders
- `POST /api/orders` - Create new order
- `PUT /api/orders/<id>/status` - Update order status

## 📞 SWAIG Functions

The voice interface provides the following functions:

### Reservation Management

- **`create_reservation`** - Create new reservations
- **`get_reservation`** - Look up reservations by phone number
- **`update_reservation`** - Modify existing reservations
- **`cancel_reservation`** - Cancel reservations

### Menu & Ordering

- **`get_menu`** - Browse menu items by category
- **`create_order`** - Place orders for pickup or delivery
- **`get_order_status`** - Check order status

### Kitchen Operations

- **`update_order_status`** - Update order status (for staff)

For detailed SWAIG documentation, see [SWAIG_README.md](SWAIG_README.md).

## 🧪 Testing

### Run All Tests

```bash
# Test SWAIG functions
python test_swaig_functions.py

# Test web functionality (manual testing via browser)
python app.py
```

### Test Individual Components

```bash
# Test database models
python -c "from models import *; print('Models imported successfully')"

# Test agent creation
python -c "from swaig_agents import RestaurantReceptionistAgent; print('Agent created successfully')"
```

## 🔧 Development

### Project Structure

```
bobbystable/
├── app.py                 # Main Flask application
├── swaig_agents.py        # SignalWire agents
├── models.py              # Database models
├── start_agents.py        # Startup script
├── test_swaig_functions.py # SWAIG tests
├── templates/             # HTML templates
├── static/               # CSS, JS, images
├── instance/             # Database files
└── requirements.txt      # Python dependencies
```

### Adding New Features

1. **Web Features**: Add routes to `app.py`, templates to `templates/`, and static files to `static/`
2. **Voice Features**: Add methods to `RestaurantReceptionistAgent` class in `swaig_agents.py`
3. **Database Changes**: Update `models.py` and create migration scripts

### Code Style

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings to all functions
- Include error handling and validation

## 🚀 Deployment

### Production Setup

1. **Environment Configuration**
   ```bash
   export FLASK_ENV=production
   export SIGNALWIRE_PROJECT_ID=your_production_project_id
   export SIGNALWIRE_TOKEN=your_production_token
   ```

2. **Database Setup**
   ```bash
   # Use PostgreSQL for production
   export DATABASE_URL=postgresql://user:password@localhost/restaurant_db
   ```

3. **Start Services**
   ```bash
   # Use production WSGI server
   gunicorn app:app --bind 0.0.0.0:5000 &
   python swaig_agents.py &
   ```

### Docker Deployment

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000 8001

CMD ["python", "start_agents.py"]
```

### SignalWire Configuration

1. Create SignalWire project
2. Configure phone numbers
3. Set webhook URLs:
   - Voice: `https://yourdomain.com:8001/receptionist`
   - SMS: `https://yourdomain.com:8001/receptionist`

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:

- Check the [SWAIG_README.md](SWAIG_README.md) for voice interface details
- Review the code comments and docstrings
- Test with the provided test scripts

---

**Bobby's Table** - Where technology meets hospitality! 🍽️📞 