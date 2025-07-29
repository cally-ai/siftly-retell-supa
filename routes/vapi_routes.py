"""
VAPI AI webhook route handlers
"""
from flask import Blueprint, request, jsonify
from typing import Dict, Any, Optional
from config import Config
from services.airtable_service import AirtableService
from utils.logger import get_logger

logger = get_logger(__name__)

# Create blueprint
vapi_bp = Blueprint('vapi', __name__, url_prefix='/vapi')

class VAPIWebhookService:
    """Service for handling VAPI AI webhook operations"""
    
    def __init__(self):
        self.airtable_service = AirtableService()
    
    def get_assistant_configuration(self, from_number: str) -> Optional[Dict[str, Any]]:
        """
        Get assistant configuration and dynamic variables for VAPI AI
        
        Args:
            from_number: The caller's phone number
            
        Returns:
            Assistant configuration with dynamic variables or None if not found
        """
        try:
            logger.info(f"Getting assistant configuration for: {from_number}")
            
            # Step 1: Look up the from_number in the caller table
            logger.info(f"Searching caller table for phone number: {from_number}")
            caller_records = self.airtable_service.search_records_in_table(
                table_name="tbl3mjOWELyIG2m6o",  # caller table
                field="phone_number", 
                value=from_number
            )
            
            logger.info(f"Found {len(caller_records)} caller records for {from_number}")
            
            if not caller_records:
                logger.warning(f"No caller record found for: {from_number}")
                return None
            
            caller_record = caller_records[0]
            logger.info(f"Found caller record: {caller_record.get('id')}")
            
            # Step 2: Get the linked language record
            language_linked_ids = caller_record.get('fields', {}).get('language', [])
            if not language_linked_ids:
                logger.warning(f"No language linked to caller: {from_number}")
                return None
            
            # Get the first linked language record
            language_record_id = language_linked_ids[0]
            language_record = self.airtable_service.get_record_from_table(
                table_name="language",
                record_id=language_record_id
            )
            
            if not language_record:
                logger.warning(f"Language record not found: {language_record_id}")
                return None
            
            # Step 3: Get the linked vapi_assistant record
            vapi_assistant_linked_ids = language_record.get('fields', {}).get('vapi_assistant', [])
            if not vapi_assistant_linked_ids:
                logger.warning(f"No vapi_assistant linked to language record: {language_record_id}")
                return None
            
            # Get the first linked vapi_assistant record
            vapi_assistant_record_id = vapi_assistant_linked_ids[0]
            vapi_assistant_record = self.airtable_service.get_record_from_table(
                table_name=Config.TABLE_ID_VAPI_ASSISTANT,
                record_id=vapi_assistant_record_id
            )
            
            if not vapi_assistant_record:
                logger.warning(f"VAPI assistant record not found: {vapi_assistant_record_id}")
                return None
            
            # Step 4: Extract assistant_id
            assistant_id = vapi_assistant_record.get('fields', {}).get('assistant_id')
            if not assistant_id:
                logger.warning(f"No assistant_id found in VAPI assistant record: {vapi_assistant_record_id}")
                return None
            
            # Step 5: Get dynamic variables (similar to Retell inbound logic)
            dynamic_variables = self._get_dynamic_variables_for_caller(from_number)
            
            logger.info(f"Found assistant_id: {assistant_id} for from_number: {from_number}")
            
            return {
                "assistantId": assistant_id,
                "assistantOverrides": {
                    "variableValues": dynamic_variables
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting assistant configuration: {e}")
            return None
    
    def _get_dynamic_variables_for_caller(self, from_number: str) -> Dict[str, Any]:
        """
        Get dynamic variables for the caller (similar to Retell inbound logic)
        
        Args:
            from_number: The caller's phone number
            
        Returns:
            Dictionary of dynamic variables
        """
        try:
            # This follows the same pattern as the Retell inbound webhook
            # Look up customer data based on the phone number
            customer_data = self._get_customer_data_by_phone(from_number)
            
            if customer_data:
                # Known customer - use their specific dynamic variables
                return customer_data
            else:
                # Unknown caller - use default configuration
                return {
                    "customerName": "New Customer",
                    "accountType": "new",
                    "joinDate": "2024"
                }
                
        except Exception as e:
            logger.error(f"Error getting dynamic variables for caller: {e}")
            return {
                "customerName": "Unknown",
                "accountType": "unknown",
                "joinDate": "2024"
            }
    
    def _get_customer_data_by_phone(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """
        Get customer data from Airtable based on phone number
        (Follows the same pattern as Retell inbound logic)
        
        Args:
            phone_number: The phone number to look up
            
        Returns:
            Customer data dictionary or None if not found
        """
        try:
            # Step 1: Find the phone number in twilio_number table
            twilio_records = self.airtable_service.search_records_in_table(
                table_name="twilio_number",
                field="twilio_number", 
                value=phone_number
            )
            
            if not twilio_records:
                logger.info(f"No twilio_number record found for: {phone_number}")
                return None
            
            twilio_record = twilio_records[0]
            logger.info(f"Found twilio_number record: {twilio_record.get('id')}")
            
            # Step 2: Get the linked client record
            client_linked_ids = twilio_record.get('fields', {}).get('client', [])
            if not client_linked_ids:
                logger.warning(f"No client linked to twilio_number: {phone_number}")
                return None
            
            # Get the first linked client record
            client_record_id = client_linked_ids[0]
            client_record = self.airtable_service.get_record_from_table(
                table_name="client",
                record_id=client_record_id
            )
            
            if not client_record:
                logger.warning(f"Client record not found: {client_record_id}")
                return None
            
            # Step 3: Get dynamic variables from client_dynamic_variables table (same as Retell)
            client_fields = client_record.get('fields', {})
            dynamic_variables = {}
            
            # Get dynamic_variables record ID from client
            dynamic_variables_record_id = client_fields.get('dynamic_variables', [None])[0] if client_fields.get('dynamic_variables') else None
            
            if dynamic_variables_record_id:
                # Get dynamic variables record
                dynamic_record = self.airtable_service.get_record_from_table(
                    table_name="client_dynamic_variables",
                    record_id=dynamic_variables_record_id
                )
                
                if dynamic_record:
                    # Extract fields from dynamic_variables table
                    dynamic_fields = dynamic_record.get('fields', {})
                    excluded_fields = ['name', 'client_dynamic_variables_id', 'client']
                    for field_name, field_value in dynamic_fields.items():
                        if field_name not in excluded_fields:
                            dynamic_variables[field_name] = field_value
            
            # Step 4: Get language agent names from language_agent_names table (same as Retell)
            language_agent_names = client_fields.get('language_agent_names', [])
            
            for linked_record_id in language_agent_names:
                language_record = self.airtable_service.get_record_from_table(
                    table_name="language_agent_names",
                    record_id=linked_record_id
                )
                
                if language_record:
                    key_pair_value = language_record.get('fields', {}).get('key_pair', '')
                    if key_pair_value and '=' in key_pair_value:
                        parts = key_pair_value.split('=', 1)
                        if len(parts) == 2:
                            key = parts[0].strip()
                            value = parts[1].strip()
                            dynamic_variables[key] = value
            
            logger.info(f"Found dynamic variables for {phone_number}: {dynamic_variables}")
            return dynamic_variables
            
        except Exception as e:
            logger.error(f"Error getting customer data for {phone_number}: {e}")
            return None

# Initialize service
vapi_service = VAPIWebhookService()

@vapi_bp.route('/assistant-selector', methods=['POST'])
def assistant_selector():
    """Handle VAPI AI assistant selector webhook"""
    try:
        # Get the JSON data from the request
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No JSON data received'}), 400
        
        # Log the full webhook payload for debugging
        logger.info(f"VAPI webhook received - Full payload: {data}")
        
        # Validate the webhook structure
        message = data.get('message', {})
        message_type = message.get('type')
        call_data = message.get('call', {})
        
        # Handle different VAPI message types
        if message_type == 'assistant-request':
            # This is the main message we need to handle
            if not call_data:
                logger.error("No call data in webhook")
                return jsonify({'error': 'No call data provided'}), 400
            
            # Extract phone number from VAPI call data
            # VAPI uses call.customer.number instead of call.from.phoneNumber
            customer_data = call_data.get('customer', {})
            from_number = customer_data.get('number')
            
            if not from_number:
                logger.error("No customer phone number in call data")
                return jsonify({'error': 'No customer phone number provided'}), 400
            
            logger.info(f"VAPI assistant request for: {from_number}")
            
            # Get assistant configuration
            assistant_config = vapi_service.get_assistant_configuration(from_number)
            
            if not assistant_config:
                logger.warning(f"No assistant configuration found for: {from_number}")
                return jsonify({'error': 'No assistant configuration found'}), 404
            
            logger.info(f"Returning assistant configuration for {from_number}: {assistant_config}")
            return jsonify(assistant_config), 200
            
        elif message_type in ['status-update', 'speech-update', 'conversation-update', 'end-of-call-report']:
            # These are informational updates - just acknowledge them
            logger.info(f"Received VAPI {message_type} webhook")
            return jsonify({'status': 'acknowledged'}), 200
            
        else:
            logger.warning(f"Unknown message type: {message_type}")
            return jsonify({'error': 'Unknown message type'}), 400
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error processing VAPI webhook: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@vapi_bp.route('/debug', methods=['GET'])
def vapi_debug():
    """Debug endpoint to check VAPI webhook configuration"""
    try:
        # Check if Airtable is configured
        airtable_configured = vapi_service.airtable_service.is_configured()
        
        debug_info = {
            "airtable_configured": airtable_configured,
            "vapi_assistant_table_id": Config.TABLE_ID_VAPI_ASSISTANT,
            "webhook_url": "https://siftly.onrender.com/vapi/assistant-selector"
        }
        
        return debug_info, 200
        
    except Exception as e:
        logger.error(f"Error in VAPI debug endpoint: {e}")
        return {"error": str(e)}, 500 