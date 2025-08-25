"""
Webhook service utilities
"""
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import pytz
from supabase import create_client
from twilio.rest import Client
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)

class WebhookService:
    """Service class for processing webhooks"""
    
    def __init__(self):
        """Initialize webhook service"""
        self._supabase_client = None
        self._twilio_client = None

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

    @property
    def twilio(self):
        """Lazy-init Twilio client"""
        if self._twilio_client is None:
            try:
                self._twilio_client = Client(
                    Config.TWILIO_ACCOUNT_SID,
                    Config.TWILIO_AUTH_TOKEN
                )
            except Exception as e:
                logger.error(f"Could not initialize Twilio client: {e}")
                raise
        return self._twilio_client

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
            oh_resp = self.supabase.table('opening_hours').select('day, day_order, start_time, end_time, break_start_time, break_end_time').eq('client_id', client_id).execute()
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
                day_order_field = hours_record.get('day_order', '')
                
                # Convert current weekday to day_order number (1=monday, 7=sunday)
                weekday_to_number = {
                    'monday': 1, 'tuesday': 2, 'wednesday': 3, 'thursday': 4,
                    'friday': 5, 'saturday': 6, 'sunday': 7
                }
                current_day_number = weekday_to_number.get(current_weekday)
                
                # If day is a list (single record with multiple days)
                if isinstance(day_field, list):
                    days = [str(d).lower() for d in day_field]
                    if current_weekday in days:
                        current_day_hours = hours_record
                        break
                # If day is a string or enum (individual day record)
                elif isinstance(day_field, (str, object)):  # Handle both string and enum
                    day = str(day_field).lower()
                    if day == current_weekday:
                        current_day_hours = hours_record
                        break
                # If using day_order (numeric 1-7)
                elif day_order_field and current_day_number:
                    if int(day_order_field) == current_day_number:
                        current_day_hours = hours_record
                        break
            
            if not current_day_hours:
                logger.info(f"No opening hours configured for {current_weekday}")
                return False
            
            start_time = current_day_hours.get('start_time')
            end_time = current_day_hours.get('end_time')
            break_start_time = current_day_hours.get('break_start_time')
            break_end_time = current_day_hours.get('break_end_time')
            
            if not start_time or not end_time:
                logger.warning(f"Incomplete opening hours for {current_weekday}: start={start_time}, end={end_time}")
                return False
            
            logger.info(f"Business hours for {current_weekday}: {start_time} - {end_time}")
            if break_start_time and break_end_time:
                logger.info(f"Break time for {current_weekday}: {break_start_time} - {break_end_time}")
            
            # Convert current time string to time object for comparison
            try:
                from datetime import datetime
                current_time_obj = datetime.strptime(current_time_str, '%H:%M').time()
                
                # Check if within main business hours
                is_within_hours = start_time <= current_time_obj <= end_time
                
                # If there's a break time, check if we're NOT in break
                if break_start_time and break_end_time and is_within_hours:
                    is_in_break = break_start_time <= current_time_obj <= break_end_time
                    is_within_hours = not is_in_break
                    if is_in_break:
                        logger.info(f"Current time {current_time_str} is during break time {break_start_time}-{break_end_time}")
                
                logger.info(f"Current time {current_time_str} within business hours {start_time}-{end_time}: {is_within_hours}")
                return is_within_hours
                
            except ValueError as e:
                logger.error(f"Error parsing time {current_time_str}: {e}")
                return False
            
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
            tw_resp = self.supabase.table('twilio_number').select('client_id, client_ivr_language_configuration_id').eq('twilio_number', cleaned_number).limit(1).execute()
            if not tw_resp.data:
                # Fallback to original number if cleaned doesn't work
                tw_resp = self.supabase.table('twilio_number').select('client_id, client_ivr_language_configuration_id').eq('twilio_number', to_number).limit(1).execute()
            if not tw_resp.data:
                logger.warning(f"No twilio_number record found for: {to_number} (cleaned: {cleaned_number})")
                return None
            client_id = tw_resp.data[0].get('client_id')
            client_ivr_language_configuration_id = tw_resp.data[0].get('client_ivr_language_configuration_id')
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
                dynamic_variables['client_id'] = client_id  # Add client_id for function calls
                dynamic_variables['client_name'] = client_name
                dynamic_variables['client_description'] = client_description
                logger.info(f"Client data - client_id: '{client_id}', name: '{client_name}', description: '{client_description}'")

            # Get client workflow configuration
            wf_resp = self.supabase.table('client_workflow_configuration').select('*').eq('client_id', client_id).limit(1).execute()
            if wf_resp.data:
                wf_config = wf_resp.data[0]
                logger.info(f"Workflow config raw data: {wf_config}")
                # Add workflow configuration as dynamic variables (without workflow_ prefix)
                for key, value in wf_config.items():
                    if key != 'id' and key != 'client_id' and value is not None:
                        dynamic_variables[key] = value
                        logger.info(f"Added {key}: '{value}'")

            # Get client language agent names using the new structure
            if client_ivr_language_configuration_id:
                # Get all languages for this client's IVR configuration
                ivr_lang_resp = self.supabase.table('client_ivr_language_configuration_language').select(
                    'language_id'
                ).eq('client_id', client_id).eq('client_ivr_language_configuration_id', client_ivr_language_configuration_id).execute()
                
                if ivr_lang_resp.data:
                    # Get agent names for each language
                    for lang_record in ivr_lang_resp.data:
                        language_id = lang_record.get('language_id')
                        if language_id:
                            # Get agent name for this language
                            agent_resp = self.supabase.table('client_language_agent_name').select(
                                'agent_name'
                            ).eq('client_id', client_id).eq('language_id', language_id).limit(1).execute()
                            
                            if agent_resp.data:
                                agent_name = agent_resp.data[0].get('agent_name')
                                if agent_name:
                                    # Get language code for the key
                                    lang_resp = self.supabase.table('language').select('language_code').eq('id', language_id).limit(1).execute()
                                    if lang_resp.data:
                                        lang_code = lang_resp.data[0].get('language_code', 'en')
                                        dynamic_variables[f'agent_name_{lang_code}'] = agent_name
                                        logger.info(f"Added agent_name_{lang_code}: {agent_name}")
            else:
                # Fallback: Get all agent names for the client (old method)
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



            logger.info(f"Returning dynamic variables from Supabase: {list(dynamic_variables.keys())}")
            logger.info(f"=== SUPABASE LOOKUP END (async) ===")
            return dynamic_variables
            
        except Exception as e:
            logger.error(f"Error getting customer data for {to_number}: {e}")
            return None

    def _get_or_create_caller(self, from_number: str) -> Optional[str]:
        """
        Get or create a caller record based on from_number
        
        Args:
            from_number: The caller's phone number
            
        Returns:
            Caller ID (UUID) or None if failed
        """
        try:
            logger.info(f"Looking up or creating caller for: {from_number}")
            
            # First, try to find existing caller
            caller_resp = self.supabase.table('caller').select('id').eq('phone_number', from_number).limit(1).execute()
            
            if caller_resp.data:
                # Caller exists
                caller_id = caller_resp.data[0]['id']
                logger.info(f"Found existing caller with ID: {caller_id}")
                return caller_id
            
            # Caller doesn't exist, create new one
            logger.info(f"Creating new caller record for: {from_number}")
            new_caller_data = {
                'phone_number': from_number,
                'is_customer': 'unknown'  # We don't know yet
            }
            
            create_resp = self.supabase.table('caller').insert(new_caller_data).execute()
            if hasattr(create_resp, 'error') and create_resp.error:
                logger.error(f"Error creating caller record: {create_resp.error}")
                return None
            
            caller_id = create_resp.data[0]['id'] if create_resp.data else None
            logger.info(f"Created new caller with ID: {caller_id}")
            return caller_id
            
        except Exception as e:
            logger.error(f"Error in _get_or_create_caller: {e}")
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

    def _update_twilio_call_details(self, call_sid: str) -> None:
        """
        Fetch call details from Twilio API and update the twilio_call record
        
        Args:
            call_sid: The Twilio call SID to fetch details for
        """
        try:
            logger.info(f"Fetching Twilio call details for SID: {call_sid}")
            
            # Fetch call details from Twilio
            call = self.twilio.calls(call_sid).fetch()
            
            # Debug: Log available attributes
            logger.info(f"Twilio call object attributes: {dir(call)}")
            logger.info(f"Twilio call object: {call}")
            
            # Extract call details - use proper Twilio API attributes
            twilio_call_data = {
                'account_sid': getattr(call, 'account_sid', None),
                'from_number': getattr(call, 'from_', None),
                'to_number': getattr(call, 'to', None),
                'start_time': call.start_time.isoformat() if hasattr(call, 'start_time') and call.start_time else None,
                'end_time': call.end_time.isoformat() if hasattr(call, 'end_time') and call.end_time else None,
                'duration': getattr(call, 'duration', None),
                'direction': getattr(call, 'direction', None),
                'answered_by': getattr(call, 'answered_by', None),
                'forwarded_from': getattr(call, 'forwarded_from', None),
                'price': getattr(call, 'price', None),
                'call_type': getattr(call, 'call_type', None)
            }
            
            # Remove None values to avoid overwriting with null
            twilio_call_data = {k: v for k, v in twilio_call_data.items() if v is not None}
            
            logger.info(f"Twilio call details - Duration: {twilio_call_data.get('duration')}s, Direction: {twilio_call_data.get('direction')}")
            
            # Update the twilio_call record
            twilio_response = self.supabase.table('twilio_call').update(twilio_call_data).eq('call_sid', call_sid).execute()
            if hasattr(twilio_response, 'error') and twilio_response.error:
                logger.error(f"Error updating twilio_call record: {twilio_response.error}")
            else:
                logger.info(f"Successfully updated twilio_call record with Twilio details")
                
        except Exception as e:
            logger.error(f"Error fetching/updating Twilio call details: {e}")

    def _generate_node_transcript(self, transcript_with_tool_calls: str) -> str:
        """
        Generate a node-based transcript from transcript_with_tool_calls data
        
        Args:
            transcript_with_tool_calls: The raw transcript with tool calls from Retell AI
            
        Returns:
            Formatted node transcript string
        """
        try:
            if not transcript_with_tool_calls:
                logger.warning("transcript_with_tool_calls is empty or None")
                return ""
            
            # transcript_with_tool_calls is already a Python object, not JSON string
            steps = transcript_with_tool_calls
            logger.info(f"Processing transcript_with_tool_calls with {len(steps)} steps")
            
            # Initialize tracking variables
            current_node = "begin"
            node_start = None
            node_end = None
            buffer = []
            node_transcript_parts = []
            
            for step in steps:
                step_type = step.get('type', '')
                
                # Handle node transitions
                if step_type == "node_transition":
                    # Finalize current node if we have content
                    if buffer and node_start is not None:
                        node_summary = f"[Node: {current_node}] (Start: {node_start:.4f}s - End: {node_end:.4f}s)\n" + "\n".join(buffer)
                        node_transcript_parts.append(node_summary)
                    
                    # Start new node
                    current_node = step.get('new_node_name', 'unknown')
                    node_start = None
                    node_end = None
                    buffer = []
                
                # Handle agent speech
                elif step_type == "agent" and step.get('words'):
                    words = step.get('words', [])
                    if words:
                        first = words[0]
                        last = words[-1]
                        node_start = node_start or first.get('start', 0)
                        node_end = last.get('end', 0)
                        buffer.append(f'Agent: "{step.get("content", "")}"')
                
                # Handle user speech
                elif step_type == "user" and step.get('words'):
                    words = step.get('words', [])
                    if words:
                        first = words[0]
                        last = words[-1]
                        node_start = node_start or first.get('start', 0)
                        node_end = last.get('end', 0)
                        buffer.append(f'User: "{step.get("content", "")}"')
                
                # Handle DTMF (touch-tone)
                elif step_type == "dtmf":
                    buffer.append(f'User: Pressed DTMF "{step.get("digit", "")}"')
                
                # Handle tool calls
                elif step_type == "tool_call_invocation":
                    tool_name = step.get('tool_name', '')
                    if tool_name == "extract_dynamic_variables":
                        buffer.append("System: Detected language as Dutch")
                    elif tool_name == "agent_swap":
                        agent_id = step.get('agent_id', 'unknown')
                        buffer.append(f"System: Swapped to Dutch agent ({agent_id})")
                    else:
                        buffer.append(f"System: Executed tool {tool_name}")
            
            # Finalize the last node
            if buffer and node_start is not None:
                node_summary = f"[Node: {current_node}] (Start: {node_start:.4f}s - End: {node_end:.4f}s)\n" + "\n".join(buffer)
                node_transcript_parts.append(node_summary)
            
            # Join all node parts
            node_transcript = "\n\n".join(node_transcript_parts)
            logger.info(f"Generated node transcript with {len(node_transcript_parts)} nodes")
            return node_transcript
            
        except Exception as e:
            logger.error(f"Error generating node transcript: {e}")
            return ""

    def _handle_call_ended_event(self, data: Dict[str, Any]) -> None:
        """
        Handle call_ended events by updating existing retell_event record
        
        Args:
            data: The webhook payload from Retell AI
        """
        try:
            call_data = data.get('call', {})
            
            # Extract data from call_ended payload
            call_id = call_data.get('call_id', '')
            call_status = call_data.get('call_status', '')
            end_timestamp = call_data.get('end_timestamp', '')
            disconnection_reason = call_data.get('disconnection_reason', '')
            transcript = call_data.get('transcript', '')
            transcript_object = call_data.get('transcript_object', '')
            transcript_with_tool_calls = call_data.get('transcript_with_tool_calls', '')
            node_transcript = call_data.get('node_transcript', '')
            recording_url = call_data.get('recording_url', '')
            opt_out_sensitive_data_storage = call_data.get('opt_out_sensitive_data_storage', False)
            
            logger.info(f"Updating retell_event record for call_ended event - Call ID: {call_id}")
            
            # Find existing retell_event record by call_id
            retell_resp = self.supabase.table('retell_event').select('id').eq('call_id', call_id).limit(1).execute()
            if not retell_resp.data:
                logger.error(f"No retell_event record found for call_id: {call_id}")
                return
            
            retell_event_id = retell_resp.data[0]['id']
            logger.info(f"Found existing retell_event record with ID: {retell_event_id}")
            
            # Generate node transcript from transcript_with_tool_calls
            logger.info(f"Generating node transcript - transcript_with_tool_calls length: {len(transcript_with_tool_calls) if transcript_with_tool_calls else 0}")
            logger.info(f"transcript_with_tool_calls preview: {transcript_with_tool_calls[:200] if transcript_with_tool_calls else 'None'}")
            generated_node_transcript = self._generate_node_transcript(transcript_with_tool_calls)
            logger.info(f"Generated node transcript length: {len(generated_node_transcript) if generated_node_transcript else 0}")
            logger.info(f"Generated node transcript preview: {generated_node_transcript[:200] if generated_node_transcript else 'None'}")
            
            # Update retell_event record with call_ended data
            update_data = {
                'call_status': call_status,
                'end_timestamp': end_timestamp,
                'disconnection_reason': disconnection_reason,
                'transcript': transcript,
                'transcript_object': transcript_object,
                'transcript_with_tool_calls': transcript_with_tool_calls,
                'node_transcript': generated_node_transcript,
                'recording_url': recording_url,
                'opt_out_sensitive_data_storage': opt_out_sensitive_data_storage
            }
            
            # Remove None values to avoid overwriting with null
            update_data = {k: v for k, v in update_data.items() if v is not None}
            
            retell_response = self.supabase.table('retell_event').update(update_data).eq('id', retell_event_id).execute()
            if hasattr(retell_response, 'error') and retell_response.error:
                logger.error(f"Error updating retell_event record: {retell_response.error}")
            else:
                logger.info(f"Successfully updated retell_event record for call_ended event")
                
        except Exception as e:
            logger.error(f"Error handling call_ended event: {e}")

    def _handle_call_analyzed_event(self, data: Dict[str, Any]) -> None:
        """
        Handle call_analyzed events by updating existing retell_event record with call analysis data
        and then fetching complete call details from Twilio
        
        Args:
            data: The webhook payload from Retell AI
        """
        try:
            call_data = data.get('call', {})
            
            # Extract call_id from call_analyzed payload
            call_id = call_data.get('call_id', '')
            
            # Extract call_analysis data
            call_analysis = call_data.get('call_analysis', {})
            call_summary = call_analysis.get('call_summary', '')
            in_voicemail = call_analysis.get('in_voicemail', False)
            user_sentiment = call_analysis.get('user_sentiment', '')
            call_successful = call_analysis.get('call_successful', False)
            custom_analysis_data = call_analysis.get('custom_analysis_data', {})
            
            logger.info(f"Updating retell_event record for call_analyzed event - Call ID: {call_id}")
            logger.info(f"Call analysis - Summary: {call_summary[:100]}..., Voicemail: {in_voicemail}, Sentiment: {user_sentiment}, Successful: {call_successful}")
            
            # Find existing retell_event record by call_id
            retell_resp = self.supabase.table('retell_event').select('id').eq('call_id', call_id).limit(1).execute()
            if not retell_resp.data:
                logger.error(f"No retell_event record found for call_id: {call_id}")
                return
            
            retell_event_id = retell_resp.data[0]['id']
            logger.info(f"Found existing retell_event record with ID: {retell_event_id}")
            
            # Update retell_event record with call_analysis data
            update_data = {
                'call_status': 'analyzed',  # Update call status to analyzed
                'call_summary': call_summary,
                'in_voicemail': in_voicemail,
                'user_sentiment': user_sentiment,
                'call_successful': call_successful,
                'custom_analysis_data': custom_analysis_data
            }
            
            # Remove None values to avoid overwriting with null
            update_data = {k: v for k, v in update_data.items() if v is not None}
            
            retell_response = self.supabase.table('retell_event').update(update_data).eq('id', retell_event_id).execute()
            if hasattr(retell_response, 'error') and retell_response.error:
                logger.error(f"Error updating retell_event record: {retell_response.error}")
            else:
                logger.info(f"Successfully updated retell_event record for call_analyzed event with call analysis data")
            
            # Now fetch and update Twilio call details
            telephony_identifier = call_data.get('telephony_identifier', {})
            twilio_call_sid = telephony_identifier.get('twilio_call_sid', '')
            
            if twilio_call_sid:
                logger.info(f"Fetching Twilio call details for SID: {twilio_call_sid}")
                self._update_twilio_call_details(twilio_call_sid)
            else:
                logger.warning("No Twilio call SID found, skipping Twilio call details update")
                
        except Exception as e:
            logger.error(f"Error handling call_analyzed event: {e}")

    def _handle_call_started_event(self, data: Dict[str, Any]) -> None:
        """
        Handle call_started events by updating existing retell_event record and creating twilio_call record
        
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
            
            # Get retell_event_id, caller_id, and original_call_sid from dynamic variables
            retell_event_id = retell_llm_dynamic_variables.get('retell_event_id')
            caller_id = retell_llm_dynamic_variables.get('caller_id')
            original_call_sid = retell_llm_dynamic_variables.get('original_call_sid')  # Media Stream CallSid
            
            logger.info(f"Updating retell_event for call_started event - Call ID: {call_id}, Retell Event ID: {retell_event_id}, Twilio SID: {twilio_call_sid}, Original CallSid: {original_call_sid}")
            
            if not retell_event_id:
                logger.error("No retell_event_id found in dynamic variables")
                return
            
            # 1. Update existing retell_event record
            retell_event_update_data = {
                'call_id': call_id,
                'call_type': call_type,
                'agent_id': agent_id,
                'call_status': call_status,
                'direction': direction,
                'retell_llm_dynamic_variables': retell_llm_dynamic_variables
            }
            
            retell_response = self.supabase.table('retell_event').update(retell_event_update_data).eq('id', retell_event_id).execute()
            if hasattr(retell_response, 'error') and retell_response.error:
                logger.error(f"Error updating retell_event record: {retell_response.error}")
                return
            
            logger.info(f"Updated retell_event record with ID: {retell_event_id}")
            
            # 2. Create twilio_call record (if we have a Twilio call SID)
            if original_call_sid and caller_id:
                # Use the original_call_sid (Media Stream CallSid) for the database record
                # This ensures transcription can find the correct record
                twilio_call_data = {
                    'call_sid': original_call_sid,  # Media Stream CallSid
                    'from_number': from_number,
                    'to_number': to_number,
                    'direction': direction,
                    'retell_event_id': retell_event_id,  # Link to retell_event
                    'caller_id': caller_id  # Link to caller
                }
                
                twilio_response = self.supabase.table('twilio_call').insert(twilio_call_data).execute()
                if hasattr(twilio_response, 'error') and twilio_response.error:
                    logger.error(f"Error creating twilio_call record: {twilio_response.error}")
                else:
                    logger.info(f"Created twilio_call record with ID: {twilio_response.data[0]['id'] if twilio_response.data else 'unknown'}")
            else:
                if not original_call_sid:
                    logger.warning("No original_call_sid found in dynamic variables, skipping twilio_call record creation")
                if not caller_id:
                    logger.warning("No caller_id found in dynamic variables, skipping twilio_call record creation")
                
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
            
            # Handle call_ended events - update existing retell_event record
            if event_type == 'call_ended':
                self._handle_call_ended_event(data)
            
            # Handle call_analyzed events - update existing retell_event record
            if event_type == 'call_analyzed':
                self._handle_call_analyzed_event(data)
            
            # Only process inbound webhook response for call_inbound events
            if event_type == 'call_inbound':
                # Extract data from call_inbound webhook
                inbound_data = data.get('call_inbound', {})
                from_number = inbound_data.get('from_number', '')
                to_number = inbound_data.get('to_number', '')
                agent_id = inbound_data.get('agent_id', '')
                phone_number_id = inbound_data.get('phone_number_id', '')
                
                logger.info(f"Processing inbound webhook - From: {from_number}, To: {to_number}, Agent: {agent_id}")
                
                # 1. Get or create caller record
                caller_id = self._get_or_create_caller(from_number)
                if not caller_id:
                    logger.error(f"Failed to get or create caller for: {from_number}")
                    return {'error': 'Failed to process caller'}, 500
                
                # 2. Create initial retell_event record
                retell_event_data = {
                    'from_number': from_number,
                    'to_number': to_number,
                    'agent_id': agent_id,
                    'call_status': 'inbound',  # Initial status
                    'direction': 'inbound'
                }
                
                retell_response = self.supabase.table('retell_event').insert(retell_event_data).execute()
                if hasattr(retell_response, 'error') and retell_response.error:
                    logger.error(f"Error creating retell_event record: {retell_response.error}")
                    return {'error': 'Failed to create call record'}, 500
                
                retell_event_id = retell_response.data[0]['id'] if retell_response.data else None
                logger.info(f"Created retell_event record with ID: {retell_event_id}")
                
                # 3. Get customer data based on to_number
                customer_data = self._get_customer_data(to_number)
                
                # 4. Build dynamic variables
                dynamic_variables = {}
                if customer_data:
                    # Use customer data from Supabase
                    dynamic_variables.update(customer_data)
                    logger.info(f"Using customer data for known customer: {list(customer_data.keys())}")
                else:
                    # Default variables for unknown customers
                    dynamic_variables = {
                        'customer_name': 'Valued Customer',
                        'customer_id': 'unknown',
                        'account_type': 'standard',
                        'client_name': 'Our Company'
                    }
                    logger.info("Using default variables for unknown customer")
                
                # 5. Add retell_event_id and caller_id to dynamic variables
                dynamic_variables['retell_event_id'] = retell_event_id
                dynamic_variables['caller_id'] = caller_id
                
                # 6. Build metadata
                metadata = {
                    'inbound_timestamp': datetime.now().isoformat(),
                    'phone_number_id': phone_number_id
                }
                
                # 7. Build response
                response = {
                    'call_inbound': {
                        'dynamic_variables': dynamic_variables,
                        'metadata': metadata
                    }
                }
                
                # 8. Add agent override if customer has a preferred agent
                if customer_data and 'preferred_agent_id' in customer_data:
                    response['call_inbound']['override_agent_id'] = customer_data['preferred_agent_id']
                    logger.info(f"Overriding agent to: {customer_data['preferred_agent_id']}")
                
                logger.info(f"Inbound webhook processed successfully. Retell Event ID: {retell_event_id}, Caller ID: {caller_id}")
                return response
            else:
                # For other events (call_started, call_ended, call_analyzed), just return success
                logger.info(f"Processed {event_type} event successfully")
                return {'status': 'success', 'event': event_type}
            
        except Exception as e:
            logger.error(f"Error processing inbound webhook: {e}")
            # Return a safe default response
            return {
                'call_inbound': {
                    'dynamic_variables': {
                        'customer_name': 'Valued Customer',
                        'customer_id': 'unknown',
                        'account_type': 'standard',
                        'client_name': 'Our Company'
                    },
                    'metadata': {
                        'inbound_timestamp': datetime.now().isoformat(),
                        'caller_known': False,
                        'error': str(e)
                    }
                }
            }

# Global instance
webhook_service = WebhookService() 