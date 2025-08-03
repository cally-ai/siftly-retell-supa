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
    
    def create_vapi_webhook_event(self, from_number: str, caller_id: str, client_id: str, call_sid: str = None, start_time: str = None) -> bool:
        """
        Create a record in the vapi_webhook_event table
        
        Args:
            from_number: The caller's phone number
            caller_id: The caller record ID
            client_id: The client record ID
            call_sid: The Twilio Call SID
            start_time: The Twilio call start time
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Creating VAPI webhook event for caller: {from_number}")
            
            # Try different field name variations
            event_data = {
                'from_number': from_number,
                'caller': [caller_id],
                'client': [client_id]
            }
            
            # Add Twilio Call SID if provided
            if call_sid:
                event_data['twilio_CallSid'] = call_sid
                logger.info(f"Adding Twilio Call SID: {call_sid}")
            
            # Add Twilio Start Time if provided
            if start_time:
                event_data['twilio_StartTime'] = start_time
                logger.info(f"Adding Twilio Start Time: {start_time}")
            
            # Add created_time with current datetime in ISO format
            from datetime import datetime
            created_time = datetime.utcnow().isoformat() + 'Z'
            event_data['created_time'] = created_time
            logger.info(f"Adding created_time: {created_time}")
            
            # Also try with different field names in case Airtable uses different naming
            # event_data = {
            #     'from_number': from_number,
            #     'Caller': [caller_id],  # Capitalized
            #     'Client': [client_id]   # Capitalized
            # }
            
            logger.info(f"Creating VAPI webhook event with data: {event_data}")
            logger.info(f"Caller ID being linked: {caller_id}")
            logger.info(f"Client ID being linked: {client_id}")
            
            # Verify the caller record exists
            caller_record = self.airtable_service.get_record_from_table("caller", caller_id)
            if caller_record:
                logger.info(f"Caller record exists: {caller_record.get('fields', {}).get('phone_number', 'unknown')}")
            else:
                logger.error(f"Caller record {caller_id} does not exist!")
            
            event_record = self.airtable_service.create_record_in_table(
                table_name="vapi_webhook_event",
                data=event_data
            )
            
            logger.info(f"Airtable create_record response: {event_record}")
            
            if event_record:
                logger.info(f"Created VAPI webhook event record: {event_record['id']} for caller {from_number}")
                return True
            else:
                logger.error(f"Failed to create VAPI webhook event record for {from_number}")
                return False
                
        except Exception as e:
            logger.error(f"Error creating VAPI webhook event: {e}")
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
        
        # Log IVR start time
        from datetime import datetime
        ivr_start_time = datetime.utcnow().isoformat() + 'Z'
        logger.info(f"[IVR START] Call from {from_number} to {to_number} at {ivr_start_time}")
        
        # Save IVR start record in Airtable
        ivr_service.airtable_service.create_record_in_table(
            table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
            data={
                'twilio_CallSid_ivr': call_sid,
                'twilio_From_ivr': from_number,
                'twilio_To_ivr': to_number,
                'twilio_StartTime_ivr': ivr_start_time,
                'Direction_ivr': request.form.get('Direction')
            }
        )
        
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
        
        # Update existing VAPI webhook event record
        # Try different possible field names for start time
        start_time = request.form.get('StartTime') or request.form.get('CallStartTime') or request.form.get('start_time')
        
        # Get call_sid for lookup
        call_sid = request.form.get('CallSid')
        
        if not call_sid:
            logger.warning(f"No CallSid provided for IVR transfer")
        else:
            logger.info(f"Looking up existing record with twilio_CallSid_ivr: {call_sid}")
            
            # Look up existing record by twilio_CallSid_ivr field
            records = ivr_service.airtable_service.search_records_in_table(
                table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                field="twilio_CallSid_ivr",
                value=call_sid
            )
            
            if not records:
                logger.warning(f"No vapi_webhook_event record found with twilio_CallSid_ivr: {call_sid}")
            else:
                # Update the first matching record
                record = records[0]
                record_id = record['id']
                
                logger.info(f"Found matching vapi_webhook_event record for IVR transfer: {record_id}")
                
                # Prepare update data
                update_data = {}
                
                # Add transferred_time
                from datetime import datetime
                transferred_time = datetime.utcnow().isoformat() + 'Z'
                update_data['transferred_time'] = transferred_time
                logger.info(f"Adding transferred_time: {transferred_time}")
                
                # Update the record in Airtable
                ivr_service.airtable_service.update_record_in_table(
                    table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                    record_id=record_id,
                    data=update_data
                )
                
                logger.info(f"Successfully updated vapi_webhook_event record {record_id} with transferred_time")
        
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
    """Handle Twilio status callbacks and update existing vapi_webhook_event records"""
    try:
        # Log all webhook data for debugging
        logger.info("Webhook received:")
        logger.info(dict(request.form))
        
        # Log and parse values from request.form
        call_sid = request.form.get('CallSid')
        call_status = request.form.get('CallStatus')
        from_number = request.form.get('From')
        to_number = request.form.get('To')
        start_time = request.form.get('StartTime')
        end_time = request.form.get('EndTime')
        call_duration = request.form.get('CallDuration')
        
        logger.info(f"Twilio status callback received - CallSid: {call_sid}, Status: {call_status}")
        logger.info(f"Status callback data - From: {from_number}, To: {to_number}, StartTime: {start_time}, EndTime: {end_time}, Duration: {call_duration}")
        
        # Check for ParentCallSid field
        parent_call_sid = request.form.get('ParentCallSid')
        logger.info(f"ParentCallSid: {parent_call_sid}")
        
        if not call_sid:
            logger.warning("No CallSid provided in status callback")
            return '', 200
        
        # Initialize Airtable service
        airtable_service = AirtableService()
        
        # Handle different logic based on ParentCallSid presence and call status
        if parent_call_sid and parent_call_sid.strip() != '':
            # ParentCallSid has a value - handle VAPI call
            if call_status == "answered":
                logger.info(f"ParentCallSid has value and call status is 'answered' - Processing VAPI call start")
                
                # Get VAPI call start data
                call_sid = request.form.get('CallSid')
                call_status = request.form.get('CallStatus')
                from_number = request.form.get('From')
                to_number = request.form.get('To')
                start_time = request.form.get('StartTime')
                parent_call_sid = request.form.get('ParentCallSid')
                direction = request.form.get('Direction')
                
                logger.info(f"VAPI call start data - CallSid: {call_sid}, Status: {call_status}, From: {from_number}, To: {to_number}, StartTime: {start_time}, ParentCallSid: {parent_call_sid}, Direction: {direction}")
                
                if not call_sid:
                    logger.warning("No CallSid provided in VAPI call start")
                    return '', 200
                
                # Look up records in vapi_webhook_event table by twilio_ParentCallSid field
                records = airtable_service.search_records_in_table(
                    table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                    field="twilio_ParentCallSid",
                    value=parent_call_sid
                )
                
                if not records:
                    logger.warning(f"No vapi_webhook_event record found with twilio_ParentCallSid: {parent_call_sid}")
                    return '', 200
                
                # Update the first matching record
                record = records[0]
                record_id = record['id']
                
                logger.info(f"Found matching vapi_webhook_event record for VAPI call: {record_id}")
                
                # Prepare VAPI update data
                update_data = {}
                
                if call_sid:
                    update_data['twilio_CallSid'] = call_sid
                if from_number:
                    update_data['twilio_From'] = from_number
                if to_number:
                    update_data['twilio_To'] = to_number
                if start_time:
                    update_data['twilio_StartTime'] = start_time
                if parent_call_sid:
                    update_data['twilio_ParentCallSid'] = parent_call_sid
                if direction:
                    update_data['Direction'] = direction
                
                if update_data:
                    # Update the record in Airtable
                    airtable_service.update_record_in_table(
                        table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                        record_id=record_id,
                        data=update_data
                    )
                    
                    logger.info(f"Successfully updated vapi_webhook_event record {record_id} with VAPI call start data")
                else:
                    logger.info(f"No new VAPI data to update for record {record_id}")
                
                return '', 200
        
        elif not parent_call_sid or parent_call_sid.strip() == '':
            # Check if this is an "answered" call (IVR call start)
            if call_status == "answered":
                logger.info(f"ParentCallSid is empty and call status is 'answered' - Processing IVR call start")
                
                # Get IVR call start data
                call_sid = request.form.get('CallSid')
                call_status = request.form.get('CallStatus')
                from_number = request.form.get('From')
                to_number = request.form.get('To')
                start_time = request.form.get('StartTime')
                parent_call_sid = request.form.get('ParentCallSid')
                direction = request.form.get('Direction')
                
                logger.info(f"IVR call start data - CallSid: {call_sid}, Status: {call_status}, From: {from_number}, To: {to_number}, StartTime: {start_time}, ParentCallSid: {parent_call_sid}, Direction: {direction}")
                
                if not call_sid:
                    logger.warning("No CallSid provided in IVR call start")
                    return '', 200
                
                # Create a new record in vapi_webhook_event table
                ivr_call_data = {
                    'twilio_CallSid_ivr': call_sid,
                    'twilio_From_ivr': from_number,
                    'twilio_To_ivr': to_number,
                    'twilio_StartTime_ivr': start_time,
                    'twilio_ParentCallSid_ivr': parent_call_sid,
                    'Direction_ivr': direction
                }
                
                # Remove None values to avoid issues
                ivr_call_data = {k: v for k, v in ivr_call_data.items() if v is not None}
                
                logger.info(f"Creating IVR call start record with data: {ivr_call_data}")
                
                # Create the record in Airtable
                new_record = airtable_service.create_record_in_table(
                    table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                    data=ivr_call_data
                )
                
                if new_record:
                    logger.info(f"Successfully created IVR call start record: {new_record['id']}")
                else:
                    logger.error(f"Failed to create IVR call start record")
                
                return '', 200
            
            # Handle IVR call completion (existing logic)
            logger.info(f"ParentCallSid is empty or not present - Processing IVR call completion")
            
            # Get IVR-specific data
            call_sid = request.form.get('CallSid')
            end_time = request.form.get('EndTime')
            call_duration = request.form.get('CallDuration')
            
            logger.info(f"IVR call completion data - CallSid: {call_sid}, EndTime: {end_time}, Duration: {call_duration}")
            
            if not call_sid:
                logger.warning("No CallSid provided in IVR status callback")
                return '', 200
            
            # Look up records in vapi_webhook_event table by twilio_CallSid_ivr field
            records = airtable_service.search_records_in_table(
                table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                field="twilio_CallSid_ivr",
                value=call_sid
            )
            
            if not records:
                logger.warning(f"No vapi_webhook_event record found with twilio_CallSid_ivr: {call_sid}")
                return '', 200
            
            # Update the first matching record
            record = records[0]
            record_id = record['id']
            
            logger.info(f"Found matching vapi_webhook_event record for IVR call: {record_id}")
            
            # Prepare IVR update data
            update_data = {}
            
            if end_time:
                update_data['twilio_EndTime_ivr'] = end_time
            if call_duration:
                update_data['twilio_Duration_ivr'] = call_duration
            
            if update_data:
                # Update the record in Airtable
                airtable_service.update_record_in_table(
                    table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                    record_id=record_id,
                    data=update_data
                )
                
                logger.info(f"Successfully updated vapi_webhook_event record {record_id} with IVR call completion data")
            else:
                logger.info(f"No new IVR data to update for record {record_id}")
            
            return '', 200
        
        # Look up the corresponding Airtable record in vapi_webhook_event table
        # where twilio_CallSid matches the incoming CallSid
        
        # Search for existing record with matching twilio_CallSid
        records = airtable_service.search_records_in_table(
            table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
            field="twilio_CallSid",
            value=call_sid
        )
        
        if not records:
            logger.warning(f"No vapi_webhook_event record found with twilio_CallSid: {call_sid}")
            return '', 200
        
        # Update the first matching record (should be only one)
        record = records[0]
        record_id = record['id']
        
        logger.info(f"Found matching vapi_webhook_event record: {record_id}")
        
        # Prepare update data
        update_data = {}
        
        if call_sid:
            update_data['twilio_CallSid'] = call_sid
        if from_number:
            update_data['from_number'] = from_number
        if to_number:
            update_data['to_number'] = to_number
        if start_time:
            update_data['twilio_StartTime'] = start_time
        if end_time:
            update_data['twilio_EndTime'] = end_time
        if call_duration:
            update_data['twilio_Duration'] = call_duration
        
        if update_data:
            # Update the record in Airtable
            airtable_service.update_record_in_table(
                table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                record_id=record_id,
                data=update_data
            )
            
            logger.info(f"Successfully updated vapi_webhook_event record {record_id} with status callback data")
            
            # Step 2: Extract call_id from the updated record
            updated_record = airtable_service.get_record_from_table(
                table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                record_id=record_id
            )
            
            if updated_record and updated_record.get('fields', {}).get('call_id'):
                call_id = updated_record['fields']['call_id']
                logger.info(f"Extracted call_id: {call_id} from updated record")
                
                # Step 3: Fetch and update VAPI call data
                if call_id and call_id.strip():
                    logger.info(f"Triggering VAPI call data fetch for call_id: {call_id}")
                    fetch_and_update_vapi_call_data(call_id)
                else:
                    logger.warning(f"Empty or invalid call_id: '{call_id}'")
            else:
                logger.warning(f"No call_id found in updated record {record_id}")
        else:
            logger.info(f"No new data to update for record {record_id}")
        
        return '', 200
        
    except Exception as e:
        logger.error(f"Error processing Twilio status callback: {str(e)}")
        return '', 200  # Always return 200 to Twilio even on error

def fetch_and_update_vapi_call_data(call_id: str) -> bool:
    """
    Fetch call details from VAPI and update the Airtable record
    
    Args:
        call_id: The VAPI call ID to fetch details for
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info(f"Fetching VAPI call details for call_id: {call_id}")
        
        # Fetch call details from VAPI
        response = requests.get(
            f"https://api.vapi.ai/call?id={call_id}",
            headers={"Authorization": f"Bearer {Config.VAPI_API_KEY}"},
        )
        
        if response.status_code != 200:
            logger.error(f"VAPI API error: {response.status_code} - {response.text}")
            return False
        
        call_data_list = response.json()
        if not call_data_list:
            logger.warning(f"No call data found for call_id: {call_id}")
            return False
        
        call_data = call_data_list[0]  # Expecting a list with one object
        logger.info(f"Successfully fetched VAPI call data for call_id: {call_id}")
        
        # Find the Airtable record by call_id
        airtable_service = AirtableService()
        records = airtable_service.search_records_in_table(
            table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
            field="call_id",
            value=call_id
        )
        
        if not records:
            logger.warning(f"No vapi_webhook_event record found with call_id: {call_id}")
            return False
        
        # Update the first matching record
        record = records[0]
        record_id = record['id']
        
        logger.info(f"Found matching vapi_webhook_event record: {record_id}")
        
        # Prepare update data with exact values from VAPI response
        update_data = {
            "endedAt": call_data.get("endedAt"),
            "transcript": call_data.get("transcript"),
            "recordingUrl": call_data.get("recordingUrl"),
            "summary": call_data.get("summary"),
            "status": call_data.get("status"),
            "cost": call_data.get("cost"),
            "endedReason": call_data.get("endedReason"),
        }
        
        # Handle nested analysis fields
        analysis = call_data.get("analysis", {})
        if analysis:
            update_data["analysis_summary"] = analysis.get("summary")
            update_data["analysis_succes_evaluation"] = analysis.get("successEvaluation")
        
        # Handle JSON serialization for complex objects
        if call_data.get("costBreakdown"):
            update_data["costBreakdown"] = json.dumps(call_data["costBreakdown"])
        
        if call_data.get("variableValues"):
            update_data["variableValues"] = json.dumps(call_data["variableValues"])
        
        # Remove None values to avoid overwriting with empty data
        update_data = {k: v for k, v in update_data.items() if v is not None}
        
        if update_data:
            # Update the record in Airtable
            airtable_service.update_record_in_table(
                table_name=Config.TABLE_ID_VAPI_WEBHOOK_EVENT,
                record_id=record_id,
                data=update_data
            )
            
            logger.info(f"Successfully updated vapi_webhook_event record {record_id} with VAPI call data")
            return True
        else:
            logger.info(f"No new VAPI data to update for record {record_id}")
            return True
            
    except Exception as e:
        logger.error(f"Error fetching and updating VAPI call data for call_id {call_id}: {str(e)}")
        return False

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