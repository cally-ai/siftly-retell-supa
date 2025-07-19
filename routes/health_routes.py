"""
Health and system route handlers
"""
from flask import Blueprint, jsonify
from datetime import datetime
from utils.logger import get_logger
from services.airtable_service import airtable_service
from config import Config

logger = get_logger(__name__)

# Create blueprint
health_bp = Blueprint('health', __name__)

@health_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    try:
        # Check Airtable connection
        airtable_status = 'connected' if airtable_service.is_configured() else 'disconnected'
        
        # Get basic system info
        system_info = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'airtable_configured': airtable_service.is_configured(),
            'airtable_status': airtable_status,
            'environment': Config.FLASK_ENV,
            'debug_mode': Config.DEBUG
        }
        
        # Test Airtable connection if configured
        if airtable_service.is_configured():
            try:
                # Try to get one record to test connection
                test_records = airtable_service.get_records(max_records=1)
                system_info['airtable_test'] = 'success'
                system_info['airtable_records_count'] = len(test_records)
            except Exception as e:
                system_info['airtable_test'] = 'failed'
                system_info['airtable_error'] = str(e)
                system_info['status'] = 'degraded'
        
        return jsonify(system_info), 200
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }), 500

@health_bp.route('/status', methods=['GET'])
def system_status():
    """Detailed system status endpoint"""
    try:
        status_info = {
            'application': 'Siftly Retell AI Webhook Handler',
            'version': '1.0.0',
            'status': 'running',
            'timestamp': datetime.now().isoformat(),
            'uptime': 'N/A',  # Could be enhanced with actual uptime tracking
            'services': {
                'airtable': {
                    'configured': airtable_service.is_configured(),
                    'status': 'connected' if airtable_service.is_configured() else 'disconnected'
                }
            },
            'configuration': {
                'environment': Config.FLASK_ENV,
                'debug_mode': Config.DEBUG,
                'log_level': Config.LOG_LEVEL
            }
        }
        
        return jsonify(status_info), 200
        
    except Exception as e:
        logger.error(f"System status check failed: {e}")
        return jsonify({
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }), 500

@health_bp.route('/ping', methods=['GET'])
def ping():
    """Simple ping endpoint for load balancers"""
    return jsonify({
        'pong': True,
        'timestamp': datetime.now().isoformat()
    }), 200 