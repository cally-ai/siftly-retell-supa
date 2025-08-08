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
    

    
    def _get_dynamic_variables_for_caller(self, from_number: str, phone_number_id: str = None) -> Dict[str, Any]:
        """
        Get dynamic variables for the caller (similar to Retell inbound logic)
        
        Args:
            from_number: The caller's phone number
            phone_number_id: The phone_number_id from the incoming payload (optional)
            
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
            
            # Add caller_language dynamic variable if phone_number_id is provided
            if phone_number_id:
                caller_language = self._get_caller_language_from_phone_id(phone_number_id)
                if caller_language:
                    all_dynamic_variables["caller_language"] = caller_language
                    logger.info(f"Added caller_language dynamic variable: {caller_language}")
                else:
                    logger.warning(f"Could not determine caller_language for phone_number_id: {phone_number_id}")
            
            logger.info(f"Found {len(all_dynamic_variables)} dynamic variables for {phone_number}")
            return all_dynamic_variables
            
        except Exception as e:
            logger.error(f"Error getting customer data for {phone_number}: {e}")
            return None
            
    def _get_caller_language_from_phone_id(self, phone_number_id: str) -> Optional[str]:
        """
        Get caller language based on phone_number_id from twilio_number table
        
        Args:
            phone_number_id: The phone_number_id from the incoming payload
            
        Returns:
            The vapi_language_code value or None if not found
        """
        try:
            logger.info(f"Looking up caller language for phone_number_id: {phone_number_id}")
            
            # Search in twilio_number table for matching vapi_phone_number_id
            twilio_records = self.airtable_service.search_records_in_table(
                table_name="tbl0PeZoX2qgl74ZT",  # twilio_number table
                field="vapi_phone_number_id",
                value=phone_number_id
            )
            
            if not twilio_records:
                logger.warning(f"No twilio_number record found for phone_number_id: {phone_number_id}")
                return None
            
            twilio_record = twilio_records[0]
            language_linked_ids = twilio_record.get('fields', {}).get('language', [])
            
            if not language_linked_ids:
                logger.warning(f"No language linked to twilio_number record for phone_number_id: {phone_number_id}")
                return None
            
            # Get the language record to extract vapi_language_code
            language_record = self.airtable_service.get_record_from_table(
                table_name="tblT79Xju3vLxNipr",  # language table
                record_id=language_linked_ids[0]
            )
            
            if not language_record:
                logger.warning(f"Language record not found for ID: {language_linked_ids[0]}")
                return None
            
            vapi_language_code = language_record.get('fields', {}).get('vapi_language_code')
            
            if vapi_language_code:
                logger.info(f"Found caller language: {vapi_language_code} for phone_number_id: {phone_number_id}")
                return vapi_language_code
            else:
                logger.warning(f"No vapi_language_code found in language record for phone_number_id: {phone_number_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting caller language for phone_number_id {phone_number_id}: {e}")
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



@vapi_bp.route('/debug', methods=['GET'])
def vapi_debug():
    """Debug endpoint to check VAPI webhook configuration"""
    try:
        # Check if Airtable is configured
        airtable_configured = vapi_service.airtable_service.is_configured()
        
        debug_info = {
            "airtable_configured": airtable_configured,
            "vapi_workflow_table_id": Config.TABLE_ID_VAPI_WORKFLOW,
            "webhook_url": "https://siftly.onrender.com/vapi/get-client-dynamic-variables"
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
        
        # Extract required fields from the new payload format
        caller_number = data.get('caller_number')
        time_api_request = data.get('time_api_request')
        
        if not caller_number:
            logger.error("No caller_number found in request data")
            return jsonify({'error': 'No caller_number provided'}), 400
        
        if not time_api_request:
            logger.error("No time_api_request found in request data")
            return jsonify({'error': 'No time_api_request provided'}), 400
        
        logger.info(f"Processing request for caller: {caller_number}, time: {time_api_request}")
        
        # Transform time format from "Aug 5, 2025, 8:12 AM UTC" to ISO format
        try:
            from datetime import datetime
            import pytz
            
            # Parse the time string
            parsed_time = datetime.strptime(time_api_request, "%b %d, %Y, %I:%M %p UTC")
            # Convert to UTC timezone
            utc_time = pytz.UTC.localize(parsed_time)
            # Format as ISO string
            iso_time = utc_time.isoformat()
            
            logger.info(f"Transformed time: {time_api_request} -> {iso_time}")
            
        except Exception as e:
            logger.error(f"Error parsing time format: {e}")
            return jsonify({'error': f'Invalid time format: {time_api_request}'}), 400
        
        # Step 1: Find matching vapi_webhook_event record
        logger.info(f"Searching for vapi_webhook_event with from_number: {caller_number}")
        
        vapi_service = VAPIWebhookService()
        vapi_records = vapi_service.airtable_service.search_records_in_table(
            table_name="vapi_webhook_event",
            field="from_number",
            value=caller_number
        )
        
        if not vapi_records:
            logger.warning(f"No vapi_webhook_event records found for caller: {caller_number}")
            return jsonify({'error': 'No matching vapi_webhook_event found'}), 404
        
        # Step 2: Filter by transferred_time within 2 minutes of the API request time
        matching_records = []
        for record in vapi_records:
            transferred_time = record.get('fields', {}).get('transferred_time')
            if transferred_time:
                try:
                    # Parse the transferred_time (should be in ISO format)
                    transferred_dt = datetime.fromisoformat(transferred_time.replace('Z', '+00:00'))
                    # Calculate time difference
                    time_diff = abs((utc_time - transferred_dt).total_seconds())
                    
                    # Check if within 2 minutes (120 seconds)
                    if time_diff <= 120:
                        matching_records.append({
                            'record': record,
                            'transferred_time': transferred_time,
                            'time_diff': time_diff
                        })
                        logger.info(f"Found matching record with transferred_time: {transferred_time}, time_diff: {time_diff}s")
                        
                except Exception as e:
                    logger.warning(f"Error parsing transferred_time {transferred_time}: {e}")
                    continue
        
        if not matching_records:
            logger.warning(f"No vapi_webhook_event records within 2 minutes for caller: {caller_number}")
            return jsonify({'error': 'No matching vapi_webhook_event within time window'}), 404
        
        # Step 3: Get the record with newest transferred_time
        matching_records.sort(key=lambda x: x['transferred_time'], reverse=True)
        call_id_match = matching_records[0]['record']
        
        logger.info(f"Selected record with newest transferred_time: {matching_records[0]['transferred_time']}")
        
        # Step 4: Extract client from the matched record
        client_linked_ids = call_id_match.get('fields', {}).get('client', [])
        if not client_linked_ids:
            logger.error(f"No client linked to vapi_webhook_event record")
            return jsonify({'error': 'No client linked to matched record'}), 500
        
        client_record_id = client_linked_ids[0]
        logger.info(f"Found client record ID: {client_record_id}")
        
        # Step 5: Get client's twilio_number
        client_record = vapi_service.airtable_service.get_record_from_table(
            table_name="client",
            record_id=client_record_id
        )
        
        if not client_record:
            logger.error(f"Client record not found: {client_record_id}")
            return jsonify({'error': 'Client record not found'}), 500
        
        client_twilio_number = client_record.get('fields', {}).get('twilio_number')
        if not client_twilio_number:
            logger.error(f"No twilio_number found in client record: {client_record_id}")
            return jsonify({'error': 'No twilio_number in client record'}), 500
        
        # Handle case where twilio_number is a list (linked record)
        if isinstance(client_twilio_number, list):
            if len(client_twilio_number) > 0:
                client_twilio_number = client_twilio_number[0]  # Take first element
                logger.info(f"Extracted twilio_number from list: {client_twilio_number}")
            else:
                logger.error(f"Empty twilio_number list in client record: {client_record_id}")
                return jsonify({'error': 'Empty twilio_number list in client record'}), 500
        
        logger.info(f"Found client twilio_number: {client_twilio_number}")
        
        # Step 6: Get dynamic variables from cache using client_twilio_number
        from services.webhook_service import webhook_service
        dynamic_variables = webhook_service._get_customer_data(client_twilio_number)
        
        if not dynamic_variables:
            logger.warning(f"No dynamic variables found for twilio_number: {client_twilio_number}")
            dynamic_variables = {
                "customerName": "Unknown",
                "accountType": "unknown"
            }
        
        # Step 6.5: Add caller_language dynamic variable if phone_number_id is provided
        phone_number_id = data.get('phone_number_id')
        if phone_number_id:
            caller_language = vapi_service._get_caller_language_from_phone_id(phone_number_id)
            if caller_language:
                dynamic_variables["caller_language"] = caller_language
                logger.info(f"Added caller_language dynamic variable: {caller_language}")
            else:
                logger.warning(f"Could not determine caller_language for phone_number_id: {phone_number_id}")
        
        # Step 7: Return call_id and dynamic variables as flat structure
        call_id = call_id_match.get('fields', {}).get('call_id')
        
        # Create flat response with call_id and all dynamic variables at root level
        response_data = {
            "call_id": call_id,
            **dynamic_variables  # Unpack all dynamic variables at root level
        }
        
        logger.info(f"Returning call_id: {call_id} and {len(dynamic_variables)} dynamic variables")
        logger.info(f"Response payload: {response_data}")
        
        return jsonify(response_data), 200
            
    except Exception as e:
        logger.error(f"Error in get-client-dynamic-variables: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500 

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
            
            logger.info(f"VAPI creating record with fields: {airtable_fields}")
            
            # Check for existing records that match our criteria
            # Use the from_number that was already extracted from the webhook payload
            # (don't re-extract from call_data as it might not have the customer info)
            started_at = call_data.get('startedAt', '')
            
            logger.info(f"VAPI matching search - from_number: {from_number}, started_at: {started_at}")
            logger.info(f"VAPI call_data customer: {call_data.get('customer', {})}")
            logger.info(f"VAPI call_data keys: {list(call_data.keys())}")
            
            if from_number and started_at:
                # Convert started_at to datetime for comparison
                from datetime import datetime
                try:
                    started_at_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                    logger.info(f"VAPI started_at datetime: {started_at_dt}")
                    
                    # Search for records with empty call_id and matching from_number
                    existing_records = vapi_service.airtable_service.search_records_in_table(
                        table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                        field="from_number",
                        value=from_number
                    )
                    
                    logger.info(f"VAPI found {len(existing_records)} existing records with from_number: {from_number}")
                    
                    # Filter records that have empty call_id and are within 2 minutes
                    matching_records = []
                    for i, record in enumerate(existing_records):
                        record_fields = record.get('fields', {})
                        call_id = record_fields.get('call_id', '')
                        created_time = record_fields.get('created_time', '')
                        
                        logger.info(f"VAPI checking record {i+1}: id={record['id']}, call_id='{call_id}', created_time='{created_time}'")
                        
                        # Check if call_id is empty
                        if not call_id or call_id == '':
                            logger.info(f"VAPI record {record['id']} has empty call_id, checking time")
                            # Check if transferred_time is within 2 minutes of started_at
                            transferred_time = record_fields.get('transferred_time', '')
                            if transferred_time:
                                try:
                                    transferred_dt = datetime.fromisoformat(transferred_time.replace('Z', '+00:00'))
                                    time_diff = abs((started_at_dt - transferred_dt).total_seconds())
                                    
                                    logger.info(f"VAPI time comparison: transferred_dt={transferred_dt}, time_diff={time_diff}s")
                                    
                                    if time_diff <= 120:  # 2 minutes = 120 seconds
                                        matching_records.append(record)
                                        logger.info(f"VAPI record {record['id']} MATCHES criteria (time_diff={time_diff}s)")
                                    else:
                                        logger.info(f"VAPI record {record['id']} REJECTED (time_diff={time_diff}s > 120s)")
                                except Exception as e:
                                    logger.warning(f"Error parsing transferred_time {transferred_time}: {e}")
                            else:
                                logger.info(f"VAPI record {record['id']} has no transferred_time")
                        else:
                            logger.info(f"VAPI record {record['id']} REJECTED (has call_id: '{call_id}')")
                    
                    logger.info(f"VAPI found {len(matching_records)} matching records")
                    
                    # If we have matching records, update the newest one
                    if matching_records:
                        # Sort by transferred_time (newest first) and take the first one
                        matching_records.sort(key=lambda x: x.get('fields', {}).get('transferred_time', ''), reverse=True)
                        newest_record = matching_records[0]
                        
                        logger.info(f"VAPI updating newest matching record: {newest_record['id']}")
                        
                        # Update the existing record
                        record = vapi_service.airtable_service.update_record_in_table(
                            table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                            record_id=newest_record['id'],
                            data=airtable_fields
                        )
                        logger.info(f"VAPI updated existing record: {newest_record['id']}")
                    else:
                        # No matching records found, create new one
                        logger.info(f"VAPI no matching records found for {from_number}, creating new record")
                        record = vapi_service.airtable_service.create_record_in_table(
                            Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                            airtable_fields
                        )
                        logger.info(f"VAPI created new record: {record['id'] if record else 'failed'}")
                        
                except Exception as e:
                    logger.error(f"VAPI error processing datetime comparison: {e}")
                    # Fallback to creating new record
                    record = vapi_service.airtable_service.create_record_in_table(
                        Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                        airtable_fields
                    )
                    logger.info(f"VAPI created new record (fallback): {record['id'] if record else 'failed'}")
            else:
                # Missing required data, create new record
                logger.warning(f"VAPI missing from_number or started_at, creating new record")
                record = vapi_service.airtable_service.create_record_in_table(
                    Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                    airtable_fields
                )
                logger.info(f"VAPI created new record: {record['id'] if record else 'failed'}")
            
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