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
    
    # Required fields for Retell webhook format
    required_fields = ['event', 'call']
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    
    # Validate event type
    if 'event' in data:
        valid_events = ['call_started', 'call_ended', 'call_analyzed']
        if data['event'] not in valid_events:
            errors.append(f"Invalid event. Must be one of: {', '.join(valid_events)}")
    
    # Validate call object
    if 'call' in data:
        call_data = data['call']
        if not isinstance(call_data, dict):
            errors.append("call must be an object")
        else:
            # Validate required call fields
            call_required_fields = ['call_id']
            for field in call_required_fields:
                if field not in call_data:
                    errors.append(f"Missing required call field: {field}")
            
            # Validate call_id format
            if 'call_id' in call_data and not isinstance(call_data['call_id'], str):
                errors.append("call_id must be a string")
            
            # Validate timestamps if present
            if 'start_timestamp' in call_data:
                if not isinstance(call_data['start_timestamp'], (int, float)) or call_data['start_timestamp'] < 0:
                    errors.append("start_timestamp must be a non-negative number")
            
            if 'end_timestamp' in call_data:
                if not isinstance(call_data['end_timestamp'], (int, float)) or call_data['end_timestamp'] < 0:
                    errors.append("end_timestamp must be a non-negative number")
    
    return len(errors) == 0, errors

def validate_retell_inbound_webhook(data: Dict[str, Any]) -> tuple[bool, List[str]]:
    """
    Validate Retell AI inbound webhook data
    
    Args:
        data: Inbound webhook data dictionary
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Check if data is a dictionary
    if not isinstance(data, dict):
        errors.append("Data must be a JSON object")
        return False, errors
    
    # Required fields for inbound webhook format
    required_fields = ['event', 'call_inbound']
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    
    # Validate event type
    if 'event' in data:
        if data['event'] != 'call_inbound':
            errors.append("Invalid event. Must be 'call_inbound'")
    
    # Validate call_inbound object
    if 'call_inbound' in data:
        call_inbound_data = data['call_inbound']
        if not isinstance(call_inbound_data, dict):
            errors.append("call_inbound must be an object")
        else:
            # Validate required call_inbound fields
            call_inbound_required_fields = ['from_number', 'to_number']
            for field in call_inbound_required_fields:
                if field not in call_inbound_data:
                    errors.append(f"Missing required call_inbound field: {field}")
            
            # Validate phone number formats (basic validation)
            if 'from_number' in call_inbound_data:
                from_number = call_inbound_data['from_number']
                if not isinstance(from_number, str) or not from_number.startswith('+'):
                    errors.append("from_number must be a string starting with '+'")
            
            if 'to_number' in call_inbound_data:
                to_number = call_inbound_data['to_number']
                if not isinstance(to_number, str) or not to_number.startswith('+'):
                    errors.append("to_number must be a string starting with '+'")
            
            # Validate agent_id if present
            if 'agent_id' in call_inbound_data:
                agent_id = call_inbound_data['agent_id']
                if not isinstance(agent_id, str):
                    errors.append("agent_id must be a string")
    
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
    Sanitize Retell AI webhook data for safe storage
    
    Args:
        data: Raw webhook data
    
    Returns:
        Sanitized data dictionary
    """
    sanitized = {}
    
    # Sanitize top-level fields
    if 'event' in data:
        sanitized['event'] = str(data['event'])
    
    # Sanitize call object
    if 'call' in data and isinstance(data['call'], dict):
        call_data = data['call']
        sanitized_call = {}
        
        # Define call field mappings and sanitization rules
        call_field_mappings = {
            'call_id': str,
            'agent_id': str,
            'call_type': str,
            'from_number': str,
            'to_number': str,
            'direction': str,
            'call_status': str,
            'disconnection_reason': str,
            'transcript': str,
            'start_timestamp': (int, float),
            'end_timestamp': (int, float),
            'duration_ms': (int, float),
            'recording_url': str,
            'opt_out_sensitive_data_storage': bool
        }
        
        for field, expected_type in call_field_mappings.items():
            if field in call_data:
                value = call_data[field]
                
                # Type conversion and validation
                try:
                    if isinstance(expected_type, tuple):
                        # Handle multiple allowed types
                        if any(isinstance(value, t) for t in expected_type):
                            sanitized_call[field] = value
                        else:
                            # Try to convert to first type in tuple
                            sanitized_call[field] = expected_type[0](value)
                    else:
                        sanitized_call[field] = expected_type(value)
                except (ValueError, TypeError):
                    # Skip invalid fields
                    continue
        
        # Handle complex objects (metadata, dynamic variables)
        if 'metadata' in call_data and isinstance(call_data['metadata'], dict):
            sanitized_call['metadata'] = call_data['metadata']
        
        if 'retell_llm_dynamic_variables' in call_data and isinstance(call_data['retell_llm_dynamic_variables'], dict):
            sanitized_call['retell_llm_dynamic_variables'] = call_data['retell_llm_dynamic_variables']
        
        if 'collected_dynamic_variables' in call_data and isinstance(call_data['collected_dynamic_variables'], dict):
            sanitized_call['collected_dynamic_variables'] = call_data['collected_dynamic_variables']
        
        if 'call_cost' in call_data and isinstance(call_data['call_cost'], dict):
            sanitized_call['call_cost'] = call_data['call_cost']
        
        if 'transcript_object' in call_data and isinstance(call_data['transcript_object'], list):
            sanitized_call['transcript_object'] = call_data['transcript_object']
        
        if 'transcript_with_tool_calls' in call_data and isinstance(call_data['transcript_with_tool_calls'], list):
            sanitized_call['transcript_with_tool_calls'] = call_data['transcript_with_tool_calls']
        
        sanitized['call'] = sanitized_call
    
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