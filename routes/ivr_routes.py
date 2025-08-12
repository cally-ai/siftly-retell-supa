"""
IVR Routes for handling Twilio IVR calls with dynamic language options
"""
import logging
import time
import threading
from flask import Blueprint, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather, Number

from config import Config
from supabase import create_client
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
        # Don't create the client yet - lazy initialization
        self._supabase_client = None
    
    @property
    def supabase(self):
        """
        Lazy-init Supabase client on first access.
        Any errors creating the client will now happen at use-time,
        not import-time.
        """
        if self._supabase_client is None:
            try:
                self._supabase_client = create_client(
                    Config.SUPABASE_URL,
                    Config.SUPABASE_SERVICE_ROLE_KEY
                )
            except Exception as e:
                logger.error(f"Could not initialize Supabase client: {e}")
                raise
        return self._supabase_client
    
    def get_ivr_configuration(self, twilio_number: str) -> dict:
        """
        Get IVR configuration for a specific Twilio number
        
        Args:
            twilio_number: The Twilio number that was called
            
        Returns:
            Dictionary containing IVR configuration
        """
        try:
            # Supabase lookup
            
            # Step 1: Query twilio_number table to get client_ivr_language_id
            twilio_number_response = self.supabase.table('twilio_number').select('*').eq('twilio_number', twilio_number).execute()
            
            if not twilio_number_response.data:
                logger.warning(f"No twilio_number record found for: {twilio_number}")
                return None
            
            twilio_number_record = twilio_number_response.data[0]
            client_ivr_language_id = twilio_number_record.get('client_ivr_language_id')
            
            if not client_ivr_language_id:
                logger.warning(f"No client_ivr_language_id found for twilio_number: {twilio_number}")
                return None
            
            # Step 2: Query client_ivr_language_configuration table
            ivr_config_response = self.supabase.table('client_ivr_language_configuration').select('*').eq('id', client_ivr_language_id).execute()
            
            if not ivr_config_response.data:
                logger.warning(f"No IVR configuration found for client_ivr_language_id: {client_ivr_language_id}")
                return None
            
            ivr_record = ivr_config_response.data[0]
            
            # Step 2.5: Get client_id from client table using client_ivr_language_configuration_id
            client_response = self.supabase.table('client').select('id').eq('client_ivr_language_configuration_id', client_ivr_language_id).execute()
            
            if not client_response.data:
                logger.warning(f"No client found for client_ivr_language_configuration_id: {client_ivr_language_id}")
                return None
            
            client_id = client_response.data[0].get('id')
            
            # Extract basic configuration
            config = {
                'client_number': twilio_number,  # Use the input twilio_number
                'client_id': client_id,
                'ivr_setup': ivr_record.get('ivr_setup', True),  # Default to True for backward compatibility
                'audio_url_ivr': ivr_record.get('audio_url_ivr'),  # Main IVR audio URL
                'options': []
            }
            
            # Check if IVR setup is enabled
            if config['ivr_setup']:
                # Step 3: Query client_ivr_language_configuration_language join table
                language_options_response = self.supabase.table('client_ivr_language_configuration_language').select('*, language(*)').eq('client_ivr_language_configuration_id', client_ivr_language_id).order('order', desc=False).execute()
                
                if language_options_response.data:
                    for language_option in language_options_response.data:
                        language_data = language_option.get('language', {})
                        order_number = language_option.get('order', 1)
                        
                        option_config = {
                            'number': str(order_number),
                            'audio_reply': language_option.get('audio_url_reply'),
                            'language_id': language_data.get('id')
                        }
                        
                        config['options'].append(option_config)
            else:
                # For single language setup, get the first language from the join table
                language_options_response = self.supabase.table('client_ivr_language_configuration_language').select('*, language(*)').eq('client_ivr_language_configuration_id', client_ivr_language_id).limit(1).execute()
                
                if language_options_response.data:
                    language_data = language_options_response.data[0].get('language', {})
                    config['language_1_id'] = language_data.get('id')
                else:
                    logger.error(f"No language configured for single language setup: {twilio_number}")
                    return None
            
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
            # Supabase lookup
            
            # Step 1: Query vapi_workflow table to get the workflow for this language
            vapi_workflow_response = self.supabase.table('vapi_workflow').select('*').eq('language_id', language_id).execute()
            
            if not vapi_workflow_response.data:
                logger.warning(f"No vapi_workflow found for language_id: {language_id}")
                return None
            
            vapi_workflow_record = vapi_workflow_response.data[0]
            vapi_workflow_id = vapi_workflow_record.get('id')
            
            # Step 2: Query twilio_number table to get the transfer number for this workflow
            twilio_number_response = self.supabase.table('twilio_number').select('*').eq('vapi_workflow_id', vapi_workflow_id).execute()
            
            if not twilio_number_response.data:
                logger.warning(f"No twilio_number found for vapi_workflow_id: {vapi_workflow_id}")
                return None
            
            # Use the first twilio_number record (assuming one per workflow)
            twilio_number_record = twilio_number_response.data[0]
            transfer_number = twilio_number_record.get('twilio_number')
            

            
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
            
            # Step 1: Check if a caller exists with the same phone number
            caller_response = self.supabase.table('caller').select('*').eq('phone_number', phone_number).limit(1).execute()
            
            if caller_response.data:
                # Step 2: Caller exists - update their language
                caller_record = caller_response.data[0]
                caller_id = caller_record['id']
                
                # Update the caller record with new language
                update_response = self.supabase.table('caller').update({
                    'caller_language_id': language_id
                }).eq('id', caller_id).execute()
                
                if not update_response.data:
                    logger.error(f"Failed to update caller record: {caller_id}")
                    return None
                
                # Step 3: Check if client_caller relationship exists
                client_caller_response = self.supabase.table('client_caller').select('*').eq('client_id', client_id).eq('caller_id', caller_id).execute()
                
                if not client_caller_response.data:
                    # Create client_caller relationship
                    self.supabase.table('client_caller').insert({
                        'client_id': client_id,
                        'caller_id': caller_id
                    }).execute()
                    logger.info(f"Created client_caller relationship for caller: {caller_id}, client: {client_id}")
                
                logger.info(f"Updated existing caller record: {caller_id} for {phone_number} with new language: {language_id}")
                return caller_id
            else:
                # Step 4: Caller does not exist - create new caller
                caller_insert_response = self.supabase.table('caller').insert({
                    'phone_number': phone_number,
                    'caller_language_id': language_id
                }).execute()
                
                if not caller_insert_response.data:
                    logger.error(f"Failed to create caller record for {phone_number}")
                    return None
                
                new_caller_id = caller_insert_response.data[0]['id']
                
                # Step 5: Create client_caller relationship
                self.supabase.table('client_caller').insert({
                    'client_id': client_id,
                    'caller_id': new_caller_id
                }).execute()
                
                logger.info(f"Created new caller record: {new_caller_id} for {phone_number} with client: {client_id}, language: {language_id}")
                return new_caller_id
                    
        except Exception as e:
            logger.error(f"Error finding/creating caller for {phone_number}: {e}")
            return None
    
    def create_vapi_webhook_event(self, from_number: str, caller_id: str, client_id: str) -> str:
        """
        Create VAPI webhook event record (synchronous part)
        
        Args:
            from_number: The caller's phone number
            caller_id: The caller record ID (can be None for initial creation)
            client_id: The client record ID
            
        Returns:
            VAPI webhook event record ID or None if failed
        """
        try:
            logger.info(f"Creating VAPI webhook event record for caller: {from_number}")
            
            # Create VAPI webhook event record with only specified fields
            vapi_event_data = {
                'from_number': from_number,
                'client_id': client_id,
                'transferred_time': datetime.utcnow().isoformat() + 'Z'
            }
            
            # Only add caller field if caller_id is provided
            if caller_id:
                vapi_event_data['caller_id'] = caller_id
            
            logger.info(f"Creating VAPI webhook event with data: {vapi_event_data}")
            
            # Create the VAPI webhook event record
            vapi_event_response = self.supabase.table('vapi_webhook_event').insert(vapi_event_data).execute()

            if not getattr(vapi_event_response, 'data', None):
                logger.error(f"Failed to create VAPI webhook event record for {from_number}: No data returned")
                return None
                
            vapi_event_id = vapi_event_response.data[0]['id']
            logger.info(f"Created VAPI webhook event record: {vapi_event_id} for caller {from_number}")
            return vapi_event_id
                
        except Exception as e:
            logger.error(f"Error creating VAPI webhook event record: {e}")
            return None

    def create_twilio_call_record(self, call_sid: str, vapi_event_id: str) -> bool:
        """
        Create Twilio call record (asynchronous part)
        
        Args:
            call_sid: The Twilio Call SID
            vapi_event_id: The VAPI webhook event record ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Creating Twilio call record for CallSid: {call_sid}")
            
            # Create Twilio call record
            twilio_call_data = {
                'call_sid': call_sid,  # Primary field
                'call_type': 'ivr',  # Enum field
                'vapi_webhook_event_id': vapi_event_id  # Foreign key to VAPI event record
            }
            
            logger.info(f"Creating Twilio call record with data: {twilio_call_data}")
            
            # Create the Twilio call record
            twilio_call_response = self.supabase.table('twilio_call').insert(twilio_call_data).execute()
            
            if not getattr(twilio_call_response, 'data', None):
                logger.error(f"Failed to create Twilio call record for CallSid: {call_sid}: No data returned")
                return False
                
            twilio_call_id = twilio_call_response.data[0]['id']
            logger.info(f"Created Twilio call record: {twilio_call_id} for CallSid: {call_sid}")
            logger.info(f"Successfully linked VAPI event {vapi_event_id} to Twilio call {twilio_call_id}")
            
            return True
                
        except Exception as e:
            logger.error(f"Error creating Twilio call record: {e}")
            return False

    def update_vapi_webhook_event_caller(self, vapi_event_id: str, caller_id: str) -> bool:
        """
        Update VAPI webhook event record with real caller_id
        
        Args:
            vapi_event_id: The VAPI webhook event record ID
            caller_id: The real caller record ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Updating VAPI webhook event {vapi_event_id} with caller_id {caller_id}")
            
            # Update the VAPI webhook event record
            update_data = {
                'caller_id': caller_id
            }
            
            update_response = self.supabase.table('vapi_webhook_event').update(update_data).eq('id', vapi_event_id).execute()

            if not getattr(update_response, 'data', None):
                logger.error(f"Failed to update VAPI webhook event {vapi_event_id} with caller_id {caller_id}: No data returned")
                return False
                
            logger.info(f"Successfully updated VAPI webhook event {vapi_event_id} with caller_id {caller_id}")
            return True
                
        except Exception as e:
            logger.error(f"Error updating VAPI webhook event caller: {e}")
            return False

