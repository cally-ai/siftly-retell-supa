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

# Conference transfer context tracking
TRANSFER_CTX = {}  # conf_name -> {"caller_call_sid": ..., "agent_call_sid": ...}

def end_vapi_leg_for(orig_call_sid: str):
    """End the VAPI leg for a given caller to save AI minutes"""
    try:
        # Example: if you store the 3 legs with the same vapi_webhook_event_id
        row = vapi_service.supabase.table('twilio_call')\
            .select('call_sid')\
            .eq('related_caller_sid', orig_call_sid)\
            .eq('call_type', 'vapi')\
            .limit(1).execute()
        vapi_sid = (row.data or [{}])[0].get('call_sid')
        if vapi_sid:
            from twilio.rest import Client
            Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)\
                .calls(vapi_sid).update(status='completed')
            logger.info(f"Ended VAPI leg {vapi_sid} for caller {orig_call_sid}")
    except Exception as e:
        logger.error(f"Error ending VAPI leg for {orig_call_sid}: {e}")

def _is_valid_twilio_request(req) -> bool:
    """Validate Twilio signature for security"""
    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(Config.TWILIO_AUTH_TOKEN)
        url = request.url  # must be the full URL Twilio used (https!)
        params = request.form.to_dict()
        signature = request.headers.get('X-Twilio-Signature', '')
        return validator.validate(url, params, signature)
    except Exception:
        return False



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
        # Log the full payload for debugging
        logger.info(f"Get-client-dynamic-variables request received - Full payload: {request.get_json()}")
        
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
        
        # Get call_sid from linked twilio_call record with call_type "ivr"
        call_sid = None
        if event.get('id'):  # Make sure we have a vapi_webhook_event_id
            twilio_call_resp = vapi_service.supabase\
                .table('twilio_call')\
                .select('call_sid')\
                .eq('vapi_webhook_event_id', event.get('id'))\
                .eq('call_type', 'ivr')\
                .limit(1)\
                .execute()
            
            if twilio_call_resp.data:
                call_sid = twilio_call_resp.data[0].get('call_sid')
                logger.info(f"Found call_sid: {call_sid} from twilio_call record")
            else:
                logger.warning(f"No twilio_call record found with call_type 'ivr' for vapi_webhook_event_id: {event.get('id')}")
        
        # Create flat response with call_id, call_sid and all dynamic variables at root level
        response_data = {
            "call_id": call_id,
            "client_id": client_id,  # Add client_id from the matched event
            **dynamic_variables  # Unpack all dynamic variables at root level
        }
        
        # Add call_sid if found
        if call_sid:
            response_data["call_sid"] = call_sid
        
        # Add vapi_webhook_event_id (the ID of the event record itself)
        vapi_webhook_event_id = event.get('id')
        if vapi_webhook_event_id:
            response_data["vapi_webhook_event_id"] = vapi_webhook_event_id
            logger.info(f"Added vapi_webhook_event_id: {vapi_webhook_event_id} to response")
        
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

            # Normalize timestamp fields: use None instead of empty strings
            for ts_key in ('started_at', 'ended_at'):
                if not payload.get(ts_key):
                    payload[ts_key] = None
            
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

# Conference transfer flow routes

