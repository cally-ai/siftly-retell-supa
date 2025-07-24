"""
Webhook service for processing Retell AI webhooks
"""
import json
import asyncio
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from pyairtable import Table
from config import Config
from utils.logger import get_logger
from utils.validators import validate_retell_webhook, validate_retell_inbound_webhook, sanitize_webhook_data
from services.airtable_service import airtable_service
from services.deepgram_service import get_deepgram_service
from services.redis_client import redis_client, is_redis_configured

logger = get_logger(__name__)

class WebhookService:
    """Service class for processing webhooks"""
    
    def __init__(self):
        """Initialize webhook service"""
        self.keywords = [
            'urgent', 'important', 'issue', 'problem', 'help', 'emergency',
            'broken', 'error', 'failed', 'support', 'assistance', 'critical'
        ]

    
    def process_retell_webhook(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming Retell AI webhook
        
        Args:
            data: Raw webhook data from Retell AI
        
        Returns:
            Processed webhook data with additional insights
        """
        # Add webhook deduplication logging (skip detailed logging for call_started)
        call_id = data.get('call', {}).get('call_id', 'unknown')
        event_type = data.get('event', 'unknown')
        
        # Minimal logging for all events
        if event_type == 'call_started':
            logger.info(f"Call started: {call_id}")
        elif event_type == 'call_analyzed':
            logger.info(f"Call analyzed: {call_id}")
        elif event_type == 'call_ended':
            # Keep some details for call_ended but minimal
            from_num = data.get('call', {}).get('from_number', 'unknown')
            to_num = data.get('call', {}).get('to_number', 'unknown')
            duration_ms = data.get('call', {}).get('duration_ms', 0)
            duration_s = duration_ms // 1000 if duration_ms else 0
            logger.info(f"Call ended: {call_id} ({from_num} → {to_num}, {duration_s}s)")
        
        event_type = data.get('event', 'unknown')
        # Removed verbose call event logging to reduce bloat
        
        # Validate webhook data
        is_valid, errors = validate_retell_webhook(data)
        if not is_valid:
            logger.error(f"Invalid webhook data: {errors}")
            raise ValueError(f"Invalid webhook data: {errors}")
        
        # Sanitize data
        sanitized_data = sanitize_webhook_data(data)
        
        # Extract and process webhook information
        webhook_data = self._extract_webhook_data(sanitized_data)
        
        # Add processing insights
        processed_data = self._add_insights(webhook_data)
        
        # Save to Airtable (only for call_analyzed events)
        self._save_to_airtable(processed_data)
        
        # Perform additional processing based on event type
        self._handle_event_specific_processing(processed_data)
        
        return processed_data
    
    def process_inbound_webhook(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming inbound call webhook from Retell AI
        
        Args:
            data: Raw inbound webhook data from Retell AI
        
        Returns:
            Response data with dynamic variables and configuration
        """
        start_time = time.time()
        event_type = data.get('event', 'unknown')
        # Removed verbose inbound webhook logging to reduce bloat
        
        # Validate inbound webhook data
        validation_start = time.time()
        is_valid, errors = validate_retell_inbound_webhook(data)
        validation_duration = time.time() - validation_start
        # Removed validation duration logging to reduce bloat
        
        if not is_valid:
            logger.error(f"Invalid inbound webhook data: {errors}")
            raise ValueError(f"Invalid inbound webhook data: {errors}")
        
        # Extract inbound call data
        inbound_data = data.get('call_inbound', {})
        from_number = inbound_data.get('from_number', '')
        to_number = inbound_data.get('to_number', '')
        agent_id = inbound_data.get('agent_id', '')
        
        # Get client name for better logging
        customer_data = self._get_customer_data(to_number)
        client_name = customer_data.get('client_name', 'Unknown') if customer_data else 'Unknown'
        logger.info(f"Inbound call: {from_number} → {to_number} ({client_name})")
        
        # Get dynamic variables and configuration based on caller
        config_start = time.time()
        response_data = self._get_inbound_configuration(from_number, to_number, agent_id)
        # Removed verbose timing and response logging to reduce bloat
        
        return response_data
    
    def _get_inbound_configuration(self, from_number: str, to_number: str, agent_id: str) -> Dict[str, Any]:
        """
        Get dynamic variables and configuration for inbound call
        
        Args:
            from_number: Caller's phone number
            to_number: Receiver's phone number
            agent_id: Default agent ID (if configured)
        
        Returns:
            Configuration response for Retell AI
        """
        # Initialize response structure
        response = {
            "call_inbound": {}
        }
        
        # Example logic: Different dynamic variables based on caller
        # You can customize this based on your business logic
        
        # Check if we have customer data for this number
        # Removed verbose customer data lookup logging to reduce bloat
        
        lookup_start = time.time()
        customer_data = self._get_customer_data(to_number)
        lookup_duration = time.time() - lookup_start
        # Removed lookup duration logging to reduce bloat
        
        if customer_data:
            # Known customer - use their specific dynamic variables from Airtable
            dynamic_vars = customer_data
            
            # Override agent if customer has a preferred agent
            if customer_data.get('preferred_agent_id'):
                response["call_inbound"]["override_agent_id"] = customer_data['preferred_agent_id']
            
        else:
            # Unknown caller - use default configuration
            dynamic_vars = {
                "customer_name": "New Customer",
                "customer_id": "",
                "account_type": "new",
                "preferred_language": "English",
                "company_name": "Your Company",
                "company_name_agent": "Assistant"
            }
        
        # Add metadata for tracking
        metadata = {
            "inbound_timestamp": datetime.now().isoformat(),
            "from_number": from_number,
            "to_number": to_number,
            "original_agent_id": agent_id,
            "customer_known": customer_data is not None
        }
        
        # Build response
        response["call_inbound"]["dynamic_variables"] = dynamic_vars
        response["call_inbound"]["metadata"] = metadata
        
        return response
    
    async def _get_customer_data_async(self, to_number: str) -> Optional[Dict[str, Any]]:
        """
        Get customer data from Airtable based on to_number (async version)
        
        Args:
            to_number: The phone number to look up
        
        Returns:
            Customer data dictionary or None if not found
        """

        logger.info(f"=== AIRTABLE LOOKUP START (async) ===")
        
        try:
            # Step 1: Find the to_number in TABLE_ID_TWILIO_NUMBER
            twilio_table = Table(Config.AIRTABLE_API_KEY, Config.AIRTABLE_BASE_ID, 'tbl0PeZoX2qgl74ZT')
            logger.info(f"Searching Twilio table for number: {to_number}")
            twilio_records = await asyncio.to_thread(
                twilio_table.all, formula=f"{{twilio_number}} = '{to_number}'"
            )
            
            logger.info(f"Found {len(twilio_records)} Twilio records")
            
            if not twilio_records:
                logger.warning(f"No Twilio number found for: {to_number}")
                return None
            
            # Get the client record ID from the first match
            twilio_record = twilio_records[0]
            client_record_id = twilio_record['fields'].get('client', [None])[0] if twilio_record['fields'].get('client') else None
            
            if not client_record_id:
                logger.warning(f"No client linked to Twilio number: {to_number}")
                return None
            
            # Step 2-4: Run client + dynamic vars + language lookups in parallel
            client_table = Table(Config.AIRTABLE_API_KEY, Config.AIRTABLE_BASE_ID, 'tblkyQzhGKVv6H03U')
            dynamic_table = Table(Config.AIRTABLE_API_KEY, Config.AIRTABLE_BASE_ID, 'tblGIPAQZ2rgn6naD')
            
            # Get client record first to extract metadata
            client_record = await asyncio.to_thread(client_table.get, client_record_id)
            
            if not client_record:
                logger.warning(f"Client record not found: {client_record_id}")
                return None
            
            client_fields = client_record['fields']
            
            # Extract IDs for parallel lookups
            dynamic_variables_record_id = client_fields.get('dynamic_variables', [None])[0] if client_fields.get('dynamic_variables') else None
            language_agent_names = client_fields.get('language_agent_names', [])
            
            if not dynamic_variables_record_id:
                logger.warning(f"No dynamic variables ID found for client: {client_record_id}")
                return None
            
            # Prepare parallel tasks
            tasks = []
            
            # Task 1: Get dynamic variables
            dynamic_record_task = asyncio.to_thread(dynamic_table.get, dynamic_variables_record_id)
            tasks.append(dynamic_record_task)
            
            # Task 2+: Get language agent names
            language_tasks = []
            if language_agent_names:
                language_table = Table(Config.AIRTABLE_API_KEY, Config.AIRTABLE_BASE_ID, 'tblT79Xju3vLxNipr')
                for linked_record_id in language_agent_names:
                    language_tasks.append(asyncio.to_thread(language_table.get, linked_record_id))
                tasks.extend(language_tasks)
            
            # Execute all lookups in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            dynamic_record = results[0]
            language_records = results[1:] if len(results) > 1 else []
            
            # Check for exceptions
            if isinstance(dynamic_record, Exception):
                logger.error(f"Error getting dynamic record: {dynamic_record}")
                return None
            
            # Build dynamic variables dictionary
            dynamic_variables = {}
            
            # Add dynamic variables
            if dynamic_record:
                dynamic_fields = dynamic_record['fields']
                excluded_fields = ['name', 'client_dynamic_variables_id', 'client']
                for field_name, field_value in dynamic_fields.items():
                    if field_name not in excluded_fields:
                        dynamic_variables[field_name] = field_value
            
            # Add language agent mappings
            for i, lang_rec in enumerate(language_records):
                if isinstance(lang_rec, Exception):
                    logger.warning(f"Error getting language record {language_agent_names[i]}: {lang_rec}")
                    continue
                if lang_rec:
                    key_pair_value = lang_rec['fields'].get('key_pair', '')
                    if key_pair_value and '=' in key_pair_value:
                        parts = key_pair_value.split('=', 1)
                        if len(parts) == 2:
                            key = parts[0].strip()
                            value = parts[1].strip()
                            dynamic_variables[key] = value

            

            logger.info(f"Returning dynamic variables: {dynamic_variables}")
            logger.info(f"=== AIRTABLE LOOKUP END (async) ===")
            
            return dynamic_variables
            
        except Exception as e:
            logger.error(f"Error getting customer data for {to_number}: {e}")
            return None

    def _get_customer_data(self, to_number: str) -> Optional[Dict[str, Any]]:
        """
        Get customer data from Airtable based on to_number (sync wrapper with Redis cache)
        
        Args:
            to_number: The phone number to look up
        
        Returns:
            Customer data dictionary or None if not found
        """
        # Check Redis cache first if configured
        if is_redis_configured():
            try:
                cached_data = asyncio.run(redis_client.get(to_number))
                if cached_data:
                    logger.info(f"Redis cache hit for {to_number}")
                    return json.loads(cached_data)
                else:
                    logger.info(f"Redis cache miss for {to_number}")
            except Exception as e:
                logger.warning(f"Redis cache error for {to_number}: {e}")
        
        # Fallback to Airtable lookup
        logger.info(f"Performing Airtable lookup for {to_number}")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(self._get_customer_data_async(to_number))
            
            # Cache result in Redis if found and Redis is configured
            if data and is_redis_configured():
                try:
                    asyncio.run(redis_client.set(to_number, json.dumps(data), ex=10800))  # 3 hours TTL
                    logger.info(f"Cached data for {to_number} in Redis")
                except Exception as e:
                    logger.warning(f"Failed to cache data for {to_number}: {e}")
            
            return data
        finally:
            if 'loop' in locals():
                loop.close()
    
    def _extract_webhook_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and structure webhook data from Retell AI format
        
        Args:
            data: Sanitized webhook data
        
        Returns:
            Structured webhook data
        """
        # Extract call object from Retell webhook format
        call_data = data.get('call', {})
        
        # Removed verbose field extraction logging to reduce bloat
        
        # Check for fields that might be at different levels
        recording_url = call_data.get('recording_url', '')
        duration_ms = call_data.get('duration_ms', 0)
        collected_dynamic_variables = call_data.get('collected_dynamic_variables', {})
        call_cost = call_data.get('call_cost', {})
        
        # Calculate duration from timestamps
        start_timestamp = call_data.get('start_timestamp', 0)
        end_timestamp = call_data.get('end_timestamp', 0)
        duration_seconds = (end_timestamp - start_timestamp) / 1000 if end_timestamp > start_timestamp else 0
        
        # Extract twilio_call_sid from telephony_identifier
        telephony_identifier = call_data.get('telephony_identifier', {})
        twilio_call_sid = telephony_identifier.get('twilio_call_sid', '')
        
        # Generate node-based transcript summary
        node_transcript = self._generate_node_transcript(call_data.get('transcript_with_tool_calls', []))
        
        return {
            'timestamp': datetime.now().isoformat(),
            'raw_data': data,
            'event_type': data.get('event', 'unknown'),
            'call_id': call_data.get('call_id', ''),
            'agent_id': call_data.get('agent_id', ''),
            'call_type': call_data.get('call_type', ''),
            'from_number': call_data.get('from_number', ''),
            'to_number': call_data.get('to_number', ''),
            'direction': call_data.get('direction', ''),
            'call_status': call_data.get('call_status', ''),
            'disconnection_reason': call_data.get('disconnection_reason', ''),
            'transcript': call_data.get('transcript', ''),
            'transcript_object': call_data.get('transcript_object', {}),
            'transcript_with_tool_calls': call_data.get('transcript_with_tool_calls', []),
            'start_timestamp': start_timestamp,
            'end_timestamp': end_timestamp,
            'duration_seconds': duration_seconds,
            'duration_ms': call_data.get('duration_ms', 0),
            'metadata': call_data.get('metadata', {}),
            'retell_llm_dynamic_variables': call_data.get('retell_llm_dynamic_variables', {}),
            'collected_dynamic_variables': call_data.get('collected_dynamic_variables', {}),
            'recording_url': call_data.get('recording_url', ''),
            'call_cost': call_data.get('call_cost', {}),
            'opt_out_sensitive_data_storage': call_data.get('opt_out_sensitive_data_storage', False),
            'call_analysis': call_data.get('call_analysis', {}),
            'twilio_call_sid': twilio_call_sid,
            'node_transcript': node_transcript
        }
    
    def _generate_node_transcript(self, transcript_with_tool_calls: List[Dict[str, Any]]) -> str:
        """
        Generate a human-readable, node-based summary of the call transcript with timestamps
        
        Args:
            transcript_with_tool_calls: List of transcript steps from Retell AI
        
        Returns:
            Formatted string with node-based transcript summary
        """
        if not transcript_with_tool_calls:
            return ""
        
        node_summaries = []
        current_node = "begin"
        node_start = None
        node_end = None
        buffer = []
        
        # Removed logging to reduce log bloat
        
        # Loop over transcript entries
        for step in transcript_with_tool_calls:
            if step.get('role') == "node_transition":
                # If ending a node, finalize it
                if buffer and node_start is not None and node_end is not None:
                    node_summary = f"[Node: {current_node}] (Start: {node_start:.4f}s - End: {node_end:.4f}s)\n" + "\n".join(buffer)
                    node_summaries.append(node_summary)
                
                # Transition to the new node
                current_node = step.get('new_node_name', 'unknown')
                buffer = []
                node_start = None
                node_end = None
                continue
            
            if step.get('role') == "agent" and step.get('words'):
                # Use first and last word for timestamp range
                words = step['words']
                if words:
                    first = words[0]
                    last = words[-1]
                    node_start = node_start or first.get('start', 0)
                    node_end = last.get('end', 0)
                    buffer.append(f'Agent: "{step.get("content", "")}"')
            
            if step.get('role') == "dtmf":
                buffer.append(f'User: Pressed DTMF "{step.get("digit", "")}"')
            
            if step.get('role') == "tool_call_invocation":
                tool_name = step.get('name', '')
                if tool_name == "extract_dynamic_variables":
                    try:
                        args = json.loads(step.get('arguments', '{}'))
                        detected = next((arg for arg in args if arg.get('name') == "caller_language"), None)
                        if detected:
                            buffer.append("System: Detected language as Dutch")
                    except (json.JSONDecodeError, KeyError):
                        logger.warning("Failed to parse extract_dynamic_variables arguments")
                
                elif tool_name == "agent_swap":
                    try:
                        args = json.loads(step.get('arguments', '{}'))
                        agent_id = args.get('agentId', 'unknown')
                        buffer.append(f"System: Swapped to Dutch agent ({agent_id})")
                    except (json.JSONDecodeError, KeyError):
                        logger.warning("Failed to parse agent_swap arguments")
            
            if step.get('role') == "tool_call_result" and step.get('content', '').find("transferred") != -1:
                try:
                    content = json.loads(step.get('content', '{}'))
                    status = content.get('status', 'Unknown transfer status')
                    buffer.append(f"System: {status}")
                except (json.JSONDecodeError, KeyError):
                    logger.warning("Failed to parse tool_call_result content")
        
        # Push final node if any content left
        if buffer and node_start is not None and node_end is not None:
            node_summary = f"[Node: {current_node}] (Start: {node_start:.4f}s - End: {node_end:.4f}s)\n" + "\n".join(buffer)
            node_summaries.append(node_summary)
        
        # Join the full transcript string
        full_transcript = "\n\n".join(node_summaries)
        
        return full_transcript
    
    def _add_insights(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add insights and analysis to webhook data
        
        Args:
            webhook_data: Structured webhook data
        
        Returns:
            Webhook data with insights
        """
        insights = {
            'call_processed': True,
            'processing_timestamp': datetime.now().isoformat(),
            'keywords_found': [],
            'sentiment_score': self._calculate_sentiment_score(webhook_data.get('sentiment', '')),
            'priority_level': 'normal',
            'requires_followup': False
        }
        
        # Analyze transcript for keywords
        if webhook_data.get('transcript'):
            transcript = webhook_data['transcript'].lower()
            found_keywords = []
            
            for keyword in self.keywords:
                if keyword in transcript:
                    found_keywords.append(keyword)
            
            insights['keywords_found'] = found_keywords
            
            # Determine priority based on keywords
            if any(word in ['urgent', 'emergency', 'critical'] for word in found_keywords):
                insights['priority_level'] = 'high'
                insights['requires_followup'] = True
            elif any(word in ['important', 'issue', 'problem'] for word in found_keywords):
                insights['priority_level'] = 'medium'
                insights['requires_followup'] = True
        
        # Analyze sentiment
        if webhook_data.get('sentiment') == 'negative':
            insights['requires_followup'] = True
        
        # Analyze duration for potential issues
        duration = webhook_data.get('duration_seconds', 0)
        if duration > 600:  # More than 10 minutes
            insights['long_call'] = True
            if insights['priority_level'] == 'normal':
                insights['priority_level'] = 'medium'
        
        webhook_data['insights'] = insights
        return webhook_data
    
    def _calculate_sentiment_score(self, sentiment: str) -> float:
        """
        Calculate sentiment score
        
        Args:
            sentiment: Sentiment string
        
        Returns:
            Sentiment score (0.0 to 1.0)
        """
        sentiment_scores = {
            'positive': 0.8,
            'negative': 0.2,
            'neutral': 0.5,
            'mixed': 0.5
        }
        return sentiment_scores.get(sentiment.lower(), 0.5)
    
    def _save_to_airtable(self, webhook_data: Dict[str, Any]) -> bool:
        """
        Save webhook data to Airtable
        
        Args:
            webhook_data: Processed webhook data
        
        Returns:
            True if successful, False otherwise
        """
        # Only save call details when event is "call_ended"
        event_type = webhook_data.get('event_type', 'unknown')
        if event_type != 'call_ended':
            logger.info(f"Skipping Airtable save for event type: {event_type} (only saving 'call_ended' events)")
            return True  # Return True since this is expected behavior
        
        # Check if a record with this call_id already exists to prevent duplicates
        call_id = webhook_data.get('call_id', '')
        if call_id:
            existing_records = airtable_service.search_records('call_id', call_id)
            if existing_records:
                logger.warning(f"Record with call_id {call_id} already exists, skipping duplicate save")
                return True  # Return True since this is expected behavior
        
        if not airtable_service.is_configured():
            logger.warning("Airtable not configured, skipping save")
            return False
        
        try:
            # Prepare Airtable record - only Retell data with correct field names
            airtable_record = {
                'event': webhook_data['event_type'],
                'call_id': webhook_data['call_id'],
                'agent_id': webhook_data['agent_id'],
                'call_type': webhook_data['call_type'],
                'from_number': webhook_data['from_number'],
                'to_number': webhook_data['to_number'],
                'direction': webhook_data['direction'],
                'call_status': webhook_data['call_status'],
                'disconnection_reason': webhook_data['disconnection_reason'],
                'transcript': webhook_data['transcript'],
                'transcript_object': json.dumps(webhook_data.get('transcript_object', [])),
                'transcript_with_tool_calls': json.dumps(webhook_data.get('transcript_with_tool_calls', [])),
                'start_timestamp': webhook_data['start_timestamp'],
                'end_timestamp': webhook_data['end_timestamp'],
                'duration_ms': webhook_data.get('duration_ms', 0),
                'metadata': json.dumps(webhook_data['metadata']),
                'retell_llm_dynamic_variables': json.dumps(webhook_data['retell_llm_dynamic_variables']),
                'collected_dynamic_variables': json.dumps(webhook_data.get('collected_dynamic_variables', {})),
                'recording_url': webhook_data.get('recording_url', '').strip() if webhook_data.get('recording_url') else '',
                'call_cost': json.dumps(webhook_data.get('call_cost', {})),
                'opt_out_sensitive_data_storage': str(webhook_data.get('opt_out_sensitive_data_storage', False)).lower(),
                'call_analysis': json.dumps(webhook_data.get('call_analysis', {})),
                'twilio_call_sid': webhook_data.get('twilio_call_sid', ''),
                'created_time': datetime.now().isoformat(),
                'node_transcript': webhook_data.get('node_transcript', '')
            }
            
            # Removed verbose Airtable save logging to reduce bloat
            
            record = airtable_service.create_record(airtable_record)
            if record:
                record_id = record.get('id', 'unknown')
                # Get cost for logging
                call_cost = webhook_data.get('call_cost', {})
                combined_cost = call_cost.get('combined_cost', 0)
                cost_str = f"€{combined_cost:.2f}" if combined_cost > 0 else "€0.00"
                logger.info(f"Saved to Airtable: {record_id} ({cost_str})")
                
                # Add recording file attachment if recording_url exists
                recording_url = webhook_data.get('recording_url', '').strip()
                if recording_url:
                    call_id = webhook_data.get('call_id', 'unknown')
                    created_time = airtable_record.get('created_time', '')
                    recording_success = airtable_service.download_and_upload_recording(
                        recording_url, record_id, call_id, created_time
                    )
                    if recording_success:
                        # Transcribe audio with Deepgram after recording is saved
                        deepgram_service = get_deepgram_service()
                        deepgram_transcription = deepgram_service.transcribe_audio_url(recording_url)
                        
                        if deepgram_transcription:
                            # Save Deepgram transcription to Airtable
                            update_data = {
                                'deepgram_transcription': deepgram_transcription
                            }
                            
                            updated_record = airtable_service.update_record(record_id, update_data)
                            if updated_record:
                                logger.info(f"Deepgram: \"{deepgram_transcription[:50]}{'...' if len(deepgram_transcription) > 50 else ''}\"")
                            else:
                                logger.error(f"Failed to save Deepgram transcription to record: {record_id}")
                        else:
                            logger.warning(f"Deepgram transcription failed for record: {record_id}")
                    else:
                        logger.warning(f"Failed to add recording file to record: {record_id}")
                
                # Process language linking after record is saved
                self._process_language_linking(record_id, webhook_data)
                
                return True
            else:
                logger.error("Failed to save webhook to Airtable")
                return False
                
        except Exception as e:
            logger.error(f"Error saving to Airtable: {e}")
            return False
    
    def _handle_event_specific_processing(self, webhook_data: Dict[str, Any]) -> None:
        """
        Handle event-specific processing logic
        
        Args:
            webhook_data: Processed webhook data
        """
        event_type = webhook_data['event_type']
        
        if event_type == 'call_ended':
            self._handle_call_ended(webhook_data)
        elif event_type == 'call_started':
            self._handle_call_started(webhook_data)
        elif event_type == 'call_analyzed':
            self._handle_call_analyzed(webhook_data)
    
    def _handle_call_ended(self, webhook_data: Dict[str, Any]) -> None:
        """Handle call ended event"""
        # Removed verbose call ended logging to reduce bloat
        
        # Add your custom logic for call ended events
        # For example: trigger follow-up actions, send notifications, etc.
        
        if webhook_data['insights']['requires_followup']:
            logger.info(f"Call {webhook_data['call_id']} requires follow-up")
            # Add follow-up logic here
    
    def _handle_call_started(self, webhook_data: Dict[str, Any]) -> None:
        """Handle call started event"""
        # Minimal logging for call started events to reduce log bloat
        # logger.info(f"Call started: {webhook_data['call_id']}")
        
        # Add your custom logic for call started events
        # For example: log call initiation, update status, etc.
    
    def _handle_call_analyzed(self, webhook_data: Dict[str, Any]) -> None:
        """Handle call analyzed event - update existing record with call_analysis data"""
        call_id = webhook_data['call_id']
        
        # Get call_analysis from the raw data
        call_analysis = webhook_data['raw_data'].get('call', {}).get('call_analysis', {})
        if not call_analysis:
            logger.warning(f"No call_analysis data found for call {call_id}")
            return
        
        # Look up the existing record in Airtable using call_id
        if not airtable_service.is_configured():
            logger.error("Airtable service not configured, cannot update call_analysis")
            return
        
        try:
            # Search for the record with matching call_id
            matching_records = airtable_service.search_records('call_id', call_id)
            
            if not matching_records:
                logger.warning(f"No existing record found for call_id: {call_id}")
                return
            
            if len(matching_records) > 1:
                logger.warning(f"Multiple records found for call_id: {call_id}, using first one")
            
            # Get the first matching record
            existing_record = matching_records[0]
            record_id = existing_record.get('id')
            
            if not record_id:
                logger.error(f"No record ID found in existing record for call_id: {call_id}")
                return
            
            # Prepare the update data with call_analysis
            update_data = {
                'call_analysis': json.dumps(call_analysis)
            }
            
            # Update the record
            updated_record = airtable_service.update_record(record_id, update_data)
            
            if updated_record:
                # Extract key info for minimal logging
                sentiment = call_analysis.get('user_sentiment', 'Unknown')
                logger.info(f"Call analysis: {call_id} - {sentiment} sentiment")
            else:
                logger.error(f"Failed to update record {record_id} with call_analysis for call_id: {call_id}")
                
        except Exception as e:
            logger.error(f"Error updating call_analysis for call_id {call_id}: {e}")
    
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

# Global instance
webhook_service = WebhookService() 