"""
Twilio Media Streams (stereo) -> Deepgram multichannel -> Supabase transcript writer
"""
import base64
import threading
import orjson
from typing import Dict, Any, List, Tuple, Optional

from flask import Blueprint
from flask_sock import Sock
import websocket

from config import Config
from utils.logger import get_logger
from supabase import create_client, Client

logger = get_logger(__name__)

transcription_bp = Blueprint("transcription", __name__, url_prefix="")
sock = Sock()  # IMPORTANT: call sock.init_app(app) in your app factory / main

DEEPGRAM_WSS = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=mulaw&sample_rate=8000&channels=2&multichannel=true"
    "&punctuate=true&endpointing=50"
)

def get_supabase() -> Client:
    return create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_ROLE_KEY)


def _extract_channel_texts_and_final(dg_msg: Dict[str, Any]) -> Tuple[List[Tuple[int, str]], bool]:
    """
    Extract per-channel transcripts + is_final flag from Deepgram message.
    Returns ([(channel_index, text), ...], is_final)
    """
    channel_texts: List[Tuple[int, str]] = []
    is_final = False

    if "channel" in dg_msg and isinstance(dg_msg["channel"], dict):
        ch_obj = dg_msg["channel"]
        idx = ch_obj.get("channel_index", 0)
        alts = ch_obj.get("alternatives") or []
        if alts and isinstance(alts[0], dict):
            txt = (alts[0].get("transcript") or "").strip()
            if txt:
                channel_texts.append((idx, txt))
        is_final = bool(dg_msg.get("is_final", False))

    elif "results" in dg_msg and isinstance(dg_msg["results"], dict):
        channels = dg_msg["results"].get("channels") or []
        is_final = bool(dg_msg.get("is_final", False))
        for ch in channels:
            idx = ch.get("channel_index", 0)
            alts = ch.get("alternatives") or []
            if alts and isinstance(alts[0], dict):
                txt = (alts[0].get("transcript") or "").strip()
                if txt:
                    channel_texts.append((idx, txt))

    elif "transcript" in dg_msg and isinstance(dg_msg["transcript"], str):
        channel_texts.append((0, dg_msg["transcript"].strip()))
        is_final = bool(dg_msg.get("is_final", False))

    return channel_texts, is_final


