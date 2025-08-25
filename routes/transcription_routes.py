"""
Twilio Media Streams (2 legs, 2 WS) -> 2x Deepgram -> append into same Supabase fields
- Each WS handles ONE leg (inbound OR outbound) as μ-law 8k mono
- Writes:
    partial  -> append to live_transcript_partial
    final    -> append to live_transcript_final, then clear partial
"""
import base64
import threading
import asyncio
import orjson
from typing import Dict, Any, Optional
from urllib.parse import urlparse, parse_qs

from flask import Blueprint, request
from flask_sock import Sock
import websocket  # websocket-client

from config import Config
from utils.logger import get_logger
from supabase import create_client, Client

logger = get_logger(__name__)

transcription_bp = Blueprint("transcription", __name__, url_prefix="")
sock = Sock()  # call sock.init_app(app) in your app factory

DG_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=mulaw&sample_rate=8000&channels=1&multichannel=false"
    "&punctuate=true&smart_format=true&endpointing=300&utterances=true"
)

def supa() -> Client:
    return create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_ROLE_KEY)

def role_from_track(track: Optional[str]) -> str:
    # Map Twilio tracks to friendly labels
    # inbound  -> user (caller)
    # outbound -> agent (dialed party / Retell)
    return "agent" if track == "outbound" else "user"

def extract_channel_texts_and_final(dg_msg: Dict[str, Any]):
    """
    Tolerant parser for Deepgram transcript events.
    Returns (text: str | None, is_final: bool)
    """
    is_final = bool(dg_msg.get("is_final", False))
    text = None

    # Common forms
    if "channel" in dg_msg and isinstance(dg_msg["channel"], dict):
        alts = dg_msg["channel"].get("alternatives") or []
        if alts and isinstance(alts[0], dict):
            text = (alts[0].get("transcript") or "").strip()

    elif "results" in dg_msg and isinstance(dg_msg["results"], dict):
        # Single-channel stream; might still be under results
        channels = dg_msg["results"].get("channels") or []
        if channels:
            alts = channels[0].get("alternatives") or []
            if alts and isinstance(alts[0], dict):
                text = (alts[0].get("transcript") or "").strip()
        else:
            # Some payloads: results.alternatives
            alts = dg_msg["results"].get("alternatives") or []
            if alts and isinstance(alts[0], dict):
                text = (alts[0].get("transcript") or "").strip()

    elif isinstance(dg_msg.get("transcript"), str):
        text = dg_msg["transcript"].strip()

    if text:
        text = " ".join(text.split())  # normalize whitespace
    return text, is_final