# Initialize service lazily
ivr_service = None

def get_ivr_service():
    """Get the IVR service instance, creating it if needed."""
    global ivr_service
    if ivr_service is None:
        ivr_service = IVRService()
    return ivr_service

def run_post_transfer_updates(from_number: str, vapi_event_id: str, call_sid: str, client_id: str, language_id: str):
    """
    Background function to create Twilio call record and update caller after transfer
    
    Args:
        from_number: The caller's phone number
        vapi_event_id: The VAPI webhook event record ID
        call_sid: The Twilio Call SID
        client_id: The client record ID
        language_id: The language record ID
    """
    try:
        logger.info(f"Background: Processing caller lookup and Twilio call record for CallSid: {call_sid}")
        
        # Find or create caller record (this was blocking the TwiML response)
        service = get_ivr_service()
        caller_id = service.find_or_create_caller(
            from_number,
            client_id,
            language_id
        )
        
        if caller_id:
            logger.info(f"Background: Found/created caller record: {caller_id}")
            
            # Update VAPI webhook event with real caller_id
            try:
                update_success = service.update_vapi_webhook_event_caller(vapi_event_id, caller_id)
                if update_success:
                    logger.info(f"Background: Successfully updated VAPI webhook event {vapi_event_id} with caller_id {caller_id}")
                else:
                    logger.error(f"Background: Failed to update VAPI webhook event {vapi_event_id} with caller_id {caller_id}")
            except Exception as e:
                logger.error(f"Background: Error updating VAPI webhook event caller: {e}")
        else:
            logger.error(f"Background: Failed to find/create caller record for: {from_number}")
        
        # Create Twilio call record in background
        success = service.create_twilio_call_record(call_sid, vapi_event_id)
        
        if success:
            logger.info(f"Background: Successfully created Twilio call record for CallSid: {call_sid}")
        else:
            logger.error(f"Background: Failed to create Twilio call record for CallSid: {call_sid}")
            
    except Exception as e:
        logger.error(f"Background: Error in post-transfer updates for CallSid {call_sid}: {e}")

