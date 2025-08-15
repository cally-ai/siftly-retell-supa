"""
Webhook service utilities
"""
import asyncio
from typing import Dict, Any, Optional, List
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
            
    
            
            # Step 2: Get the current server time
            current_utc_time = datetime.utcnow()
    
            
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
    
                
                if not timezone_str:
                    logger.warning(f"No valid timezone found for client_id: {client_id}")
                    return {"within_business_hours": "0"}
                
                client_tz = pytz.timezone(timezone_str)
                client_local_time = current_utc_time.replace(tzinfo=pytz.UTC).astimezone(client_tz)

                
                # Get current weekday (lowercase)
                current_weekday = client_local_time.strftime('%A').lower()
                current_time_str = client_local_time.strftime('%H:%M')
                

                
                # Step 5: Check if within business hours
                within_hours = self._check_business_hours(
                    opening_hours, current_weekday, current_time_str
                )
                
                result = {"within_business_hours": "true" if within_hours else "false"}

                return result
                
            except pytz.exceptions.UnknownTimeZoneError:
                logger.error(f"Invalid timezone: {timezone_str}")
                return {"within_business_hours": "false"}
                
        except Exception as e:
            logger.error(f"Error processing business hours check: {e}")
            return {"within_business_hours": "false"}

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
            opening_hours: List of opening hours records from Supabase
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
        Get customer data based on to_number (async version) from Supabase
        
        Args:
            to_number: The phone number to look up
        
        Returns:
            Customer data dictionary or None if not found
        """

        logger.info(f"=== SUPABASE LOOKUP START (async) ===")
        
        try:
            # Clean phone number by removing spaces and special characters
            cleaned_number = to_number.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            logger.info(f"Original number: {to_number}, Cleaned number: {cleaned_number}")
            
            # Step 1: Find client via twilio_number (try both original and cleaned)
            tw_resp = self.supabase.table('twilio_number').select('client_id, language_id').eq('twilio_number', cleaned_number).limit(1).execute()
            if not tw_resp.data:
                # Fallback to original number if cleaned doesn't work
                tw_resp = self.supabase.table('twilio_number').select('client_id, language_id').eq('twilio_number', to_number).limit(1).execute()
            if not tw_resp.data:
                logger.warning(f"No twilio_number record found for: {to_number} (cleaned: {cleaned_number})")
                return None
            client_id = tw_resp.data[0].get('client_id')
            language_id = tw_resp.data[0].get('language_id')
            if not client_id:
                logger.warning(f"twilio_number {to_number} has no client_id")
                return None

            # Step 2: Get client information and configuration
            dynamic_variables: Dict[str, Any] = {}
            
            # Get client basic info
            client_resp = self.supabase.table('client').select('name, client_description').eq('id', client_id).limit(1).execute()
            if client_resp.data:
                client = client_resp.data[0]
                client_name = client.get('name', 'Our Company')
                client_description = client.get('client_description', '')
                dynamic_variables['client_name'] = client_name
                dynamic_variables['client_description'] = client_description
                logger.info(f"Client data - name: '{client_name}', description: '{client_description}'")

            # Get client workflow configuration
            wf_resp = self.supabase.table('client_workflow_configuration').select('*').eq('client_id', client_id).limit(1).execute()
            if wf_resp.data:
                wf_config = wf_resp.data[0]
                logger.info(f"Workflow config raw data: {wf_config}")
                # Add workflow configuration as dynamic variables
                for key, value in wf_config.items():
                    if key != 'id' and key != 'client_id' and value is not None:
                        dynamic_variables[f'workflow_{key}'] = value
                        logger.info(f"Added workflow_{key}: '{value}'")

            # Get client language agent names
            agent_names_resp = self.supabase.table('client_language_agent_name').select('language_id, agent_name').eq('client_id', client_id).execute()
            if agent_names_resp.data:
                for agent_record in agent_names_resp.data:
                    agent_language_id = agent_record.get('language_id')
                    agent_name = agent_record.get('agent_name')
                    if agent_language_id and agent_name:
                        # Get language code for the key
                        lang_resp = self.supabase.table('language').select('language_code').eq('id', agent_language_id).limit(1).execute()
                        if lang_resp.data:
                            lang_code = lang_resp.data[0].get('language_code', 'en')
                            dynamic_variables[f'agent_name_{lang_code}'] = agent_name

            # Get caller language from the twilio_number record
            if language_id:
                lang_resp = self.supabase.table('language').select('language_code').eq('id', language_id).limit(1).execute()
                if lang_resp.data:
                    caller_language = lang_resp.data[0].get('language_code', 'en')
                    dynamic_variables['caller_language'] = caller_language
                    dynamic_variables['preferred_language'] = caller_language
                    logger.info(f"Found caller language from twilio_number: {caller_language}")

            logger.info(f"Returning dynamic variables from Supabase: {list(dynamic_variables.keys())}")
            logger.info(f"=== SUPABASE LOOKUP END (async) ===")
            return dynamic_variables
            
        except Exception as e:
            logger.error(f"Error getting customer data for {to_number}: {e}")
            return None

    def _get_customer_data(self, to_number: str) -> Optional[Dict[str, Any]]:
        """
        Get customer data based on to_number from Supabase
        
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
    

    def _get_caller_language_from_phone_id(self, phone_number_id: str) -> Optional[str]:
        """
        Get caller language based on phone_number_id from twilio_number table
        
        Args:
            phone_number_id: The phone_number_id from the incoming payload
            
        Returns:
            The language_code value or None if not found
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
            lang_resp = self.supabase.table('language').select('language_code').eq('id', language_id).limit(1).execute()
            if not lang_resp.data:
                logger.warning(f"Language not found for id: {language_id}")
                return None
            language_code = lang_resp.data[0].get('language_code')
            if language_code:
                logger.info(f"Found caller language: {language_code} for phone_number_id: {phone_number_id}")
                return language_code
            logger.warning(f"No language_code found for language id: {language_id}")
            return None
                
        except Exception as e:
            logger.error(f"Error getting caller language for phone_number_id {phone_number_id}: {e}")
            return None

    def _handle_call_started_event(self, data: Dict[str, Any]) -> None:
        """
        Handle call_started events by creating records in retell_event and twilio_call tables
        
        Args:
            data: The webhook payload from Retell AI
        """
        try:
            call_data = data.get('call', {})
            
            # Extract data from call_started payload
            call_id = call_data.get('call_id', '')
            call_type = call_data.get('call_type', '')
            agent_id = call_data.get('agent_id', '')
            agent_name = call_data.get('agent_name', '')
            call_status = call_data.get('call_status', '')
            from_number = call_data.get('from_number', '')
            to_number = call_data.get('to_number', '')
            direction = call_data.get('direction', '')
            
            # Extract Twilio call SID from telephony_identifier
            telephony_identifier = call_data.get('telephony_identifier', {})
            twilio_call_sid = telephony_identifier.get('twilio_call_sid', '')
            
            # Extract dynamic variables if present
            retell_llm_dynamic_variables = call_data.get('retell_llm_dynamic_variables', {})
            
            logger.info(f"Creating database records for call_started event - Call ID: {call_id}, Twilio SID: {twilio_call_sid}")
            
            # 1. Create retell_event record
            retell_event_data = {
                'call_id': call_id,
                'call_type': call_type,
                'agent_id': agent_id,
                'call_status': call_status,
                'from_number': from_number,
                'retell_llm_dynamic_variables': retell_llm_dynamic_variables
            }
            
            retell_response = self.supabase.table('retell_event').insert(retell_event_data).execute()
            if hasattr(retell_response, 'error') and retell_response.error:
                logger.error(f"Error creating retell_event record: {retell_response.error}")
                return
            
            retell_event_id = retell_response.data[0]['id'] if retell_response.data else None
            logger.info(f"Created retell_event record with ID: {retell_event_id}")
            
            # 2. Create twilio_call record (if we have a Twilio call SID)
            if twilio_call_sid:
                twilio_call_data = {
                    'call_sid': twilio_call_sid,
                    'from_number': from_number,
                    'to_number': to_number,
                    'direction': direction,
                    'retell_event_id': retell_event_id  # Link to retell_event
                }
                
                twilio_response = self.supabase.table('twilio_call').insert(twilio_call_data).execute()
                if hasattr(twilio_response, 'error') and twilio_response.error:
                    logger.error(f"Error creating twilio_call record: {twilio_response.error}")
                else:
                    logger.info(f"Created twilio_call record with ID: {twilio_response.data[0]['id'] if twilio_response.data else 'unknown'}")
            else:
                logger.warning("No Twilio call SID found, skipping twilio_call record creation")
                
        except Exception as e:
            logger.error(f"Error handling call_started event: {e}")

    def process_inbound_webhook(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process inbound webhook from Retell AI
        
        Args:
            data: The webhook payload from Retell AI
            
        Returns:
            Response with dynamic variables and metadata
        """
        try:
            event_type = data.get('event', '')
            
            # Handle call_started events - create database records
            if event_type == 'call_started':
                self._handle_call_started_event(data)
            
            # Extract data from the webhook (handle both call_inbound and call_started)
            if event_type == 'call_inbound':
                inbound_data = data.get('call_inbound', {})
            else:
                inbound_data = data.get('call', {})
                
            from_number = inbound_data.get('from_number', '')
            to_number = inbound_data.get('to_number', '')
            agent_id = inbound_data.get('agent_id', '')
            phone_number_id = inbound_data.get('phone_number_id', '')
            
            logger.info(f"Processing inbound webhook - From: {from_number}, To: {to_number}, Agent: {agent_id}")
            
            # Get customer data based on to_number (includes language info)
            customer_data = self._get_customer_data(to_number)
            customer_known = customer_data is not None
            
            # Build dynamic variables
            dynamic_variables = {}
            if customer_known and customer_data:
                # Use customer data from Supabase (includes caller_language and preferred_language)
                dynamic_variables.update(customer_data)
                logger.info(f"Using customer data for known customer: {list(customer_data.keys())}")
            else:
                # Default variables for unknown customers
                dynamic_variables = {
                    'customer_name': 'Valued Customer',
                    'customer_id': 'unknown',
                    'account_type': 'standard',
                    'preferred_language': 'en',
                    'client_name': 'Our Company'
                }
                logger.info("Using default variables for unknown customer")
            
            # Build metadata
            metadata = {
                'inbound_timestamp': datetime.now().isoformat(),
                'from_number': from_number,
                'to_number': to_number,
                'original_agent_id': agent_id,
                'customer_known': customer_known,
                'phone_number_id': phone_number_id
            }
            
            # Build response
            response = {
                'call_inbound': {
                    'dynamic_variables': dynamic_variables,
                    'metadata': metadata
                }
            }
            
            # Add agent override if customer has a preferred agent
            if customer_known and customer_data and 'preferred_agent_id' in customer_data:
                response['call_inbound']['override_agent_id'] = customer_data['preferred_agent_id']
                logger.info(f"Overriding agent to: {customer_data['preferred_agent_id']}")
            
            logger.info(f"Inbound webhook processed successfully. Customer known: {customer_known}")
            return response
            
        except Exception as e:
            logger.error(f"Error processing inbound webhook: {e}")
            # Return a safe default response
            return {
                'call_inbound': {
                    'dynamic_variables': {
                        'customer_name': 'Valued Customer',
                        'customer_id': 'unknown',
                        'account_type': 'standard',
                        'preferred_language': 'en',
                        'client_name': 'Our Company'
                    },
                    'metadata': {
                        'inbound_timestamp': datetime.now().isoformat(),
                        'from_number': from_number if 'from_number' in locals() else 'unknown',
                        'to_number': to_number if 'to_number' in locals() else 'unknown',
                        'original_agent_id': agent_id if 'agent_id' in locals() else 'unknown',
                        'customer_known': False,
                        'error': str(e)
                    }
                }
            }

# Global instance
webhook_service = WebhookService() 