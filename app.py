"""
Siftly - Retell AI Webhook Handler
Main application entry point
"""
import os
from flask import Flask
from utils.logger import setup_logger
from config import Config, config
from routes.health_routes import health_bp

from routes.airtable_routes import airtable_bp

from routes.vapi_routes import vapi_bp
from routes.ivr_routes import ivr_bp

# Version check for debugging
try:
    from openai import OpenAI
    import openai
    print(f"=== OPENAI SDK VERSION: {openai.__version__} ===")
except ImportError:
    print("=== OPENAI SDK: NOT INSTALLED ===")
except Exception as e:
    print(f"=== OPENAI SDK VERSION CHECK ERROR: {e} ===")

def create_app(config_name=None):
    """
    Application factory pattern for creating Flask app
    
    Args:
        config_name: Configuration name (development, production, testing)
    
    Returns:
        Configured Flask application
    """
    # Create Flask app
    app = Flask(__name__)
    
    # Setup logging
    logger = setup_logger(__name__)
    
    # Load configuration
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'production')
    
    app.config.from_object(config[config_name])
    
    # Validate configuration
    try:
        Config.validate_config()
        logger.info("Configuration validated successfully")
    except ValueError as e:
        logger.warning(f"Configuration validation failed: {e}")
    
    # Register blueprints
    app.register_blueprint(health_bp)

    app.register_blueprint(airtable_bp)

    app.register_blueprint(vapi_bp)
    app.register_blueprint(ivr_bp)
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Endpoint not found'}, 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {error}")
        return {'error': 'Internal server error'}, 500
    
    @app.errorhandler(413)
    def too_large(error):
        return {'error': 'Request too large'}, 413
    
    logger.info(f"Application created with {config_name} configuration")
    return app

# Create the application instance
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=Config.DEBUG) 