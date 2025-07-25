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
        
        # Reduce logging for call_analyzed events to reduce log bloat
        event_type = data.get('event', 'unknown')
        if event_type == 'call_analyzed':
            logger.info(f"Received call_analyzed webhook - Call ID: {data.get('call', {}).get('call_id', 'unknown')}")
        
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

@webhook_bp.route('/function/siftly_check_business_hours', methods=['POST'])
def siftly_check_business_hours():
    """Handle siftly_check_business_hours function call from Retell AI"""
    try:
        # Get the JSON data from the request
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No JSON data received'}), 400
        
        # Process the business hours check using the service
        result = webhook_service.process_business_hours_check(data)
        
        return jsonify(result), 200
        
    except ValueError as e:
        logger.error(f"Validation error in business hours check: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error processing business hours check: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@webhook_bp.route('/inbound', methods=['POST'])
def inbound_webhook():
    """Handle inbound call webhooks from Retell AI"""
    try:
        # Get the JSON data from the request
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No JSON data received'}), 400
        
        # Removed verbose inbound webhook logging to reduce bloat
        
        # Process the inbound webhook using the service
        response_data = webhook_service.process_inbound_webhook(data)
        
        return jsonify(response_data), 200
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error processing inbound webhook: {e}")
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