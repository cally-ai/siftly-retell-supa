"""
Voice webhook route handlers for Twilio integration with Retell AI + Media Streams (stereo)
"""
import os
import requests
from typing import Optional, Dict, Any
from flask import Blueprint, request, Response
from twilio.twiml.voice_response import VoiceResponse, Dial, Start
from config import Config
from utils.logger import get_logger
from supabase import create_client, Client

logger = get_logger(__name__)

# IMPORTANT: expose exactly /voice-webhook (no prefix)
voice_bp = Blueprint("voice", __name__, url_prefix="")

class VoiceWebhookService:
    """Service for handling voice webhook operations"""

    def __init__(self):
        self.retell_api_key = Config.RETELL_API_KEY

        if not self.retell_api_key:
            logger.error("RETELL_API_KEY not configured")
            raise ValueError("RETELL_API_KEY environment variable is required")

        # PUBLIC_HOSTNAME is used to build the wss URL Twilio streams to
        self.public_hostname = getattr(Config, "PUBLIC_HOSTNAME", None)
        if not self.public_hostname:
            logger.warning("PUBLIC_HOSTNAME not configured - will use default")
            self.public_hostname = "siftly-retell-supa.onrender.com"  # Default fallback
        else:
            # Extract just the hostname from the full WebSocket URL
            # Example: "wss://siftly-retell-supa.onrender.com/transcription/stream" -> "siftly-retell-supa.onrender.com"
            if self.public_hostname.startswith("wss://"):
                self.public_hostname = self.public_hostname.replace("wss://", "").split("/")[0]
            elif self.public_hostname.startswith("https://"):
                self.public_hostname = self.public_hostname.replace("https://", "").split("/")[0]
            elif self.public_hostname.startswith("http://"):
                self.public_hostname = self.public_hostname.replace("http://", "").split("/")[0]

    def get_supabase_client(self) -> Client:
        """Get Supabase client using your existing pattern"""
        return create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_ROLE_KEY)

    # ---------- Supabase lookup chain ----------
    # 1) Find row in table twilio_number where twilio_number == To
    # 2) Read client_ivr_language_configuration_id
    # 3) Find row in table retell_agent_id where client_ivr_language_configuration_id matches
    # 4) Return agent_id
    def get_agent_id_from_supabase(self, to_number: str) -> Optional[str]:
        try:
            supabase = self.get_supabase_client()
            
            tn = (
                supabase.table("twilio_number")
                .select("client_ivr_language_configuration_id")
                .eq("twilio_number", to_number)
                .single()
                .execute()
            )

            if not tn or not getattr(tn, "data", None):
                logger.warning(f"No twilio_number row for: {to_number}")
                return None

            civr_id = tn.data.get("client_ivr_language_configuration_id")
            if not civr_id:
                logger.warning(f"No client_ivr_language_configuration_id for: {to_number}")
                return None

            ra = (
                supabase.table("retell_agent_id")
                .select("agent_id")
                .eq("client_ivr_language_configuration_id", civr_id)
                .single()
                .execute()
            )

            if not ra or not getattr(ra, "data", None):
                logger.warning(f"No retell_agent_id row for civr_id: {civr_id}")
                return None

            agent_id = ra.data.get("agent_id")
            if not agent_id or not isinstance(agent_id, str):
                logger.warning(f"Invalid agent_id for civr_id: {civr_id}")
                return None

            logger.info(f"Resolved agent_id '{agent_id}' for To {to_number}")
            return agent_id

        except Exception as e:
            logger.error(f"Supabase lookup error: {e}")
            return None

    def _get_dynamic_variables_from_supabase(self, to_number: str, from_number: str, original_call_sid: str) -> Dict[str, Any]:
        """
        Get dynamic variables using the same chain as call_inbound webhook
        """
        try:
            logger.info(f"Getting dynamic variables for to_number: {to_number}, from_number: {from_number}")
            
            # Clean phone number by removing spaces and special characters
            cleaned_number = to_number.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            logger.info(f"Original number: {to_number}, Cleaned number: {cleaned_number}")
            
            # Step 1: Find client via twilio_number (try both original and cleaned)
            tw_resp = self.get_supabase_client().table('twilio_number').select('client_id, client_ivr_language_configuration_id').eq('twilio_number', cleaned_number).limit(1).execute()
            if not tw_resp.data:
                # Fallback to original number if cleaned doesn't work
                tw_resp = self.get_supabase_client().table('twilio_number').select('client_id, client_ivr_language_configuration_id').eq('twilio_number', to_number).limit(1).execute()
            if not tw_resp.data:
                logger.warning(f"No twilio_number record found for: {to_number} (cleaned: {cleaned_number})")
                return self._get_default_dynamic_variables(from_number, to_number, original_call_sid)
            
            client_id = tw_resp.data[0].get('client_id')
            client_ivr_language_configuration_id = tw_resp.data[0].get('client_ivr_language_configuration_id')
            if not client_id:
                logger.warning(f"twilio_number {to_number} has no client_id")
                return self._get_default_dynamic_variables(from_number, to_number, original_call_sid)

            # Step 2: Get client information and configuration
            dynamic_variables: Dict[str, Any] = {}
            
            # Get client basic info
            client_resp = self.get_supabase_client().table('client').select('name, client_description').eq('id', client_id).limit(1).execute()
            if client_resp.data:
                client = client_resp.data[0]
                client_name = client.get('name', 'Our Company')
                client_description = client.get('client_description', '')
                dynamic_variables['client_id'] = client_id
                dynamic_variables['client_name'] = client_name
                dynamic_variables['client_description'] = client_description
                logger.info(f"Client data - client_id: '{client_id}', name: '{client_name}', description: '{client_description}'")

            # Get client workflow configuration
            wf_resp = self.get_supabase_client().table('client_workflow_configuration').select('*').eq('client_id', client_id).limit(1).execute()
            if wf_resp.data:
                wf_config = wf_resp.data[0]
                logger.info(f"Workflow config raw data: {wf_config}")
                # Add workflow configuration as dynamic variables (without workflow_ prefix)
                for key, value in wf_config.items():
                    if key != 'id' and key != 'client_id' and value is not None:
                        dynamic_variables[key] = value
                        logger.info(f"Added {key}: '{value}'")

            # Get client language agent names using the new structure
            if client_ivr_language_configuration_id:
                # Get all languages for this client's IVR configuration
                ivr_lang_resp = self.get_supabase_client().table('client_ivr_language_configuration_language').select(
                    'language_id'
                ).eq('client_id', client_id).eq('client_ivr_language_configuration_id', client_ivr_language_configuration_id).execute()
                
                if ivr_lang_resp.data:
                    # Get agent names for each language
                    for lang_record in ivr_lang_resp.data:
                        language_id = lang_record.get('language_id')
                        if language_id:
                            # Get agent name for this language
                            agent_resp = self.get_supabase_client().table('client_language_agent_name').select(
                                'agent_name'
                            ).eq('client_id', client_id).eq('language_id', language_id).limit(1).execute()
                            
                            if agent_resp.data:
                                agent_name = agent_resp.data[0].get('agent_name')
                                if agent_name:
                                    # Get language code for the key
                                    lang_resp = self.get_supabase_client().table('language').select('language_code').eq('id', language_id).limit(1).execute()
                                    if lang_resp.data:
                                        lang_code = lang_resp.data[0].get('language_code', 'en')
                                        dynamic_variables[f'agent_name_{lang_code}'] = agent_name
                                        logger.info(f"Added agent_name_{lang_code}: {agent_name}")
            else:
                # Fallback: Get all agent names for the client (old method)
                agent_names_resp = self.get_supabase_client().table('client_language_agent_name').select('language_id, agent_name').eq('client_id', client_id).execute()
                if agent_names_resp.data:
                    for agent_record in agent_names_resp.data:
                        agent_language_id = agent_record.get('language_id')
                        agent_name = agent_record.get('agent_name')
                        if agent_language_id and agent_name:
                            # Get language code for the key
                            lang_resp = self.get_supabase_client().table('language').select('language_code').eq('id', agent_language_id).limit(1).execute()
                            if lang_resp.data:
                                lang_code = lang_resp.data[0].get('language_code', 'en')
                                dynamic_variables[f'agent_name_{lang_code}'] = agent_name

            # Add basic call information
            dynamic_variables['caller_number'] = from_number
            dynamic_variables['callee_number'] = to_number
            dynamic_variables['call_type'] = 'inbound'
            dynamic_variables['source'] = 'twilio_webhook'

            # Create retell_event record and get caller_id for the call_started webhook
            retell_event_data = {
                'from_number': from_number,
                'to_number': to_number,
                'agent_id': 'pending',  # Will be updated by call_started webhook
                'call_status': 'inbound',  # Initial status
                'direction': 'inbound'
            }
            
            retell_response = self.get_supabase_client().table('retell_event').insert(retell_event_data).execute()
            if hasattr(retell_response, 'error') and retell_response.error:
                logger.error(f"Error creating retell_event record: {retell_response.error}")
                return self._get_default_dynamic_variables(from_number, to_number, original_call_sid)
            
            retell_event_id = retell_response.data[0]['id'] if retell_response.data else None
            logger.info(f"Created retell_event record with ID: {retell_event_id}")
            
            # Get or create caller record
            caller_id = self._get_or_create_caller(from_number)
            if not caller_id:
                logger.error(f"Failed to get or create caller for: {from_number}")
                return self._get_default_dynamic_variables(from_number, to_number, original_call_sid)
            
            # Create original twilio_call record (Media Stream CallSid) for transcription
            original_twilio_call_data = {
                'call_sid': original_call_sid,  # Media Stream CallSid
                'from_number': from_number,
                'to_number': to_number,
                'direction': 'inbound',
                'retell_event_id': retell_event_id,
                'caller_id': caller_id
            }
            
            original_twilio_response = self.get_supabase_client().table('twilio_call').insert(original_twilio_call_data).execute()
            if hasattr(original_twilio_response, 'error') and original_twilio_response.error:
                logger.error(f"Error creating original twilio_call record: {original_twilio_response.error}")
            else:
                original_twilio_call_id = original_twilio_response.data[0]['id'] if original_twilio_response.data else None
                logger.info(f"Created original twilio_call record with ID: {original_twilio_call_id} for Media Stream CallSid: {original_call_sid}")
            
            # Add retell_event_id, caller_id, original_call_sid, and original_twilio_call_id to dynamic variables
            dynamic_variables['retell_event_id'] = retell_event_id
            dynamic_variables['caller_id'] = caller_id
            dynamic_variables['original_call_sid'] = original_call_sid  # Media Stream CallSid
            dynamic_variables['original_twilio_call_id'] = original_twilio_call_id  # ID of the original record

            logger.info(f"Dynamic variables built successfully: {list(dynamic_variables.keys())}")
            return dynamic_variables

        except Exception as e:
            logger.error(f"Error getting dynamic variables: {e}")
            return self._get_default_dynamic_variables(from_number, to_number, original_call_sid)

    def _get_or_create_caller(self, from_number: str) -> Optional[str]:
        """
        Get or create caller record in Supabase
        """
        try:
            # Check if caller already exists
            caller_resp = self.get_supabase_client().table('caller').select('id').eq('phone_number', from_number).limit(1).execute()
            
            if caller_resp.data:
                caller_id = caller_resp.data[0].get('id')
                logger.info(f"Found existing caller with ID: {caller_id}")
                return caller_id
            
            # Create new caller record
            caller_data = {
                'phone_number': from_number,
                'name': f"Caller from {from_number}",
                'email': None,
                'address': None
            }
            
            new_caller_resp = self.get_supabase_client().table('caller').insert(caller_data).execute()
            if hasattr(new_caller_resp, 'error') and new_caller_resp.error:
                logger.error(f"Error creating caller record: {new_caller_resp.error}")
                return None
            
            new_caller_id = new_caller_resp.data[0]['id'] if new_caller_resp.data else None
            logger.info(f"Created new caller with ID: {new_caller_id}")
            return new_caller_id
            
        except Exception as e:
            logger.error(f"Error in _get_or_create_caller: {e}")
            return None

    def _get_default_dynamic_variables(self, from_number: str, to_number: str, original_call_sid: str) -> Dict[str, Any]:
        """
        Get default dynamic variables when customer lookup fails
        """
        logger.info("Using default dynamic variables for unknown customer")
        return {
            'customer_name': 'Valued Customer',
            'customer_id': 'unknown',
            'account_type': 'standard',
            'client_name': 'Our Company',
            'caller_number': from_number,
            'callee_number': to_number,
            'call_type': 'inbound',
            'source': 'twilio_webhook',
            'original_call_sid': original_call_sid
        }

    def register_phone_call_with_retell(self, agent_id: str, from_number: str, to_number: str, original_call_sid: str) -> Optional[str]:
        """
        Register phone call with Retell AI and return call_id
        """
        try:
            # Get dynamic variables using the same chain as call_inbound webhook
            dynamic_variables = self._get_dynamic_variables_from_supabase(to_number, from_number, original_call_sid)
            
            # Prepare request payload
            payload = {
                "agent_id": agent_id,
                "from_number": from_number,
                "to_number": to_number,
                "direction": "inbound",
                "retell_llm_dynamic_variables": dynamic_variables
            }
            
            headers = {"Authorization": f"Bearer {self.retell_api_key}"}
            
            # Log the request details
            logger.info("=== RETELL API REGISTRATION REQUEST ===")
            logger.info(f"URL: https://api.retellai.com/v2/register-phone-call")
            logger.info(f"Headers: {headers}")
            logger.info(f"Payload: {payload}")
            logger.info("=== END RETELL API REQUEST ===")
            
            resp = requests.post(
                "https://api.retellai.com/v2/register-phone-call",
                json=payload,
                headers=headers,
                timeout=30,
            )
            
            # Log the response
            logger.info("=== RETELL API RESPONSE ===")
            logger.info(f"Status Code: {resp.status_code}")
            logger.info(f"Response Headers: {dict(resp.headers)}")
            logger.info(f"Response Body: {resp.text}")
            logger.info("=== END RETELL API RESPONSE ===")
            
            if resp.status_code not in (200, 201):
                logger.error(f"Retell API error: {resp.status_code} - {resp.text}")
                return None

            call_id = resp.json().get("call_id")
            if not call_id:
                logger.error("No call_id returned from Retell API")
                return None

            logger.info(f"Successfully registered Retell call_id={call_id}")
            return call_id

        except requests.exceptions.RequestException as e:
            logger.error(f"Request error registering call with Retell: {e}")
            return None
        except Exception as e:
            logger.error(f"Error registering call with Retell: {e}")
            return None

    def generate_twiml_response(self, call_id: str) -> str:
        """
        TwiML:
          1) Start Media Stream for INBOUND (caller) 
          2) Dial Retell with Media Stream for OUTBOUND (agent)
        """
        try:
            vr = VoiceResponse()

            # 1) Caller leg (inbound) BEFORE the bridge
            start_in = Start()
            start_in.stream(
                url=f"wss://{self.public_hostname}/transcription/stream?track=inbound",
                track="inbound_track"   # <-- REQUIRED
            )
            vr.append(start_in)

            # 2) Bridge to Retell
            dial = Dial()
            sip_url = f"sip:{call_id}@5t4n6j0wnrl.sip.livekit.cloud"
            dial.sip(sip_url)

            # 3) Agent leg (outbound) INSIDE <Dial> AFTER <Sip>
            start_out = Start()
            start_out.stream(
                url=f"wss://{self.public_hostname}/transcription/stream?track=outbound",
                track="outbound_track"  # <-- REQUIRED
            )
            dial.append(start_out)

            logger.info(f"Dialing Retell SIP: {sip_url}")
            vr.append(dial)

            return str(vr)

        except Exception as e:
            logger.error(f"Error generating TwiML: {e}")
            fallback = VoiceResponse()
            fallback.say("Sorry, there was an error processing your call.")
            return str(fallback)