@vapi_bp.route('/start-transfer', methods=['POST'])
def start_transfer():
    """Start a conference transfer from VAPI to an agent"""
    try:
        # Log the full payload for debugging
        logger.info(f"Start-transfer request received - Full payload: {request.get_json()}")
        
        data = request.get_json()
        
        if not data:
            logger.error("No JSON data received for start-transfer")
            return jsonify({'error': 'No JSON data received'}), 400
        
        # Extract required fields
        call_sid = data.get('call_sid')
        client_transfer_number = data.get('client_transfer_number')
        client_id = data.get('client_id')
        timeout_secs = data.get('timeout_secs')
        
        if not call_sid:
            logger.error("No call_sid provided in start-transfer request")
            return jsonify({'error': 'call_sid is required'}), 400
        
        if not client_transfer_number:
            logger.error("No client_transfer_number provided in start-transfer request")
            return jsonify({'error': 'client_transfer_number is required'}), 400
        
        if not client_id:
            logger.error("No client_id provided in start-transfer request")
            return jsonify({'error': 'client_id is required'}), 400
        
        # Get client's Twilio number from database
        try:
            twilio_number_response = vapi_service.supabase\
                .table('twilio_number')\
                .select('twilio_number')\
                .eq('client_id', client_id)\
                .limit(1)\
                .execute()
            
            if not twilio_number_response.data:
                logger.error(f"No twilio_number found for client_id: {client_id}")
                return jsonify({'error': 'No Twilio number configured for this client'}), 404
            
            client_twilio_number = twilio_number_response.data[0]['twilio_number']
            logger.info(f"Using client Twilio number: {client_twilio_number} for client_id: {client_id}")
            
        except Exception as e:
            logger.error(f"Error fetching client Twilio number: {e}")
            return jsonify({'error': 'Failed to fetch client Twilio number'}), 500
        
        if timeout_secs is None:
            logger.error("No timeout_secs provided in start-transfer request")
            return jsonify({'error': 'timeout_secs is required'}), 400
        
        timeout_secs = int(timeout_secs)
        if timeout_secs < 3 or timeout_secs > 60:
            logger.error(f"Invalid timeout_secs: {timeout_secs}")
            return jsonify({'error': 'timeout_secs must be between 3 and 60 seconds'}), 400
        
        logger.info(f"Starting transfer for call_sid: {call_sid}, transfer_number: {client_transfer_number}, timeout: {timeout_secs}s")
        
        # Build conference name
        conf_name = f"transfer_{call_sid}"
        
        # Update database: set conference_status="transferring"
        try:
            update_response = vapi_service.supabase\
                .table('twilio_call')\
                .update({
                    'conference_status': 'transferring',
                    'conference_sid': None  # Clear any old conference_sid
                })\
                .eq('call_sid', call_sid)\
                .execute()
            
            if not update_response.data:
                logger.error(f"No twilio_call record found for call_sid: {call_sid}")
                return jsonify({'error': 'Call record not found'}), 404
            
            logger.info(f"Updated twilio_call record for call_sid: {call_sid} with conference_status=transferring")
            
        except Exception as e:
            logger.error(f"Error updating twilio_call record: {e}")
            return jsonify({'error': 'Database update failed'}), 500
        
        # Move the caller into the conference (hold)
        try:
            from twilio.rest import Client
            client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
            
            # Update the caller's call to join the conference
            caller_update = client.calls(call_sid).update(
                url=f"{Config.APP_BASE_URL}/vapi/twiml/conference?name={conf_name}&role=caller",
                method="POST"
            )
            
            logger.info(f"Updated caller call {call_sid} to join conference {conf_name}")
            
        except Exception as e:
            logger.error(f"Error updating caller call: {e}")
            return jsonify({'error': 'Failed to update caller call'}), 500
        
        # Dial the agent with TwiML that joins the same conference
        try:
            from twilio.twiml.voice_response import VoiceResponse, Dial, Conference
            
            # Create TwiML for agent dial
            response = VoiceResponse()
            dial = response.dial(timeout=timeout_secs)
            conference = dial.conference(
                conf_name,
                start_conference_on_enter=True,
                end_conference_on_exit=False,
                beep=False,
                wait_url="http://twimlets.com/holdmusic?Bucket=com.twilio.music.classical",
                status_callback=f"{Config.APP_BASE_URL}/vapi/conference-update",
                status_callback_event="start end join leave mute hold modify speaker"
            )
            
            # Make the call to the agent
            agent_call = client.calls.create(
                to=client_transfer_number,
                from_=client_twilio_number,  # Use client-specific Twilio number
                twiml=str(response)
                # Removed call status callback - relying on conference events only
            )
            
            logger.info(f"Initiated agent call {agent_call.sid} to {client_transfer_number}")
            
            # Store transfer context in database
            from datetime import datetime, timedelta, timezone
            
            deadline = datetime.now(timezone.utc) + timedelta(seconds=timeout_secs)
            
            # Get the original IVR call record to get its Supabase ID and vapi_webhook_event_id
            original_call_response = vapi_service.supabase.table('twilio_call')\
                .select('id, vapi_webhook_event_id')\
                .eq('call_sid', call_sid)\
                .execute()
            
            if not original_call_response.data:
                logger.error(f"No twilio_call record found for call_sid: {call_sid}")
                return jsonify({'error': 'Original call record not found'}), 404
            
            original_call_id = original_call_response.data[0]['id']
            vapi_webhook_event_id = original_call_response.data[0].get('vapi_webhook_event_id')
            
            # Update the original IVR call record with transfer info
            vapi_service.supabase.table('twilio_call').update({
                'conference_name': conf_name,
                'transfer_timeout_at': deadline.isoformat(),
                'transfer_started_at': datetime.now(timezone.utc).isoformat(),
            }).eq('id', original_call_id).execute()
            
            # Create a new twilio_call record for the agent call
            agent_call_data = {
                'call_sid': agent_call.sid,
                'call_type': 'conference',
                'parent_id': original_call_id,  # Use the Supabase ID of the original IVR call
                'conference_name': conf_name,
                'from_number': client_twilio_number,
                'to_number': client_transfer_number,
                'direction': 'outbound-api',
                'start_time': datetime.now(timezone.utc).isoformat(),
                'conference_status': 'transferring'
            }
            
            if vapi_webhook_event_id:
                agent_call_data['vapi_webhook_event_id'] = vapi_webhook_event_id
            
            vapi_service.supabase.table('twilio_call').insert(agent_call_data).execute()
            logger.info(f"Created agent call record: {agent_call.sid} for transfer")
            
            # Keep TRANSFER_CTX for fast lookup (nice to have), but DB is the source of truth
            TRANSFER_CTX[conf_name] = {
                "caller_call_sid": call_sid,
                "agent_call_sid": agent_call.sid,
            }
            
        except Exception as e:
            logger.error(f"Error dialing agent: {e}")
            return jsonify({'error': 'Failed to dial agent'}), 500
        
        # Start watchdog thread for timeout
        def timeout_watchdog():
            import time
            time.sleep(timeout_secs)
            from twilio.rest import Client
            client_th = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)

            try:
                check_response = vapi_service.supabase.table('twilio_call')\
                    .select('conference_status').eq('call_sid', call_sid).execute()
                current_status = (check_response.data or [{}])[0].get('conference_status')

                if current_status == 'transferring':
                    logger.info(f"Transfer timeout for call_sid: {call_sid}")
                    
                    # Update original IVR call record
                    vapi_service.supabase.table('twilio_call')\
                        .update({'conference_status': 'timeout_failed'})\
                        .eq('call_sid', call_sid).execute()
                    
                    # Get the original IVR call record to get its Supabase ID for agent call update
                    original_call_response = vapi_service.supabase.table('twilio_call')\
                        .select('id')\
                        .eq('call_sid', call_sid)\
                        .execute()
                    
                    if original_call_response.data:
                        original_call_id = original_call_response.data[0]['id']
                        
                        # Update agent call record
                        vapi_service.supabase.table('twilio_call')\
                            .update({'conference_status': 'timeout_failed'})\
                            .eq('parent_id', original_call_id)\
                            .eq('call_type', 'conference').execute()

                    # end agent if known (use DB as source of truth)
                    agent_sid = None
                    ctx = TRANSFER_CTX.get(conf_name, {})
                    agent_sid = ctx.get("agent_call_sid")
                    
                    # Fallback to DB if not in memory
                    if not agent_sid:
                        row = vapi_service.supabase.table('twilio_call')\
                            .select('agent_call_sid').eq('call_sid', call_sid).limit(1).execute()
                        agent_sid = (row.data or [{}])[0].get('agent_call_sid')
                    
                    if agent_sid:
                        try:
                            client_th.calls(agent_sid).update(status='completed')
                            logger.info(f"Hung up agent leg {agent_sid} due to timeout")
                        except Exception as e:
                            logger.error(f"Error hanging up agent leg: {e}")
                    # end caller (ends conference)
                    client_th.calls(call_sid).update(status='completed')
                    logger.info(f"Hung up caller leg {call_sid} due to timeout")

                    TRANSFER_CTX.pop(conf_name, None)
                else:
                    logger.info(f"Transfer completed successfully for call_sid: {call_sid}, status: {current_status}")
                    TRANSFER_CTX.pop(conf_name, None)
            except Exception as e:
                logger.error(f"Error in timeout watchdog: {e}")
                TRANSFER_CTX.pop(conf_name, None)
        
        # Start the watchdog thread
        import threading
        watchdog_thread = threading.Thread(target=timeout_watchdog)
        watchdog_thread.daemon = True
        watchdog_thread.start()
        
        logger.info(f"Started timeout watchdog for {timeout_secs} seconds")
        
        return jsonify({
            'status': 'success',
            'message': 'Transfer initiated',
            'conference_name': conf_name,
            'agent_call_sid': agent_call.sid if 'agent_call' in locals() else None
        }), 200
        
    except Exception as e:
        logger.error(f"Error in start-transfer: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@vapi_bp.route('/conference-update', methods=['POST'])
def conference_update():
    """Handle Twilio conference webhooks"""
    try:
        # Validate Twilio signature in production
        if Config.FLASK_ENV == 'production' and not _is_valid_twilio_request(request):
            logger.warning("Invalid Twilio signature")
            return '', 403
        
        # Log the full payload for debugging
        logger.info(f"Conference webhook received - Full payload: {dict(request.form)}")
        
        # Extract webhook data
        status_callback_event = request.form.get('StatusCallbackEvent')
        conference_sid = request.form.get('ConferenceSid')
        friendly_name = request.form.get('FriendlyName')
        call_sid = request.form.get('CallSid')
        
        logger.info(f"Conference event: {status_callback_event}, SID: {conference_sid}, Name: {friendly_name}, CallSid: {call_sid}")
        
        # Map FriendlyName → original caller call_sid
        if not friendly_name or not friendly_name.startswith('transfer_'):
            logger.warning(f"Invalid conference friendly name: {friendly_name}")
            return '', 200
        
        orig_call_sid = friendly_name[len('transfer_'):]
        logger.info(f"Mapped conference {friendly_name} to original call_sid: {orig_call_sid}")
        
        # Get transfer context
        ctx = TRANSFER_CTX.get(friendly_name, {})
        agent_call_sid = ctx.get("agent_call_sid")
        caller_call_sid = ctx.get("caller_call_sid", orig_call_sid)
        
        # Read from DB if memory is empty (cross-instance reliability)
        if not agent_call_sid:
            row = vapi_service.supabase.table('twilio_call')\
                .select('agent_call_sid').eq('call_sid', orig_call_sid).limit(1).execute()
            agent_call_sid = (row.data or [{}])[0].get('agent_call_sid')
            logger.info(f"Retrieved agent_call_sid {agent_call_sid} from DB for call_sid {orig_call_sid}")
        
        # Get the original IVR call record to get its Supabase ID
        original_call_response = vapi_service.supabase.table('twilio_call')\
            .select('id')\
            .eq('call_sid', orig_call_sid)\
            .execute()
        
        if not original_call_response.data:
            logger.error(f"No twilio_call record found for call_sid: {orig_call_sid}")
            return '', 404
        
        original_call_id = original_call_response.data[0]['id']
        
        # Save ConferenceSid whenever present (update both IVR and agent call records)
        if conference_sid:
            try:
                # Update original IVR call record
                vapi_service.supabase.table('twilio_call')\
                    .update({'conference_sid': conference_sid})\
                    .eq('call_sid', orig_call_sid).execute()
                
                # Update agent call record if it exists
                vapi_service.supabase.table('twilio_call')\
                    .update({'conference_sid': conference_sid})\
                    .eq('parent_id', original_call_id)\
                    .eq('call_type', 'conference').execute()
                
                logger.info(f"Saved conference_sid {conference_sid} for call_sid {orig_call_sid} and agent call")
            except Exception as e:
                logger.error(f"Error saving conference_sid: {e}")
        
        # Handle different conference events
        if status_callback_event == 'participant-join':
            if call_sid == caller_call_sid:
                # Customer joined - optional logging
                logger.info(f"Customer joined conference: {call_sid}")
                # Optional: mark caller_joined in DB for cleaner telemetry
                try:
                    vapi_service.supabase.table('twilio_call')\
                        .update({'conference_status': 'caller_joined'})\
                        .eq('call_sid', orig_call_sid).execute()
                except Exception as e:
                    logger.error(f"Error updating conference_status to caller_joined: {e}")
            else:
                is_agent = False
                if agent_call_sid:
                    is_agent = (call_sid == agent_call_sid)
                else:
                    # fallback: treat any non-caller as agent if we didn't store agent sid
                    is_agent = True

                if is_agent:
                    logger.info(f"Agent joined conference: {call_sid}")
                    
                    try:
                        # Update original IVR call record
                        vapi_service.supabase.table('twilio_call')\
                            .update({'conference_status': 'agent_joined'})\
                            .eq('call_sid', orig_call_sid).execute()
                        
                                        # Update agent call record
                vapi_service.supabase.table('twilio_call')\
                    .update({'conference_status': 'agent_joined'})\
                    .eq('parent_id', original_call_id)\
                    .eq('call_type', 'conference').execute()
                        
                        logger.info(f"Updated conference_status to 'agent_joined' for call_sid: {orig_call_sid} and agent call")
                    except Exception as e:
                        logger.error(f"Error updating conference_status: {e}")
                    
                    # Clean up transient map
                    TRANSFER_CTX.pop(friendly_name, None)
                    
                    # OPTIONAL: end VAPI leg here to save AI minutes
                    end_vapi_leg_for(orig_call_sid)
        
        elif status_callback_event == 'conference-end':
            # Conference ended
            logger.info(f"Conference ended: {conference_sid}")
            
            try:
                # Update original IVR call record
                vapi_service.supabase.table('twilio_call')\
                    .update({'conference_status': 'ended'})\
                    .eq('call_sid', orig_call_sid).execute()
                
                # Update agent call record
                vapi_service.supabase.table('twilio_call')\
                    .update({'conference_status': 'ended'})\
                    .eq('parent_id', original_call_id)\
                    .eq('call_type', 'conference').execute()
                
                logger.info(f"Updated conference_status to 'ended' for call_sid: {orig_call_sid} and agent call")
            except Exception as e:
                logger.error(f"Error updating conference_status to ended: {e}")
            
            TRANSFER_CTX.pop(friendly_name, None)
        
        else:
            # Other events (conference-start, mute, hold, modify, speaker) - just log
            logger.info(f"Conference event {status_callback_event} for call_sid: {call_sid}")
        
        return '', 200
        
    except Exception as e:
        logger.error(f"Error in conference-update: {e}")
        return '', 500

@vapi_bp.route('/twiml/conference', methods=['GET', 'POST'])
def twiml_conference():
    """Return TwiML to join a named conference"""
    try:
        # Get query parameters
        name = request.args.get('name')
        role = request.args.get('role', 'caller')  # Default to caller
        
        if not name:
            logger.error("No conference name provided")
            return jsonify({'error': 'Conference name is required'}), 400
        
        logger.info(f"Generating TwiML for conference: {name}, role: {role}")
        
        # Create TwiML response
        from twilio.twiml.voice_response import VoiceResponse, Dial, Conference
        
        response = VoiceResponse()
        dial = response.dial()
        
        # Configure conference based on role
        start_conference_on_enter = role != 'caller'  # False for caller, True for agent
        end_conference_on_exit = role == 'caller'     # True for caller, False for agent
        
        conference = dial.conference(
            name,
            start_conference_on_enter=start_conference_on_enter,
            end_conference_on_exit=end_conference_on_exit,
            beep=False,
            wait_url="http://twimlets.com/holdmusic?Bucket=com.twilio.music.classical",
            status_callback=f"{Config.APP_BASE_URL}/vapi/conference-update",
            status_callback_event="start end join leave mute hold modify speaker"
        )
        
        logger.info(f"Generated TwiML for conference {name} with role {role}")
        
        from flask import Response
        return Response(str(response), mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Error generating conference TwiML: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@vapi_bp.route('/check-business-hours', methods=['POST'])
def check_business_hours():
    """Check if current time is within business hours for a client"""
    try:
        data = request.get_json()
        
        if not data:
            logger.error("No JSON data received for check-business-hours")
            return jsonify({'error': 'No JSON data received'}), 400
        
        # Extract required fields
        client_id = data.get('client_id')
        
        if not client_id:
            logger.error("No client_id provided in check-business-hours request")
            return jsonify({'error': 'client_id is required'}), 400
        
        # Process the business hours check
        from services.webhook_service import webhook_service
        result = webhook_service.process_business_hours_check({
            'name': 'siftly_check_business_hours',
            'args': {'client_id': client_id}
        })
        
        # Get string response directly
        within_hours = result.get('within_business_hours', 'false')
        
        return jsonify({'within_business_hours': within_hours}), 200
        
    except Exception as e:
        logger.error(f"Error in business hours check: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@vapi_bp.route('/save-live-call-transcript', methods=['POST'])
def save_live_call_transcript():
    """Save live call transcript from VAPI payload"""
    try:
        data = request.get_json()
        
        if not data:
            logger.error("No JSON data received for save-live-call-transcript")
            return jsonify({'error': 'No JSON data received'}), 400
        
        # Extract vapi_webhook_event_id from variables
        variables = data.get('variables', {})
        vapi_webhook_event_id = variables.get('vapi_webhook_event_id')
        
        if not vapi_webhook_event_id:
            logger.error("No vapi_webhook_event_id found in variables")
            return jsonify({'error': 'vapi_webhook_event_id is required in variables'}), 400
        
        # Extract messagesOpenAIFormatted from payload
        messages = data.get('message', {}).get('artifact', {}).get('messagesOpenAIFormatted', [])
        
        if not messages:
            logger.error("No messagesOpenAIFormatted found in payload")
            return jsonify({'error': 'No messages found in payload'}), 400
        
        # Build transcript from messages
        def to_plain_text_content(content):
            if isinstance(content, str):
                return content.strip() or None
            if isinstance(content, list):
                texts = []
                for item in content:
                    if isinstance(item, dict) and 'text' in item:
                        text = item.get('text')
                        if text:
                            texts.append(text)
                return ' '.join(texts).strip() or None
            return None
        
        lines = []
        for msg in messages:
            # Skip anything with tool_calls
            if msg.get('tool_calls') and len(msg.get('tool_calls', [])) > 0:
                continue
            
            # Only assistant or user messages
            if msg.get('role') in ['assistant', 'user']:
                text = to_plain_text_content(msg.get('content'))
                if text:
                    lines.append(f"{msg['role']}: {text}")
        
        # Create transcript string
        transcript = '\n'.join(lines)
        
        if not transcript:
            logger.error("No transcript content generated")
            return jsonify({'error': 'No transcript content found'}), 400
        
        # Save transcript to database
        try:
            update_response = vapi_service.supabase\
                .table('vapi_webhook_event')\
                .update({'live_call_transcript': transcript})\
                .eq('id', vapi_webhook_event_id)\
                .execute()
            
            if not update_response.data:
                logger.error(f"No vapi_webhook_event record found for id: {vapi_webhook_event_id}")
                return jsonify({'error': 'vapi_webhook_event record not found'}), 404
            
            return jsonify({
                'status': 'success',
                'message': 'Transcript saved successfully',
                'vapi_webhook_event_id': vapi_webhook_event_id,
                'transcript_lines': len(lines)
            }), 200
            
        except Exception as e:
            logger.error(f"Error saving transcript to database: {e}")
            return jsonify({'error': 'Database update failed'}), 500
        
    except Exception as e:
        logger.error(f"Error in save-live-call-transcript: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@vapi_bp.route('/log-payload', methods=['POST'])
def log_payload():
    """Log the full payload received in the request"""
    try:
        # Log the full payload for debugging
        logger.info(f"Log-payload request received - Full payload: {request.get_json()}")
        
        # Return success response
        return jsonify({'status': 'success', 'message': 'Payload logged successfully'}), 200
        
    except Exception as e:
        logger.error(f"Error in log-payload: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500 