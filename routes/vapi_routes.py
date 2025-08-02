"""
VAPI AI webhook route handlers
"""
from flask import Blueprint, request, jsonify
from typing import Dict, Any, Optional
from config import Config
from services.airtable_service import AirtableService
from utils.logger import get_logger
import json
import requests

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
            # Step 1: Look up the from_number in the caller table
            caller_records = self.airtable_service.search_records_in_table(
                table_name="tbl3mjOWELyIG2m6o",  # caller table
                field="phone_number", 
                value=from_number
            )
            
            if not caller_records:
                logger.warning(f"No caller record found for: {from_number}")
                return None
            
            caller_record = caller_records[0]
            
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
                table_name=Config.TABLE_ID_VAPI_WORKFLOW,
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
        Get customer data by phone number from Airtable
        
        Args:
            phone_number: The customer's phone number
            
        Returns:
            Customer data dictionary or None if not found
        """
        try:
            # Search in the twilio_number table for the phone number
            twilio_records = self.airtable_service.search_records_in_table(
                table_name="tbl0PeZoX2qgl74ZT",  # twilio_number table
                field="twilio_number", 
                value=phone_number
            )
            
            if not twilio_records:
                logger.warning(f"No twilio_number record found for: {phone_number}")
                return None
            
            twilio_record = twilio_records[0]
            
            # Get the linked client record
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
            
            # Get client dynamic variables
            client_dynamic_variables = {}
            client_dynamic_variables_linked_ids = client_record.get('fields', {}).get('client_dynamic_variables', [])
            
            if client_dynamic_variables_linked_ids:
                for var_id in client_dynamic_variables_linked_ids:
                    var_record = self.airtable_service.get_record_from_table(
                        table_name="client_dynamic_variables",
                        record_id=var_id
                    )
                    if var_record:
                        var_name = var_record.get('fields', {}).get('variable_name')
                        var_value = var_record.get('fields', {}).get('variable_value')
                        if var_name and var_value:
                            client_dynamic_variables[var_name] = var_value
            
            # Get language agent names
            language_agent_names = {}
            language_agent_names_linked_ids = client_record.get('fields', {}).get('language_agent_names', [])
            
            if language_agent_names_linked_ids:
                for lang_id in language_agent_names_linked_ids:
                    lang_record = self.airtable_service.get_record_from_table(
                        table_name="tblT79Xju3vLxNipr",  # language_agent_names table
                        record_id=lang_id
                    )
                    if lang_record:
                        lang_name = lang_record.get('fields', {}).get('language_name')
                        agent_name = lang_record.get('fields', {}).get('agent_name')
                        if lang_name and agent_name:
                            language_agent_names[lang_name] = agent_name
            
            # Combine all dynamic variables
            all_dynamic_variables = {**client_dynamic_variables, **language_agent_names}
            
            logger.info(f"Found {len(all_dynamic_variables)} dynamic variables for {phone_number}")
            return all_dynamic_variables
            
        except Exception as e:
            logger.error(f"Error getting customer data for {phone_number}: {e}")
            return None

    def get_vapi_call_data(self, call_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve call data from VAPI API using the call ID
        
        Args:
            call_id: The VAPI call ID
            
        Returns:
            Extracted call data dictionary or None if failed
        """
        try:
            logger.info(f"Retrieving VAPI call data for call_id: {call_id}")
            
            if not Config.VAPI_API_KEY:
                logger.error("VAPI_API_KEY not configured")
                return None
            
            # Make API call to VAPI
            url = f"https://api.vapi.ai/call?id={call_id}"
            headers = {
                "Authorization": Config.VAPI_API_KEY
            }
            
            response = requests.get(url, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"VAPI API call failed with status {response.status_code}: {response.text}")
                return None
            
            call_data = response.json()
            
            if not call_data or not isinstance(call_data, list) or len(call_data) == 0:
                logger.warning(f"No call data found for call_id: {call_id}")
                return None
            
            call_info = call_data[0]  # Get the first (and should be only) call record
            
            # Extract the required fields
            extracted_data = {
                'id': call_info.get('id', ''),
                'phoneNumberId': call_info.get('phoneNumberId', ''),
                'type': call_info.get('type', ''),
                'startedAt': call_info.get('startedAt', ''),
                'endedAt': call_info.get('endedAt', ''),
                'transcript': call_info.get('transcript', ''),
                'recordingUrl': call_info.get('recordingUrl', ''),
                'summary': call_info.get('summary', ''),
                'orgId': call_info.get('orgId', ''),
                'status': call_info.get('status', ''),
                'cost': call_info.get('cost', 0),
                'workflowId': call_info.get('workflowId', ''),
                'from_number': call_info.get('variableValues', {}).get('customer', {}).get('number', ''),
                'vapi_workflow_number': call_info.get('variableValues', {}).get('phoneNumber', {}).get('number', ''),
                'analysis_summary': call_info.get('analysis', {}).get('summary', ''),
                'analysis_succes_evaluation': call_info.get('analysis', {}).get('successEvaluation', '')
            }
            
            logger.info(f"Successfully extracted VAPI call data for call_id: {call_id}")
            return extracted_data
            
        except Exception as e:
            logger.error(f"Error retrieving VAPI call data for {call_id}: {e}")
            return None
    
    def _find_caller_by_phone_number(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """
        Find a caller record by phone number
        
        Args:
            phone_number: The phone number to search for
            
        Returns:
            Caller record if found, None otherwise
        """
        try:
            caller_records = self.airtable_service.search_records_in_table(
                table_name="tbl3mjOWELyIG2m6o",  # caller table
                field="phone_number", 
                value=phone_number
            )
            
            if caller_records:
                return caller_records[0]
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error finding caller by phone number: {e}")
            return None
    
    def _find_vapi_workflow_by_workflow_id(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Find a VAPI workflow record by workflow_id
        
        Args:
            workflow_id: The workflow ID to search for
            
        Returns:
            VAPI workflow record if found, None otherwise
        """
        try:
            if not Config.TABLE_ID_VAPI_WORKFLOW:
                logger.error("TABLE_ID_VAPI_WORKFLOW is not configured")
                return None
            
            workflow_records = self.airtable_service.search_records_in_table(
                table_name=Config.TABLE_ID_VAPI_WORKFLOW,
                field="workflow_id", 
                value=workflow_id
            )
            
            if workflow_records:
                return workflow_records[0]
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error finding VAPI workflow by workflow_id: {e}")
            return None
    
    def _link_vapi_event_to_caller(self, caller_record_id: str, vapi_event_record_id: str) -> bool:
        """
        Link a VAPI webhook event record to a caller record
        
        Args:
            caller_record_id: The ID of the caller record
            vapi_event_record_id: The ID of the VAPI webhook event record
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Update the caller record to link to the VAPI webhook event
            update_data = {
                'vapi_webhook_event': [vapi_event_record_id]
            }
            
            result = self.airtable_service.update_record_in_table(
                table_name="tbl3mjOWELyIG2m6o",  # caller table
                record_id=caller_record_id,
                data=update_data
            )
            
            if result:
                return True
            else:
                logger.error(f"Failed to link VAPI event {vapi_event_record_id} to caller {caller_record_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error linking VAPI event to caller: {e}")
            return False
    
    def _link_vapi_event_to_workflow(self, workflow_record_id: str, vapi_event_record_id: str) -> bool:
        """
        Link a VAPI webhook event record to a VAPI workflow record
        
        Args:
            workflow_record_id: The ID of the VAPI workflow record
            vapi_event_record_id: The ID of the VAPI webhook event record
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Update the VAPI workflow record to link to the VAPI webhook event
            update_data = {
                'vapi_webhook_event': [vapi_event_record_id]
            }
            
            result = self.airtable_service.update_record_in_table(
                table_name=Config.TABLE_ID_VAPI_WORKFLOW,
                record_id=workflow_record_id,
                data=update_data
            )
            
            if result:
                return True
            else:
                logger.error(f"Failed to link VAPI event {vapi_event_record_id} to workflow {workflow_record_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error linking VAPI event to workflow: {e}")
            return False

# Initialize service
vapi_service = VAPIWebhookService()

def assistant_selector():
    """Handle VAPI AI assistant selector webhook"""
    try:
        # Get the JSON data from the request
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No JSON data received'}), 400
        
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
            
            logger.info(f"Returning assistant configuration for {from_number}")
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

@vapi_bp.route('/assistant-override-variable-values', methods=['POST'])
def assistant_override_variable_values():
    """Handle VAPI AI assistant override variable values webhook"""
    try:
        # Get the JSON data from the request first to check message type
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No JSON data received'}), 400
        
        # Validate the webhook structure
        message = data.get('message', {})
        message_type = message.get('type')
        call_data = message.get('call', {})
        
        # Skip logging for conversation-update messages to reduce log bloat
        if message_type == 'conversation-update':
            return jsonify({'status': 'acknowledged'}), 200
        
        # Handle different VAPI message types
        if message_type == 'status-update':
            # Only process when status is "in-progress"
            status = message.get('status')
            if status != 'in-progress':
                logger.info(f"Status update received but not 'in-progress': {status}")
                return jsonify({'status': 'acknowledged'}), 200
            
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
            
            logger.info(f"VAPI override request for: {from_number} (status: in-progress)")
            
            # Get dynamic variables only (no assistant lookup needed)
            dynamic_variables = vapi_service._get_dynamic_variables_for_caller(from_number)
            
            if not dynamic_variables:
                logger.warning(f"No dynamic variables found for: {from_number}")
                return jsonify({'error': 'No dynamic variables found'}), 404
            
            # Return only the workflowOverrides (no assistantId)
            response = {
                "workflowOverrides": {
                    "variableValues": dynamic_variables
                }
            }
            
            logger.info(f"Returning override variables for {from_number}")
            return jsonify(response), 200
            
        elif message_type in ['status-update', 'speech-update', 'end-of-call-report']:
            # Acknowledge other message types
            logger.info(f"Received VAPI {message_type} webhook")
            return jsonify({'status': 'acknowledged'}), 200
        else:
            logger.warning(f"Invalid message type: {message_type}")
            return jsonify({'error': 'Invalid message type'}), 400
            
    except Exception as e:
        logger.error(f"Error processing VAPI override webhook: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@vapi_bp.route('/debug', methods=['GET'])
def vapi_debug():
    """Debug endpoint to check VAPI webhook configuration"""
    try:
        # Check if Airtable is configured
        airtable_configured = vapi_service.airtable_service.is_configured()
        
        debug_info = {
            "airtable_configured": airtable_configured,
            "vapi_workflow_table_id": Config.TABLE_ID_VAPI_WORKFLOW,
            "webhook_url": "https://siftly.onrender.com/vapi/assistant-selector"
        }
        
        return debug_info, 200
        
    except Exception as e:
        logger.error(f"Error in VAPI debug endpoint: {e}")
        return {"error": str(e)}, 500 

@vapi_bp.route('/get-client-dynamic-variables', methods=['POST'])
def get_client_dynamic_variables():
    """Get dynamic variables for a client based on phone number"""
    try:
        data = request.get_json()
        
        # Log the full payload for debugging
        logger.info(f"VAPI get-client-dynamic-variables - Full payload: {data}")
        
        if not data:
            logger.warning("No JSON data received - checking if it's a form request")
            # Check if data is in form format instead
            form_data = dict(request.form)
            if form_data:
                logger.info(f"Found form data: {form_data}")
                data = form_data
            else:
                logger.error("No JSON data or form data received")
                return jsonify({'error': 'No data received'}), 400
        
        # Extract toolCallId from the VAPI tool call format
        tool_call_id = None
        
        # Check for function tool format (has message.toolCallList)
        if 'message' in data:
            if 'toolCallList' in data['message']:
                tool_call_list = data['message']['toolCallList']
                if tool_call_list and len(tool_call_list) > 0:
                    tool_call_id = tool_call_list[0].get('id')
        
        # Check for API Request format (no toolCallId, just direct data)
        if not tool_call_id:
            tool_call_id = "api_request_tool_call_id"
        
        # Extract phone number from the request
        # VAPI AI might send it in different formats, so we'll check multiple possible locations
        from_number = None
        
        # Check if it's in the message data
        if 'message' in data and 'call' in data['message']:
            call_data = data['message']['call']
            if 'customer' in call_data and 'number' in call_data['customer']:
                from_number = call_data['customer']['number']
        
        # Check if it's in the variables
        if not from_number and 'message' in data and 'variables' in data['message']:
            variables = data['message']['variables']
            if 'customer' in variables and 'number' in variables['customer']:
                from_number = variables['customer']['number']
        
        # Check if it's directly in the payload
        if not from_number and 'from_number' in data:
            from_number = data['from_number']
        
        if not from_number:
            logger.error("No from phone number found in request data")
            return jsonify({
                "results": [{
                    "toolCallId": tool_call_id,
                    "result": "Error: No from_number provided"
                }]
            }), 400
        
        logger.info(f"Looking up dynamic variables for: {from_number}")
        
        # Get dynamic variables using the same logic as the override endpoint
        vapi_service = VAPIWebhookService()
        dynamic_variables = vapi_service._get_dynamic_variables_for_caller(from_number)
        
        if dynamic_variables:
            logger.info(f"Dynamic variables found for {from_number}")
            return jsonify({
                "results": [{
                    "toolCallId": tool_call_id,
                    "result": json.dumps(dynamic_variables)
                }]
            }), 200
        else:
            logger.warning(f"No dynamic variables found for {from_number}")
            return jsonify({
                "results": [{
                    "toolCallId": tool_call_id,
                    "result": "Error: No dynamic variables found"
                }]
            }), 404
            
    except Exception as e:
        logger.error(f"Error in get-client-dynamic-variables: {e}")
        return jsonify({
            "results": [{
                "toolCallId": tool_call_id if 'tool_call_id' in locals() else "unknown",
                "result": f"Error: {str(e)}"
            }]
        }), 500 

@vapi_bp.route('/vapi-new-incoming-call-event', methods=['POST'])
def vapi_new_incoming_call_event():
    """Handle VAPI AI new incoming call event webhook"""
    try:
        # Get the JSON data from the request
        data = request.get_json()
        
        if not data:
            logger.warning("No JSON data received for new incoming call event")
            return jsonify({'error': 'No JSON data received'}), 400
        
        # Extract call_id and other data from the webhook payload
        message = data.get('message', {})
        call_id = message.get('call', {}).get('id')
        
        if not call_id:
            logger.warning("No call_id found in webhook payload")
            return jsonify({'error': 'No call_id found in payload'}), 400
        
        # Extract from_number and vapi_workflow_number from webhook payload
        from_number = message.get('customer', {}).get('number', '')
        vapi_workflow_number = message.get('phoneNumber', {}).get('number', '')
        
        # Retrieve detailed call data from VAPI API
        vapi_service = VAPIWebhookService()
        call_data = vapi_service.get_vapi_call_data(call_id)
        
        if not call_data:
            logger.warning(f"Failed to retrieve call data for call_id: {call_id}")
            return jsonify({'error': 'Failed to retrieve call data'}), 500
        
        # Save detailed call data to Airtable
        try:
            # Prepare fields for Airtable using the extracted call data and webhook payload
            airtable_fields = {
                'call_id': call_data.get('id', ''),
                'phoneNumberId': call_data.get('phoneNumberId', ''),
                'type': call_data.get('type', ''),
                'startedAt': call_data.get('startedAt', ''),
                'endedAt': call_data.get('endedAt', ''),
                'transcript': call_data.get('transcript', ''),
                'recordingUrl': call_data.get('recordingUrl', ''),
                'summary': call_data.get('summary', ''),
                'orgId': call_data.get('orgId', ''),
                'status': call_data.get('status', ''),
                'cost': call_data.get('cost', 0),
                'workflowId': call_data.get('workflowId', ''),
                'from_number': from_number,  # From webhook payload
                'vapi_language_workflow_number': vapi_workflow_number,  # From webhook payload
                'analysis_summary': call_data.get('analysis_summary', ''),
                'analysis_succes_evaluation': call_data.get('analysis_succes_evaluation', '')
            }
            
            # Add caller and client linked fields if we can find them
            if from_number:
                try:
                    # Look for existing caller record with matching phone number
                    caller_record = vapi_service._find_caller_by_phone_number(from_number)
                    
                    if caller_record:
                        caller_record_id = caller_record.get('id')
                        airtable_fields['caller'] = [caller_record_id]
                        logger.info(f"Adding caller link: {caller_record_id} for {from_number}")
                        
                        # Also try to get the client from the caller record
                        caller_fields = caller_record.get('fields', {})
                        client_link = caller_fields.get('client', [])
                        if client_link:
                            airtable_fields['client'] = client_link
                            logger.info(f"Adding client link: {client_link} from caller record")
                        
                except Exception as link_error:
                    logger.error(f"Error finding caller for linking: {link_error}")
                    # Continue without caller/client links if lookup fails
            
            # Add VAPI workflow linked field if we can find it
            workflow_id = call_data.get('workflowId', '')
            if workflow_id:
                try:
                    # Look for existing VAPI workflow record with matching workflow_id
                    workflow_record = vapi_service._find_vapi_workflow_by_workflow_id(workflow_id)
                    
                    if workflow_record:
                        workflow_record_id = workflow_record.get('id')
                        airtable_fields['vapi_workflow'] = [workflow_record_id]
                        logger.info(f"Adding VAPI workflow link: {workflow_record_id} for workflow_id: {workflow_id}")
                        
                except Exception as link_error:
                    logger.error(f"Error finding VAPI workflow for linking: {link_error}")
                    # Continue without workflow link if lookup fails
            
            # Add created_time with current datetime in ISO format
            from datetime import datetime
            created_time = datetime.utcnow().isoformat() + 'Z'
            airtable_fields['created_time'] = created_time
            logger.info(f"Adding created_time: {created_time}")
            
            logger.info(f"VAPI creating record with fields: {airtable_fields}")
            
            # Check for existing records that match our criteria
            from_number = call_data.get('customer', {}).get('number', '')
            started_at = call_data.get('startedAt', '')
            
            if from_number and started_at:
                # Convert started_at to datetime for comparison
                from datetime import datetime
                try:
                    started_at_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                    
                    # Search for records with empty call_id and matching from_number
                    existing_records = vapi_service.airtable_service.search_records_in_table(
                        table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                        field="from_number",
                        value=from_number
                    )
                    
                    # Filter records that have empty call_id and are within 2 minutes
                    matching_records = []
                    for record in existing_records:
                        record_fields = record.get('fields', {})
                        call_id = record_fields.get('call_id', '')
                        created_time = record_fields.get('created_time', '')
                        
                        # Check if call_id is empty
                        if not call_id or call_id == '':
                            # Check if created_time is within 2 minutes of started_at
                            if created_time:
                                try:
                                    created_dt = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
                                    time_diff = abs((started_at_dt - created_dt).total_seconds())
                                    
                                    if time_diff <= 120:  # 2 minutes = 120 seconds
                                        matching_records.append(record)
                                except Exception as e:
                                    logger.warning(f"Error parsing created_time {created_time}: {e}")
                    
                    # If we have matching records, update the newest one
                    if matching_records:
                        # Sort by created_time (newest first) and take the first one
                        matching_records.sort(key=lambda x: x.get('fields', {}).get('created_time', ''), reverse=True)
                        newest_record = matching_records[0]
                        
                        logger.info(f"Found {len(matching_records)} matching records, updating newest: {newest_record['id']}")
                        
                        # Update the existing record
                        record = vapi_service.airtable_service.update_record_in_table(
                            table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                            record_id=newest_record['id'],
                            data=airtable_fields
                        )
                        logger.info(f"Updated existing VAPI webhook event record: {newest_record['id']}")
                    else:
                        # No matching records found, create new one
                        logger.info(f"No matching records found for {from_number}, creating new record")
                        record = vapi_service.airtable_service.create_record_in_table(
                            Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                            airtable_fields
                        )
                        logger.info(f"Created new VAPI webhook event record: {record['id'] if record else 'failed'}")
                        
                except Exception as e:
                    logger.error(f"Error processing datetime comparison: {e}")
                    # Fallback to creating new record
                    record = vapi_service.airtable_service.create_record_in_table(
                        Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                        airtable_fields
                    )
                    logger.info(f"Created new VAPI webhook event record (fallback): {record['id'] if record else 'failed'}")
            else:
                # Missing required data, create new record
                logger.warning(f"Missing from_number or started_at, creating new record")
                record = vapi_service.airtable_service.create_record_in_table(
                    Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                    airtable_fields
                )
                logger.info(f"Created new VAPI webhook event record: {record['id'] if record else 'failed'}")
            
            if record:
                logger.info(f"Successfully created VAPI webhook event record: {record.get('id')}")
            else:
                logger.warning("Failed to save detailed call data to Airtable")
                
        except Exception as e:
            logger.error(f"Error saving detailed call data to Airtable: {e}")
            # Continue processing even if Airtable save fails
        
        # Acknowledge the webhook with a success response
        return jsonify({'status': 'success', 'message': 'New incoming call event received and processed'}), 200
        
    except Exception as e:
        logger.error(f"Error processing VAPI new incoming call event webhook: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500 