# Initialize service
voice_service = VoiceWebhookService()

@voice_bp.route("/voice-webhook", methods=["POST"])
def voice_webhook():
    """Handle incoming voice webhooks from Twilio"""
    try:
        # Twilio form payload
        from_number = request.form.get("From")
        to_number = request.form.get("To")
        original_call_sid = request.form.get("CallSid")  # This is the Media Stream CallSid

        logger.info(f"/voice-webhook payload: {dict(request.form)}")

        if not from_number or not to_number:
            logger.error("Missing From/To")
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Invalid request parameters</Say></Response>',
                mimetype="text/xml",
                status=400,
            )

        # 1) Resolve Retell agent via Supabase chain
        agent_id = voice_service.get_agent_id_from_supabase(to_number)
        if not agent_id:
            logger.error(f"No agent configured for To={to_number}")
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Service not available for this number</Say></Response>',
                mimetype="text/xml",
                status=400,
            )

        # 2) Register call with Retell (returns call_id)
        call_id = voice_service.register_phone_call_with_retell(agent_id, from_number, to_number, original_call_sid)
        if not call_id:
            logger.error("Failed to register call with Retell")
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Service temporarily unavailable</Say></Response>',
                mimetype="text/xml",
                status=500,
            )

        # 3) Return TwiML: Start Media Stream (stereo) + Dial Retell
        twiml_response = voice_service.generate_twiml_response(call_id)
        logger.info("=== TWIML RESPONSE ===")
        logger.info(f"CallSid: {original_call_sid}")
        logger.info(f"Retell call_id: {call_id}")
        logger.info(f"TwiML Content: {twiml_response}")
        logger.info("=== END TWIML RESPONSE ===")
        return Response(twiml_response, mimetype="text/xml")

    except Exception as e:
        logger.error(f"Error in /voice-webhook: {e}")
        return Response(
            '<?xml version="1.0" encoding="UTF-8"?><Response><Say>An error occurred processing your call</Say></Response>',
            mimetype="text/xml",
            status=500,
        )
