"""
Webhook route handlers for Retell AI integration
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
from utils.logger import get_logger
from utils.validators import validate_retell_inbound_webhook
from services.webhook_service import WebhookService
from config import Config

logger = get_logger(__name__)

# Create blueprint
webhook_bp = Blueprint('webhook', __name__, url_prefix='/webhook')

@webhook_bp.route('/inbound', methods=['POST'])
def inbound_webhook():
    """
    Handle incoming inbound call webhooks from Retell AI
    
    Expected payload structure:
    {
        "event": "call_inbound",
        "call_inbound": {
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "agent_id": "agent_123",
            "phone_number_id": "phone_456"
        }
    }
    
    Returns:
        JSON response with dynamic variables and metadata
    """
    try:
        # Get request data
        data = request.get_json()
        
        # Log the full webhook payload
        logger.info(f"=== INBOUND WEBHOOK PAYLOAD ===")
        logger.info(f"Full payload: {data}")
        logger.info(f"Headers: {dict(request.headers)}")
        logger.info(f"=== END PAYLOAD ===")
        
        if not data:
            logger.error("No JSON data received in webhook")
            return jsonify({
                'error': 'No JSON data received',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # Validate the webhook data
        try:
            validate_retell_inbound_webhook(data)
        except ValueError as e:
            logger.error(f"Webhook validation failed: {e}")
            return jsonify({
                'error': f'Invalid webhook data: {str(e)}',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # Process the webhook
        webhook_service = WebhookService()
        response_data = webhook_service.process_inbound_webhook(data)
        
        # Log the response we're sending back
        logger.info(f"=== WEBHOOK RESPONSE ===")
        logger.info(f"Response data: {response_data}")
        logger.info(f"=== END RESPONSE ===")
        
        logger.info(f"Inbound webhook processed successfully for call from {data.get('call_inbound', {}).get('from_number', 'unknown')}")
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error processing inbound webhook: {e}")
        return jsonify({
            'error': 'Internal server error processing webhook',
            'timestamp': datetime.now().isoformat()
        }), 500

@webhook_bp.route('/test', methods=['GET'])
def webhook_test():
    """Test endpoint to verify webhook routes are working"""
    return jsonify({
        'status': 'webhook routes active',
        'timestamp': datetime.now().isoformat(),
        'endpoints': {
            'inbound': '/webhook/inbound (POST)',
            'test': '/webhook/test (GET)'
        }
    }), 200
