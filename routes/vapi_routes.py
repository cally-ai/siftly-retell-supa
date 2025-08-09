"""
VAPI AI webhook route handlers
"""
from flask import Blueprint, request, jsonify
from typing import Dict, Any, Optional
from config import Config
from supabase import create_client
from utils.logger import get_logger

import requests

logger = get_logger(__name__)

# Create blueprint
vapi_bp = Blueprint('vapi', __name__, url_prefix='/vapi')

class VAPIWebhookService:
    """Service for handling VAPI AI webhook operations"""
    
    def __init__(self):
        self._supabase = None

    @property
    def supabase(self):
        if self._supabase is None:
            try:
                self._supabase = create_client(
                    Config.SUPABASE_URL,
                    Config.SUPABASE_SERVICE_ROLE_KEY
                )
            except Exception as e:
                logger.error(f"Could not init Supabase client: {e}")
                raise
        return self._supabase
    

    

    

            
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
            
            # Single joined query to get language code directly
            resp = self.supabase\
                .table('twilio_number')\
                .select('language(vapi_language_code)')\
                .eq('vapi_phone_number_id', phone_number_id)\
                .limit(1)\
                .execute()
            
            if not resp.data:
                logger.warning(f"No twilio_number record found for phone_number_id: {phone_number_id}")
                return None
            
            # Validate response structure
            # New client returns data without an error attribute
            
            # Extract vapi_language_code from the joined response
            language_data = resp.data[0].get('language', {})
            vapi_language_code = language_data.get('vapi_language_code')
            
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
            
            response = requests.get(url, headers=headers, timeout=5)
            
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
                'analysis_success_evaluation': call_info.get('analysis', {}).get('successEvaluation', '')
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
            resp = self.supabase\
                .table('caller')\
                .select('*')\
                .eq('phone_number', phone_number)\
                .limit(1)\
                .execute()
            
            if resp.data:
                return resp.data[0]
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
            resp = self.supabase\
                .table('vapi_workflow')\
                .select('*')\
                .eq('workflow_id', workflow_id)\
                .limit(1)\
                .execute()
            
            if resp.data:
                return resp.data[0]
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error finding VAPI workflow by workflow_id: {e}")
            return None
    


# Initialize service
vapi_service = VAPIWebhookService()



