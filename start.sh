#!/bin/bash

# Exit on any error
set -e

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
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Verify pip is available in the virtual environment
if ! command -v pip &> /dev/null; then
    echo "Error: pip is not available in the virtual environment."
    exit 1
fi

# Upgrade pip to the latest version
echo "Upgrading pip..."
pip install --upgrade pip

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    echo "Error: requirements.txt not found."
    exit 1
fi

# Install requirements with no cache
echo "Installing requirements..."
pip install --no-cache-dir -r requirements.txt

# Check if app.py exists
if [ ! -f "app.py" ]; then
    echo "Error: app.py not found."
    exit 1
fi

# Run the application
echo "Starting the application..."
python app.py