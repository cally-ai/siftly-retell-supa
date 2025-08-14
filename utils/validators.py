"""
Validation utilities for the Siftly application
"""
from typing import Dict, Any
import re

def validate_retell_inbound_webhook(data: Dict[str, Any]) -> None:
    """
    Validate Retell inbound webhook data
    
    Args:
        data: The webhook payload to validate
        
    Raises:
        ValueError: If validation fails
    """
    if not isinstance(data, dict):
        raise ValueError("Data must be a dictionary")
    
    # Check required top-level fields
    if 'event' not in data:
        raise ValueError("Missing required field: event")
    
    if data['event'] != 'call_inbound':
        raise ValueError("Event must be 'call_inbound'")
    
    if 'call_inbound' not in data:
        raise ValueError("Missing required field: call_inbound")
    
    inbound_data = data['call_inbound']
    if not isinstance(inbound_data, dict):
        raise ValueError("call_inbound must be a dictionary")
    
    # Validate phone numbers if present
    for field in ['from_number', 'to_number']:
        if field in inbound_data:
            phone_number = inbound_data[field]
            if not isinstance(phone_number, str):
                raise ValueError(f"{field} must be a string")
            
            # Phone numbers should start with '+'
            if not phone_number.startswith('+'):
                raise ValueError(f"{field} must start with '+'")
            
            # Basic phone number format validation (at least 7 digits)
            digits_only = re.sub(r'[^\d]', '', phone_number)
            if len(digits_only) < 7:
                raise ValueError(f"{field} must contain at least 7 digits")
    
    # Validate other fields if present
    for field in ['agent_id', 'phone_number_id']:
        if field in inbound_data:
            value = inbound_data[field]
            if not isinstance(value, str):
                raise ValueError(f"{field} must be a string")
            if not value.strip():
                raise ValueError(f"{field} cannot be empty")