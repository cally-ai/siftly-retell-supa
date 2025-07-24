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
print(f"AIRTABLE_API_KEY: {os.getenv('AIRTABLE_API_KEY', 'NOT SET')}")
print(f"AIRTABLE_BASE_ID: {os.getenv('AIRTABLE_BASE_ID', 'NOT SET')}")
print(f"AIRTABLE_TABLE_NAME: {os.getenv('AIRTABLE_TABLE_NAME', 'NOT SET')}")
print(f"OPENAI_API_KEY: {os.getenv('OPENAI_API_KEY', 'NOT SET')}")
print(f"DEEPGRAM_API_KEY: {os.getenv('DEEPGRAM_API_KEY', 'NOT SET')}")
print("=== END DEBUG ===")

class Config:
    """Base configuration class"""
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    FLASK_ENV = os.getenv('FLASK_ENV', 'production')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Airtable Configuration
    AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
    AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
    AIRTABLE_TABLE_NAME = os.getenv('AIRTABLE_TABLE_NAME')
    
    # Retell AI Configuration
    RETELL_WEBHOOK_SECRET = os.getenv('RETELL_WEBHOOK_SECRET')
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    
    # Deepgram Configuration
    DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
    
    # Redis Configuration
    REDIS_URL = os.getenv('REDIS_URL')
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Application Configuration
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    @classmethod
    def validate_config(cls):
        """Validate that required configuration is present"""
        missing_vars = []
        
        if not cls.AIRTABLE_API_KEY:
            missing_vars.append('AIRTABLE_API_KEY')
        if not cls.AIRTABLE_BASE_ID:
            missing_vars.append('AIRTABLE_BASE_ID')
        if not cls.AIRTABLE_TABLE_NAME:
            missing_vars.append('AIRTABLE_TABLE_NAME')
        
        # Debug logging - use print for now since logger might not be set up yet
        print(f"Config validation - AIRTABLE_API_KEY: {'SET' if cls.AIRTABLE_API_KEY else 'NOT SET'}")
        print(f"Config validation - AIRTABLE_BASE_ID: {'SET' if cls.AIRTABLE_BASE_ID else 'NOT SET'}")
        print(f"Config validation - AIRTABLE_TABLE_NAME: {cls.AIRTABLE_TABLE_NAME}")
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