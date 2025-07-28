"""
Airtable service for handling all Airtable operations
"""
import requests
import tempfile
import os
from typing import Dict, Any, List, Optional, Union
from pyairtable import Api, Base, Table
from config import Config
from utils.logger import get_logger
from utils.validators import validate_airtable_record

logger = get_logger(__name__)

class AirtableService:
    """Service class for Airtable operations"""
    
    def __init__(self, api_key: str = None, base_id: str = None, table_name: str = None):
        """
        Initialize Airtable service
        
        Args:
            api_key: Airtable API key (uses config if not provided)
            base_id: Airtable base ID (uses config if not provided)
            table_name: Airtable table name (uses config if not provided)
        """
        self.api_key = api_key or Config.AIRTABLE_API_KEY
        self.base_id = base_id or Config.AIRTABLE_BASE_ID
        self.table_name = table_name or Config.AIRTABLE_TABLE_NAME
        
        logger.info(f"Airtable config - API Key: {'SET' if self.api_key else 'NOT SET'}, Base ID: {'SET' if self.base_id else 'NOT SET'}, Table Name: {self.table_name}")
        
        if not self.api_key or not self.base_id or not self.table_name:
            logger.warning("Airtable credentials not provided. Service will be disabled.")
            self.table = None
        else:
            try:
                self.table = Table(self.api_key, self.base_id, self.table_name)
                logger.info(f"Airtable service initialized for table: {self.table_name}")
            except Exception as e:
                logger.error(f"Failed to initialize Airtable service: {e}")
                self.table = None
    
    def is_configured(self) -> bool:
        """Check if Airtable service is properly configured"""
        return self.table is not None
    
    def create_record(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a new record in Airtable
        
        Args:
            data: Record data dictionary
        
        Returns:
            Created record or None if failed
        """
        if not self.is_configured():
            logger.error("Airtable service not configured")
            return None
        
        # Validate data
        is_valid, errors = validate_airtable_record(data)
        if not is_valid:
            logger.error(f"Invalid record data: {errors}")
            return None
        
        try:
            record = self.table.create(data)
            # Removed verbose record creation logging to reduce bloat
            return record
        except Exception as e:
            logger.error(f"Failed to create Airtable record: {e}")
            return None
    
    def get_records(self, max_records: int = None, formula: str = None) -> List[Dict[str, Any]]:
        """
        Get records from Airtable
        
        Args:
            max_records: Maximum number of records to retrieve
            formula: Airtable formula for filtering
        
        Returns:
            List of records
        """
        if not self.is_configured():
            logger.error("Airtable service not configured")
            return []
        
        try:
            if formula:
                records = self.table.all(formula=formula, max_records=max_records)
            else:
                records = self.table.all(max_records=max_records)
            
            # Removed verbose record retrieval logging to reduce bloat
            return records
        except Exception as e:
            logger.error(f"Failed to retrieve Airtable records: {e}")
            return []
    
    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific record by ID
        
        Args:
            record_id: Airtable record ID
        
        Returns:
            Record data or None if not found
        """
        if not self.is_configured():
            logger.error("Airtable service not configured")
            return None
        
        try:
            record = self.table.get(record_id)
            # Removed verbose record retrieval logging to reduce bloat
            return record
        except Exception as e:
            logger.error(f"Failed to retrieve Airtable record {record_id}: {e}")
            return None
    
    def update_record(self, record_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update an existing record
        
        Args:
            record_id: Airtable record ID
            data: Updated data dictionary
        
        Returns:
            Updated record or None if failed
        """
        if not self.is_configured():
            logger.error("Airtable service not configured")
            return None
        
        # Validate data
        is_valid, errors = validate_airtable_record(data)
        if not is_valid:
            logger.error(f"Invalid record data: {errors}")
            return None
        
        try:
            record = self.table.update(record_id, data)
            # Removed verbose record update logging to reduce bloat
            return record
        except Exception as e:
            logger.error(f"Failed to update Airtable record {record_id}: {e}")
            return None
    
    def delete_record(self, record_id: str) -> bool:
        """
        Delete a record
        
        Args:
            record_id: Airtable record ID
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_configured():
            logger.error("Airtable service not configured")
            return False
        
        try:
            self.table.delete(record_id)
            logger.info(f"Deleted Airtable record: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete Airtable record {record_id}: {e}")
            return False
    
    def search_records(self, field: str, value: str) -> List[Dict[str, Any]]:
        """
        Search records by field value
        
        Args:
            field: Field name to search
            value: Value to search for
        
        Returns:
            List of matching records
        """
        if not self.is_configured():
            logger.error("Airtable service not configured")
            return []
        
        try:
            formula = f"{{{field}}} = '{value}'"
            records = self.table.all(formula=formula)
            # Removed verbose search logging to reduce bloat
            return records
        except Exception as e:
            logger.error(f"Failed to search Airtable records: {e}")
            return []
    
    def search_records_in_table(self, table_name: str, field: str, value: str) -> List[Dict[str, Any]]:
        """
        Search records by field value in a specific table
        
        Args:
            table_name: Name of the table to search in
            field: Field name to search
            value: Value to search for
        
        Returns:
            List of matching records
        """
        if not self.is_configured():
            logger.error("Airtable service not configured")
            return []
        
        try:
            # Create a temporary table instance for the specified table
            temp_table = Table(self.api_key, self.base_id, table_name)
            formula = f"{{{field}}} = '{value}'"
            records = temp_table.all(formula=formula)
            logger.info(f"Found {len(records)} records in table '{table_name}' matching {field}={value}")
            return records
        except Exception as e:
            logger.error(f"Failed to search records in table '{table_name}': {e}")
            return []
    
    def get_record_from_table(self, table_name: str, record_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific record from a table by record ID
        
        Args:
            table_name: Name of the table to get record from
            record_id: ID of the record to retrieve
        
        Returns:
            Record data if found, None otherwise
        """
        if not self.is_configured():
            logger.error("Airtable service not configured")
            return None
        
        try:
            # Create a temporary table instance for the specified table
            temp_table = Table(self.api_key, self.base_id, table_name)
            record = temp_table.get(record_id)
            logger.info(f"Retrieved record {record_id} from table '{table_name}'")
            return record
        except Exception as e:
            logger.error(f"Failed to get record {record_id} from table '{table_name}': {e}")
            return None
    
    def link_record(self, record_id: str, field_name: str, linked_record_ids: List[str]) -> bool:
        """
        Link records to a field (for linked record fields)
        
        Args:
            record_id: ID of the record to update
            field_name: Name of the field to link to
            linked_record_ids: List of record IDs to link
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_configured():
            logger.error("Airtable service not configured")
            return False
        
        try:
            update_data = {field_name: linked_record_ids}
            updated_record = self.update_record(record_id, update_data)
            if updated_record:
                logger.info(f"Successfully linked {len(linked_record_ids)} records to field '{field_name}' in record {record_id}")
                return True
            else:
                logger.error(f"Failed to link records to field '{field_name}' in record {record_id}")
                return False
        except Exception as e:
            logger.error(f"Error linking records: {e}")
            return False
    
    def batch_create_records(self, records_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create multiple records in batch
        
        Args:
            records_data: List of record data dictionaries
        
        Returns:
            List of created records
        """
        if not self.is_configured():
            logger.error("Airtable service not configured")
            return []
        
        if not records_data:
            logger.warning("No records provided for batch creation")
            return []
        
        # Validate all records
        valid_records = []
        for i, data in enumerate(records_data):
            is_valid, errors = validate_airtable_record(data)
            if is_valid:
                valid_records.append(data)
            else:
                logger.warning(f"Skipping invalid record at index {i}: {errors}")
        
        if not valid_records:
            logger.error("No valid records to create")
            return []
        
        try:
            # Airtable allows up to 10 records per batch
            batch_size = 10
            created_records = []
            
            for i in range(0, len(valid_records), batch_size):
                batch = valid_records[i:i + batch_size]
                batch_records = self.table.batch_create(batch)
                created_records.extend(batch_records)
            
            logger.info(f"Created {len(created_records)} records in batch")
            return created_records
        except Exception as e:
            logger.error(f"Failed to batch create records: {e}")
            return []
    
    def download_and_upload_recording(self, recording_url: str, record_id: str, call_id: str, created_time: str) -> bool:
        """
        Download recording file from URL and upload to Airtable as attachment
        
        Args:
            recording_url: URL of the recording file
            record_id: Airtable record ID to attach the file to
            call_id: Call ID for filename
            created_time: Created time for filename
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_configured():
            logger.error("Airtable service not configured")
            return False
        
        if not recording_url:
            logger.warning("No recording URL provided")
            return False
        
        try:
            # Removed verbose download logging to reduce bloat
            
            # Download the file
            response = requests.get(recording_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # Removed file size logging to reduce bloat
            
            # Format the filename with call_id and created_time
            safe_created_time = created_time.replace(':', '-').replace('.', '-').replace('T', '_')
            filename = f"call_{call_id}_{safe_created_time}.wav"
            
            # Removed filename logging to reduce bloat
            
            # Create a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                temp_file.write(response.content)
                temp_file_path = temp_file.name
            
            try:
                # Upload to Airtable as attachment
                # Removed verbose upload logging to reduce bloat
                
                # For Airtable attachments, we use URL references
                # Airtable will download and store the file from the URL
                # Removed verbose attachment logging to reduce bloat
                
                # Create attachment data with URL (Airtable will download and store the file)
                attachment_data = {
                    'url': recording_url,
                    'filename': filename
                }
                
                update_data = {
                    'recording_file': [attachment_data]
                }
                
                updated_record = self.update_record(record_id, update_data)
                
                if updated_record:
                    # Removed verbose success logging to reduce bloat
                    return True
                else:
                    logger.error(f"Failed to add recording URL to record: {record_id}")
                    return False
                        
            finally:
                # Clean up temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    # Removed cleanup logging to reduce bloat
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download recording from {recording_url}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error processing recording file: {e}")
            return False

# Global instance
airtable_service = AirtableService() 