@ivr_bp.route('', methods=['POST'], strict_slashes=False)
@ivr_bp.route('/', methods=['POST'], strict_slashes=False)
def ivr_handler():
    """Handle incoming IVR calls from Twilio"""
    try:
        # Get form data from Twilio
        from_number = request.form.get('From')
        to_number = request.form.get('To')
        call_sid = request.form.get('CallSid')
        

        
        # Get IVR configuration
        service = get_ivr_service()
        ivr_config = service.get_ivr_configuration(to_number)
        
        if not ivr_config:
            logger.error(f"No IVR configuration found for number: {to_number}")
            # Return a simple error message
            response = VoiceResponse()
            response.say("Sorry, this number is not configured for IVR.", voice='alice')
            return Response(str(response), mimetype='text/xml')
        
        # Check if IVR setup is enabled
        if ivr_config['ivr_setup']:
            
            # Build TwiML response for language selection
            response = VoiceResponse()
            gather = Gather(num_digits=1, action='/ivr/handle-selection', method='POST', timeout=10)
            
            # Check if we have an audio URL for the IVR menu
            if ivr_config.get('audio_url_ivr'):
                # Use the audio URL directly
                audio_url = ivr_config['audio_url_ivr']
                
                if audio_url:
                    gather.play(audio_url)
                else:
                    logger.error(f"Audio URL is empty for IVR menu - no fallback available")
            else:
                logger.error(f"No audio URL found for IVR menu - no fallback available")
            
            # Add fallback if no digits pressed
            response.append(gather)
            response.say("No selection made. Goodbye.", voice='alice')
            
            return Response(str(response), mimetype='text/xml')
            
        else:
            
            # For single language setup, directly transfer the call
            language_1_id = ivr_config.get('language_1_id')
            if not language_1_id:
                logger.error(f"No language_1_id found in single language configuration")
                response = VoiceResponse()
                response.say("Sorry, language configuration not found.", voice='alice')
                return Response(str(response), mimetype='text/xml')
            
            # Get transfer number for the single language
            transfer_number = ivr_service.get_transfer_number(language_1_id)
            
            if not transfer_number:
                logger.error(f"No transfer number found for language: {language_1_id}")
                response = VoiceResponse()
                response.say("Sorry, transfer number not configured.", voice='alice')
                return Response(str(response), mimetype='text/xml')
            

            
            # Find or create caller record
            caller_id = ivr_service.find_or_create_caller(from_number, ivr_config['client_id'], language_1_id)
            
            if not caller_id:
                logger.error(f"Failed to find or create caller record for {from_number}")
                response = VoiceResponse()
                response.say("Sorry, caller record could not be created.", voice='alice')
                return Response(str(response), mimetype='text/xml')
            
            # Create VAPI webhook event record (synchronous)
            vapi_event_id = ivr_service.create_vapi_webhook_event(
                from_number,
                caller_id,
                ivr_config['client_id']
            )
            
            if not vapi_event_id:
                logger.error(f"Failed to create VAPI webhook event for {from_number}")
                response = VoiceResponse()
                response.say("Sorry, call setup failed.", voice='alice')
                return Response(str(response), mimetype='text/xml')
            
            # Create Twilio call record in background
            background_thread = threading.Thread(
                target=run_post_transfer_updates,
                args=(caller_id, vapi_event_id, call_sid)
            )
            background_thread.daemon = True
            background_thread.start()
            
            # Transfer the call
            response = VoiceResponse()
            response.dial(
                Number(transfer_number),
                caller_id=from_number  # Preserve original caller ID
            )
            

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

        
        # Get IVR configuration again
        service = get_ivr_service()
        ivr_config = service.get_ivr_configuration(to_number)
        
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
        

        
        # Get transfer number
        transfer_number = service.get_transfer_number(selected_option['language_id'])
        
        if not transfer_number:
            logger.error(f"No transfer number found for language: {selected_option['language_id']}")
            response = VoiceResponse()
            response.say("Sorry, transfer number not configured.", voice='alice')
            return Response(str(response), mimetype='text/xml')
        

        
        # Create VAPI webhook event record (synchronous - must complete before TwiML response)
        # Create without caller field initially, will be updated in background
        vapi_event_id = service.create_vapi_webhook_event(
            from_number,
            None,  # No caller ID initially
            ivr_config['client_id']
        )
        
        if not vapi_event_id:
            logger.error(f"Failed to create VAPI webhook event for: {from_number}")
            response = VoiceResponse()
            response.say("Sorry, an error occurred. Please try again.", voice='alice')
            return Response(str(response), mimetype='text/xml')
        

        
        # Create Twilio call record and update caller in background (after TwiML response)
        background_thread = threading.Thread(
            target=run_post_transfer_updates,
            args=(from_number, vapi_event_id, call_sid, ivr_config['client_id'], selected_option['language_id'])
        )
        background_thread.daemon = True
        background_thread.start()
        
        # Build TwiML response
        response = VoiceResponse()
        
        # Play the reply message if configured
        if selected_option.get('audio_reply'):
    
            # Use the audio URL directly
            audio_reply_url = selected_option['audio_reply']
            
            if audio_reply_url:
                response.play(audio_reply_url)
            else:
                logger.error(f"Audio reply URL is empty - no fallback available")
        else:
            logger.error(f"No audio reply URL found for selected option - no fallback available")
        
        # Transfer the call
        dial = response.dial(
            caller_id=from_number,
            status_callback="https://siftly.onrender.com/ivr/status-callback",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST"
        )
        dial.number(transfer_number)
        

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
        # Status callback received
        
        # Extract CallSid
        call_sid = request.form.get('CallSid')
        call_status = request.form.get('CallStatus')
        

        
        if not call_sid:
            logger.warning("No CallSid provided in status callback")
            return '', 200
        
        # Only handle "completed" status
        if call_status != "completed":
            return '', 200
        
        # Initialize Twilio client and fetch call details
        from twilio.rest import Client
        client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
        
        call_details = client.calls(call_sid).fetch()
        
        # Look up the CallSid in our twilio_call table
        service = get_ivr_service()
        twilio_call_response = service.supabase.table("twilio_call").select("*").eq("call_sid", call_sid).execute()
        
        twilio_call_match = twilio_call_response.data or []
        
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
            # Add 15-second delay for Branch 1
            time.sleep(15)
            
            record = twilio_call_match[0]
            record_id = record['id']
            
            # Check if the IVR record has vapi_webhook_event_id, if not, we need to create one
            existing_vapi_webhook_event_id = record.get('vapi_webhook_event_id')
            
            # Convert to list format for compatibility with existing logic
            existing_vapi_webhook_event = [existing_vapi_webhook_event_id] if existing_vapi_webhook_event_id else []
            
            if not existing_vapi_webhook_event:
                logger.info(f"Branch 1: IVR record missing vapi_webhook_event, creating one")
                
                # Create a new vapi_webhook_event record
                vapi_event_data = {
                    'from_number': update_data.get('From'),
                    'transferred_time': datetime.utcnow().isoformat() + 'Z'
                }
                
                # Try to get caller_id and client_id from the record if available
                if record.get('caller_id'):
                    vapi_event_data['caller_id'] = record.get('caller_id')
                if record.get('client_id'):
                    vapi_event_data['client_id'] = record.get('client_id')
                
                vapi_event_response = service.supabase.table("vapi_webhook_event").insert(vapi_event_data).execute()
                vapi_event_record = vapi_event_response.data[0] if vapi_event_response.data else None
                
                if vapi_event_record:
                    logger.info(f"Branch 1: Created vapi_webhook_event record: {vapi_event_record['id']}")
                    
                    # Update the IVR record with the vapi_webhook_event link
                    update_data = {
                        'vapi_webhook_event_id': vapi_event_record['id']
                    }
                    
                    response = service.supabase.table("twilio_call").update(update_data).eq("id", record_id).execute()
                    if not getattr(response, 'data', None):
                        logger.warning("Update twilio_call with vapi_webhook_event_id returned no data")
                    
                    logger.info(f"Branch 1: Updated IVR record with vapi_webhook_event link")
                    existing_vapi_webhook_event = [vapi_event_record['id']]
                else:
                    logger.error(f"Branch 1: Failed to create vapi_webhook_event record")
            else:
                pass
            
            # Update the record
            
            # Update the existing record in Supabase
            if update_data:
                # Map fields to Supabase-compatible names
                mapped_data = {}
                if 'CallSid' in update_data:
                    mapped_data['call_sid'] = update_data['CallSid']
                if 'AccountSid' in update_data:
                    mapped_data['account_sid'] = update_data['AccountSid']
                if 'From' in update_data:
                    mapped_data['from_number'] = update_data['From']
                if 'To' in update_data:
                    mapped_data['to_number'] = update_data['To']
                if 'Direction' in update_data:
                    mapped_data['direction'] = update_data['Direction']
                if 'StartTime' in update_data:
                    mapped_data['start_time'] = update_data['StartTime']
                if 'EndTime' in update_data:
                    mapped_data['end_time'] = update_data['EndTime']
                if 'Duration' in update_data:
                    mapped_data['duration'] = int(update_data['Duration'])
                if 'AnsweredBy' in update_data:
                    mapped_data['answered_by'] = update_data['AnsweredBy']
                if 'ForwardedFrom' in update_data:
                    mapped_data['forwarded_from'] = update_data['ForwardedFrom']
                
                response = service.supabase.table("twilio_call").update(mapped_data).eq("id", record_id).execute()
                if getattr(response, 'data', None):
        
                else:
                    logger.warning(f"Update twilio_call {record_id} returned no data")
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
                
                # Get vapi_webhook_event_id from parent record
                vapi_webhook_event_id = record.get('vapi_webhook_event_id')
                if vapi_webhook_event_id:
                    child_call_data['vapi_webhook_event'] = [vapi_webhook_event_id]  # Convert to list for compatibility
                    logger.info(f"Branch 1: Linking child call to same vapi_webhook_event_id: {vapi_webhook_event_id}")
                
                logger.info(f"Branch 1: Creating child call record with data: {child_call_data}")
                
                # Map child call data to Supabase-compatible names
                mapped_child_data = {}
                if 'CallSid' in child_call_data:
                    mapped_child_data['call_sid'] = child_call_data['CallSid']
                if 'Type' in child_call_data:
                    mapped_child_data['call_type'] = child_call_data['Type']
                if 'Parent' in child_call_data:
                    mapped_child_data['parent_id'] = child_call_data['Parent'][0] if child_call_data['Parent'] else None
                if 'AccountSid' in child_call_data:
                    mapped_child_data['account_sid'] = child_call_data['AccountSid']
                if 'From' in child_call_data:
                    mapped_child_data['from_number'] = child_call_data['From']
                if 'To' in child_call_data:
                    mapped_child_data['to_number'] = child_call_data['To']
                if 'Direction' in child_call_data:
                    mapped_child_data['direction'] = child_call_data['Direction']
                if 'StartTime' in child_call_data:
                    mapped_child_data['start_time'] = child_call_data['StartTime']
                if 'EndTime' in child_call_data:
                    mapped_child_data['end_time'] = child_call_data['EndTime']
                if 'Duration' in child_call_data:
                    mapped_child_data['duration'] = int(child_call_data['Duration'])
                if 'AnsweredBy' in child_call_data:
                    mapped_child_data['answered_by'] = child_call_data['AnsweredBy']
                if 'ForwardedFrom' in child_call_data:
                    mapped_child_data['forwarded_from'] = child_call_data['ForwardedFrom']
                if 'vapi_webhook_event' in child_call_data:
                    mapped_child_data['vapi_webhook_event_id'] = child_call_data['vapi_webhook_event'][0] if child_call_data['vapi_webhook_event'] else None
                
                # Create child call record
                child_response = service.supabase.table("twilio_call").insert(mapped_child_data).execute()
                child_record = child_response.data[0] if child_response.data else None
                
                if child_record:
                    logger.info(f"Branch 1: Successfully created child call record: {child_record['id']}")
                else:
                    logger.error(f"Branch 1: Failed to create child call record")
            else:
                logger.info(f"Branch 1: No child calls found for ParentCallSid: {call_sid}")
            
            # Now look for a matching VAPI record to link vapi_webhook_event
            logger.info(f"Branch 1: Looking for matching VAPI record with same From field and similar EndTime")
            
            # Get the From field and EndTime from our updated record
            from_number = update_data.get('From')
            end_time = update_data.get('EndTime')
            
            if from_number and end_time:
                # Search for records with same From field and Type = "vapi"
                response = service.supabase.table("twilio_call").select("*").eq("from_number", from_number).execute()
                matching_records = response.data or []
                
                logger.info(f"Branch 1: Found {len(matching_records)} records with same From field: {from_number}")
                
                # Filter for records with Type = "vapi" and similar EndTime
                from datetime import datetime
                matching_vapi_records = []
                
                for record in matching_records:
                    record_type = record.get('call_type')
                    record_end_time = record.get('end_time')
                    
                    # Check if it's a VAPI record
                    if record_type == 'vapi' and record_end_time:
                        try:
                            # Parse the end times for comparison
                            new_end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                            record_end_dt = datetime.fromisoformat(record_end_time.replace('Z', '+00:00'))
                            
                            # Calculate time difference
                            time_diff = abs((new_end_dt - record_end_dt).total_seconds())
                            
                            logger.info(f"Branch 1: Comparing with record {record['id']}: time_diff={time_diff}s")
                            
                            # Check if within 15 seconds
                            if time_diff <= 15:
                                matching_vapi_records.append(record)
                                logger.info(f"Branch 1: Found matching VAPI record {record['id']} (time_diff={time_diff}s)")
                            
                        except Exception as e:
                            logger.warning(f"Branch 1: Error parsing EndTime for record {record['id']}: {e}")
                
                # If we found a matching VAPI record, link the vapi_webhook_event
                if matching_vapi_records:
                    # Take the first matching record (closest in time)
                    matching_vapi_record = matching_vapi_records[0]
                    vapi_webhook_event_id = matching_vapi_record.get('vapi_webhook_event_id')
                    
                    logger.info(f"Branch 1: Matching VAPI record: {matching_vapi_record}")
                    logger.info(f"Branch 1: vapi_webhook_event_id value: {vapi_webhook_event_id}")
                    
                    # Get the vapi_webhook_event from our IVR record (the one we just updated)
                    ivr_vapi_webhook_event = existing_vapi_webhook_event  # Use the variable we set earlier
                    
                    logger.info(f"Branch 1: IVR record vapi_webhook_event: {ivr_vapi_webhook_event}")
                    
                    if ivr_vapi_webhook_event:
                        logger.info(f"Branch 1: Updating VAPI record {matching_vapi_record['id']} with vapi_webhook_event from IVR record")
                        
                        # Validate ivr_vapi_webhook_event is a non-empty list
                        if isinstance(ivr_vapi_webhook_event, list) and ivr_vapi_webhook_event:
                            vapi_webhook_event_id = ivr_vapi_webhook_event[0]
                            
                            # Update the VAPI record with the vapi_webhook_event_id from the IVR record
                            update_data = {
                                'vapi_webhook_event_id': vapi_webhook_event_id
                            }
                            
                            response = service.supabase.table("twilio_call").update(update_data).eq("id", matching_vapi_record['id']).execute()
                            if getattr(response, 'data', None):
                                logger.info(f"Branch 1: Successfully updated VAPI record {matching_vapi_record['id']} with vapi_webhook_event_id")
                            else:
                                logger.warning(f"Update twilio_call {matching_vapi_record['id']} with vapi_webhook_event_id returned no data")
                        else:
                            logger.warning("ivr_vapi_webhook_event is empty or invalid; skipping Supabase update")
                        
                        # Now fetch VAPI details using the call_id from the linked vapi_webhook_event record
                        logger.info(f"Branch 1: Fetching VAPI details for linked vapi_webhook_event")
                        
                        # Get the vapi_webhook_event record to extract call_id
                        record_id = ivr_vapi_webhook_event[0]  # Take the first linked record
                        response = service.supabase.table("vapi_webhook_event").select("*").eq("id", record_id).limit(1).execute()
                        
                        if getattr(response, 'data', None):
                            vapi_event_record = response.data[0]
                        else:
                            vapi_event_record = None
                        
                        if vapi_event_record:
                            call_id = vapi_event_record.get('call_id')
                            
                            if call_id:
                                logger.info(f"Branch 1: Found call_id {call_id} in vapi_webhook_event record")
                                
                                # Fetch VAPI call data
                                from routes.vapi_routes import VAPIWebhookService
                                vapi_service = VAPIWebhookService()
                                call_data = vapi_service.get_vapi_call_data(call_id)
                                
                                if call_data:
                                    logger.info(f"Branch 1: Successfully fetched VAPI call data for call_id: {call_id}")
                                    
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
                                        vapi_update_data['analysis_success_evaluation'] = analysis.get('successEvaluation')
                                    
                                    # Remove None values
                                    vapi_update_data = {k: v for k, v in vapi_update_data.items() if v is not None}
                                    
                                    if vapi_update_data:
                                        # Map fields to Supabase-compatible names
                                        mapped_vapi_data = {}
                                        if 'endedAt' in vapi_update_data:
                                            mapped_vapi_data['ended_at'] = vapi_update_data['endedAt']
                                        if 'transcript' in vapi_update_data:
                                            mapped_vapi_data['transcript'] = vapi_update_data['transcript']
                                        if 'recordingUrl' in vapi_update_data:
                                            mapped_vapi_data['recording_url'] = vapi_update_data['recordingUrl']
                                        if 'summary' in vapi_update_data:
                                            mapped_vapi_data['summary'] = vapi_update_data['summary']
                                        if 'status' in vapi_update_data:
                                            mapped_vapi_data['status'] = vapi_update_data['status']
                                        if 'cost' in vapi_update_data:
                                            mapped_vapi_data['cost'] = vapi_update_data['cost']
                                        if 'endedReason' in vapi_update_data:
                                            mapped_vapi_data['ended_reason'] = vapi_update_data['endedReason']
                                        if 'analysis_summary' in vapi_update_data:
                                            mapped_vapi_data['analysis_summary'] = vapi_update_data['analysis_summary']
                                        if 'analysis_success_evaluation' in vapi_update_data:
                                            mapped_vapi_data['analysis_success_evaluation'] = vapi_update_data['analysis_success_evaluation']
                                        
                                        # Update the vapi_webhook_event record with VAPI data
                                        record_id = ivr_vapi_webhook_event[0]
                                        response = service.supabase.table("vapi_webhook_event").update(mapped_vapi_data).eq("id", record_id).execute()
                                        if getattr(response, 'data', None):
                                            logger.info(f"Branch 1: Successfully updated vapi_webhook_event record with VAPI data")
                                        else:
                                            logger.warning(f"Update vapi_webhook_event {record_id} returned no data")
                                    else:
                                        logger.warning(f"Branch 1: No VAPI data to update")
                                else:
                                    logger.warning(f"Branch 1: Failed to fetch VAPI call data for call_id: {call_id}")
                            else:
                                logger.warning(f"Branch 1: No call_id found in vapi_webhook_event record")
                        else:
                            logger.warning(f"Branch 1: Could not retrieve vapi_webhook_event record")
                    else:
                        logger.warning(f"Branch 1: No vapi_webhook_event found in IVR record to copy to VAPI record")
                else:
                    logger.info(f"Branch 1: No matching VAPI record found within 15 seconds")
            else:
                logger.warning(f"Branch 1: Missing From field or EndTime for comparison")
        
        # Branch 2: No matching record found
        else:
            logger.info(f"Branch 2: No twilio_call record found for CallSid: {call_sid}, creating new record")
            
            # Create new record with the same fields
            new_call_data = update_data.copy()
            new_call_data['Type'] = 'vapi'  # Set type to vapi for new records
            
            logger.info(f"Branch 2: Creating new twilio_call record with data: {new_call_data}")
            
            # Create the new record in Supabase
            if new_call_data:
                # Map fields to Supabase-compatible names
                mapped_new_data = {}
                if 'CallSid' in new_call_data:
                    mapped_new_data['call_sid'] = new_call_data['CallSid']
                if 'AccountSid' in new_call_data:
                    mapped_new_data['account_sid'] = new_call_data['AccountSid']
                if 'From' in new_call_data:
                    mapped_new_data['from_number'] = new_call_data['From']
                if 'To' in new_call_data:
                    mapped_new_data['to_number'] = new_call_data['To']
                if 'Direction' in new_call_data:
                    mapped_new_data['direction'] = new_call_data['Direction']
                if 'StartTime' in new_call_data:
                    mapped_new_data['start_time'] = new_call_data['StartTime']
                if 'EndTime' in new_call_data:
                    mapped_new_data['end_time'] = new_call_data['EndTime']
                if 'Duration' in new_call_data:
                    mapped_new_data['duration'] = int(new_call_data['Duration'])
                if 'AnsweredBy' in new_call_data:
                    mapped_new_data['answered_by'] = new_call_data['AnsweredBy']
                if 'ForwardedFrom' in new_call_data:
                    mapped_new_data['forwarded_from'] = new_call_data['ForwardedFrom']
                if 'Type' in new_call_data:
                    mapped_new_data['call_type'] = new_call_data['Type']
                
                response = service.supabase.table("twilio_call").insert(mapped_new_data).execute()
                new_record = response.data[0] if response.data else None
                
                if new_record:
                    logger.info(f"Branch 2: Successfully created new twilio_call record: {new_record['id']}")
                    
                    # Now look for a matching IVR record to link vapi_webhook_event
                    logger.info(f"Branch 2: Looking for matching IVR record with same From field and similar EndTime")
                    
                    # Get the From field and EndTime from our new record
                    from_number = new_call_data.get('From')
                    end_time = new_call_data.get('EndTime')
                    
                    if from_number and end_time:
                        # Search for records with same from_number field
                        response = service.supabase.table("twilio_call").select("*").eq("from_number", from_number).execute()
                        matching_records = response.data or []
                        
                        logger.info(f"Branch 2: Found {len(matching_records)} records with same From field: {from_number}")
                        
                        # Filter for records with Type = "ivr" and similar EndTime
                        from datetime import datetime
                        matching_ivr_records = []
                        
                        for record in matching_records:
                            record_type = record.get('call_type')
                            record_end_time = record.get('end_time')
                            
                            # Check if it's an IVR record
                            if record_type == 'ivr' and record_end_time:
                                try:
                                    # Parse the end times for comparison
                                    new_end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                                    record_end_dt = datetime.fromisoformat(record_end_time.replace('Z', '+00:00'))
                                    
                                    # Calculate time difference
                                    time_diff = abs((new_end_dt - record_end_dt).total_seconds())
                                    
                                    logger.info(f"Branch 2: Comparing with record {record['id']}: time_diff={time_diff}s")
                                    
                                    # Check if within 15 seconds
                                    if time_diff <= 15:
                                        matching_ivr_records.append(record)
                                        logger.info(f"Branch 2: Found matching IVR record {record['id']} (time_diff={time_diff}s)")
                                    
                                except Exception as e:
                                    logger.warning(f"Branch 2: Error parsing EndTime for record {record['id']}: {e}")
                        
                        # If we found a matching IVR record, link the vapi_webhook_event
                        if matching_ivr_records:
                            # Take the first matching record (closest in time)
                            matching_ivr_record = matching_ivr_records[0]
                            vapi_webhook_event_id = matching_ivr_record.get('vapi_webhook_event_id')
                            
                            if vapi_webhook_event_id:
                                logger.info(f"Branch 2: Linking vapi_webhook_event_id {vapi_webhook_event_id} from IVR record {matching_ivr_record['id']}")
                                
                                # Update our new record with the vapi_webhook_event_id link
                                update_data = {
                                    'vapi_webhook_event_id': vapi_webhook_event_id
                                }
                                
                                response = service.supabase.table("twilio_call").update(update_data).eq("id", new_record['id']).execute()
                                if getattr(response, 'data', None):
                                    logger.info(f"Branch 2: Successfully linked vapi_webhook_event_id to new record {new_record['id']}")
                                else:
                                    logger.warning(f"Update twilio_call {new_record['id']} with vapi_webhook_event_id returned no data")
                            else:
                                logger.warning(f"Branch 2: No vapi_webhook_event_id found in matching IVR record {matching_ivr_record['id']}")
                        else:
                            logger.info(f"Branch 2: No matching IVR record found within 15 seconds")
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
            'database': 'Supabase'
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        } 