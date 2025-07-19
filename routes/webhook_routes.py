"""
Webhook route handlers
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
from utils.logger import get_logger
from services.webhook_service import webhook_service

logger = get_logger(__name__)

# Create blueprint
webhook_bp = Blueprint('webhook', __name__, url_prefix='/webhook')

@webhook_bp.route('/retell', methods=['POST'])
def retell_webhook():
    """Handle incoming webhooks from Retell AI"""
    try:
        # Get the JSON data from the request
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No JSON data received'}), 400
        
        logger.info(f"Received webhook from Retell AI: {data.get('event_type', 'unknown')}")
        
        # Process the webhook using the service
        processed_data = webhook_service.process_retell_webhook(data)
        
        return jsonify({
            'status': 'success',
            'message': 'Webhook processed successfully',
            'processed_data': processed_data
        }), 200
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@webhook_bp.route('/statistics', methods=['GET'])
def get_webhook_statistics():
    """Get webhook statistics"""
    try:
        # Get hours parameter from query string
        hours = request.args.get('hours', 24, type=int)
        
        # Validate hours parameter
        if hours <= 0 or hours > 168:  # Max 1 week
            return jsonify({'error': 'Hours must be between 1 and 168'}), 400
        
        # Get statistics from service
        stats = webhook_service.get_webhook_statistics(hours=hours)
        
        return jsonify({
            'status': 'success',
            'statistics': stats,
            'period_hours': hours
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting webhook statistics: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500 