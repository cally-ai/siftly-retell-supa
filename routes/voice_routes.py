"""
Voice webhook route handlers for Twilio integration with Retell AI
"""
from flask import Blueprint, request, Response
from twilio.twiml.voice_response import VoiceResponse, Dial
import requests
import os
from typing import Optional, Dict, Any
from config import Config
from services.airtable_service import AirtableService
from utils.logger import get_logger

logger = get_logger(__name__)

# Create blueprint
voice_bp = Blueprint('voice', __name__, url_prefix='/voice')

class VoiceWebhookService:
    """Service for handling voice webhook operations"""
    
    def __init__(self):
        self.retell_api_key = Config.RETELL_API_KEY
        self.airtable_service = AirtableService()
        
        if not self.retell_api_key:
            logger.error("RETELL_API_KEY not configured")
            raise ValueError("RETELL_API_KEY environment variable is required")
    
    def get_agent_id_from_airtable(self, to_number: str) -> Optional[str]:
        """
        Get agent_id from Airtable based on to_number
        
        Args:
            to_number: The phone number being called
            
        Returns:
            Agent ID if found, None otherwise
        """
        try:
            # Step 1: Look up the to_number in the twilio_number table
            twilio_records = self.airtable_service.search_records_in_table(
                table_name="twilio_number",
                field="twilio_number", 
                value=to_number
            )
            
            if not twilio_records:
                logger.warning(f"No twilio_number record found for: {to_number}")
                return None
            
            twilio_record = twilio_records[0]
            logger.info(f"Found twilio_number record: {twilio_record.get('id')}")
            
            # Step 2: Get the linked client record
            client_linked_ids = twilio_record.get('fields', {}).get('client', [])
            if not client_linked_ids:
                logger.warning(f"No client linked to twilio_number: {to_number}")
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
            
            # Step 3: Extract agent_id from client record
            agent_id = client_record.get('fields', {}).get('agent_id')
            if not agent_id:
                logger.warning(f"No agent_id found in client record: {client_record_id}")
                return None
            
            # Handle case where agent_id might be a list (linked record)
            if isinstance(agent_id, list) and len(agent_id) > 0:
                agent_id = agent_id[0]
            elif not isinstance(agent_id, str):
                logger.warning(f"Invalid agent_id format in client record: {client_record_id}")
                return None
            
            logger.info(f"Found agent_id: {agent_id} for to_number: {to_number}")
            return agent_id
            
        except Exception as e:
            logger.error(f"Error getting agent_id from Airtable: {e}")
            return None
    
    def register_phone_call_with_retell(self, agent_id: str, from_number: str, to_number: str) -> Optional[str]:
        """
        Register phone call with Retell AI
        
        Args:
            agent_id: The Retell agent ID
            from_number: The calling number
            to_number: The called number
            
        Returns:
            Call ID if successful, None otherwise
        """
        try:
            response = requests.post(
                "https://api.retellai.com/v2/register-phone-call",
                json={
                    "agent_id": agent_id,
                    "from_number": from_number,
                    "to_number": to_number,
                    "direction": "inbound"
                },
                headers={"Authorization": f"Bearer {self.retell_api_key}"},
                timeout=30
            )
            
            if response.status_code not in [200, 201]:
                logger.error(f"Retell API error: {response.status_code} - {response.text}")
                return None
            
            call_data = response.json()
            call_id = call_data.get("call_id")
            
            if not call_id:
                logger.error("No call_id returned from Retell API")
                return None
            
            logger.info(f"Successfully registered call with Retell: {call_id}")
            return call_id
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error registering call with Retell: {e}")
            return None
        except Exception as e:
            logger.error(f"Error registering call with Retell: {e}")
            return None
    
    def generate_twiml_response(self, call_id: str) -> str:
        """
        Generate TwiML response for the call
        
        Args:
            call_id: The Retell call ID
            
        Returns:
            TwiML response as string
        """
        try:
            voice_response = VoiceResponse()
            dial = Dial()
            dial.sip(f"sip:{call_id}@5t4n6j0wnrl.sip.livekit.cloud")
            voice_response.append(dial)
            
            return str(voice_response)
            
        except Exception as e:
            logger.error(f"Error generating TwiML response: {e}")
            # Return a simple error response
            voice_response = VoiceResponse()
            voice_response.say("Sorry, there was an error processing your call.")
            return str(voice_response)

# Initialize service
voice_service = VoiceWebhookService()

@voice_bp.route('/webhook', methods=['POST'])
def voice_webhook():
    """Handle incoming voice webhooks from Twilio"""
    try:
        # Get form data from Twilio
        from_number = request.form.get('From')
        to_number = request.form.get('To')
        
        if not from_number or not to_number:
            logger.error("Missing required parameters: From or To")
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Invalid request parameters</Say></Response>',
                mimetype='text/xml'
            ), 400
        
        logger.info(f"Voice webhook received - From: {from_number}, To: {to_number}")
        
        # Step 1: Get agent_id from Airtable
        agent_id = voice_service.get_agent_id_from_airtable(to_number)
        if not agent_id:
            logger.error(f"No agent_id found for to_number: {to_number}")
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Service not available for this number</Say></Response>',
                mimetype='text/xml'
            ), 400
        
        # Step 2: Register phone call with Retell
        call_id = voice_service.register_phone_call_with_retell(agent_id, from_number, to_number)
        if not call_id:
            logger.error("Failed to register call with Retell")
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Service temporarily unavailable</Say></Response>',
                mimetype='text/xml'
            ), 500
        
        # Step 3: Generate TwiML response
        twiml_response = voice_service.generate_twiml_response(call_id)
        
        logger.info(f"Successfully processed voice webhook - Call ID: {call_id}")
        return Response(twiml_response, mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Error processing voice webhook: {e}")
        return Response(
            '<?xml version="1.0" encoding="UTF-8"?><Response><Say>An error occurred processing your call</Say></Response>',
            mimetype='text/xml'
        ), 500 