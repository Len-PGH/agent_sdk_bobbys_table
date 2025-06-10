#!/bin/bash

# Exit on any error
set -e

# Install requirements using UPM (Universal Package Manager)
echo "Installing requirements..."
upm install

# Check if init_db.py exists
if [ ! -f "init_db.py" ]; then
    echo "Error: init_db.py not found."
    exit 1
fi

# Check if init_test_data.py exists
if [ ! -f "init_test_data.py" ]; then
    echo "Error: init_test_data.py not found."
    exit 1
fi

# Check if app.py exists
if [ ! -f "app.py" ]; then
    echo "Error: app.py not found."
    exit 1
fi

# Initialize the database
echo "Running init_db.py to initialize the database..."
python init_db.py

# Load test data
echo "Running init_test_data.py to load test data..."
python init_test_data.py

# Run the application
echo "Starting the application..."
python app.py
