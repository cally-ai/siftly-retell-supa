"""
Webhook service for processing Retell AI webhooks
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
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
        logger.info(f"Processing Retell webhook: {data.get('event', 'unknown')}")
        
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
        
        # Save to Airtable
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
        logger.info(f"Processing inbound webhook: {data.get('event', 'unknown')}")
        
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
        logger.info(f"Returning inbound configuration: {response_data}")
        
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
        customer_data = self._get_customer_data(from_number)
        
        if customer_data:
            # Known customer - use their specific data
            dynamic_vars = {
                "customer_name": customer_data.get('name', 'Valued Customer'),
                "customer_id": customer_data.get('id', ''),
                "account_type": customer_data.get('account_type', 'standard'),
                "preferred_language": customer_data.get('language', 'English'),
                "company_name": customer_data.get('company', 'Your Company'),
                "company_name_agent": f"{customer_data.get('company', 'Your Company')} Assistant"
            }
            
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
    
    def _get_customer_data(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """
        Get customer data from database/storage based on phone number
        
        Args:
            phone_number: Customer's phone number
        
        Returns:
            Customer data dictionary or None if not found
        """
        # This is where you would integrate with your customer database
        # For now, using a simple example with hardcoded data
        
        # Example customer database lookup
        customer_database = {
            "+12137771234": {
                "id": "CUST001",
                "name": "John Doe",
                "company": "Acme Corp",
                "account_type": "premium",
                "language": "English",
                "preferred_agent_id": "agent_premium_001"
            },
            "+12137771235": {
                "id": "CUST002", 
                "name": "Jane Smith",
                "company": "Tech Solutions",
                "account_type": "enterprise",
                "language": "English",
                "preferred_agent_id": "agent_enterprise_001"
            }
        }
        
        return customer_database.get(phone_number)
    
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
        
        # Calculate duration from timestamps
        start_timestamp = call_data.get('start_timestamp', 0)
        end_timestamp = call_data.get('end_timestamp', 0)
        duration_seconds = (end_timestamp - start_timestamp) / 1000 if end_timestamp > start_timestamp else 0
        
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
            'start_timestamp': start_timestamp,
            'end_timestamp': end_timestamp,
            'duration_seconds': duration_seconds,
            'metadata': call_data.get('metadata', {}),
            'retell_llm_dynamic_variables': call_data.get('retell_llm_dynamic_variables', {}),
            'opt_out_sensitive_data_storage': call_data.get('opt_out_sensitive_data_storage', False)
        }
    
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
        if not airtable_service.is_configured():
            logger.warning("Airtable not configured, skipping save")
            return False
        
        try:
            # Prepare Airtable record
            airtable_record = {
                'Timestamp': webhook_data['timestamp'],
                'Event Type': webhook_data['event_type'],
                'Call ID': webhook_data['call_id'],
                'Agent ID': webhook_data['agent_id'],
                'Call Type': webhook_data['call_type'],
                'From Number': webhook_data['from_number'],
                'To Number': webhook_data['to_number'],
                'Direction': webhook_data['direction'],
                'Call Status': webhook_data['call_status'],
                'Disconnection Reason': webhook_data['disconnection_reason'],
                'Transcript': webhook_data['transcript'],
                'Duration Seconds': webhook_data['duration_seconds'],
                'Start Timestamp': webhook_data['start_timestamp'],
                'End Timestamp': webhook_data['end_timestamp'],
                'Priority Level': webhook_data['insights']['priority_level'],
                'Keywords Found': ', '.join(webhook_data['insights']['keywords_found']),
                'Requires Followup': webhook_data['insights']['requires_followup'],
                'Sentiment Score': webhook_data['insights']['sentiment_score'],
                'Metadata': str(webhook_data['metadata']),
                'Dynamic Variables': str(webhook_data['retell_llm_dynamic_variables']),
                'Raw Data': str(webhook_data['raw_data'])
            }
            
            record = airtable_service.create_record(airtable_record)
            if record:
                logger.info(f"Saved webhook to Airtable: {record.get('id', 'unknown')}")
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