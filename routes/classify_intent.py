# routes/classify_intent.py
import os, re, json, time, uuid as uuidlib
from typing import List, Dict, Any, Optional
from flask import Blueprint, request, jsonify
from supabase import create_client, Client
from openai import OpenAI
from config import Config

# --- Blueprint dedicated to this feature ---
classify_bp = Blueprint("classify_bp", __name__)

# --- Configuration ---
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
CLASSIFY_MODEL = os.getenv("CLASSIFY_MODEL", "anthropic/claude-3.5-sonnet")
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "openai/gpt-4o-mini")
TOP_K = int(os.getenv("TOP_K", "7"))

# --- Clients (lazy initialization) ---
_supabase_client = None
_emb_client = None
_or_client = None

def get_supabase_client() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_ROLE_KEY)
    return _supabase_client

def get_emb_client() -> OpenAI:
    global _emb_client
    if _emb_client is None:
        _emb_client = OpenAI(api_key=Config.OPENAI_API_KEY)
    return _emb_client

def get_or_client() -> OpenAI:
    global _or_client
    if _or_client is None:
        _or_client = OpenAI(api_key=Config.OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)
    return _or_client

# --- Helpers ---
ACK_REGEX = re.compile(
    r'^(?:y|yes|yeah|yep|yup|sure|okay|ok|affirmative|correct|that\'s right|no|nope|nah)\W*$',
    flags=re.I
)

def _normalize_convo_lines(conversation: str) -> list[tuple[str, str]]:
    if not conversation:
        return []
    lines = [l.strip() for l in conversation.splitlines() if l.strip()]
    out: list[tuple[str, str]] = []
    for l in lines:
        m = re.match(r"^(User|Caller|Customer|Agent|System)\s*[:\-]\s*(.*)$", l, flags=re.I)
        if m:
            role = m.group(1).lower()
            text = (m.group(2) or "").strip()
        else:
            role, text = "user", l
        out.append((role, text))
    return out

def _extract_user_context(conversation: str, max_lines: int = 50) -> str:
    """
    If transcript <= max_lines, return all lines.
    Else return first 15 + '...' + last (max_lines-15) lines.
    """
    if not conversation:
        return ""
    lines = [l.strip() for l in conversation.splitlines() if l.strip()]
    n = len(lines)
    if n <= max_lines:
        selected = lines
    else:
        head = lines[:15]
        tail = lines[-(max_lines - 15):]
        selected = head + ["… [context gap] …"] + tail
    return "\n".join(selected)

def _extract_embedding_query(conversation: str) -> str:
    """
    Returns the best text to embed for retrieval:
      - Prefer the last USER turn if it's substantive.
      - If the last USER turn is an acknowledgement (yes/no/ok) or too short,
        prepend the immediately preceding AGENT question/utterance.
      - Fallback gracefully to the last non-empty line.
    """
    parsed = _normalize_convo_lines(conversation)
    if not parsed:
        return ""

    # Find last user turn
    last_user_idx = None
    for i in range(len(parsed) - 1, -1, -1):
        if parsed[i][0] in ("user", "caller", "customer"):
            last_user_idx = i
            break

    if last_user_idx is None:
        # No explicit user role; embed the last line text
        return parsed[-1][1]

    last_user_text = parsed[last_user_idx][1]
    is_ack = bool(ACK_REGEX.match(last_user_text)) or len(last_user_text.split()) <= 2

    if not is_ack:
        # Substantive final user text — use it as-is
        return last_user_text

    # Ack: try to prepend the prior agent line to give meaning
    # (e.g., "Agent: Do you want to reschedule?" + "User: Yes")
    prev_agent_text = None
    for j in range(last_user_idx - 1, -1, -1):
        if parsed[j][0] == "agent":
            prev_agent_text = parsed[j][1]
            break

    if prev_agent_text:
        return f"Agent: {prev_agent_text}\nUser: {last_user_text}"

    # If no agent line found, try previous substantive user line
    for k in range(last_user_idx - 1, -1, -1):
        if parsed[k][0] in ("user", "caller", "customer"):
            prior_user = parsed[k][1]
            if prior_user and len(prior_user.split()) >= 3:
                return f"{prior_user}\n{last_user_text}"

    # Absolute fallback
    return last_user_text

