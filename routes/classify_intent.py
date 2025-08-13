# routes/classify_intent.py
import os, re, json, time, uuid as uuidlib
from typing import List, Dict, Any, Optional
from flask import Blueprint, request, jsonify
from supabase import create_client, Client
from openai import OpenAI

# --- Blueprint dedicated to this feature ---
classify_bp = Blueprint("classify_bp", __name__)

# --- Env (expects you already have these set) ---
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]               # embeddings
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]       # translate + classify
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
CLASSIFY_MODEL = os.getenv("CLASSIFY_MODEL", "anthropic/claude-3.5-sonnet")
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "openai/gpt-4o-mini")
TOP_K = int(os.getenv("TOP_K", "7"))

# --- Clients ---
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
emb_client = OpenAI(api_key=OPENAI_API_KEY)                                   # OpenAI embeddings
or_client = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)  # OpenRouter (OpenAI-compatible)

# --- Helpers ---
def _extract_last_user_text(conversation: str) -> str:
    if not conversation: return ""
    lines = [l.strip() for l in conversation.splitlines() if l.strip()]
    if not lines: return ""
    last = lines[-1]
    return re.sub(r"^(User|Caller|Customer|Agent|System)\s*[:\-]\s*", "", last, flags=re.I)

def _redact_pii(s: str) -> str:
    if not s: return s
    s = re.sub(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[redacted-email]", s)
    s = re.sub(r"\b\+?\d[\d\s().-]{7,}\b", "[redacted-phone]", s)
    return s

def _detect_language_simple(s: str) -> str:
    return "en" if re.match(r"^[\x00-\x7F]*$", s or "") else "unknown"

def _json_string(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)

def translate_to_english(text: str) -> tuple[str, int]:
    if not text: return "", 0
    t0 = time.time()
    resp = or_client.chat.completions.create(
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
    resp = emb_client.embeddings.create(model="text-embedding-3-small", input=text)
    latency_ms = int((time.time() - t0) * 1000)
    return resp.data[0].embedding, latency_ms, "text-embedding-3-small"

def match_topk(client_id: str, vec: list[float], k: int) -> list[dict]:
    r = supabase.rpc("match_intents", {"client_row_id": client_id, "query_embedding": vec, "match_count": k}).execute()
    if r.error: raise RuntimeError(r.error.message)
    return r.data or []

def load_intents(intent_ids: list[str]) -> list[dict]:
    if not intent_ids: return []
    r = supabase.table("intent").select(
        "id,name,description,category_id,action_policy_override,transfer_number_override,priority,routing_target"
    ).in_("id", intent_ids).execute()
    if r.error: raise RuntimeError(r.error.message)
    return r.data or []

def load_category(category_id: Optional[str]) -> Optional[dict]:
    if not category_id: return None
    r = supabase.table("intent_category").select(
        "id,name,default_action_policy,transfer_number,priority"
    ).eq("id", category_id).single().execute()
    return None if getattr(r, "error", None) else r.data

def get_curated_clarifier(a: str, b: str) -> Optional[str]:
    cond = f"and(intent_id_a.eq.{a},intent_id_b.eq.{b}),and(intent_id_a.eq.{b},intent_id_b.eq.{a})"
    r = supabase.table("intent_clarifier").select("question,intent_id_a,intent_id_b").or_(cond).maybe_single().execute()
    return None if getattr(r, "error", None) else (r.data or {}).get("question")

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
    resp = or_client.chat.completions.create(
        model=CLASSIFY_MODEL,
        messages=[
            {"role": "system", "content": "You are a call intent classifier. Choose exactly one best intent from the candidate list. If uncertain, set needs_clarification=true and output ONE short question." + (f" If a question is needed, write it in {target_language}." if target_language and target_language != 'en' else "")},
            {"role": "user", "content": f'Caller (EN): "{utter_en}"\n\nCandidate intents:\n{cand_list}'}
        ],
        response_format={"type": "json_schema", "json_schema": schema}
    )
    latency_ms = int((time.time() - t0) * 1000)
    content = (resp.choices[0].message.content or "{}").strip()
    parsed = json.loads(content)
    parsed["latency_ms"] = latency_ms
    parsed["model"] = CLASSIFY_MODEL
    parsed["request_id"] = getattr(resp, "id", None)
    usage = getattr(resp, "usage", None) or {}
    parsed["prompt_tokens"] = getattr(usage, "prompt_tokens", None) or usage.get("prompt_tokens")
    parsed["completion_tokens"] = getattr(usage, "completion_tokens", None) or usage.get("completion_tokens")
    return parsed

def effective_policy(intent_row: dict, category_row: Optional[dict]) -> dict:
    action = intent_row.get("action_policy_override") or (category_row or {}).get("default_action_policy") or "ask_urgency_then_collect"
    number = intent_row.get("transfer_number_override") or (category_row or {}).get("transfer_number")
    category_name = (category_row or {}).get("name") or intent_row.get("routing_target")
    return {"action_policy": action, "transfer_number": number, "category_name": category_name}

def _resolve_call_id(call_id: Optional[str], vapi_webhook_event_id: Optional[str]) -> str:
    if call_id: return call_id.strip()
    ev = (vapi_webhook_event_id or "").strip()
    return f"VAPI:{ev}" if ev else f"auto:{uuidlib.uuid4()}"

# --- Language normalization helpers ---
DG_LANG_MAP = {
    "en": "en", "en-US": "en", "en-GB": "en",
    "nl": "nl", "fr": "fr", "de": "de", "es": "es", "it": "it",
    "pt": "pt", "pt-BR": "pt",
    "sv": "sv", "da": "da", "no": "no", "fi": "fi",
    "pl": "pl", "ro": "ro", "cs": "cs", "sk": "sk", "sl": "sl", "hu": "hu",
    "el": "el", "tr": "tr", "ru": "ru", "uk": "uk",
    "ar": "ar", "he": "he", "fa": "fa",
    "hi": "hi", "th": "th", "vi": "vi", "id": "id", "ms": "ms",
    "ja": "ja", "ko": "ko",
    "zh": "zh", "zh-CN": "zh", "zh-HK": "zh", "zh-TW": "zh"
}

def normalize_target_language(caller_lang: Optional[str]) -> Optional[str]:
    """
    Convert Deepgram language codes to a language tag for clarifying questions.
    Return None for English so the model writes the question in English (or not at all).
    """
    if not caller_lang:
        return None
    c = caller_lang.strip()
    if not c:
        return None
    # direct map first
    mapped = DG_LANG_MAP.get(c)
    if mapped is None:
        # fallback: take base before hyphen (e.g., 'en-AU' -> 'en')
        base = c.split("-")[0].lower()
        mapped = DG_LANG_MAP.get(base, base)
    # if English, return None (we don't need a non-English question)
    return None if mapped == "en" else mapped

# --- Route: POST /classify-intent (Vapi tool format) ---
@classify_bp.route("/classify-intent", methods=["POST"])
def classify_intent():
    """
    Input JSON (Vapi):
    {
      "message": {
        "toolCallList": [
          {
            "id": "toolu_01...MF",          // echo this back as toolCallId
            "name": "your_function_name",
            "arguments": {
              "client_id": "uuid",
              "conversation": "The conversation history content",
              "vapi_webhook_event_id": "webhook_event_id",
              "call_id": "CAxxxxxxxx",            // optional but preferred
              "caller_language": "nl"              // Deepgram code (e.g., en, en-US, nl, fr, de, es, pt-BR, ja, ko, zh, zh-TW)
            }
          }
        ]
      }
    }

    Output JSON:
    {
      "results": [
        { "toolCallId": "<same id>", "result": "<JSON string>" }
      ]
    }
    """
    body = request.get_json(silent=True) or {}
    message = body.get("message") or {}
    tool_calls: List[Dict[str, Any]] = message.get("toolCallList") or []

    results: List[Dict[str, Any]] = []

    if not tool_calls:
        results.append({"toolCallId": "call_id", "result": "No toolCallList in payload"})
        return jsonify({"results": results}), 400

    for tc in tool_calls:
        tool_id = (tc.get("id") or "").strip() or "call_id"
        args = tc.get("arguments") or {}

        client_id = (args.get("client_id") or "").strip()
        conversation = (args.get("conversation") or "").strip()
        vapi_event_id = (args.get("vapi_webhook_event_id") or "").strip()
        provided_call_id = (args.get("call_id") or "").strip()
        caller_language = (args.get("caller_language") or "").strip()  # Deepgram language code if provided

        # Validate
        missing = [k for k in ["client_id", "conversation", "vapi_webhook_event_id"] if not args.get(k)]
        if missing:
            results.append({"toolCallId": tool_id, "result": f"Missing required fields: {', '.join(missing)}"})
            continue

        # 1) Last user text
        user_text = _extract_last_user_text(conversation)
        if not user_text:
            results.append({"toolCallId": tool_id, "result": "Conversation missing user content"})
            continue

        # 2) Decide language & translate only if not English
        # Prefer explicit caller_language from Vapi (Deepgram); fallback to simple heuristic if missing.
        is_english = False
        if caller_language:
            is_english = caller_language == "en" or caller_language.startswith("en-")
        else:
            # fallback heuristic only if caller_language not provided
            detected_lang = _detect_language_simple(user_text)
            caller_language = detected_lang  # store something for logging
            is_english = detected_lang == "en"

        if is_english:
            utter_en, _translate_ms = user_text, 0
        else:
            utter_en, _translate_ms = translate_to_english(user_text)

        # Language to use for clarifying question (None = English)
        target_lang = normalize_target_language(caller_language)

        # 3) Embed + shortlist
        vec, embed_ms, emb_model = embed_english(utter_en)
        top = match_topk(client_id, vec, TOP_K)  # [{intent_id, similarity}]
        intent_ids = [t["intent_id"] for t in top]
        intents = load_intents(intent_ids)
        candidates = [{"id": i["id"], "name": i["name"], "description": i.get("description","")}
                      for t in top for i in intents if i["id"] == t["intent_id"]]

        # 4) Classify (JSON schema)
        cls = classify_with_openrouter(utter_en, candidates, target_lang)

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

        # 6) Log (rich but safe)
        call_id = _resolve_call_id(provided_call_id, vapi_event_id)
        try:
            supabase.table("call_reason_log").insert({
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
                "utterance": _redact_pii(user_text),
                "detected_lang": caller_language or None,
                "utterance_en": _redact_pii(utter_en)
            }).execute()
        except Exception:
            pass

        # 7) Build result (must be STRING)
        result_obj = {
            "call_id": call_id,
            "intent_id": (best_row or {}).get("id"),
            "intent_name": (best_row or {}).get("name"),
            "confidence": cls.get("confidence"),
            "needs_clarification": bool(cls.get("needs_clarification")),
            "clarify_question": clarify_q if cls.get("needs_clarification") else "",
            "routing": routing,
            "telemetry": {
                "embedding_top1_sim": (top[0]["similarity"] if top else None),
                "topK": [{"rank": i+1, "intent_id": t["intent_id"], "sim": t["similarity"]} for i, t in enumerate(top)]
            }
        }
        results.append({"toolCallId": tool_id, "result": _json_string(result_obj)})

    return jsonify({"results": results})
