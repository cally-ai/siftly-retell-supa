"""
Webhook service utilities
"""
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
import pytz
from supabase import create_client
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)

class WebhookService:
    """Service class for processing webhooks"""
    
    def __init__(self):
        """Initialize webhook service"""
        self._supabase_client = None

    @property
    def supabase(self):
        """Lazy-init Supabase client"""
        if self._supabase_client is None:
            try:
                self._supabase_client = create_client(
                    Config.SUPABASE_URL,
                    Config.SUPABASE_SERVICE_ROLE_KEY
                )
            except Exception as e:
                logger.error(f"Could not initialize Supabase client: {e}")
                raise
        return self._supabase_client

    def process_business_hours_check(self, data: Dict[str, Any]) -> Dict[str, str]:
        """
        Process check_business_hours function call from Retell AI
        
        Args:
            data: Function call data from Retell AI
        
        Returns:
            Response with within_business_hours status
        """
        try:
            # Step 1: Parse the incoming request
            function_name = data.get('name', '')
            if function_name not in ['siftly_check_business_hours', 'check_business_hours']:
                raise ValueError(f"Invalid function name: {function_name}")
            
            # Extract client_id from args or call
            args = data.get('args', {})
            call_data = data.get('call', {})
            client_id = args.get('client_id') or call_data.get('client_id')
            
            if not client_id:
                raise ValueError("client_id not found in request")
            
            logger.info(f"Processing business hours check for client_id: {client_id}")
            
            # Step 2: Get the current server time
            current_utc_time = datetime.utcnow()
            logger.info(f"Current UTC time: {current_utc_time}")
            
            # Step 3: Look up the client in Supabase
            client_data = self._get_client_business_hours(client_id)
            if not client_data:
                logger.warning(f"Client not found or no business hours configured for client_id: {client_id}")
                return {"within_business_hours": "0"}
            
            timezone_str = client_data.get('timezone')
            opening_hours = client_data.get('opening_hours', [])
            
            # Debug logging
            logger.info(f"Timezone field type: {type(timezone_str)}, value: {timezone_str}")
            logger.info(f"Opening hours count: {len(opening_hours)}")
            
            if not timezone_str:
                logger.warning(f"No timezone configured for client_id: {client_id}")
                return {"within_business_hours": "0"}
            
            if not opening_hours:
                logger.warning(f"No opening hours configured for client_id: {client_id}")
                return {"within_business_hours": "0"}
            
            # Step 4: Convert to client's timezone and evaluate business hours
            try:
                # Handle timezone if it's a list (take first item)
                if isinstance(timezone_str, list):
                    timezone_str = timezone_str[0] if timezone_str else None
                    logger.info(f"Extracted timezone from list: {timezone_str}")
                
                if not timezone_str:
                    logger.warning(f"No valid timezone found for client_id: {client_id}")
                    return {"within_business_hours": "0"}
                
                client_tz = pytz.timezone(timezone_str)
                client_local_time = current_utc_time.replace(tzinfo=pytz.UTC).astimezone(client_tz)
                logger.info(f"Client local time ({timezone_str}): {client_local_time}")
                
                # Get current weekday (lowercase)
                current_weekday = client_local_time.strftime('%A').lower()
                current_time_str = client_local_time.strftime('%H:%M')
                
                logger.info(f"Current weekday: {current_weekday}, time: {current_time_str}")
                
                # Step 5: Check if within business hours
                within_hours = self._check_business_hours(
                    opening_hours, current_weekday, current_time_str
                )
                
                result = {"within_business_hours": "1" if within_hours else "0"}
                logger.info(f"Business hours check result: {result}")
                return result
                
            except pytz.exceptions.UnknownTimeZoneError:
                logger.error(f"Invalid timezone: {timezone_str}")
                return {"within_business_hours": "0"}
                
        except Exception as e:
            logger.error(f"Error processing business hours check: {e}")
            return {"within_business_hours": "0"}

    def _get_client_business_hours(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Get client's business hours configuration from Supabase
        
        Args:
            client_id: The client's record ID
        
        Returns:
            Dict with 'timezone' and 'opening_hours' list, or None
        """
        try:
            # 1) Get client's timezone_id
            client_resp = self.supabase.table('client').select('timezone_id').eq('id', client_id).limit(1).execute()
            if not client_resp.data:
                logger.warning(f"Client not found: {client_id}")
                return None
            timezone_id = client_resp.data[0].get('timezone_id')
            timezone_name = None
            if timezone_id:
                tz_resp = self.supabase.table('timezone').select('name').eq('id', timezone_id).limit(1).execute()
                if tz_resp.data:
                    timezone_name = tz_resp.data[0].get('name')
            if not timezone_name:
                logger.warning(f"No timezone configured for client: {client_id}")
                return None
            
            # 2) Fetch opening hours for this client
            oh_resp = self.supabase.table('opening_hours').select('day, start_time, end_time').eq('client_id', client_id).execute()
            opening_hours_records = oh_resp.data or []
            if not opening_hours_records:
                logger.warning(f"No opening hours configured for client: {client_id}")
                return None
            
            return {
                'timezone': timezone_name,
                'opening_hours': opening_hours_records
            }
        except Exception as e:
            logger.error(f"Error getting client business hours from Supabase: {e}")
            return None

    def _check_business_hours(self, opening_hours: List[Dict[str, Any]], current_weekday: str, current_time_str: str) -> bool:
        """
        Check if current time is within business hours
        
        Args:
            opening_hours: List of opening hours records from Airtable
            current_weekday: Current weekday in lowercase (e.g., 'monday')
            current_time_str: Current time in HH:MM format (e.g., '14:30')
        
        Returns:
            True if within business hours, False otherwise
        """
        try:
            # Find the opening hours record for the current weekday
            current_day_hours = None
            
            # Handle both scenarios: single record with list of days, or multiple records with individual days
            for hours_record in opening_hours:
                day_field = hours_record.get('day', '')
                
                # If day is a list (single record with multiple days)
                if isinstance(day_field, list):
                    days = [str(d).lower() for d in day_field]
                    if current_weekday in days:
                        current_day_hours = hours_record
                        break
                # If day is a string (individual day record)
                elif isinstance(day_field, str):
                    day = day_field.lower()
                    if day == current_weekday:
                        current_day_hours = hours_record
                        break
            
            if not current_day_hours:
                logger.info(f"No opening hours configured for {current_weekday}")
                return False
            
            start_time = current_day_hours.get('start_time', '')
            end_time = current_day_hours.get('end_time', '')
            
            if not start_time or not end_time:
                logger.warning(f"Incomplete opening hours for {current_weekday}: start={start_time}, end={end_time}")
                return False
            
            logger.info(f"Business hours for {current_weekday}: {start_time} - {end_time}")
            
            # Compare times (HH:MM format allows direct string comparison)
            is_within_hours = start_time <= current_time_str <= end_time
            
            logger.info(f"Current time {current_time_str} within hours {start_time}-{end_time}: {is_within_hours}")
            return is_within_hours
            
        except Exception as e:
            logger.error(f"Error checking business hours: {e}")
            return False

  
    async def _get_customer_data_async(self, to_number: str) -> Optional[Dict[str, Any]]:
        """
        Get customer data from Airtable based on to_number (async version)
        
        Args:
            to_number: The phone number to look up
        
        Returns:
            Customer data dictionary or None if not found
        """

        logger.info(f"=== SUPABASE LOOKUP START (async) ===")
        
        try:
            # Step 1: Find client via twilio_number
            tw_resp = self.supabase.table('twilio_number').select('client_id').eq('twilio_number', to_number).limit(1).execute()
            if not tw_resp.data:
                logger.warning(f"No twilio_number record found for: {to_number}")
                return None
            client_id = tw_resp.data[0].get('client_id')
            if not client_id:
                logger.warning(f"twilio_number {to_number} has no client_id")
                return None

            # Step 2: Fetch client_dynamic_variables
            dynamic_variables: Dict[str, Any] = {}
            cdv_resp = self.supabase.table('client_dynamic_variables').select('*').eq('client_id', client_id).limit(1).execute()
            if cdv_resp.data:
                cdv = cdv_resp.data[0]
                for k, v in cdv.items():
                    if k not in ('id', 'client_id') and v is not None:
                        dynamic_variables[k] = v

            # Step 3: Fetch client_language_agent_name key pairs
            clan_resp = self.supabase.table('client_language_agent_name').select('key_pair').eq('client_id', client_id).execute()
            for rec in clan_resp.data or []:
                key_pair_value = rec.get('key_pair') or ''
                if isinstance(key_pair_value, str) and '=' in key_pair_value:
                    parts = key_pair_value.split('=', 1)
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip()
                        if key:
                            dynamic_variables[key] = value

            logger.info(f"Returning dynamic variables from Supabase: {list(dynamic_variables.keys())}")
            logger.info(f"=== SUPABASE LOOKUP END (async) ===")
            return dynamic_variables
            
        except Exception as e:
            logger.error(f"Error getting customer data for {to_number}: {e}")
            return None

    def _get_customer_data(self, to_number: str) -> Optional[Dict[str, Any]]:
        """
        Get customer data from Airtable based on to_number
        
        Args:
            to_number: The phone number to look up
        
        Returns:
            Customer data dictionary or None if not found
        """
        # Supabase lookup
        logger.info(f"Performing Supabase lookup for {to_number}")
        try:
            # Use ThreadPoolExecutor to run async operations in sync context
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                data = executor.submit(lambda: asyncio.run(self._get_customer_data_async(to_number))).result()
            
            return data
        except Exception as e:
            logger.error(f"Error in _get_customer_data: {e}")
            return None
    
    
    def _process_language_linking(self, record_id: str, webhook_data: Dict[str, Any]) -> None:
        """
        Process language linking based on collected_dynamic_variables
        
        Args:
            record_id: ID of the saved Airtable record
            webhook_data: Webhook data containing collected_dynamic_variables
        """
        try:
            # Extract collected_dynamic_variables
            collected_vars = webhook_data.get('collected_dynamic_variables', {})
            if not collected_vars:
                logger.info(f"No collected_dynamic_variables found for record: {record_id}")
                return
            
            # Extract caller_language
            caller_language = collected_vars.get('caller_language')
            if not caller_language:
                logger.info(f"No caller_language found in collected_dynamic_variables for record: {record_id}")
                return
            
            # Search for matching language record in the 'language' table
            language_records = airtable_service.search_records_in_table('language', 'language_name', caller_language)
            
            if not language_records:
                logger.warning(f"No language record found for '{caller_language}' in language table")
                return
            
            if len(language_records) > 1:
                logger.warning(f"Multiple language records found for '{caller_language}', using first one")
            
            # Get the first matching language record
            language_record = language_records[0]
            language_record_id = language_record.get('id')
            
            if not language_record_id:
                logger.error(f"Language record found but no ID available for '{caller_language}'")
                return
            
            # Link the language record to the event record
            link_success = airtable_service.link_record(record_id, 'language', [language_record_id])
            
            if link_success:
                logger.info(f"Language linked: {caller_language}")
            else:
                logger.error(f"Failed to link language record {language_record_id} to event record {record_id}")
                
        except Exception as e:
            logger.error(f"Error processing language linking for record {record_id}: {e}")
    
    def get_webhook_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get webhook statistics for the specified time period
        
        Args:
            hours: Number of hours to look back
        
        Returns:
            Statistics dictionary
        """
        if not airtable_service.is_configured():
            return {}
        
        try:
            # Calculate timestamp for filtering
            from datetime import timedelta
            cutoff_time = datetime.now() - timedelta(hours=hours)
            cutoff_iso = cutoff_time.isoformat()
            
            # Get records from the last N hours
            formula = f"IS_AFTER({{Timestamp}}, '{cutoff_iso}')"
            records = airtable_service.get_records(formula=formula)
            
            # Calculate statistics
            stats = {
                'total_calls': len(records),
                'call_types': {},
                'sentiments': {},
                'priority_levels': {},
                'average_duration': 0,
                'total_cost': 0,
                'requires_followup': 0
            }
            
            total_duration = 0
            total_cost = 0
            
            for record in records:
                fields = record.get('fields', {})
                
                # Count event types
                event_type = fields.get('Event Type', 'unknown')
                stats['call_types'][event_type] = stats['call_types'].get(event_type, 0) + 1
                
                # Count sentiments
                sentiment = fields.get('Sentiment', 'unknown')
                stats['sentiments'][sentiment] = stats['sentiments'].get(sentiment, 0) + 1
                
                # Count priority levels
                priority = fields.get('Priority Level', 'normal')
                stats['priority_levels'][priority] = stats['priority_levels'].get(priority, 0) + 1
                
                # Sum durations and costs
                duration = fields.get('Duration', 0)
                total_duration += duration
                
                cost = fields.get('Cost', 0)
                total_cost += cost
                
                # Count follow-ups
                if fields.get('Requires Followup', False):
                    stats['requires_followup'] += 1
            
            # Calculate averages
            if stats['total_calls'] > 0:
                stats['average_duration'] = total_duration / stats['total_calls']
                stats['total_cost'] = total_cost
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting webhook statistics: {e}")
            return {}

    def _get_caller_language_from_phone_id(self, phone_number_id: str) -> Optional[str]:
        """
        Get caller language based on phone_number_id from twilio_number table
        
        Args:
            phone_number_id: The phone_number_id from the incoming payload
            
        Returns:
            The vapi_language_code value or None if not found
        """
        try:
            logger.info(f"Looking up caller language for phone_number_id: {phone_number_id}")
            # Find twilio_number row by vapi_phone_number_id
            tn_resp = self.supabase.table('twilio_number').select('language_id').eq('vapi_phone_number_id', phone_number_id).limit(1).execute()
            if not tn_resp.data:
                logger.warning(f"No twilio_number found for phone_number_id: {phone_number_id}")
                return None
            language_id = tn_resp.data[0].get('language_id')
            if not language_id:
                logger.warning(f"No language_id set for phone_number_id: {phone_number_id}")
                return None
            lang_resp = self.supabase.table('language').select('vapi_language_code').eq('id', language_id).limit(1).execute()
            if not lang_resp.data:
                logger.warning(f"Language not found for id: {language_id}")
                return None
            vapi_language_code = lang_resp.data[0].get('vapi_language_code')
            if vapi_language_code:
                logger.info(f"Found caller language: {vapi_language_code} for phone_number_id: {phone_number_id}")
                return vapi_language_code
            logger.warning(f"No vapi_language_code found for language id: {language_id}")
            return None
                
        except Exception as e:
            logger.error(f"Error getting caller language for phone_number_id {phone_number_id}: {e}")
            return None

# Global instance
webhook_service = WebhookService() 