def _redact_pii(s: str) -> str:
    if not s: return s
    s = re.sub(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[redacted-email]", s)
    s = re.sub(r"\b\+?\d[\d\s().-]{7,}\b", "[redacted-phone]", s)
    return s

def _detect_language_simple(s: str) -> str:
    return "en" if re.match(r"^[\x00-\x7F]*$", s or "") else "unknown"

def _json_string(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)

def _extract_retell_args(body: dict) -> Optional[dict]:
    """
    Expecting Retell payload:
      body.call.transcript (string)
      body.call.retell_llm_dynamic_variables.client_id (uuid text)
      body.call.call_id (string)
      body.call.telephony_identifier.twilio_call_sid (string, optional)
    Returns dict: {client_id, conversation, retell_event_id, call_id, caller_language}
    """
    call = body.get("call") or {}
    transcript = call.get("transcript") or ""
    dyn = call.get("retell_llm_dynamic_variables") or {}
    client_id = (dyn.get("client_id") or "").strip()

    # Prefer Retell's call_id; also capture Twilio SID for logging/trace
    call_id = (call.get("call_id") or "").strip()
    twilio_sid = ((call.get("telephony_identifier") or {}).get("twilio_call_sid") or "").strip()
    if not call_id and twilio_sid:
        call_id = f"TWILIO:{twilio_sid}"

    # A lightweight 'event id' if you want uniqueness in your logs
    retell_event_id = call_id or f"evt:{uuidlib.uuid4()}"

    if not transcript or not client_id:
        return None

    return {
        "client_id": client_id,
        "conversation": transcript,
        "retell_event_id": retell_event_id,
        "call_id": call_id,
        "caller_language": None  # Retell doesn't send this; language detection will handle it
    }

def translate_to_english(text: str) -> tuple[str, int]:
    if not text: return "", 0
    t0 = time.time()
    resp = get_or_client().chat.completions.create(
        model=TRANSLATE_MODEL,
        messages=[
            {"role": "system", "content": "Translate to neutral English. Return only the translation."},
            {"role": "user", "content": text}
        ]
    )
    latency_ms = int((time.time() - t0) * 1000)
    out = (resp.choices[0].message.content or "").strip() or text
    return out, latency_ms

def embed_english(text: str) -> tuple[list[float], int, str]:
    t0 = time.time()
    resp = get_emb_client().embeddings.create(model="text-embedding-3-small", input=text)
    latency_ms = int((time.time() - t0) * 1000)
    return resp.data[0].embedding, latency_ms, "text-embedding-3-small"

def match_topk(client_id: str, vec: list[float], k: int) -> list[dict]:
    r = get_supabase_client().rpc("match_intents", {"client_row_id": client_id, "query_embedding": vec, "match_count": k}).execute()
    if hasattr(r, 'error') and r.error: 
        raise RuntimeError(r.error.message)
    return r.data or []

def load_intents(intent_ids: list[str]) -> list[dict]:
    if not intent_ids: return []
    r = get_supabase_client().table("intent").select(
        "id,name,description,category_id,action_policy_override,transfer_number_override,priority,routing_target"
    ).in_("id", intent_ids).execute()
    if hasattr(r, 'error') and r.error: 
        raise RuntimeError(r.error.message)
    return r.data or []

def load_category(category_id: Optional[str]) -> Optional[dict]:
    if not category_id: return None
    r = get_supabase_client().table("intent_category").select(
        "id,name,default_action_policy,transfer_number,priority"
    ).eq("id", category_id).single().execute()
    return None if (hasattr(r, "error") and r.error) else r.data

def get_curated_clarifier(a: str, b: str) -> Optional[str]:
    cond = f"and(intent_id_a.eq.{a},intent_id_b.eq.{b}),and(intent_id_a.eq.{b},intent_id_b.eq.{a})"
    r = get_supabase_client().table("intent_clarifier").select("question,intent_id_a,intent_id_b").or_(cond).maybe_single().execute()
    if hasattr(r, "error") and r.error:
        return None
    if r is None or not hasattr(r, "data"):
        return None
    return (r.data or {}).get("question")

def classify_with_openrouter(utter_en: str, candidates: list[dict], target_language: Optional[str]) -> dict:
    schema = {
        "name": "intent_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "best_intent_id": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "needs_clarification": {"type": "boolean"},
                "clarify_question": {"type": "string", "default": ""},
                "alternatives": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "intent_id": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                        },
                        "required": ["intent_id", "confidence"]
                    },
                    "default": []
                }
            },
            "required": ["best_intent_id", "confidence", "needs_clarification", "clarify_question", "alternatives"]
        }
    }
    cand_list = "\n".join([f"- [{c['id']}] {c['name']}: {c.get('description','')}".strip() for c in candidates])
    t0 = time.time()
    
    try:
        resp = get_or_client().chat.completions.create(
            model=CLASSIFY_MODEL,
            messages=[
                {"role": "system", "content": "You are a call intent classifier. Choose exactly one best intent from the candidate list. If uncertain, set needs_clarification=true and output ONE short question." + (f" If a question is needed, write it in {target_language}." if target_language and target_language != 'en' else "")},
                {"role": "user", "content": f'Caller (EN): "{utter_en}"\n\nCandidate intents:\n{cand_list}'}
            ],
            response_format={"type": "json_schema", "json_schema": schema}
        )
        latency_ms = int((time.time() - t0) * 1000)
        content = (resp.choices[0].message.content or "{}").strip()
        
        # Debug logging
        print(f"OpenRouter response content: '{content}'")
        print(f"OpenRouter response length: {len(content)}")
        
        if not content or content.strip() == "":
            raise ValueError("Empty response from OpenRouter API")
        
        # Try to extract just the JSON part if there's extra text
        explanation = ""
        try:
            # First try to parse as-is
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # If that fails, try to find the JSON object in the response
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                parsed = json.loads(json_str)
                
                # Extract explanation from the remaining text
                remaining_text = content[json_match.end():].strip()
                if remaining_text:
                    # Look for explanation patterns
                    explanation_match = re.search(r'explanation[:\s]*["\']?([^"\']+)["\']?', remaining_text, re.IGNORECASE)
                    if explanation_match:
                        explanation = explanation_match.group(1).strip()
                    else:
                        # If no specific explanation pattern, take the first sentence
                        explanation = remaining_text.split('.')[0].strip()
            else:
                raise ValueError("Could not extract valid JSON from response")
        
        # Map the response to our expected format
        result = {
            "best_intent_id": parsed.get("intent") or parsed.get("best_intent_id") or "",
            "confidence": parsed.get("confidence", 0.5),
            "needs_clarification": parsed.get("needs_clarification", False),
            "clarify_question": parsed.get("clarifying_question") or parsed.get("clarify_question") or "",
            "alternatives": parsed.get("alternatives", []),
            "explanation": explanation,  # Add the explanation
            "latency_ms": latency_ms,
            "model": CLASSIFY_MODEL,
            "request_id": getattr(resp, "id", None),
            "prompt_tokens": getattr(getattr(resp, "usage", None), "prompt_tokens", None),
            "completion_tokens": getattr(getattr(resp, "usage", None), "completion_tokens", None)
        }
        
        return result
        
    except Exception as e:
        print(f"Error in classify_with_openrouter: {e}")
        print(f"OpenRouter API Key set: {bool(Config.OPENROUTER_API_KEY)}")
        print(f"OpenRouter Base URL: {OPENROUTER_BASE_URL}")
        print(f"Classify Model: {CLASSIFY_MODEL}")
        
        # Return a fallback response
        return {
            "best_intent_id": candidates[0]["id"] if candidates else "",
            "confidence": 0.5,
            "needs_clarification": True,
            "clarify_question": "I'm having trouble understanding. Could you please repeat that?",
            "alternatives": [],
            "latency_ms": int((time.time() - t0) * 1000),
            "model": CLASSIFY_MODEL,
            "request_id": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "error": str(e)
        }

