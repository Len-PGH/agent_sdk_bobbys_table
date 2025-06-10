#!/bin/bash

# Exit on any error
set -e

# Debug: Print shell and Python version
echo "Running in shell: $SHELL"
echo "Python3 version: $(python3 --version 2>&1)"

# Remove existing venv if it exists
if [ -d "venv" ]; then
    echo "Removing existing virtual environment..."
    rm -rf venv
fi

# Check if python3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed or not found in PATH."
    exit 1
fi

# Create new virtual environment
echo "Creating new virtual environment..."
if ! python3 -m venv venv; then
    echo "Error: Failed to create virtual environment."
    exit 1
fi

# Check if activate script exists
if [ ! -f "venv/bin/activate" ]; then
    echo "Error: activate script not found. Virtual environment creation may have failed."
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "PATH after activation: $PATH"
echo "Python used: $(which python)"
echo "Pip used: $(which pip)"

# Verify pip is available
if ! command -v pip &> /dev/null; then
    echo "Error: pip is not available in the virtual environment."
    exit 1
fi

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    echo "Error: requirements.txt not found."
    exit 1
fi

# Install requirements
echo "Installing requirements..."
pip install --no-cache-dir -r requirements.txt

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