@sock.route("/transcription/stream")
def transcription_stream(ws):
    """
    Twilio connects here (stereo, both legs).
    Forwards audio to Deepgram and writes transcripts into Supabase:
      - PARTIAL: append to live_transcript_partial
      - FINAL: append to live_transcript_final, then clear partial
    """
    logger.info("=== TRANSCRIPTION WEBSOCKET CONNECTION STARTED ===")
    supabase = get_supabase()
    call_sid: Optional[str] = None

    # Simple queue for audio chunks
    audio_queue = []
    events_queue = []

               def deepgram_pump():
               headers = {"Authorization": f"Token {Config.DEEPGRAM_API_KEY}"}
               logger.info("=== DEEPGRAM WEBSOCKET SETUP ===")
               logger.info(f"URL: {DEEPGRAM_WSS}")
               logger.info(f"Headers: {headers}")
               logger.info("=== END DEEPGRAM SETUP ===")
               
               def on_message(ws, message):
                   try:
                       data = orjson.loads(message)
                       events_queue.append(data)
                       logger.debug(f"Received Deepgram message: {data}")
                   except Exception as e:
                       logger.error(f"Error parsing Deepgram message: {e}")
        
        def on_error(ws, error):
            logger.error(f"Deepgram WebSocket error: {error}")
        
        def on_close(ws, close_status_code, close_msg):
            logger.info("Deepgram WebSocket connection closed")
        
        def on_open(ws):
            logger.info("Deepgram WebSocket connection opened")
        
        dg_ws = websocket.WebSocketApp(
            DEEPGRAM_WSS,
            header=headers,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        def sender():
            while True:
                if audio_queue:
                    chunk = audio_queue.pop(0)
                    if chunk is None:
                        break
                    try:
                        dg_ws.send(chunk, websocket.ABNF.OPCODE_BINARY)
                    except Exception:
                        break
                else:
                    import time
                    time.sleep(0.01)  # Small delay to prevent busy waiting
        
        sender_thread = threading.Thread(target=sender, daemon=True)
        sender_thread.start()
        
        dg_ws.run_forever()

    pump_thread = threading.Thread(target=deepgram_pump, daemon=True)
    pump_thread.start()

    try:
        while True:
            raw = ws.receive()
            if raw is None:
                break

            try:
                evt = orjson.loads(raw)
            except Exception:
                continue

            etype = evt.get("event")

                               if etype == "start":
                       call_sid = evt.get("start", {}).get("callSid")
                       logger.info(f"=== MEDIA STREAM START ===")
                       logger.info(f"CallSid: {call_sid}")
                       logger.info(f"Full start event: {evt}")
                       logger.info("=== END MEDIA STREAM START ===")
                       if call_sid:
                           try:
                               supabase.table("twilio_call").upsert({
                                   "call_sid": call_sid,
                                   "live_transcript_partial": "",
                                   "live_transcript_final": ""
                               }).execute()
                               logger.info(f"Successfully created/updated twilio_call record for {call_sid}")
                           except Exception as e:
                               logger.error(f"Failed to create twilio_call record: {e}")

                               elif etype == "media":
                       payload_b64 = evt.get("media", {}).get("payload")
                       if payload_b64:
                           audio_bytes = base64.b64decode(payload_b64)
                           audio_queue.append(audio_bytes)
                           logger.debug(f"Received audio chunk: {len(audio_bytes)} bytes")
                       else:
                           logger.warning("Media event without payload")

                               elif etype == "stop":
                       logger.info(f"=== MEDIA STREAM STOP ===")
                       logger.info(f"CallSid: {call_sid}")
                       logger.info(f"Full stop event: {evt}")
                       logger.info("=== END MEDIA STREAM STOP ===")
                       break

                               # Process Deepgram events
                   while events_queue:
                       dg_msg = events_queue.pop(0)
                       logger.debug(f"Processing Deepgram message: {dg_msg}")
                       channel_texts, is_final = _extract_channel_texts_and_final(dg_msg)
                       if not channel_texts or not call_sid:
                           logger.debug(f"Skipping Deepgram message - no channel_texts or call_sid")
                           continue

                       line = " ".join([f"[ch{ch}] {txt}" for ch, txt in channel_texts if txt]).strip()
                       if not line:
                           logger.debug(f"Skipping Deepgram message - empty line")
                           continue

                                       if is_final:
                           logger.info(f"=== FINAL TRANSCRIPT ===")
                           logger.info(f"CallSid: {call_sid}")
                           logger.info(f"Text: {line}")
                           logger.info("=== END FINAL TRANSCRIPT ===")
                           
                           # Append to FINAL and clear PARTIAL
                           try:
                               current = (
                                   supabase.table("twilio_call")
                                   .select("live_transcript_final")
                                   .eq("call_sid", call_sid)
                                   .single()
                                   .execute()
                               )
                               existing_final = ""
                               if getattr(current, "data", None):
                                   existing_final = current.data.get("live_transcript_final") or ""

                               new_final = (existing_final + ("\n" if existing_final else "") + line).strip()
                               supabase.table("twilio_call").update({
                                   "live_transcript_final": new_final,
                                   "live_transcript_partial": ""
                               }).eq("call_sid", call_sid).execute()
                               logger.info(f"Successfully updated final transcript for {call_sid}")
                           except Exception as e:
                               logger.error(f"Failed to update final transcript: {e}")

                                       else:
                           logger.info(f"=== PARTIAL TRANSCRIPT ===")
                           logger.info(f"CallSid: {call_sid}")
                           logger.info(f"Text: {line}")
                           logger.info("=== END PARTIAL TRANSCRIPT ===")
                           
                           # Append to PARTIAL
                           try:
                               current = (
                                   supabase.table("twilio_call")
                                   .select("live_transcript_partial")
                                   .eq("call_sid", call_sid)
                                   .single()
                                   .execute()
                               )
                               existing_partial = ""
                               if getattr(current, "data", None):
                                   existing_partial = current.data.get("live_transcript_partial") or ""

                               new_partial = (existing_partial + ("\n" if existing_partial else "") + line).strip()
                               supabase.table("twilio_call").update({
                                   "live_transcript_partial": new_partial
                               }).eq("call_sid", call_sid).execute()
                               logger.info(f"Successfully updated partial transcript for {call_sid}")
                           except Exception as e:
                               logger.error(f"Failed to update partial transcript: {e}")

    finally:
        try:
            audio_queue.append(None)  # Signal to stop
            pump_thread.join(timeout=5)
        except Exception:
            pass