def effective_policy(intent_row: dict, category_row: Optional[dict]) -> dict:
    action = intent_row.get("action_policy_override") or (category_row or {}).get("default_action_policy") or "ask_urgency_then_collect"
    number = intent_row.get("transfer_number_override") or (category_row or {}).get("transfer_number")
    category_name = (category_row or {}).get("name") or intent_row.get("routing_target")
    return {"action_policy": action, "transfer_number": number, "category_name": category_name}

def _resolve_call_id(call_id: Optional[str], retell_event_id: Optional[str]) -> str:
    if call_id: return call_id.strip()
    ev = (retell_event_id or "").strip()
    return f"RETELL:{ev}" if ev else f"auto:{uuidlib.uuid4()}"

# --- Language normalization helpers ---
DG_LANG_MAP = {
    # english
    "en": "en", "en-us": "en", "en-gb": "en", "en-au": "en",
    # dutch
    "nl": "nl", "nl-be": "nl",  # <-- explicit support for nl-BE
    # common EU langs
    "fr": "fr", "fr-be": "fr", "de": "de", "es": "es", "it": "it",
    # nordics
    "sv": "sv", "da": "da", "no": "no", "fi": "fi",
    # others you already see
    "pt": "pt", "pt-br": "pt", "pl": "pl", "cs": "cs", "sk": "sk",
    "ro": "ro", "hu": "hu", "tr": "tr", "el": "el",
    "ru": "ru", "uk": "uk",
    "ar": "ar", "he": "he", "fa": "fa",
    "hi": "hi", "vi": "vi", "th": "th", "id": "id", "ms": "ms",
    "ja": "ja", "ko": "ko",
    "zh": "zh", "zh-cn": "zh", "zh-hk": "zh", "zh-tw": "zh"
}

