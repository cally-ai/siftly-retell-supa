"""
Typeform integration routes for dynamic form creation and webhook handling
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import os
import requests
import json
from typing import Dict, List, Any, Optional
from utils.logger import get_logger
from config import Config
from supabase import create_client

logger = get_logger(__name__)

# Create blueprint
typeform_bp = Blueprint('typeform', __name__, url_prefix='/typeform')

# Initialize Supabase client
def get_supabase_client():
    return create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_ROLE_KEY)

# Typeform API configuration
TYPEFORM_API_KEY = os.getenv('TYPEFORM_API_KEY')
TYPEFORM_WEBHOOK_URL = os.getenv('TYPEFORM_WEBHOOK_URL')
TYPEFORM_API_BASE_URL = "https://api.typeform.com"

def translate_text(text: str, target_language: str) -> str:
    """
    Translate text using OpenAI GPT-3.5-turbo
    """
    try:
        import openai
        openai.api_key = Config.OPENAI_API_KEY
        
        prompt = f"Translate this text to {target_language}. Only return the translated text, nothing else: {text}"
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.1
        )
        
        translated = response.choices[0].message.content.strip()
        logger.info(f"Translated '{text}' to '{translated}' ({target_language})")
        return translated
        
    except Exception as e:
        logger.error(f"Translation failed for '{text}' to {target_language}: {e}")
        return text  # Fallback to original text

def get_client_question_fields(client_id: str) -> List[Dict[str, Any]]:
    """
    Get client question fields ordered by order_number
    """
    try:
        supabase = get_supabase_client()
        
        # Get client question fields with standard field details
        response = supabase.table('client_question_fields').select(
            'order_number, standard_field_id'
        ).eq('client_id', client_id).order('order_number').execute()
        
        if not response.data:
            logger.warning(f"No question fields found for client_id: {client_id}")
            return []
        
        # Get standard field details for each question
        question_fields = []
        for field in response.data:
            standard_field_id = field['standard_field_id']
            
            # Get standard field details
            std_response = supabase.table('standard_question_fields').select('*').eq('id', standard_field_id).limit(1).execute()
            
            if std_response.data:
                standard_field = std_response.data[0]
                question_fields.append({
                    'order_number': field['order_number'],
                    'standard_field': standard_field
                })
        
        logger.info(f"Found {len(question_fields)} question fields for client_id: {client_id}")
        return question_fields
        
    except Exception as e:
        logger.error(f"Error getting client question fields: {e}")
        return []

def get_typeform_screen_data() -> Dict[str, Any]:
    """
    Get welcome and thank you screen data
    """
    try:
        supabase = get_supabase_client()
        
        response = supabase.table('typeform_screen_data').select('*').eq('id', 'b117a8ac-1724-44f2-bae5-e527895c17f0').limit(1).execute()
        
        if not response.data:
            logger.warning("No typeform screen data found")
            return {}
        
        return response.data[0]
        
    except Exception as e:
        logger.error(f"Error getting typeform screen data: {e}")
        return {}

def build_typeform_fields(question_fields: List[Dict[str, Any]], caller_language: str) -> List[Dict[str, Any]]:
    """
    Build Typeform v2 fields from question fields
    """
    fields = []
    
    for question in question_fields:
        standard_field = question['standard_field']
        
        # Translate title
        title = translate_text(standard_field.get('title', ''), caller_language)
        
        # Build field structure for Typeform v2
        field = {
            "ref": standard_field.get('ref', ''),
            "type": standard_field.get('type', 'short_text'),
            "title": title,
            "properties": {},
            "validations": {"required": True}
        }
        
        # Handle choices for dropdown/multiple_choice fields
        if standard_field.get('type') in ['dropdown', 'multiple_choice'] and standard_field.get('choices'):
            choices = []
            for choice in standard_field['choices']:
                translated_label = translate_text(choice.get('label', ''), caller_language)
                choices.append({
                    "ref": choice.get('ref', ''),
                    "label": translated_label
                })
            field["properties"]["choices"] = choices
        
        fields.append(field)
    
    return fields

def create_typeform_v2(form_data: Dict[str, Any]) -> Optional[str]:
    """
    Create Typeform using v2 API
    """
    try:
        headers = {
            'Authorization': f'Bearer {TYPEFORM_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Typeform v2 API endpoint
        url = f"{TYPEFORM_API_BASE_URL}/forms"
        
        response = requests.post(url, headers=headers, json=form_data)
        
        if response.status_code == 201:
            form_id = response.json().get('id')
            logger.info(f"Created Typeform with ID: {form_id}")
            return form_id
        else:
            logger.error(f"Failed to create Typeform: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error creating Typeform: {e}")
        return None

def add_webhook_to_typeform(form_id: str) -> bool:
    """
    Add webhook URL to existing Typeform
    """
    try:
        headers = {
            'Authorization': f'Bearer {TYPEFORM_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        webhook_data = {
            "url": TYPEFORM_WEBHOOK_URL,
            "enabled": True
        }
        
        url = f"{TYPEFORM_API_BASE_URL}/forms/{form_id}/webhooks"
        
        response = requests.post(url, headers=headers, json=webhook_data)
        
        if response.status_code in [200, 201]:
            logger.info(f"Added webhook to Typeform {form_id}")
            return True
        else:
            logger.error(f"Failed to add webhook: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error adding webhook to Typeform: {e}")
        return False

@typeform_bp.route('/create-typeform', methods=['POST'])
def create_dynamic_typeform():
    """
    Create a dynamic Typeform based on client configuration
    """
    try:
        data = request.get_json()
        
        # Extract function call data
        function_name = data.get('name', '')
        args = data.get('args', {})
        
        caller_id = args.get('caller_id')
        caller_language = args.get('caller_language', 'en')
        client_id = args.get('client_id')
        client_name = args.get('client_name', '')
        retell_event_id = args.get('retell_event_id')
        
        logger.info(f"Creating Typeform for caller_id: {caller_id}, client_id: {client_id}, language: {caller_language}")
        
        if not all([caller_id, client_id, retell_event_id]):
            return jsonify({"error": "Missing required parameters"}), 400
        
        # 1. Get client question fields
        question_fields = get_client_question_fields(client_id)
        if not question_fields:
            return jsonify({"error": "No question fields found for client"}), 400
        
        # 2. Build Typeform fields
        fields = build_typeform_fields(question_fields, caller_language)
        
        # 3. Get screen data
        screen_data = get_typeform_screen_data()
        
        # 4. Build form data for Typeform v2
        form_title = f"Call-{caller_id}-{client_id}-{datetime.now().isoformat()}"
        
        form_data = {
            "title": form_title,
            "fields": fields,
            "hidden": ["retell_event_id"],
            "settings": {
                "language": caller_language,
                "progress_bar": "proportion",
                "show_progress_bar": False,
                "show_typeform_branding": True,
                "notifications": {},
                "auto_translate": True,
                "is_public": True
            },
            "cui_settings": {"typing_emulation_speed": "medium"}
        }
        
        # Add welcome screen if available
        if screen_data.get('welcome_screen_title'):
            welcome_title = translate_text(screen_data['welcome_screen_title'], caller_language)
            welcome_button = translate_text(screen_data.get('welcome_screen_button_text', 'Start'), caller_language)
            
            form_data["welcome_screens"] = [{
                "ref": screen_data.get('welcome_screen_ref', 'welcome'),
                "title": welcome_title,
                "properties": {
                    "button_text": welcome_button
                }
            }]
        
        # Add thank you screen if available
        if screen_data.get('thank_you_screen_title'):
            thank_title = translate_text(screen_data['thank_you_screen_title'], caller_language)
            thank_button = translate_text(screen_data.get('thank_you_screen_button_text', 'Done'), caller_language)
            
            form_data["thankyou_screens"] = [{
                "ref": screen_data.get('thank_you_screen_ref', 'thankyou'),
                "type": "thankyou_screen",
                "title": thank_title,
                "properties": {
                    "redirect_url": screen_data.get('thank_you_screen_redirect_url', ''),
                    "show_button": True,
                    "button_text": thank_button
                }
            }]
        
        # 5. Create Typeform
        form_id = create_typeform_v2(form_data)
        if not form_id:
            return jsonify({"error": "Failed to create Typeform"}), 500
        
        # 6. Add webhook URL
        webhook_added = add_webhook_to_typeform(form_id)
        if not webhook_added:
            logger.warning(f"Failed to add webhook to Typeform {form_id}")
        
        # 7. Get form URL
        form_url = f"https://form.typeform.com/to/{form_id}"
        
        # 8. Save record in typeform_form table
        try:
            supabase = get_supabase_client()
            form_record = {
                "typeform_id": form_id,
                "typeform_url": form_url,
                "retell_event_id": retell_event_id,
                "caller_id": caller_id
            }
            
            response = supabase.table('typeform_form').insert(form_record).execute()
            
            if hasattr(response, 'error') and response.error:
                logger.error(f"Error saving typeform record: {response.error}")
            else:
                logger.info(f"Saved typeform record for form_id: {form_id}")
                
        except Exception as e:
            logger.error(f"Error saving typeform record: {e}")
        
        return jsonify({
            "success": True,
            "form_id": form_id,
            "form_url": form_url,
            "webhook_added": webhook_added
        })
        
    except Exception as e:
        logger.error(f"Error creating dynamic Typeform: {e}")
        return jsonify({"error": "Internal server error"}), 500

@typeform_bp.route('/webhook', methods=['POST'])
def typeform_webhook():
    """
    Handle Typeform submission webhooks
    """
    try:
        data = request.get_json()
        
        logger.info(f"Received Typeform webhook: {json.dumps(data, indent=2)}")
        
        # Extract form response data
        form_response = data.get('form_response', {})
        form_id = form_response.get('form_id')
        answers = form_response.get('answers', [])
        hidden = form_response.get('hidden', {})
        
        retell_event_id = hidden.get('retell_event_id')
        
        logger.info(f"Form submission - Form ID: {form_id}, Retell Event ID: {retell_event_id}")
        
        # Process answers and save to database
        # TODO: Implement answer processing logic
        
        return jsonify({"success": True}), 200
        
    except Exception as e:
        logger.error(f"Error processing Typeform webhook: {e}")
        return jsonify({"error": "Internal server error"}), 500