@vapi_bp.route('/debug', methods=['GET'])
def vapi_debug():
    """Debug endpoint to check VAPI webhook configuration"""
    try:
        # Check if Supabase is configured
        supabase_configured = bool(Config.SUPABASE_URL and Config.SUPABASE_SERVICE_ROLE_KEY)
        
        debug_info = {
            "supabase_configured": supabase_configured,
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
        
        # Find matching vapi_webhook_event record with time window
        logger.info(f"Searching for vapi_webhook_event with from_number: {caller_number}")
        
        from datetime import timedelta
        
        # Build ISO bounds (two minutes either side of utc_time)
        lower = (utc_time - timedelta(minutes=2)).isoformat()
        upper = (utc_time + timedelta(minutes=2)).isoformat()
        
        resp = vapi_service.supabase\
            .table('vapi_webhook_event')\
            .select('*')\
            .eq('from_number', caller_number)\
            .gte('transferred_time', lower)\
            .lte('transferred_time', upper)\
            .order('transferred_time', desc=True)\
            .limit(1)\
            .execute()
        
        if not resp.data:
            logger.warning(f"No vapi_webhook_event records found for caller: {caller_number}")
            return jsonify({'error': 'No matching vapi_webhook_event found'}), 404
        
        event = resp.data[0]
        logger.info(f"Found matching event with transferred_time: {event.get('transferred_time')}")
        
        # Extract client_id from the matched record
        client_id = event.get('client_id')
        if not client_id:
            logger.error(f"No client_id in vapi_webhook_event record")
            return jsonify({'error': 'No client linked to matched record'}), 500
        
        logger.info(f"Found client_id: {client_id}")
        
        # Get client's twilio_number from twilio_number table
        num_resp = vapi_service.supabase\
            .table('twilio_number')\
            .select('twilio_number')\
            .eq('client_id', client_id)\
            .limit(1)\
            .execute()
        
        if not num_resp.data:
            logger.error(f"No twilio_number found for client_id: {client_id}")
            return jsonify({'error': 'No twilio_number found for client'}), 500
        
        client_twilio_number = num_resp.data[0]['twilio_number']
        logger.info(f"Found client twilio_number: {client_twilio_number}")
        
        # Get dynamic variables from cache using client_twilio_number
        from services.webhook_service import webhook_service
        dynamic_variables = webhook_service._get_customer_data(client_twilio_number)
        
        if not dynamic_variables:
            logger.warning(f"No dynamic variables found for twilio_number: {client_twilio_number}")
            dynamic_variables = {
                "customerName": "Unknown",
                "accountType": "unknown"
            }
        
        # Add caller_language dynamic variable if phone_number_id is provided
        phone_number_id = data.get('phone_number_id')
        if phone_number_id:
            caller_language = vapi_service._get_caller_language_from_phone_id(phone_number_id)
            if caller_language:
                dynamic_variables["caller_language"] = caller_language
                logger.info(f"Added caller_language dynamic variable: {caller_language}")
            else:
                logger.warning(f"Could not determine caller_language for phone_number_id: {phone_number_id}")
        
        # Return call_id and dynamic variables as flat structure
        call_id = event.get('call_id')
        
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
        
        # Save detailed call data to Supabase
        try:
            from datetime import datetime, timedelta
            
            # Prepare payload for Supabase using the extracted call data and webhook payload
            payload = {
                'call_id': call_data.get('id', ''),
                'phoneNumberId': call_data.get('phoneNumberId', ''),
                'type': call_data.get('type', ''),
                'started_at': call_data.get('startedAt', ''),
                'ended_at': call_data.get('endedAt', ''),
                'transcript': call_data.get('transcript', ''),
                'recording_url': call_data.get('recordingUrl', ''),
                'summary': call_data.get('summary', ''),
                'orgId': call_data.get('orgId', ''),
                'status': call_data.get('status', ''),
                'cost': call_data.get('cost', 0),
                'workflowId': call_data.get('workflowId', ''),
                'from_number': from_number,  # From webhook payload
                'vapi_language_workflow_number': vapi_workflow_number,  # From webhook payload
                'analysis_summary': call_data.get('analysis_summary', ''),
                'analysis_success_evaluation': call_data.get('analysis_success_evaluation', '')
            }
            
            # Add caller_id if we can find the caller
            if from_number:
                try:
                    caller_record = vapi_service._find_caller_by_phone_number(from_number)
                    if caller_record:
                        payload['caller_id'] = caller_record['id']
                        logger.info(f"Adding caller_id: {caller_record['id']} for {from_number}")
                except Exception as link_error:
                    logger.error(f"Error finding caller for linking: {link_error}")
            
            # Add vapi_workflow_id if we can find the workflow
            workflow_id = call_data.get('workflowId', '')
            if workflow_id:
                try:
                    workflow_record = vapi_service._find_vapi_workflow_by_workflow_id(workflow_id)
                    if workflow_record:
                        payload['vapi_workflow_id'] = workflow_record['id']
                        logger.info(f"Adding vapi_workflow_id: {workflow_record['id']} for workflow_id: {workflow_id}")
                except Exception as link_error:
                    logger.error(f"Error finding VAPI workflow for linking: {link_error}")
            
            logger.info(f"VAPI preparing payload: {payload}")
            
            # Search for existing records that match our criteria
            started_at = call_data.get('startedAt', '')
            
            if from_number and started_at:
                try:
                    # Convert started_at to datetime for comparison
                    started_at_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                    logger.info(f"VAPI started_at datetime: {started_at_dt}")
                    
                    # Build ISO bounds (two minutes either side of started_at_dt)
                    lower = (started_at_dt - timedelta(minutes=2)).isoformat()
                    upper = (started_at_dt + timedelta(minutes=2)).isoformat()
                    
                    # Search for existing records with empty call_id and matching criteria
                    resp = vapi_service.supabase\
                        .table('vapi_webhook_event')\
                        .select('*')\
                        .eq('from_number', from_number)\
                        .is_('call_id', None)\
                        .gte('transferred_time', lower)\
                        .lte('transferred_time', upper)\
                        .order('transferred_time', desc=True)\
                        .limit(1)\
                        .execute()
                    
                    existing = resp.data[0] if resp.data else None
                    
                    if existing:
                        logger.info(f"VAPI updating existing record: {existing['id']}")
                        # Update the existing record
                        result = vapi_service.supabase\
                            .table('vapi_webhook_event')\
                            .update(payload)\
                            .eq('id', existing['id'])\
                            .execute()
                        logger.info(f"VAPI updated existing record: {existing['id']}")
                    else:
                        logger.info(f"VAPI no matching records found for {from_number}, creating new record")
                        # Create new record
                        result = vapi_service.supabase\
                            .table('vapi_webhook_event')\
                            .insert(payload)\
                            .execute()
                        logger.info(f"VAPI created new record")
                        
                except Exception as e:
                    logger.error(f"VAPI error processing datetime comparison: {e}")
                    # Fallback to creating new record
                    result = vapi_service.supabase\
                        .table('vapi_webhook_event')\
                        .insert(payload)\
                        .execute()
                    logger.info(f"VAPI created new record (fallback)")
            else:
                # Missing required data, create new record
                logger.warning(f"VAPI missing from_number or started_at, creating new record")
                result = vapi_service.supabase\
                    .table('vapi_webhook_event')\
                    .insert(payload)\
                    .execute()
                logger.info(f"VAPI created new record")
            
            if result and result.data:
                logger.info(f"Successfully saved VAPI webhook event record")
            else:
                logger.warning("Failed to save detailed call data to Supabase")
                
        except Exception as e:
            logger.error(f"Error saving detailed call data to Supabase: {e}")
            # Continue processing even if Supabase save fails
        
        # Acknowledge the webhook with a success response
        return jsonify({'status': 'success', 'message': 'New incoming call event received and processed'}), 200
        
    except Exception as e:
        logger.error(f"Error processing VAPI new incoming call event webhook: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500 