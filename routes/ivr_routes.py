"""
IVR Routes for handling Twilio IVR calls with dynamic language options
"""
import logging
from flask import Blueprint, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from services.airtable_service import AirtableService
from config import Config
import json

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
        gather = Gather(num_digits=1, action='/ivr/handle-selection', method='POST')
        
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
        
        logger.info(f"IVR selection received - From: {from_number}, To: {to_number}, Digits: {digits}")
        
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
            call_sid,  # Pass the Twilio Call SID
            request.form.get('StartTime')  # Pass the Twilio Start Time
        )
        
        if not event_created:
            logger.warning(f"Failed to create VAPI webhook event for: {from_number}")
        else:
            logger.info(f"VAPI webhook event created for caller {from_number}")
        
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
        dial = response.dial(caller_id=from_number)
        dial.number(transfer_number)
        
        logger.info(f"Transferring call from {from_number} to {transfer_number} with caller ID preserved")
        return Response(str(response), mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Error in handle selection: {e}")
        response = VoiceResponse()
        response.say("An error occurred. Please try again later.", voice='alice')
        return Response(str(response), mimetype='text/xml')

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