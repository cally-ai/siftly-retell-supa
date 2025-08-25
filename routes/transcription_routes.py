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
                logger.info(f"=== DEEPGRAM MESSAGE RECEIVED ===")
                logger.info(f"Message type: {type(data)}")
                logger.info(f"Message keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                logger.info(f"Full message: {data}")
                logger.info("=== END DEEPGRAM MESSAGE ===")
            except Exception as e:
                logger.error(f"=== DEEPGRAM MESSAGE ERROR ===")
                logger.error(f"Error parsing Deepgram message: {e}")
                logger.error(f"Raw message: {message}")
                logger.error("=== END DEEPGRAM MESSAGE ERROR ===")
        
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
            chunk_count = 0
            while True:
                if audio_queue:
                    chunk = audio_queue.pop(0)
                    if chunk is None:
                        logger.info(f"=== AUDIO SENDER STOPPING ===")
                        logger.info(f"Total chunks sent to Deepgram: {chunk_count}")
                        logger.info("=== END AUDIO SENDER ===")
                        break
                    try:
                        dg_ws.send(chunk, websocket.ABNF.OPCODE_BINARY)
                        chunk_count += 1
                        if chunk_count % 100 == 0:  # Log every 100 chunks
                            logger.info(f"=== AUDIO SENDER PROGRESS ===")
                            logger.info(f"Chunks sent to Deepgram: {chunk_count}")
                            logger.info(f"Chunk size: {len(chunk)} bytes")
                            logger.info("=== END AUDIO SENDER PROGRESS ===")
                    except Exception as e:
                        logger.error(f"=== AUDIO SENDER ERROR ===")
                        logger.error(f"Error sending chunk to Deepgram: {e}")
                        logger.error(f"Chunk count: {chunk_count}")
                        logger.error("=== END AUDIO SENDER ERROR ===")
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
                media_stream_call_sid = evt.get("start", {}).get("callSid")
                logger.info(f"=== MEDIA STREAM START ===")
                logger.info(f"Media Stream CallSid: {media_stream_call_sid}")
                logger.info(f"Full start event: {evt}")
                logger.info("=== END MEDIA STREAM START ===")
                
                # For now, use the Media Stream CallSid and let the database operations fail gracefully
                # The real solution is to modify the call_started webhook to create a record with the Media Stream CallSid
                call_sid = media_stream_call_sid
                logger.info(f"Using Media Stream CallSid for transcription: {call_sid}")

            elif etype == "media":
                payload_b64 = evt.get("media", {}).get("payload")
                if payload_b64:
                    audio_bytes = base64.b64decode(payload_b64)
                    audio_queue.append(audio_bytes)
                    logger.info(f"=== AUDIO CHUNK RECEIVED ===")
                    logger.info(f"CallSid: {call_sid}")
                    logger.info(f"Audio chunk size: {len(audio_bytes)} bytes")
                    logger.info(f"Media event: {evt}")
                    logger.info("=== END AUDIO CHUNK ===")
                else:
                    logger.warning("Media event without payload")
                    logger.warning(f"Full media event: {evt}")

            elif etype == "stop":
                logger.info(f"=== MEDIA STREAM STOP ===")
                logger.info(f"CallSid: {call_sid}")
                logger.info(f"Full stop event: {evt}")
                logger.info("=== END MEDIA STREAM STOP ===")
                break
            else:
                logger.info(f"=== UNKNOWN EVENT TYPE ===")
                logger.info(f"Event type: {etype}")
                logger.info(f"Full event: {evt}")
                logger.info("=== END UNKNOWN EVENT ===")

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
