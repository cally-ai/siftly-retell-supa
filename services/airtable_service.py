"""
Airtable service for handling all Airtable operations
"""
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
        
        if not self.api_key or not self.base_id:
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
            logger.info(f"Created Airtable record: {record.get('id', 'unknown')}")
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
            
            logger.info(f"Retrieved {len(records)} records from Airtable")
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
            logger.info(f"Retrieved Airtable record: {record_id}")
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
            logger.info(f"Updated Airtable record: {record_id}")
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
            logger.info(f"Found {len(records)} records matching {field}={value}")
            return records
        except Exception as e:
            logger.error(f"Failed to search Airtable records: {e}")
            return []
    
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

# Global instance
airtable_service = AirtableService() 