def normalize_target_language(caller_lang: Optional[str]) -> Optional[str]:
    """
    Convert Deepgram language codes (e.g., 'nl-BE') to a simple target
    language for clarifying questions. Returns None for English.
    Case-insensitive; falls back to base before hyphen.
    """
    if not caller_lang:
        return None
    c = caller_lang.strip().lower()
    mapped = DG_LANG_MAP.get(c)
    if mapped is None:
        base = c.split("-")[0]
        mapped = DG_LANG_MAP.get(base, base)
    return None if mapped == "en" else mapped

# --- Route: POST /classify-intent (Retell tool format) ---
@classify_bp.route("/classify-intent", methods=["POST"])
def classify_intent():
    """
    Input JSON (Retell):
    {
      "call": {
        "transcript": "The conversation history content",
        "call_id": "call_abc123",
        "retell_llm_dynamic_variables": {
          "client_id": "uuid"
        },
        "telephony_identifier": {
          "twilio_call_sid": "CAxxxxxxxx"  // optional
        }
      }
    }

    Output JSON:
    {
      "call_id": "call_abc123",
      "intent_id": "intent_456",
      "intent_name": "Reschedule Appointment",
      "confidence": 0.85,
      "needs_clarification": false,
      "clarify_question": "",
      "action_policy": "ask_urgency_then_collect",
      "transfer_number": "+1234567890",
      "category_name": "Appointments",
      "telemetry": {
        "embedding_top1_sim": 0.92,
        "topK": [...]
      }
    }
    """
    body = request.get_json(silent=True) or {}
    args = _extract_retell_args(body)
    if not args:
        return jsonify({"error": "Missing required fields: call.transcript and client_id"}), 400

    client_id        = args["client_id"]
    conversation     = args["conversation"]
    retell_event_id  = args["retell_event_id"]
    provided_call_id = args.get("call_id") or ""
    caller_language  = args.get("caller_language") or ""

    # 1) Build context + embedding query
    context_text = _extract_user_context(conversation, max_lines=50)   # for LLM classification
    embed_query  = _extract_embedding_query(conversation)              # for vector search

    if not context_text and not embed_query:
        return jsonify({"error": "Conversation missing user content"}), 400

    # 2) Decide language based on whichever string is available (prefer embed_query)
    sample_for_lang = (embed_query or context_text or "")
    if caller_language:
        c_low = caller_language.lower()
        is_english = (c_low == "en") or c_low.startswith("en-")
    else:
        detected_lang = _detect_language_simple(sample_for_lang)
        caller_language = detected_lang
        is_english = detected_lang == "en"

    # Translate ONLY when not English
    if is_english:
        ctx_en   = context_text
        query_en = embed_query
        _translate_ms = 0
    else:
        ctx_en, t1 = translate_to_english(context_text)
        query_en, t2 = translate_to_english(embed_query)
        _translate_ms = max(t1, t2)  # keep one latency figure if you log it

    # Language for clarifying question
    target_lang = normalize_target_language(caller_language)

    # 3) Embed + shortlist (use sharp query text)
    if not (query_en or ctx_en):
        return jsonify({"error": "No usable text to embed/classify"}), 400
        
    vec, embed_ms, emb_model = embed_english(query_en or ctx_en or "")
    top = match_topk(client_id, vec, TOP_K)  # [{intent_id, similarity}]
    intent_ids = [t["intent_id"] for t in top]
    intents = load_intents(intent_ids)
    candidates = [{"id": i["id"], "name": i["name"], "description": i.get("description","")}
                  for t in top for i in intents if i["id"] == t["intent_id"]]

    # 4) Classify (use richer context)
    cls = classify_with_openrouter(ctx_en or query_en or "", candidates, target_lang)

    # Clarifier override (if curated)
    clarify_q = cls.get("clarify_question") or ""
    if cls.get("needs_clarification") and len(candidates) >= 2:
        a = cls.get("best_intent_id") or candidates[0]["id"]
        b = next((c["id"] for c in candidates if c["id"] != a), None)
        if b:
            curated = get_curated_clarifier(a, b)
            if curated: clarify_q = curated

    # 5) Effective routing
    best_id = cls.get("best_intent_id") or (candidates[0]["id"] if candidates else None)
    best_row = next((i for i in intents if i["id"] == best_id), intents[0] if intents else None)
    category = load_category(best_row.get("category_id") if best_row else None)
    routing = effective_policy(best_row or {}, category)
    
    needs = bool(cls.get("needs_clarification"))
    if needs:
        routing = None  # Hide routing until intent is clarified

    # 6) Log (rich but safe)
    call_id = _resolve_call_id(provided_call_id, retell_event_id)
    try:
        get_supabase_client().table("call_reason_log").insert({
            "client_id": client_id,
            "call_id": call_id,
            "primary_intent_id": (best_row or {}).get("id"),
            "confidence": cls.get("confidence"),
            "embedding_top1_sim": (top[0]["similarity"] if top else None),
            "alternatives": (cls.get("alternatives") or [])[:3],
            "clarifications_json": [{"asked": bool(clarify_q)}] if cls.get("needs_clarification") else [],
            "llm_model": cls.get("model"),
            "embedding_model": emb_model,
            "llm_latency_ms": cls.get("latency_ms"),
            "embed_latency_ms": embed_ms,
            "openrouter_request_id": cls.get("request_id"),
            "prompt_tokens": cls.get("prompt_tokens"),
            "completion_tokens": cls.get("completion_tokens"),
            "router_version": "v1",
            "utterance": _redact_pii(context_text),
            "detected_lang": (caller_language.lower() or None),
            "utterance_en": _redact_pii(ctx_en),
            "explanation": cls.get("explanation", "")  # Add the AI explanation
        }).execute()
    except Exception:
        pass

    # 7) Build result (must be STRING)
    result_obj = {
        "call_id": call_id,
        "intent_id": (best_row or {}).get("id"),
        "intent_name": (best_row or {}).get("name"),
        "confidence": cls.get("confidence"),
        "needs_clarification": needs,
        "clarify_question": clarify_q if needs else "",
        "telemetry": {
            "embedding_top1_sim": (top[0]["similarity"] if top else None),
            "topK": [{"rank": i+1, "intent_id": t["intent_id"], "sim": t["similarity"]} for i, t in enumerate(top)]
        }
    }
    
    # Add routing fields at top level (if not needs clarification)
    if routing and not needs:
        result_obj.update({
            "action_policy": routing.get("action_policy"),
            "transfer_number": routing.get("transfer_number"),
            "category_name": routing.get("category_name")
        })
    return jsonify(result_obj)
