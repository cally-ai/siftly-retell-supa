"""
Validation utilities for the Siftly application
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import re

def validate_retell_webhook(data: Dict[str, Any]) -> tuple[bool, List[str]]:
    """
    Validate Retell AI webhook data
    
    Args:
        data: Webhook data dictionary
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Check if data is a dictionary
    if not isinstance(data, dict):
        errors.append("Data must be a JSON object")
        return False, errors
    
    # Required fields
    required_fields = ['event_type', 'call_id']
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    
    # Validate event_type
    if 'event_type' in data:
        valid_events = ['call_started', 'call_ended', 'call_transferred', 'call_failed']
        if data['event_type'] not in valid_events:
            errors.append(f"Invalid event_type. Must be one of: {', '.join(valid_events)}")
    
    # Validate call_id format (basic validation)
    if 'call_id' in data and not isinstance(data['call_id'], str):
        errors.append("call_id must be a string")
    
    # Validate duration if present
    if 'duration' in data:
        if not isinstance(data['duration'], (int, float)) or data['duration'] < 0:
            errors.append("duration must be a non-negative number")
    
    # Validate cost if present
    if 'cost' in data:
        if not isinstance(data['cost'], (int, float)) or data['cost'] < 0:
            errors.append("cost must be a non-negative number")
    
    # Validate sentiment if present
    if 'sentiment' in data:
        valid_sentiments = ['positive', 'negative', 'neutral', 'mixed']
        if data['sentiment'] not in valid_sentiments:
            errors.append(f"Invalid sentiment. Must be one of: {', '.join(valid_sentiments)}")
    
    return len(errors) == 0, errors

def validate_airtable_record(data: Dict[str, Any]) -> tuple[bool, List[str]]:
    """
    Validate Airtable record data
    
    Args:
        data: Record data dictionary
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Check if data is a dictionary
    if not isinstance(data, dict):
        errors.append("Data must be a JSON object")
        return False, errors
    
    # Check for empty data
    if not data:
        errors.append("Record data cannot be empty")
    
    # Validate field names (Airtable has some restrictions)
    for field_name in data.keys():
        if not isinstance(field_name, str):
            errors.append("Field names must be strings")
            break
        
        # Check for invalid characters in field names
        if re.search(r'[<>"/\\?*|]', field_name):
            errors.append(f"Field name '{field_name}' contains invalid characters")
    
    return len(errors) == 0, errors

def sanitize_webhook_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize webhook data for safe storage
    
    Args:
        data: Raw webhook data
    
    Returns:
        Sanitized data dictionary
    """
    sanitized = {}
    
    # Define field mappings and sanitization rules
    field_mappings = {
        'event_type': str,
        'call_id': str,
        'agent_id': str,
        'customer_id': str,
        'status': str,
        'transcript': str,
        'summary': str,
        'sentiment': str,
        'duration': (int, float),
        'cost': (int, float)
    }
    
    for field, expected_type in field_mappings.items():
        if field in data:
            value = data[field]
            
            # Type conversion and validation
            try:
                if isinstance(expected_type, tuple):
                    # Handle multiple allowed types
                    if any(isinstance(value, t) for t in expected_type):
                        sanitized[field] = value
                    else:
                        # Try to convert to first type in tuple
                        sanitized[field] = expected_type[0](value)
                else:
                    sanitized[field] = expected_type(value)
            except (ValueError, TypeError):
                # Skip invalid fields
                continue
    
    return sanitized

def validate_email(email: str) -> bool:
    """
    Validate email format
    
    Args:
        email: Email string to validate
    
    Returns:
        True if valid email format, False otherwise
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_phone(phone: str) -> bool:
    """
    Validate phone number format (basic validation)
    
    Args:
        phone: Phone string to validate
    
    Returns:
        True if valid phone format, False otherwise
    """
    # Remove all non-digit characters
    digits_only = re.sub(r'\D', '', phone)
    return len(digits_only) >= 10 and len(digits_only) <= 15 