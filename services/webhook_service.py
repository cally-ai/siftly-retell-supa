"""
Webhook service for processing Retell AI webhooks
"""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from pyairtable import Table
from config import Config
from utils.logger import get_logger
from utils.validators import validate_retell_webhook, validate_retell_inbound_webhook, sanitize_webhook_data
from services.airtable_service import airtable_service

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
        # === COMPREHENSIVE PAYLOAD LOGGING ===
        logger.info(f"=== FULL WEBHOOK PAYLOAD RECEIVED ===")
        logger.info(f"Raw payload: {data}")
        logger.info(f"=== END FULL PAYLOAD ===")
        
        event_type = data.get('event', 'unknown')
        logger.info(f"=== CALL EVENT WEBHOOK RECEIVED ===")
        logger.info(f"Event Type: {event_type}")
        logger.info(f"Call ID: {data.get('call', {}).get('call_id', 'unknown')}")
        logger.info(f"From Number: {data.get('call', {}).get('from_number', 'unknown')}")
        logger.info(f"To Number: {data.get('call', {}).get('to_number', 'unknown')}")
        logger.info(f"Direction: {data.get('call', {}).get('direction', 'unknown')}")
        logger.info(f"Call Status: {data.get('call', {}).get('call_status', 'unknown')}")
        
        # Log transcript-related fields specifically
        call_data = data.get('call', {})
        logger.info(f"Transcript present: {'transcript' in call_data}")
        logger.info(f"Transcript object present: {'transcript_object' in call_data}")
        logger.info(f"Transcript with tool calls present: {'transcript_with_tool_calls' in call_data}")
        
        if 'transcript' in call_data:
            logger.info(f"Transcript length: {len(call_data['transcript']) if call_data['transcript'] else 0}")
        if 'transcript_object' in call_data:
            logger.info(f"Transcript object length: {len(call_data['transcript_object']) if call_data['transcript_object'] else 0}")
        if 'transcript_with_tool_calls' in call_data:
            logger.info(f"Transcript with tool calls length: {len(call_data['transcript_with_tool_calls']) if call_data['transcript_with_tool_calls'] else 0}")
        
        logger.info(f"=== END CALL EVENT WEBHOOK ===")
        
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
        logger.info(f"Processing event type: {processed_data.get('event_type', 'unknown')}")
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
        event_type = data.get('event', 'unknown')
        logger.info(f"=== INBOUND CALL WEBHOOK RECEIVED ===")
        logger.info(f"Event Type: {event_type}")
        logger.info(f"Agent ID: {data.get('call_inbound', {}).get('agent_id', 'unknown')}")
        logger.info(f"From Number: {data.get('call_inbound', {}).get('from_number', 'unknown')}")
        logger.info(f"To Number: {data.get('call_inbound', {}).get('to_number', 'unknown')}")
        logger.info(f"=== END INBOUND CALL WEBHOOK ===")
        
        # Validate inbound webhook data
        is_valid, errors = validate_retell_inbound_webhook(data)
        if not is_valid:
            logger.error(f"Invalid inbound webhook data: {errors}")
            raise ValueError(f"Invalid inbound webhook data: {errors}")
        
        # Extract inbound call data
        inbound_data = data.get('call_inbound', {})
        from_number = inbound_data.get('from_number', '')
        to_number = inbound_data.get('to_number', '')
        agent_id = inbound_data.get('agent_id', '')
        
        logger.info(f"Inbound call from {from_number} to {to_number}")
        
        # Get dynamic variables and configuration based on caller
        response_data = self._get_inbound_configuration(from_number, to_number, agent_id)
        
        # Log the response for debugging
        logger.info(f"=== INBOUND RESPONSE TO RETELL ===")
        logger.info(f"Response: {response_data}")
        logger.info(f"=== END INBOUND RESPONSE ===")
        
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
        logger.info(f"=== LOOKING UP CUSTOMER DATA ===")
        logger.info(f"Looking up to_number: {to_number}")
        
        customer_data = self._get_customer_data(to_number)
        
        logger.info(f"Customer data found: {customer_data is not None}")
        if customer_data:
            logger.info(f"Customer data: {customer_data}")
        
        if customer_data:
            # Known customer - use their specific dynamic variables from Airtable
            dynamic_vars = customer_data
            logger.info(f"Using Airtable dynamic variables: {dynamic_vars}")
            
            # Override agent if customer has a preferred agent
            if customer_data.get('preferred_agent_id'):
                response["call_inbound"]["override_agent_id"] = customer_data['preferred_agent_id']
                logger.info(f"Overriding agent to: {customer_data['preferred_agent_id']}")
            
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
            logger.info(f"Using default dynamic variables: {dynamic_vars}")
        
        logger.info(f"=== END CUSTOMER DATA LOOKUP ===")
        
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
    
    def _get_customer_data(self, to_number: str) -> Optional[Dict[str, Any]]:
        """
        Get customer data from Airtable based on to_number
        
        Args:
            to_number: The phone number to look up
        
        Returns:
            Customer data dictionary or None if not found
        """
        try:
            logger.info(f"=== AIRTABLE LOOKUP START ===")
            logger.info(f"Looking up to_number: {to_number}")
            
            # Step 1: Find the to_number in TABLE_ID_TWILIO_NUMBER
            twilio_table = Table(Config.AIRTABLE_API_KEY, Config.AIRTABLE_BASE_ID, 'tbl0PeZoX2qgl74ZT')
            logger.info(f"Searching Twilio table for number: {to_number}")
            twilio_records = twilio_table.all(formula=f"{{twilio_number}} = '{to_number}'")
            
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
            
            # Step 2: Get client data from TABLE_ID_CLIENT
            client_table = Table(Config.AIRTABLE_API_KEY, Config.AIRTABLE_BASE_ID, 'tblkyQzhGKVv6H03U')
            client_record = client_table.get(client_record_id)
            
            if not client_record:
                logger.warning(f"Client record not found: {client_record_id}")
                return None
            
            client_fields = client_record['fields']
            
            # Step 3: Get dynamic variables from TABLE_ID_CLIENT_DYNAMIC_VARIABLES
            dynamic_variables = {}
            dynamic_variables_record_id = client_fields.get('dynamic_variables', [None])[0] if client_fields.get('dynamic_variables') else None
            
            if dynamic_variables_record_id:
                dynamic_table = Table(Config.AIRTABLE_API_KEY, Config.AIRTABLE_BASE_ID, 'tblGIPAQZ2rgn6naD')
                dynamic_record = dynamic_table.get(dynamic_variables_record_id)
                
                if dynamic_record:
                    dynamic_fields = dynamic_record['fields']
                    
                    # Add all fields except excluded ones
                    excluded_fields = ['name', 'client_dynamic_variables_id', 'client']
                    for field_name, field_value in dynamic_fields.items():
                        if field_name not in excluded_fields:
                            dynamic_variables[field_name] = field_value
            
            # Step 4: Get language agent names from linked records
            language_agent_names = client_fields.get('language_agent_names', [])
            
            for linked_record_id in language_agent_names:
                try:
                    language_table = Table(Config.AIRTABLE_API_KEY, Config.AIRTABLE_BASE_ID, 'tblT79Xju3vLxNipr')
                    language_record = language_table.get(linked_record_id)
                    
                    if language_record:
                        key_pair_value = language_record['fields'].get('key_pair', '')
                        if key_pair_value and '=' in key_pair_value:
                            # Parse key_pair like "nl-be_agent_name = Tom"
                            parts = key_pair_value.split('=', 1)
                            if len(parts) == 2:
                                key = parts[0].strip()
                                value = parts[1].strip()
                                dynamic_variables[key] = value
                                
                except Exception as e:
                    logger.warning(f"Error processing language agent name record {linked_record_id}: {e}")
            
            logger.info(f"Returning dynamic variables: {dynamic_variables}")
            logger.info(f"=== AIRTABLE LOOKUP END ===")
            return dynamic_variables
            
        except Exception as e:
            logger.error(f"Error getting customer data for {to_number}: {e}")
            return None
    
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
        
        # Log all available fields for debugging
        logger.info(f"=== EXTRACTING FIELDS ===")
        logger.info(f"Call data keys: {list(call_data.keys())}")
        logger.info(f"Raw data keys: {list(data.keys())}")
        
        # Check for fields that might be at different levels
        recording_url = call_data.get('recording_url', '')
        duration_ms = call_data.get('duration_ms', 0)
        collected_dynamic_variables = call_data.get('collected_dynamic_variables', {})
        call_cost = call_data.get('call_cost', {})
        
        logger.info(f"Recording URL: {recording_url}")
        logger.info(f"Duration MS: {duration_ms}")
        logger.info(f"Collected Dynamic Variables: {collected_dynamic_variables}")
        logger.info(f"Call Cost: {call_cost}")
        logger.info(f"=== END EXTRACTING FIELDS ===")
        
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
        
        logger.info(f"=== GENERATING NODE TRANSCRIPT ===")
        logger.info(f"Total transcript steps: {len(transcript_with_tool_calls)}")
        
        # Loop over transcript entries
        for step in transcript_with_tool_calls:
            if step.get('role') == "node_transition":
                # If ending a node, finalize it
                if buffer and node_start is not None and node_end is not None:
                    node_summary = f"[Node: {current_node}] (Start: {node_start:.4f}s - End: {node_end:.4f}s)\n" + "\n".join(buffer)
                    node_summaries.append(node_summary)
                    logger.info(f"Finalized node: {current_node} ({node_start:.4f}s - {node_end:.4f}s)")
                
                # Transition to the new node
                current_node = step.get('new_node_name', 'unknown')
                buffer = []
                node_start = None
                node_end = None
                logger.info(f"Transitioning to node: {current_node}")
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
                    logger.info(f"Agent speech: {len(words)} words, time range: {first.get('start', 0):.4f}s - {last.get('end', 0):.4f}s")
            
            if step.get('role') == "dtmf":
                buffer.append(f'User: Pressed DTMF "{step.get("digit", "")}"')
                logger.info(f"DTMF input: {step.get('digit', '')}")
            
            if step.get('role') == "tool_call_invocation":
                tool_name = step.get('name', '')
                if tool_name == "extract_dynamic_variables":
                    try:
                        args = json.loads(step.get('arguments', '{}'))
                        detected = next((arg for arg in args if arg.get('name') == "caller_language"), None)
                        if detected:
                            buffer.append("System: Detected language as Dutch")
                            logger.info("Language detection: Dutch")
                    except (json.JSONDecodeError, KeyError):
                        logger.warning("Failed to parse extract_dynamic_variables arguments")
                
                elif tool_name == "agent_swap":
                    try:
                        args = json.loads(step.get('arguments', '{}'))
                        agent_id = args.get('agentId', 'unknown')
                        buffer.append(f"System: Swapped to Dutch agent ({agent_id})")
                        logger.info(f"Agent swap: {agent_id}")
                    except (json.JSONDecodeError, KeyError):
                        logger.warning("Failed to parse agent_swap arguments")
            
            if step.get('role') == "tool_call_result" and step.get('content', '').find("transferred") != -1:
                try:
                    content = json.loads(step.get('content', '{}'))
                    status = content.get('status', 'Unknown transfer status')
                    buffer.append(f"System: {status}")
                    logger.info(f"Transfer result: {status}")
                except (json.JSONDecodeError, KeyError):
                    logger.warning("Failed to parse tool_call_result content")
        
        # Push final node if any content left
        if buffer and node_start is not None and node_end is not None:
            node_summary = f"[Node: {current_node}] (Start: {node_start:.4f}s - End: {node_end:.4f}s)\n" + "\n".join(buffer)
            node_summaries.append(node_summary)
            logger.info(f"Finalized final node: {current_node} ({node_start:.4f}s - {node_end:.4f}s)")
        
        # Join the full transcript string
        full_transcript = "\n\n".join(node_summaries)
        logger.info(f"Generated node transcript with {len(node_summaries)} nodes")
        logger.info(f"=== END NODE TRANSCRIPT ===")
        
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
        # Only save call details when event is "call_analyzed"
        event_type = webhook_data.get('event_type', 'unknown')
        if event_type != 'call_analyzed':
            logger.info(f"Skipping Airtable save for event type: {event_type} (only saving 'call_analyzed' events)")
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
            
            logger.info(f"=== SAVING TO AIRTABLE ===")
            logger.info(f"Event: {airtable_record['event']}")
            logger.info(f"Call ID: {airtable_record['call_id']}")
            logger.info(f"From: {airtable_record['from_number']} -> To: {airtable_record['to_number']}")
            logger.info(f"Direction: {airtable_record['direction']}")
            logger.info(f"Call Status: {airtable_record['call_status']}")
            logger.info(f"Duration (ms): {airtable_record.get('duration_ms', 0)}")
            logger.info(f"Recording URL (raw): {webhook_data.get('recording_url', 'N/A')}")
            logger.info(f"Recording URL (raw type): {type(webhook_data.get('recording_url', 'N/A'))}")
            logger.info(f"Recording URL (length): {len(webhook_data.get('recording_url', ''))}")
            logger.info(f"Recording URL (saved): {airtable_record.get('recording_url', 'N/A')}")
            logger.info(f"Recording URL (saved type): {type(airtable_record.get('recording_url', 'N/A'))}")
            logger.info(f"Recording URL (saved length): {len(airtable_record.get('recording_url', ''))}")
            logger.info(f"Call Cost (raw): {webhook_data.get('call_cost', 'N/A')}")
            logger.info(f"Call Cost (JSON): {airtable_record.get('call_cost', 'N/A')}")
            logger.info(f"Collected Dynamic Variables: {airtable_record.get('collected_dynamic_variables', 'N/A')}")
            logger.info(f"Transcript length: {len(airtable_record['transcript']) if airtable_record['transcript'] else 0}")
            logger.info(f"Transcript object present: {'transcript_object' in airtable_record and airtable_record['transcript_object'] != '[]'}")
            logger.info(f"Transcript with tool calls present: {'transcript_with_tool_calls' in airtable_record and airtable_record['transcript_with_tool_calls'] != '[]'}")
            logger.info(f"opt_out_sensitive_data_storage: {airtable_record['opt_out_sensitive_data_storage']} (type: {type(airtable_record['opt_out_sensitive_data_storage'])})")
            logger.info(f"Call Analysis present: {'call_analysis' in airtable_record and airtable_record['call_analysis'] != '{}'}")
            logger.info(f"Twilio Call SID: {airtable_record.get('twilio_call_sid', 'N/A')}")
            logger.info(f"Created Time: {airtable_record.get('created_time', 'N/A')}")
            logger.info(f"Node Transcript length: {len(airtable_record.get('node_transcript', ''))}")
            logger.info(f"Node Transcript present: {bool(airtable_record.get('node_transcript', ''))}")
            logger.info(f"=== END AIRTABLE SAVE ===")
            
            record = airtable_service.create_record(airtable_record)
            if record:
                record_id = record.get('id', 'unknown')
                logger.info(f"Saved webhook to Airtable: {record_id}")
                
                # Add recording file attachment if recording_url exists
                recording_url = webhook_data.get('recording_url', '').strip()
                if recording_url:
                    logger.info(f"Processing recording file for record: {record_id}")
                    call_id = webhook_data.get('call_id', 'unknown')
                    created_time = airtable_record.get('created_time', '')
                    recording_success = airtable_service.download_and_upload_recording(
                        recording_url, record_id, call_id, created_time
                    )
                    if recording_success:
                        logger.info(f"Successfully added recording file to record: {record_id}")
                    else:
                        logger.warning(f"Failed to add recording file to record: {record_id}")
                else:
                    logger.info(f"No recording URL found for record: {record_id}")
                
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
        logger.info(f"Call ended: {webhook_data['call_id']}")
        
        # Add your custom logic for call ended events
        # For example: trigger follow-up actions, send notifications, etc.
        
        if webhook_data['insights']['requires_followup']:
            logger.info(f"Call {webhook_data['call_id']} requires follow-up")
            # Add follow-up logic here
    
    def _handle_call_started(self, webhook_data: Dict[str, Any]) -> None:
        """Handle call started event"""
        logger.info(f"Call started: {webhook_data['call_id']}")
        
        # Add your custom logic for call started events
        # For example: log call initiation, update status, etc.
    
    def _handle_call_analyzed(self, webhook_data: Dict[str, Any]) -> None:
        """Handle call analyzed event"""
        logger.info(f"Call analyzed: {webhook_data['call_id']}")
        
        # Add your custom logic for call analyzed events
        # For example: trigger follow-up actions, update analytics, etc.
        
        # This event contains the full call analysis data
        # You can access call_analysis object from the raw data
        call_analysis = webhook_data['raw_data'].get('call', {}).get('call_analysis', {})
        if call_analysis:
            logger.info(f"Call analysis available for {webhook_data['call_id']}")
            # Process call analysis data here
    
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