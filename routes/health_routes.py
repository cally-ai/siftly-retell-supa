"""
Health and system route handlers
"""
from flask import Blueprint, jsonify
from datetime import datetime
from utils.logger import get_logger
from config import Config
from supabase import create_client

logger = get_logger(__name__)

# Create blueprint
health_bp = Blueprint('health', __name__)

@health_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    try:
        # Check Supabase connection
        supabase_configured = bool(Config.SUPABASE_URL and Config.SUPABASE_SERVICE_ROLE_KEY)

        system_info = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'supabase_configured': supabase_configured,
            'supabase_status': 'connected' if supabase_configured else 'disconnected',
            'environment': Config.FLASK_ENV,
            'debug_mode': Config.DEBUG
        }

        # Test Supabase connection if configured
        if supabase_configured:
            try:
                client = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_ROLE_KEY)
                # Light test query: fetch 1 row from a small table
                resp = client.table('language').select('id').limit(1).execute()
                system_info['supabase_test'] = 'success'
                system_info['supabase_rows'] = len(resp.data or [])
            except Exception as e:
                system_info['supabase_test'] = 'failed'
                system_info['supabase_error'] = str(e)
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
                'supabase': {
                    'configured': bool(Config.SUPABASE_URL and Config.SUPABASE_SERVICE_ROLE_KEY),
                    'status': 'configured' if (Config.SUPABASE_URL and Config.SUPABASE_SERVICE_ROLE_KEY) else 'not_configured'
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