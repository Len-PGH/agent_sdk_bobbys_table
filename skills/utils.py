"""
Shared utilities for restaurant skills
"""

import re
from typing import Optional, List, Dict, Any

def normalize_phone_number(phone_number: Optional[str], caller_id: Optional[str] = None) -> Optional[str]:
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

def extract_phone_from_conversation(call_log: List[Dict[str, Any]]) -> Optional[str]:
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
                        normalized = normalize_phone_number(extracted_phone)
                        print(f"🔄 Extracted phone number from conversation: {normalized}")
                        return normalized
                    else:
                        # Take available digits and normalize
                        extracted_phone = ''.join(phone_digits)
                        normalized = normalize_phone_number(extracted_phone)
                        print(f"🔄 Extracted partial phone number from conversation: {normalized}")
                        return normalized
    
    return None

def validate_date_format(date_str: str) -> bool:
    """
    Validate date string is in YYYY-MM-DD format
    
    Args:
        date_str: Date string to validate
        
    Returns:
        True if valid format, False otherwise
    """
    if not date_str:
        return False
    
    try:
        from datetime import datetime
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False

def validate_time_format(time_str: str) -> bool:
    """
    Validate time string is in HH:MM format
    
    Args:
        time_str: Time string to validate
        
    Returns:
        True if valid format, False otherwise
    """
    if not time_str:
        return False
    
    try:
        from datetime import datetime
        datetime.strptime(time_str, '%H:%M')
        return True
    except ValueError:
        return False

def validate_party_size(party_size: int) -> bool:
    """
    Validate party size is within reasonable limits
    
    Args:
        party_size: Number of people in party
        
    Returns:
        True if valid, False otherwise
    """
    return isinstance(party_size, int) and 1 <= party_size <= 20

def validate_business_hours(time_str: str) -> bool:
    """
    Validate time is within business hours (8 AM - 10 PM)
    
    Args:
        time_str: Time string in HH:MM format
        
    Returns:
        True if within business hours, False otherwise
    """
    if not validate_time_format(time_str):
        return False
    
    try:
        from datetime import datetime
        time_obj = datetime.strptime(time_str, '%H:%M').time()
        # Business hours: 8:00 AM to 10:00 PM
        return time_obj >= datetime.strptime('08:00', '%H:%M').time() and \
               time_obj <= datetime.strptime('22:00', '%H:%M').time()
    except ValueError:
        return False 