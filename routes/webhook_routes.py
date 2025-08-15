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

@webhook_bp.route('/business-hours', methods=['POST'])
def business_hours_webhook():
    """
    Handle business hours check function calls from Retell AI
    
    Expected payload structure:
    {
        "name": "siftly_check_business_hours",
        "args": {
            "client_id": "uuid-of-client"
        }
    }
    
    Returns:
        JSON response with within_business_hours status
    """
    try:
        # Get request data
        data = request.get_json()
        
        # Log the full webhook payload
        logger.info(f"=== BUSINESS HOURS WEBHOOK PAYLOAD ===")
        logger.info(f"Full payload: {data}")
        logger.info(f"Headers: {dict(request.headers)}")
        logger.info(f"=== END PAYLOAD ===")
        
        if not data:
            logger.error("No JSON data received in business hours webhook")
            return jsonify({
                'error': 'No JSON data received',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # Process the business hours check
        webhook_service = WebhookService()
        response_data = webhook_service.process_business_hours_check(data)
        
        # Log the response we're sending back
        logger.info(f"=== BUSINESS HOURS RESPONSE ===")
        logger.info(f"Response data: {response_data}")
        logger.info(f"=== END RESPONSE ===")
        
        logger.info(f"Business hours check processed successfully for client_id: {data.get('args', {}).get('client_id', 'unknown')}")
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error processing business hours webhook: {e}")
        return jsonify({
            'error': 'Internal server error processing business hours check',
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
            'business_hours': '/webhook/business-hours (POST)',
            'test': '/webhook/test (GET)',
            'function_test': '/webhook/function-test (POST)'
        }
    }), 200

@webhook_bp.route('/function-test', methods=['POST'])
def function_test_webhook():
    """
    Test endpoint to see Retell function call payloads
    
    This endpoint will log everything it receives and return a simple response.
    Use this to debug Retell function calls.
    """
    try:
        # Get request data
        data = request.get_json()
        
        # Log everything we receive
        logger.info(f"=== FUNCTION TEST WEBHOOK PAYLOAD ===")
        logger.info(f"Full payload: {data}")
        logger.info(f"Headers: {dict(request.headers)}")
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(f"Method: {request.method}")
        logger.info(f"URL: {request.url}")
        logger.info(f"=== END FUNCTION TEST PAYLOAD ===")
        
        # Return a simple response
        response_data = {
            'status': 'function_test_received',
            'timestamp': datetime.now().isoformat(),
            'received_data': data,
            'message': 'Function call payload logged successfully'
        }
        
        logger.info(f"=== FUNCTION TEST RESPONSE ===")
        logger.info(f"Response data: {response_data}")
        logger.info(f"=== END FUNCTION TEST RESPONSE ===")
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error in function test webhook: {e}")
        return jsonify({
            'error': 'Internal server error in function test',
            'timestamp': datetime.now().isoformat(),
            'exception': str(e)
        }), 500
