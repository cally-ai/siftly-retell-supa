"""
Whisper service for OpenAI audio transcription
"""
import requests
import tempfile
import os
from typing import Optional
from openai import OpenAI
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)

class WhisperService:
    """Service class for OpenAI Whisper transcription
    
    Supports both URL and local file transcription with optional language detection
    and domain-specific prompts for improved accuracy.
    """
    
    def __init__(self, api_key: str = None) -> None:
        """
        Initialize Whisper service
        
        Args:
            api_key: OpenAI API key (uses config if not provided)
        """
        self.api_key = api_key or Config.OPENAI_API_KEY
        
        logger.info(f"Whisper service initialization - API Key: {'SET' if self.api_key else 'NOT SET'}")
        
        if not self.api_key:
            logger.warning("OpenAI API key not provided. Whisper service will be disabled.")
            self.client = None
        else:
            try:
                # Initialize OpenAI client with minimal configuration
                logger.info("Attempting to initialize OpenAI client...")
                self.client = OpenAI(api_key=self.api_key)
                logger.info("Whisper service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Whisper service: {e}")
                logger.error(f"Error details: {type(e).__name__}: {str(e)}")
                self.client = None
    
    def is_configured(self) -> bool:
        """Check if Whisper service is properly configured"""
        return self.client is not None
    
    def transcribe_audio_url(self, audio_url: str, language: str = None, prompt: str = None) -> Optional[str]:
        """
        Transcribe audio from URL using OpenAI Whisper
        
        Args:
            audio_url: URL of the audio file to transcribe
            language: Language code (optional, Whisper will auto-detect if not provided)
            prompt: Optional prompt to guide transcription (e.g., domain-specific terms)
        
        Returns:
            Transcribed text or None if failed
        """
        if not self.is_configured():
            logger.error("Whisper service not configured")
            return None
        
        if not audio_url:
            logger.warning("No audio URL provided")
            return None
        
        try:
            logger.info(f"Starting Whisper transcription for: {audio_url}")
            
            # Download the audio file
            logger.info("Downloading audio file for transcription")
            response = requests.get(audio_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # Log file size for debugging
            file_size = len(response.content)
            logger.info(f"Downloaded audio file size: {file_size} bytes ({file_size / 1024:.1f} KB)")
            
            # Use context manager for automatic cleanup
            with tempfile.NamedTemporaryFile(suffix='.wav') as temp_file:
                temp_file.write(response.content)
                temp_file.flush()  # Ensure all data is written
                temp_file.seek(0)  # Reset file pointer to beginning
                
                # Transcribe using OpenAI Whisper
                logger.info("Sending audio to OpenAI Whisper API")
                
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=temp_file,
                    language=language,  # Will auto-detect if None
                    prompt=prompt,  # Optional prompt for domain-specific terms
                    response_format="text"
                )
                
                transcription_text = transcript.strip()
                logger.info(f"Whisper transcription completed. Length: {len(transcription_text)} characters")
                logger.info(f"Transcription preview: {transcription_text[:100]}...")
                
                return transcription_text
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download audio from {audio_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error during Whisper transcription: {e}")
            return None
    
    def transcribe_audio_file(self, file_path: str, language: str = None, prompt: str = None) -> Optional[str]:
        """
        Transcribe audio from local file using OpenAI Whisper
        
        Args:
            file_path: Path to the local audio file
            language: Language code (optional, Whisper will auto-detect if not provided)
            prompt: Optional prompt to guide transcription (e.g., domain-specific terms)
        
        Returns:
            Transcribed text or None if failed
        """
        if not self.is_configured():
            logger.error("Whisper service not configured")
            return None
        
        if not os.path.exists(file_path):
            logger.error(f"Audio file not found: {file_path}")
            return None
        
        try:
            logger.info(f"Starting Whisper transcription for local file: {file_path}")
            
            # Log file size for debugging
            file_size = os.path.getsize(file_path)
            logger.info(f"Local audio file size: {file_size} bytes ({file_size / 1024:.1f} KB)")
            
            with open(file_path, 'rb') as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,  # Will auto-detect if None
                    prompt=prompt,  # Optional prompt for domain-specific terms
                    response_format="text"
                )
            
            transcription_text = transcript.strip()
            logger.info(f"Whisper transcription completed. Length: {len(transcription_text)} characters")
            logger.info(f"Transcription preview: {transcription_text[:100]}...")
            
            return transcription_text
            
        except Exception as e:
            logger.error(f"Error during Whisper transcription: {e}")
            return None

# Lazy loading implementation
_whisper_service = None

def get_whisper_service():
    """Get or create the WhisperService instance (lazy loading)"""
    global _whisper_service
    if _whisper_service is None:
        print("=== Initializing WhisperService ===")
        _whisper_service = WhisperService()
        print(f"=== WhisperService initialized: {'OK' if _whisper_service.is_configured() else 'FAILED'} ===")
    return _whisper_service 