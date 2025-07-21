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
    """Service class for OpenAI Whisper transcription"""
    
    def __init__(self, api_key: str = None):
        """
        Initialize Whisper service
        
        Args:
            api_key: OpenAI API key (uses config if not provided)
        """
        self.api_key = api_key or Config.OPENAI_API_KEY
        
        if not self.api_key:
            logger.warning("OpenAI API key not provided. Whisper service will be disabled.")
            self.client = None
        else:
            try:
                self.client = OpenAI(api_key=self.api_key)
                logger.info("Whisper service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Whisper service: {e}")
                self.client = None
    
    def is_configured(self) -> bool:
        """Check if Whisper service is properly configured"""
        return self.client is not None
    
    def transcribe_audio_url(self, audio_url: str, language: str = None) -> Optional[str]:
        """
        Transcribe audio from URL using OpenAI Whisper
        
        Args:
            audio_url: URL of the audio file to transcribe
            language: Language code (optional, Whisper will auto-detect if not provided)
        
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
            
            # Create a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                temp_file.write(response.content)
                temp_file_path = temp_file.name
            
            try:
                # Transcribe using OpenAI Whisper
                logger.info("Sending audio to OpenAI Whisper API")
                
                with open(temp_file_path, 'rb') as audio_file:
                    transcript = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language=language,  # Will auto-detect if None
                        response_format="text"
                    )
                
                transcription_text = transcript.strip()
                logger.info(f"Whisper transcription completed. Length: {len(transcription_text)} characters")
                logger.info(f"Transcription preview: {transcription_text[:100]}...")
                
                return transcription_text
                
            finally:
                # Clean up temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    logger.info("Cleaned up temporary audio file")
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download audio from {audio_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error during Whisper transcription: {e}")
            return None
    
    def transcribe_audio_file(self, file_path: str, language: str = None) -> Optional[str]:
        """
        Transcribe audio from local file using OpenAI Whisper
        
        Args:
            file_path: Path to the local audio file
            language: Language code (optional, Whisper will auto-detect if not provided)
        
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
            
            with open(file_path, 'rb') as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,  # Will auto-detect if None
                    response_format="text"
                )
            
            transcription_text = transcript.strip()
            logger.info(f"Whisper transcription completed. Length: {len(transcription_text)} characters")
            logger.info(f"Transcription preview: {transcription_text[:100]}...")
            
            return transcription_text
            
        except Exception as e:
            logger.error(f"Error during Whisper transcription: {e}")
            return None

# Global instance
whisper_service = WhisperService() 