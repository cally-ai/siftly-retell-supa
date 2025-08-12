"""
Logging utility for the Siftly application
"""
import logging
import sys
from config import Config

def setup_logger(name: str, level: str = None) -> logging.Logger:
    """
    Set up a logger with consistent formatting
    
    Args:
        name: Logger name
        level: Logging level (optional, uses config default if not provided)
    
    Returns:
        Configured logger instance
    """
    # Configure root logger to ensure all loggers work
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler for root logger
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # Reduce verbosity of external libraries
    logging.getLogger('twilio.http_client').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    # Create formatter
    formatter = logging.Formatter(Config.LOG_FORMAT)
    console_handler.setFormatter(formatter)
    
    # Add handler to root logger
    root_logger.addHandler(console_handler)
    
    # Get the specific logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for the given name
    
    Args:
        name: Logger name
    
    Returns:
        Logger instance
    """
    # Ensure root logger is configured
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        # Configure root logger if not already done
        root_logger.setLevel(logging.INFO)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(Config.LOG_FORMAT)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # Reduce verbosity of external libraries
        logging.getLogger('twilio.http_client').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    return logging.getLogger(name) 