"""
Voice webhook route handlers for Twilio integration with Retell AI + Media Streams (stereo)
"""
import os
import requests
from typing import Optional
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
            self.public_hostname = "https://siftly.onrender.com"  # Default fallback

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

    def register_phone_call_with_retell(self, agent_id: str, from_number: str, to_number: str) -> Optional[str]:
        """
        Register phone call with Retell AI and return call_id
        """
        try:
            # Prepare request payload
            payload = {
                "agent_id": agent_id,
                "from_number": from_number,
                "to_number": to_number,
                "direction": "inbound",
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
          1) Start Twilio Media Streams (stereo, both legs) to our WS
          2) Dial Retell SIP using the call_id
        """
        try:
            vr = VoiceResponse()

            # 1) Start stereo Media Streams (caller=ch0, callee=ch1) to your WS
            start = Start()
            # IMPORTANT: the endpoint below must be your WS handler that forwards to Deepgram (multichannel)
            start.stream(
                url=f"wss://{self.public_hostname}/transcription/stream",
                track="both_tracks",
            )
            vr.append(start)

            # 2) Dial Retell (same SIP format you used before)
            dial = Dial()
            sip_url = f"sip:{call_id}@5t4n6j0wnrl.sip.livekit.cloud"
            dial.sip(sip_url)
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
        call_sid = request.form.get("CallSid")

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
        call_id = voice_service.register_phone_call_with_retell(agent_id, from_number, to_number)
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
        logger.info(f"CallSid: {call_sid}")
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
