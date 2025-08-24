"""
Configuration settings for the Siftly application
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Debug: Print all environment variables
import os
print("=== ENVIRONMENT VARIABLES DEBUG ===")
print(f"TWILIO_ACCOUNT_SID: {os.getenv('TWILIO_ACCOUNT_SID', 'NOT SET')}")
print(f"TWILIO_AUTH_TOKEN: {os.getenv('TWILIO_AUTH_TOKEN', 'NOT SET')}")
print(f"TWILIO_PHONE_NUMBER: {os.getenv('TWILIO_PHONE_NUMBER', 'NOT SET')}")
print(f"APP_BASE_URL: {os.getenv('APP_BASE_URL', 'https://siftly.onrender.com')}")
print(f"OPENAI_API_KEY: {os.getenv('OPENAI_API_KEY', 'NOT SET')}")
print(f"OPENROUTER_API_KEY: {os.getenv('OPENROUTER_API_KEY', 'NOT SET')}")
print(f"DEEPGRAM_API_KEY: {os.getenv('DEEPGRAM_API_KEY', 'NOT SET')}")
print(f"SUPABASE_URL: {os.getenv('SUPABASE_URL', 'NOT SET')}")
print(f"SUPABASE_SERVICE_ROLE_KEY: {os.getenv('SUPABASE_SERVICE_ROLE_KEY', 'NOT SET')}")
print("=== END DEBUG ===")

class Config:
    """Base configuration class"""
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    FLASK_ENV = os.getenv('FLASK_ENV', 'production')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    ENV = os.getenv('ENV', 'production')  # For environment detection
    
    # Airtable removed
    
    # Retell AI Configuration
    RETELL_WEBHOOK_SECRET = os.getenv('RETELL_WEBHOOK_SECRET')
    RETELL_API_KEY = os.getenv('RETELL_API_KEY')
    
    # Voice Webhook Configuration
    PUBLIC_HOSTNAME = os.getenv('PUBLIC_HOSTNAME')
    
    # Twilio Configuration
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
    APP_BASE_URL = os.getenv('APP_BASE_URL', 'https://siftly.onrender.com')
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    
    # OpenRouter Configuration
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    
    # Deepgram Configuration
    DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
    
    # Supabase Configuration
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    # Redis removed
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Application Configuration
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    @classmethod
    def validate_config(cls):
        """Validate that required configuration is present"""
        missing_vars = []
        
        # No Airtable required vars
        
        # Debug logging - use print for now since logger might not be set up yet
        # Airtable validation removed
        print(f"Config validation - OPENAI_API_KEY: {'SET' if cls.OPENAI_API_KEY else 'NOT SET'}")
        print(f"Config validation - DEEPGRAM_API_KEY: {'SET' if cls.DEEPGRAM_API_KEY else 'NOT SET'}")
            
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        return True

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    FLASK_ENV = 'development'

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    FLASK_ENV = 'production'

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = True

# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': ProductionConfig
} 