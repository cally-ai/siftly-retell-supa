"""
Deepgram service for audio transcription
"""
import os
import tempfile
import requests
from typing import Optional, List
from deepgram import DeepgramClient, PrerecordedOptions, FileSource
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)

class DeepgramService:
    """Service class for Deepgram transcription
    
    Supports both URL and local file transcription with optional language detection
    and domain-specific prompts for improved accuracy.
    """
    
    def __init__(self, api_key: str = None) -> None:
        """
        Initialize Deepgram service
        
        Args:
            api_key: Deepgram API key (uses config if not provided)
        """
        self.api_key = api_key or Config.DEEPGRAM_API_KEY
        
        # Removed verbose initialization logging to reduce bloat
        
        if not self.api_key:
            logger.warning("Deepgram API key not provided. Deepgram service will be disabled.")
            self.client = None
        else:
            try:
                # Initialize Deepgram client
                self.client = DeepgramClient(self.api_key)
                # Removed verbose initialization logging to reduce bloat
            except Exception as e:
                logger.error(f"Failed to initialize Deepgram service: {e}")
                logger.error(f"Error details: {type(e).__name__}: {str(e)}")
                self.client = None
    
    def is_configured(self) -> bool:
        """Check if Deepgram service is properly configured"""
        return self.client is not None
    
    def __repr__(self):
        """String representation for debugging"""
        return f"<DeepgramService configured={self.is_configured()}>"
    
    def transcribe_audio_url(self, audio_url: str, language: str = None, prompt: str = None, model: str = "nova-3") -> Optional[str]:
        """
        Transcribe audio from URL using Deepgram
        
        Args:
            audio_url: URL of the audio file to transcribe
            language: Language code (optional, Deepgram will auto-detect if not provided)
            prompt: Optional prompt to guide transcription (e.g., domain-specific terms)
            model: Deepgram model to use (default: nova-3)
        
        Returns:
            Transcribed text or None if failed
        """
        if not self.is_configured():
            logger.error("Deepgram service not configured")
            return None
        
        if not audio_url:
            logger.warning("No audio URL provided")
            return None
        
        try:
            logger.info(f"Starting Deepgram transcription for: {audio_url}")
            
            # Convert prompt to keywords list if provided
            keywords = [prompt] if prompt else None
            
            # Configure transcription options
            options = PrerecordedOptions(
                model=model,
                smart_format=True,
                language=language,
                keywords=keywords or []
            )
            
            # Removed verbose Deepgram logging to reduce bloat
            
            # Transcribe from URL
            payload = {"url": audio_url}
            response = self.client.listen.rest.v("1").transcribe_url(payload, options)
            
            # Extract transcription text
            transcription_text = self._extract_transcript(response)
            
            if transcription_text:
                transcription_text = transcription_text.strip()
                # Removed verbose transcription logging to reduce bloat
                return transcription_text
            else:
                logger.error("Failed to extract transcript from Deepgram response")
                return None
        
        except Exception as e:
            logger.error(f"Unexpected error during Deepgram transcription: {e}")
            logger.error(f"Error details: {type(e).__name__}: {str(e)}")
            return None
    
    def transcribe_audio_file(self, file_path: str, language: str = None, prompt: str = None, model: str = "nova-3") -> Optional[str]:
        """
        Transcribe audio from local file using Deepgram
        
        Args:
            file_path: Path to the local audio file
            language: Language code (optional, Deepgram will auto-detect if not provided)
            prompt: Optional prompt to guide transcription (e.g., domain-specific terms)
            model: Deepgram model to use (default: nova-3)
        
        Returns:
            Transcribed text or None if failed
        """
        if not self.is_configured():
            logger.error("Deepgram service not configured")
            return None
        
        if not os.path.exists(file_path):
            logger.error(f"Audio file not found: {file_path}")
            return None
        
        try:
            logger.info(f"Starting Deepgram transcription for local file: {file_path}")
            
            # Log file size for debugging
            file_size = os.path.getsize(file_path)
            logger.info(f"Local audio file size: {file_size} bytes ({file_size / 1024:.1f} KB)")
            
            # Convert prompt to keywords list if provided
            keywords = [prompt] if prompt else None
            
            # Configure transcription options
            options = PrerecordedOptions(
                model=model,
                smart_format=True,
                language=language,
                keywords=keywords or []
            )
            
            logger.info(f"Deepgram options: model={model}, language={language}, keywords={keywords}")
            
            # Comprehensive debugging
            logger.info(f"=== DEEPGRAM DEBUG INFO (FILE) ===")
            logger.info(f"API key configured: {self.api_key is not None}")
            logger.info(f"API key length: {len(self.api_key) if self.api_key else 0}")
            logger.info(f"Client configured: {self.client is not None}")
            logger.info(f"=== END DEEPGRAM DEBUG INFO (FILE) ===")
            
            # Transcribe from file
            with open(file_path, "rb") as f:
                file_data = f.read()
            
            payload: FileSource = {"buffer": file_data}
            response = self.client.listen.rest.v("1").transcribe_file(payload, options)
            
            # Extract transcription text
            transcription_text = self._extract_transcript(response)
            
            if transcription_text:
                transcription_text = transcription_text.strip()
                # Removed verbose transcription logging to reduce bloat
                return transcription_text
            else:
                logger.error("Failed to extract transcript from Deepgram response")
                return None
            
        except Exception as e:
            logger.error(f"Unexpected error during Deepgram transcription: {e}")
            logger.error(f"Error details: {type(e).__name__}: {str(e)}")
            return None
    
    def transcribe_remote_to_tempfile(
        self,
        audio_url: str,
        model: str = "nova-3",
        language: str = None,
        prompt: str = None
    ) -> Optional[str]:
        """
        Download a remote audio file to a tempfile and transcribe it
        
        Args:
            audio_url: URL of the remote audio file
            model: Deepgram model to use (default: nova-3)
            language: Language code (optional)
            prompt: Optional prompt to guide transcription
        
        Returns:
            Transcribed text or None if failed
        """
        if not self.is_configured():
            logger.error("Deepgram service not configured")
            return None
        
        logger.info(f"Downloading remote audio from: {audio_url}")
        try:
            response = requests.get(audio_url, stream=True, timeout=30)
            response.raise_for_status()

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                tmp.write(response.content)
                tmp.flush()
                return self.transcribe_audio_file(
                    tmp.name,
                    model=model,
                    language=language,
                    prompt=prompt
                )
        except Exception as e:
            logger.error(f"Failed to download or transcribe audio: {e}")
            return None
    
    def _extract_transcript(self, response: dict) -> Optional[str]:
        """Extract transcript text from Deepgram API response"""
        try:
            return response["results"]["channels"][0]["alternatives"][0]["transcript"]
        except (KeyError, IndexError) as e:
            logger.error(f"Could not extract transcript from response: {e}")
            return None

# Lazy loading implementation
_deepgram_service = None

def get_deepgram_service():
    """Get or create the DeepgramService instance (lazy loading)"""
    global _deepgram_service
    if _deepgram_service is None:
        print("=== Initializing DeepgramService ===")
        _deepgram_service = DeepgramService()
        print(f"=== DeepgramService initialized: {'OK' if _deepgram_service.is_configured() else 'FAILED'} ===")
    return _deepgram_service 