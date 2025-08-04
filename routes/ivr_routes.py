"""
IVR Routes for handling Twilio IVR calls with dynamic language options
"""
import logging
from flask import Blueprint, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from services.airtable_service import AirtableService
from config import Config
import json
import requests
from datetime import datetime

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint
ivr_bp = Blueprint('ivr', __name__, url_prefix='/ivr')

class IVRService:
    """Service class for handling IVR functionality"""
    
    def __init__(self):
        self.airtable_service = AirtableService()
    
    def get_ivr_configuration(self, twilio_number: str) -> dict:
        """
        Get IVR configuration for a specific Twilio number
        
        Args:
            twilio_number: The Twilio number that was called
            
        Returns:
            Dictionary containing IVR configuration
        """
        try:
            logger.info(f"Looking up IVR configuration for Twilio number: {twilio_number}")
            
            # Search for IVR configuration record
            ivr_records = self.airtable_service.search_records_in_table(
                table_name="client_ivr_language_configuration",
                field="client_ivr_twilio_number",
                value=twilio_number
            )
            
            if not ivr_records:
                logger.warning(f"No IVR configuration found for Twilio number: {twilio_number}")
                return None
            
            ivr_record = ivr_records[0]
            fields = ivr_record.get('fields', {})
            
            # Extract basic configuration
            config = {
                'client_number': fields.get('client_ivr_twilio_number'),
                'client_id': fields.get('client', []),
                'twilio_voice': fields.get('twilio_voice'),
                'options': []
            }
            
            # Extract client_id (first linked record)
            if config['client_id']:
                config['client_id'] = config['client_id'][0]
            
            # Count and extract options
            option_count = 0
            for field_name, field_value in fields.items():
                if field_name.startswith('option_') and field_value:
                    option_num = field_name.split('_')[1]
                    option_count += 1
                    
                    # Get corresponding language code and reply
                    language_code_field = f"twilio_language_code_{option_num}"
                    reply_field = f"reply_{option_num}"
                    language_linked_field = f"language_{option_num}"
                    
                    option_config = {
                        'number': option_num,
                        'text': field_value,
                        'language_code': fields.get(language_code_field),
                        'reply': fields.get(reply_field),
                        'language_id': fields.get(language_linked_field, [])
                    }
                    
                    # Extract language_id (first linked record)
                    if option_config['language_id']:
                        option_config['language_id'] = option_config['language_id'][0]
                    
                    config['options'].append(option_config)
            
            logger.info(f"Found IVR configuration with {len(config['options'])} options for number {twilio_number}")
            return config
            
        except Exception as e:
            logger.error(f"Error getting IVR configuration for {twilio_number}: {e}")
            return None
    
    def get_transfer_number(self, language_id: str) -> str:
        """
        Get the transfer number for a specific language
        
        Args:
            language_id: The language record ID from language table
            
        Returns:
            The transfer number or None if not found
        """
        try:
            logger.info(f"Getting transfer number for language_id: {language_id}")
            
            # Step 1: Get the language record from language table
            language_record = self.airtable_service.get_record_from_table(
                table_name="language",
                record_id=language_id
            )
            
            if not language_record:
                logger.warning(f"Language record not found: {language_id}")
                return None
            
            # Step 2: Get linked vapi_workflow record
            vapi_workflow_linked_ids = language_record.get('fields', {}).get('vapi_workflow', [])
            if not vapi_workflow_linked_ids:
                logger.warning(f"No vapi_workflow linked to language: {language_id}")
                return None
            
            vapi_workflow_id = vapi_workflow_linked_ids[0]
            vapi_workflow_record = self.airtable_service.get_record_from_table(
                table_name="vapi_workflow",
                record_id=vapi_workflow_id
            )
            
            if not vapi_workflow_record:
                logger.warning(f"VAPI workflow record not found: {vapi_workflow_id}")
                return None
            
            # Step 3: Get linked twilio_number record
            twilio_number_linked_ids = vapi_workflow_record.get('fields', {}).get('twilio_number', [])
            if not twilio_number_linked_ids:
                logger.warning(f"No twilio_number linked to vapi_workflow: {vapi_workflow_id}")
                return None
            
            twilio_number_id = twilio_number_linked_ids[0]
            twilio_number_record = self.airtable_service.get_record_from_table(
                table_name="twilio_number",
                record_id=twilio_number_id
            )
            
            if not twilio_number_record:
                logger.warning(f"Twilio number record not found: {twilio_number_id}")
                return None
            
            transfer_number = twilio_number_record.get('fields', {}).get('twilio_number')
            logger.info(f"Found transfer number: {transfer_number} for language_id: {language_id} via vapi_workflow: {vapi_workflow_id}")
            return transfer_number
            
        except Exception as e:
            logger.error(f"Error getting transfer number for {language_id}: {e}")
            return None
    
    def find_or_create_caller(self, phone_number: str, client_id: str, language_id: str) -> str:
        """
        Find or create a caller record
        
        Args:
            phone_number: The caller's phone number
            client_id: The client record ID
            language_id: The language record ID
            
        Returns:
            The caller record ID
        """
        try:
            logger.info(f"Looking for caller: {phone_number}")
            
            # Search for existing caller record
            caller_records = self.airtable_service.search_records_in_table(
                table_name="caller",
                field="phone_number",
                value=phone_number
            )
            
            if caller_records:
                # Update existing caller record with new language
                caller_record = caller_records[0]
                caller_id = caller_record['id']
                
                # Update the caller record with new language
                self.airtable_service.update_record_in_table(
                    table_name="caller",
                    record_id=caller_id,
                    data={
                        'language': [language_id]
                    }
                )
                
                logger.info(f"Updated existing caller record: {caller_id} for {phone_number} with new language: {language_id}")
                return caller_id
            else:
                # Create new caller record
                caller_data = {
                    'phone_number': phone_number,
                    'client': [client_id],
                    'language': [language_id]
                }
                
                caller_record = self.airtable_service.create_record_in_table(
                    table_name="caller",
                    data=caller_data
                )
                
                if caller_record:
                    caller_id = caller_record['id']
                    logger.info(f"Created new caller record: {caller_id} for {phone_number} with client: {client_id}, language: {language_id}")
                    return caller_id
                else:
                    logger.error(f"Failed to create caller record for {phone_number}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error finding/creating caller for {phone_number}: {e}")
            return None
    
    def create_vapi_webhook_event(self, from_number: str, caller_id: str, client_id: str, call_sid: str = None) -> bool:
        """
        Create records in both vapi_webhook_event and twilio_call tables
        
        Args:
            from_number: The caller's phone number
            caller_id: The caller record ID
            client_id: The client record ID
            call_sid: The Twilio Call SID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Creating VAPI webhook event and Twilio call records for caller: {from_number}")
            
            # Create VAPI webhook event record with only specified fields
            vapi_event_data = {
                'from_number': from_number,
                'caller': [caller_id],
                'client': [client_id],
                'transferred_time': datetime.utcnow().isoformat() + 'Z'
            }
            
            logger.info(f"Creating VAPI webhook event with data: {vapi_event_data}")
            
            # Create the VAPI webhook event record
            vapi_event_record = self.airtable_service.create_record_in_table(
                table_name="vapi_webhook_event",
                data=vapi_event_data
            )
            
            if not vapi_event_record:
                logger.error(f"Failed to create VAPI webhook event record for {from_number}")
                return False
                
            logger.info(f"Created VAPI webhook event record: {vapi_event_record['id']} for caller {from_number}")
            
            # Create Twilio call record
            twilio_call_data = {
                'CallSid': call_sid,  # Primary field
                'Type': 'ivr',  # Select field
                'vapi_webhook_event': [vapi_event_record['id']]  # Link to VAPI event record
            }
            
            logger.info(f"Creating Twilio call record with data: {twilio_call_data}")
            
            # Create the Twilio call record
            twilio_call_record = self.airtable_service.create_record_in_table(
                table_name="twilio_call",
                data=twilio_call_data
            )
            
            if not twilio_call_record:
                logger.error(f"Failed to create Twilio call record for {from_number}")
                return False
                
            logger.info(f"Created Twilio call record: {twilio_call_record['id']} for caller {from_number}")
            logger.info(f"Successfully linked VAPI event {vapi_event_record['id']} to Twilio call {twilio_call_record['id']}")
            
            return True
                
        except Exception as e:
            logger.error(f"Error creating VAPI webhook event and Twilio call records: {e}")
            return False

# Initialize service
ivr_service = IVRService()

@ivr_bp.route('', methods=['POST'], strict_slashes=False)
@ivr_bp.route('/', methods=['POST'], strict_slashes=False)
def ivr_handler():
    """Handle incoming IVR calls from Twilio"""
    try:
        # Get form data from Twilio
        from_number = request.form.get('From')
        to_number = request.form.get('To')
        call_sid = request.form.get('CallSid')
        
        logger.info(f"IVR call received - From: {from_number}, To: {to_number}, CallSid: {call_sid}")
        
        # Get IVR configuration
        ivr_config = ivr_service.get_ivr_configuration(to_number)
        
        if not ivr_config:
            logger.error(f"No IVR configuration found for number: {to_number}")
            # Return a simple error message
            response = VoiceResponse()
            response.say("Sorry, this number is not configured for IVR.", voice='alice')
            return Response(str(response), mimetype='text/xml')
        
        logger.info(f"IVR configuration found - Client: {ivr_config['client_id']}, Voice: {ivr_config['twilio_voice']}, Options: {len(ivr_config['options'])}")
        
        # Build TwiML response
        response = VoiceResponse()
        gather = Gather(num_digits=1, action='/ivr/handle-selection', method='POST', timeout=10)
        
        # Add options to gather
        for option in ivr_config['options']:
            if option['text'] and option['language_code'] and ivr_config['twilio_voice']:
                logger.info(f"Adding IVR option {option['number']}: '{option['text']}' in {option['language_code']}")
                gather.say(
                    option['text'],
                    voice=ivr_config['twilio_voice'],
                    language=option['language_code']
                )
        
        # Add fallback if no digits pressed
        response.append(gather)
        response.say("No selection made. Goodbye.", voice='alice')
        
        logger.info(f"Generated IVR TwiML with {len(ivr_config['options'])} options for caller {from_number}")
        return Response(str(response), mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Error in IVR handler: {e}")
        response = VoiceResponse()
        response.say("An error occurred. Please try again later.", voice='alice')
        return Response(str(response), mimetype='text/xml')

@ivr_bp.route('/handle-selection', methods=['POST'], strict_slashes=False)
def handle_selection():
    """Handle user selection from IVR"""
    try:
        # Get form data from Twilio
        from_number = request.form.get('From')
        to_number = request.form.get('To')
        digits = request.form.get('Digits')
        call_sid = request.form.get('CallSid')
        
        # Debug: Log all Twilio form data to see available fields
        logger.info(f"IVR selection received - From: {from_number}, To: {to_number}, Digits: {digits}")
        logger.info(f"Full Twilio form data: {dict(request.form)}")
        logger.info(f"StartTime from Twilio: {request.form.get('StartTime')}")
        logger.info(f"CallStartTime from Twilio: {request.form.get('CallStartTime')}")
        logger.info(f"StartTime from Twilio: {request.form.get('start_time')}")
        
        # Get IVR configuration again
        ivr_config = ivr_service.get_ivr_configuration(to_number)
        
        if not ivr_config:
            logger.error(f"No IVR configuration found for number: {to_number}")
            response = VoiceResponse()
            response.say("Sorry, this number is not configured for IVR.", voice='alice')
            return Response(str(response), mimetype='text/xml')
        
        # Find the selected option
        selected_option = None
        for option in ivr_config['options']:
            if option['number'] == digits:
                selected_option = option
                break
        
        if not selected_option:
            logger.warning(f"Invalid selection: {digits} from caller {from_number}")
            response = VoiceResponse()
            response.say("Invalid selection. Please try again.", voice='alice')
            return Response(str(response), mimetype='text/xml')
        
        logger.info(f"Caller {from_number} selected option {digits}: '{selected_option['text']}' in {selected_option['language_code']}")
        
        # Get transfer number
        transfer_number = ivr_service.get_transfer_number(selected_option['language_id'])
        
        if not transfer_number:
            logger.error(f"No transfer number found for language: {selected_option['language_id']}")
            response = VoiceResponse()
            response.say("Sorry, transfer number not configured.", voice='alice')
            return Response(str(response), mimetype='text/xml')
        
        logger.info(f"Transfer number found: {transfer_number} for language {selected_option['language_id']}")
        
        # Find or create caller record
        caller_id = ivr_service.find_or_create_caller(
            from_number,
            ivr_config['client_id'],
            selected_option['language_id']
        )
        
        if not caller_id:
            logger.error(f"Failed to find/create caller record for: {from_number}")
            response = VoiceResponse()
            response.say("Sorry, an error occurred. Please try again.", voice='alice')
            return Response(str(response), mimetype='text/xml')
        
        logger.info(f"Caller record processed - ID: {caller_id}, Client: {ivr_config['client_id']}, Language: {selected_option['language_id']}")
        
        # Create VAPI webhook event record
        event_created = ivr_service.create_vapi_webhook_event(
            from_number,
            caller_id,
            ivr_config['client_id'],
            call_sid  # Pass the Twilio Call SID
        )
        
        if not event_created:
            logger.warning(f"Failed to create VAPI webhook event and Twilio call records for: {from_number}")
        else:
            logger.info(f"VAPI webhook event and Twilio call records created for caller {from_number}")
        
        # Build TwiML response
        response = VoiceResponse()
        
        # Say the reply message if configured
        if selected_option['reply'] and selected_option['language_code'] and ivr_config['twilio_voice']:
            logger.info(f"Playing reply message: '{selected_option['reply']}' in {selected_option['language_code']}")
            response.say(
                selected_option['reply'],
                voice=ivr_config['twilio_voice'],
                language=selected_option['language_code']
            )
        
        # Transfer the call
        dial = response.dial(
            caller_id=from_number,
            status_callback="https://siftly.onrender.com/ivr/status-callback",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST"
        )
        dial.number(transfer_number)
        
        logger.info(f"Transferring call from {from_number} to {transfer_number} with caller ID preserved")
        return Response(str(response), mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Error in handle selection: {e}")
        response = VoiceResponse()
        response.say("An error occurred. Please try again later.", voice='alice')
        return Response(str(response), mimetype='text/xml')

@ivr_bp.route('/status-callback', methods=['POST'], strict_slashes=False)
def status_callback():
    """Handle Twilio status callbacks and update existing twilio_call records"""
    try:
        # Log the full payload that Twilio sends us
        logger.info("Twilio status callback received - Full payload:")
        logger.info(dict(request.form))
        
        # Extract CallSid
        call_sid = request.form.get('CallSid')
        call_status = request.form.get('CallStatus')
        
        logger.info(f"Extracted CallSid: {call_sid}, Status: {call_status}")
        
        if not call_sid:
            logger.warning("No CallSid provided in status callback")
            return '', 200
        
        # Only handle "completed" status
        if call_status != "completed":
            logger.info(f"Received status '{call_status}' - no action needed")
            return '', 200
        
        # Initialize Twilio client and fetch call details
        from twilio.rest import Client
        client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
        
        logger.info(f"Fetching call details from Twilio for CallSid: {call_sid}")
        call_details = client.calls(call_sid).fetch()
        
        # Initialize Airtable service
        airtable_service = AirtableService()
        
        # Look up the CallSid in our twilio_call table
        logger.info(f"Searching for CallSid {call_sid} in twilio_call table")
        twilio_call_match = airtable_service.search_records_in_table(
            table_name=Config.TABLE_ID_TWILIO_CALL,
            field="CallSid",
            value=call_sid
        )
        
        # Prepare update data with the specified fields
        update_data = {}
        
        # Extract the specified fields from Twilio call details
        if call_details.sid:
            update_data['CallSid'] = call_details.sid
        if call_details.account_sid:
            update_data['AccountSid'] = call_details.account_sid
        
        # Try to get From field from call details, with debugging
        from_number = None
        # Get From field from webhook payload (most reliable source)
        from_number = request.form.get('From')
        logger.info(f"Got From from webhook payload: {from_number}")
        
        if from_number:
            update_data['From'] = from_number
        else:
            logger.warning("Could not extract From field from webhook payload")
        
        if call_details.to:
            update_data['To'] = call_details.to
        if call_details.direction:
            update_data['Direction'] = call_details.direction
        if call_details.start_time:
            update_data['StartTime'] = call_details.start_time.isoformat()
        if call_details.end_time:
            update_data['EndTime'] = call_details.end_time.isoformat()
        if call_details.duration:
            update_data['Duration'] = call_details.duration
        if call_details.answered_by:
            update_data['AnsweredBy'] = call_details.answered_by
        if call_details.forwarded_from:
            update_data['ForwardedFrom'] = call_details.forwarded_from
        
        # Branch 1: Found matching record
        if twilio_call_match:
            logger.info(f"Branch 1: Found twilio_call record for CallSid: {call_sid}")
            record = twilio_call_match[0]
            record_id = record['id']
            
            logger.info(f"Updating existing twilio_call record {record_id} with data: {update_data}")
            
            # Update the existing record in Airtable
            if update_data:
                airtable_service.update_record_in_table(
                    table_name=Config.TABLE_ID_TWILIO_CALL,
                    record_id=record_id,
                    data=update_data
                )
                logger.info(f"Successfully updated twilio_call record {record_id} with Twilio call completion data")
            else:
                logger.warning(f"No update data prepared for twilio_call record {record_id}")
            
            # Now find child calls using ParentCallSid
            logger.info(f"Branch 1: Searching for child calls with ParentCallSid: {call_sid}")
            child_calls = client.calls.list(parent_call_sid=call_sid, limit=1)
            
            if child_calls:
                child_call = child_calls[0]
                child_call_sid = child_call.sid
                logger.info(f"Branch 1: Found child call SID: {child_call_sid}")
                
                # Fetch child call details
                child_call_details = client.calls(child_call_sid).fetch()
                
                # Prepare child call data
                child_call_data = {
                    'CallSid': child_call_details.sid,
                    'Type': 'transfer',  # Set type to transfer
                    'Parent': [record_id]  # Link to parent record
                }
                
                # Add the same fields as parent
                if child_call_details.account_sid:
                    child_call_data['AccountSid'] = child_call_details.account_sid
                
                # Try to get From field from child call details, with debugging
                child_from_number = None
                # For child calls (transfers), we typically don't have a From field in the API response
                # as they are outbound calls. We'll skip this for now.
                logger.info("Child call - From field not available for outbound transfer calls")
                
                if child_from_number:
                    child_call_data['From'] = child_from_number
                
                if child_call_details.to:
                    child_call_data['To'] = child_call_details.to
                if child_call_details.direction:
                    child_call_data['Direction'] = child_call_details.direction
                if child_call_details.start_time:
                    child_call_data['StartTime'] = child_call_details.start_time.isoformat()
                if child_call_details.end_time:
                    child_call_data['EndTime'] = child_call_details.end_time.isoformat()
                if child_call_details.duration:
                    child_call_data['Duration'] = child_call_details.duration
                if child_call_details.answered_by:
                    child_call_data['AnsweredBy'] = child_call_details.answered_by
                if child_call_details.forwarded_from:
                    child_call_data['ForwardedFrom'] = child_call_details.forwarded_from
                
                # Get vapi_webhook_event from parent record
                parent_fields = record.get('fields', {})
                vapi_webhook_event = parent_fields.get('vapi_webhook_event', [])
                if vapi_webhook_event:
                    child_call_data['vapi_webhook_event'] = vapi_webhook_event
                    logger.info(f"Branch 1: Linking child call to same vapi_webhook_event: {vapi_webhook_event}")
                
                logger.info(f"Branch 1: Creating child call record with data: {child_call_data}")
                
                # Create child call record
                child_record = airtable_service.create_record_in_table(
                    table_name=Config.TABLE_ID_TWILIO_CALL,
                    data=child_call_data
                )
                
                if child_record:
                    logger.info(f"Branch 1: Successfully created child call record: {child_record['id']}")
                else:
                    logger.error(f"Branch 1: Failed to create child call record")
            else:
                logger.info(f"Branch 1: No child calls found for ParentCallSid: {call_sid}")
        
        # Branch 2: No matching record found
        else:
            logger.info(f"Branch 2: No twilio_call record found for CallSid: {call_sid}, creating new record")
            
            # Create new record with the same fields
            new_call_data = update_data.copy()
            new_call_data['Type'] = 'vapi'  # Set type to vapi for new records
            
            logger.info(f"Branch 2: Creating new twilio_call record with data: {new_call_data}")
            
            # Create the new record in Airtable
            if new_call_data:
                new_record = airtable_service.create_record_in_table(
                    table_name=Config.TABLE_ID_TWILIO_CALL,
                    data=new_call_data
                )
                
                if new_record:
                    logger.info(f"Branch 2: Successfully created new twilio_call record: {new_record['id']}")
                    
                    # Now look for a matching IVR record to link vapi_webhook_event
                    logger.info(f"Branch 2: Looking for matching IVR record with same From field and similar EndTime")
                    
                    # Get the From field and EndTime from our new record
                    from_number = new_call_data.get('From')
                    end_time = new_call_data.get('EndTime')
                    
                    if from_number and end_time:
                        # Search for records with same From field and Type = "ivr"
                        matching_records = airtable_service.search_records_in_table(
                            table_name=Config.TABLE_ID_TWILIO_CALL,
                            field="From",
                            value=from_number
                        )
                        
                        logger.info(f"Branch 2: Found {len(matching_records)} records with same From field: {from_number}")
                        
                        # Filter for records with Type = "ivr" and similar EndTime
                        from datetime import datetime
                        matching_ivr_records = []
                        
                        for record in matching_records:
                            record_fields = record.get('fields', {})
                            record_type = record_fields.get('Type')
                            record_end_time = record_fields.get('EndTime')
                            
                            # Check if it's an IVR record
                            if record_type == 'ivr' and record_end_time:
                                try:
                                    # Parse the end times for comparison
                                    new_end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                                    record_end_dt = datetime.fromisoformat(record_end_time.replace('Z', '+00:00'))
                                    
                                    # Calculate time difference
                                    time_diff = abs((new_end_dt - record_end_dt).total_seconds())
                                    
                                    logger.info(f"Branch 2: Comparing with record {record['id']}: time_diff={time_diff}s")
                                    
                                    # Check if within 5 seconds
                                    if time_diff <= 5:
                                        matching_ivr_records.append(record)
                                        logger.info(f"Branch 2: Found matching IVR record {record['id']} (time_diff={time_diff}s)")
                                    
                                except Exception as e:
                                    logger.warning(f"Branch 2: Error parsing EndTime for record {record['id']}: {e}")
                        
                        # If we found a matching IVR record, link the vapi_webhook_event
                        if matching_ivr_records:
                            # Take the first matching record (closest in time)
                            matching_ivr_record = matching_ivr_records[0]
                            matching_ivr_fields = matching_ivr_record.get('fields', {})
                            vapi_webhook_event = matching_ivr_fields.get('vapi_webhook_event', [])
                            
                            if vapi_webhook_event:
                                logger.info(f"Branch 2: Linking vapi_webhook_event {vapi_webhook_event} from IVR record {matching_ivr_record['id']}")
                                
                                # Update our new record with the vapi_webhook_event link
                                airtable_service.update_record_in_table(
                                    table_name=Config.TABLE_ID_TWILIO_CALL,
                                    record_id=new_record['id'],
                                    data={'vapi_webhook_event': vapi_webhook_event}
                                )
                                
                                logger.info(f"Branch 2: Successfully linked vapi_webhook_event to new record {new_record['id']}")
                                
                                # Now fetch VAPI details using the call_id from the linked vapi_webhook_event record
                                logger.info(f"Branch 2: Fetching VAPI details for linked vapi_webhook_event")
                                
                                # Get the vapi_webhook_event record to extract call_id
                                vapi_event_record = airtable_service.get_record_from_table(
                                    table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                                    record_id=vapi_webhook_event[0]  # Take the first linked record
                                )
                                
                                if vapi_event_record:
                                    vapi_event_fields = vapi_event_record.get('fields', {})
                                    call_id = vapi_event_fields.get('call_id')
                                    
                                    if call_id:
                                        logger.info(f"Branch 2: Found call_id {call_id} in vapi_webhook_event record")
                                        
                                        # Fetch VAPI call data
                                        from routes.vapi_routes import VAPIWebhookService
                                        vapi_service = VAPIWebhookService()
                                        call_data = vapi_service.get_vapi_call_data(call_id)
                                        
                                        if call_data:
                                            logger.info(f"Branch 2: Successfully fetched VAPI call data for call_id: {call_id}")
                                            
                                            # Prepare VAPI update data
                                            vapi_update_data = {
                                                'endedAt': call_data.get('endedAt'),
                                                'transcript': call_data.get('transcript'),
                                                'recordingUrl': call_data.get('recordingUrl'),
                                                'summary': call_data.get('summary'),
                                                'status': call_data.get('status'),
                                                'cost': call_data.get('cost'),
                                                'endedReason': call_data.get('endedReason'),
                                            }
                                            
                                            # Handle nested analysis fields
                                            analysis = call_data.get('analysis', {})
                                            if analysis:
                                                vapi_update_data['analysis_summary'] = analysis.get('summary')
                                                vapi_update_data['analysis_succes_evaluation'] = analysis.get('successEvaluation')
                                            
                                            # Remove None values
                                            vapi_update_data = {k: v for k, v in vapi_update_data.items() if v is not None}
                                            
                                            if vapi_update_data:
                                                # Update the vapi_webhook_event record with VAPI data
                                                airtable_service.update_record_in_table(
                                                    table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                                                    record_id=vapi_webhook_event[0],
                                                    data=vapi_update_data
                                                )
                                                
                                                logger.info(f"Branch 2: Successfully updated vapi_webhook_event record with VAPI data")
                                            else:
                                                logger.warning(f"Branch 2: No VAPI data to update")
                                        else:
                                            logger.warning(f"Branch 2: Failed to fetch VAPI call data for call_id: {call_id}")
                                    else:
                                        logger.warning(f"Branch 2: No call_id found in vapi_webhook_event record")
                                else:
                                    logger.warning(f"Branch 2: Could not retrieve vapi_webhook_event record")
                            else:
                                logger.warning(f"Branch 2: No vapi_webhook_event found in matching IVR record {matching_ivr_record['id']}")
                        else:
                            logger.info(f"Branch 2: No matching IVR record found within 5 seconds")
                    else:
                        logger.warning(f"Branch 2: Missing From field or EndTime for comparison")
                else:
                    logger.error(f"Branch 2: Failed to create new twilio_call record")
            else:
                logger.warning(f"Branch 2: No data prepared for new twilio_call record")
        
        return '', 200
        
    except Exception as e:
        logger.error(f"Error in status callback: {e}")
        return '', 500

@ivr_bp.route('/debug', methods=['GET'], strict_slashes=False)
def ivr_debug():
    """Debug endpoint for IVR configuration"""
    try:
        return {
            'status': 'success',
            'message': 'IVR service is running',
            'service': 'IVRService',
            'airtable_service': 'AirtableService'
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        } 