@sock.route("/transcription/stream")
def transcription_stream(ws):
    """
    Each connection = one leg (inbound or outbound).
    We forward μ-law 8k mono to one Deepgram stream and append both legs into the same DB fields.
    """
    logger.info("=== TRANSCRIPTION WS: connection started ===")

    # Track hint from URL query (optional)
    try:
        q = parse_qs(urlparse(request.url).query)
        url_track_hint = (q.get("track", [None])[0]) or None
    except Exception:
        url_track_hint = None

    # State
    _supa = supa()
    call_sid: Optional[str] = None
    current_track: Optional[str] = url_track_hint  # 'inbound' / 'outbound' or None

    # Queues
    audio_queue = []
    events_queue = []
    
    # Throttling for partial updates (avoid spam)
    last_partial_update = 0
    PARTIAL_THROTTLE_MS = 500  # Only update partial every 500ms

    # Deepgram WS
    headers = [f"Authorization: Token {Config.DEEPGRAM_API_KEY}"]
    ws_open = threading.Event()

    def on_message(dgws, message):
        try:
            data = orjson.loads(message)
            events_queue.append(data)
        except Exception as e:
            logger.error(f"DG message parse error: {e}")

    def on_error(dgws, error):
        logger.error(f"Deepgram WS error: {error}")

    def on_close(dgws, code, msg):
        logger.info(f"Deepgram WS closed: code={code}, msg={msg}")

    def on_open(dgws):
        logger.info("Deepgram WS opened")
        ws_open.set()

    dg_ws = websocket.WebSocketApp(
        DG_URL,
        header=headers,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    def sender():
        logger.info("Audio sender thread started; waiting for DG open...")
        if not ws_open.wait(timeout=8):
            logger.error("Deepgram WS did not open within 8s; stopping sender")
            return

        # Buffer ~200ms of μ-law 8k (160 bytes per 20 ms -> 200 ms = 1600 bytes)
        BYTES_PER_20MS = 160
        TARGET_MS = 200
        PACKET_BYTES = (TARGET_MS // 20) * BYTES_PER_20MS
        buf = bytearray()
        sent_packets = 0

        while True:
            if audio_queue:
                chunk = audio_queue.pop(0)
                if chunk is None:
                    # flush leftover
                    if buf:
                        try:
                            dg_ws.send(bytes(buf), websocket.ABNF.OPCODE_BINARY)
                        except Exception as e:
                            logger.error(f"Flush send error: {e}")
                        buf.clear()
                    logger.info(f"Sender exit. Packets sent: {sent_packets}")
                    break
                try:
                    buf.extend(chunk)
                    if len(buf) >= PACKET_BYTES:
                        dg_ws.send(bytes(buf), websocket.ABNF.OPCODE_BINARY)
                        sent_packets += 1
                        buf.clear()
                except Exception as e:
                    logger.error(f"Send error: {e}")
                    break
            else:
                import time
                time.sleep(0.005)

    sender_thread = threading.Thread(target=sender, daemon=True)
    sender_thread.start()

    runner_thread = threading.Thread(target=lambda: dg_ws.run_forever(ping_interval=20, ping_timeout=20), daemon=True)
    runner_thread.start()

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
            if etype == "connected":
                # Twilio sends a 'connected' control frame
                continue

            if etype == "start":
                s = evt.get("start", {})
                call_sid = s.get("callSid")
                mf = s.get("mediaFormat", {})
                tracks = s.get("tracks") or []
                # If Twilio tells us the track list, keep it for logs
                logger.info(f"Start: callSid={call_sid}, tracks={tracks}, mediaFormat={mf}")

                # Trust Twilio 'media.track' per-media; fall back to URL hint for labeling
                # Ensure the DB row exists
                if call_sid:
                    _supa.table("twilio_call").upsert({
                        "call_sid": call_sid,
                        "live_transcript_partial": "",
                        "live_transcript_final": ""
                    }).execute()

            elif etype == "media":
                track = evt.get("media", {}).get("track")  # 'inbound' or 'outbound'
                if track:
                    current_track = track  # remember last-seen track for labels
                payload_b64 = evt.get("media", {}).get("payload")
                if payload_b64:
                    try:
                        audio_bytes = base64.b64decode(payload_b64)
                        audio_queue.append(audio_bytes)
                    except Exception as e:
                        logger.error(f"b64 decode error: {e}")

            elif etype == "stop":
                logger.info(f"Stop for CallSid={call_sid}")
                break

            # Drain Deepgram events
            while events_queue:
                dg_msg = events_queue.pop(0)
                text, is_final = extract_channel_texts_and_final(dg_msg)
                if not text or not call_sid:
                    continue

                who = role_from_track(current_track)  # 'user' or 'agent'
                line = f"[{who}] {text}".strip()

                if is_final:
                    # Append to FINAL and clear PARTIAL
                    try:
                        sel = _supa.table("twilio_call")\
                            .select("live_transcript_final")\
                            .eq("call_sid", call_sid).single().execute()
                        existing = ""
                        if getattr(sel, "data", None):
                            existing = sel.data.get("live_transcript_final") or ""
                        new_final = (existing + ("\n" if existing else "") + line).strip()
                        _supa.table("twilio_call").update({
                            "live_transcript_final": new_final,
                            "live_transcript_partial": ""
                        }).eq("call_sid", call_sid).execute()
                    except Exception as e:
                        logger.error(f"FINAL update error: {e}")
                else:
                    # Append to PARTIAL (with throttling)
                    import time
                    current_time = time.time() * 1000  # Convert to milliseconds
                    if current_time - last_partial_update >= PARTIAL_THROTTLE_MS:
                        try:
                            sel = _supa.table("twilio_call")\
                                .select("live_transcript_partial")\
                                .eq("call_sid", call_sid).single().execute()
                            existing = ""
                            if getattr(sel, "data", None):
                                existing = sel.data.get("live_transcript_partial") or ""
                            new_partial = (existing + ("\n" if existing else "") + line).strip()
                            _supa.table("twilio_call").update({
                                "live_transcript_partial": new_partial
                            }).eq("call_sid", call_sid).execute()
                            last_partial_update = current_time
                        except Exception as e:
                            logger.error(f"PARTIAL update error: {e}")

    finally:
        try:
            audio_queue.append(None)
        except Exception:
            pass
        try:
            # politely tell DG we're done
            dg_ws.close()
        except Exception:
            pass
