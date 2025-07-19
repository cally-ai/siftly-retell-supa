# Siftly - Retell AI Webhook Handler

A Python Flask application that receives HTTP requests from Retell AI and manages data in Airtable.

## Features

- **Retell AI Webhook Handler**: Receives and processes webhooks from Retell AI
- **Airtable Integration**: Automatically saves webhook data to Airtable
- **RESTful API**: Full CRUD operations for Airtable records
- **Modular Architecture**: Clean separation of concerns with services, routes, and utilities
- **Advanced Analytics**: Webhook statistics and insights processing
- **Comprehensive Validation**: Data validation and sanitization
- **Deployment Ready**: Configured for easy deployment on Render

## Setup

### Prerequisites

- Python 3.8+
- Airtable account with API access
- Retell AI account

### Local Development

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd Siftly
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   ```bash
   cp env.example .env
   ```
   
   Edit `.env` with your actual values:
   - `AIRTABLE_API_KEY`: Your Airtable API key
   - `AIRTABLE_BASE_ID`: Your Airtable base ID
   - `AIRTABLE_TABLE_NAME`: Your Airtable table name (default: Main)

4. **Run the application**
   ```bash
   python app.py
   ```

The application will be available at `http://localhost:5000`

### Airtable Setup

1. Create a new base in Airtable
2. Create a table with the following fields (or modify the code to match your schema):
   - `Timestamp` (Date/Time)
   - `Event Type` (Single line text)
   - `Call ID` (Single line text)
   - `Agent ID` (Single line text)
   - `Customer ID` (Single line text)
   - `Status` (Single line text)
   - `Transcript` (Long text)
   - `Summary` (Long text)
   - `Sentiment` (Single line text)
   - `Duration` (Number)
   - `Cost` (Number)
   - `Raw Data` (Long text)

3. Get your API key and base ID from Airtable settings

## Deployment on Render

### Option 1: Using render.yaml (Recommended)

1. Push your code to GitHub
2. Connect your GitHub repository to Render
3. Render will automatically detect the `render.yaml` file and configure the service
4. Add your environment variables in the Render dashboard:
   - `AIRTABLE_API_KEY`
   - `AIRTABLE_BASE_ID`
   - `AIRTABLE_TABLE_NAME` (optional, defaults to "Main")

### Option 2: Manual Setup

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Configure the service:
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
4. Add environment variables as listed above

## API Endpoints

### Health Check
```
GET /health
```
Returns the health status of the application and Airtable configuration.

### Retell AI Webhook
```
POST /webhook/retell
```
Receives webhooks from Retell AI and processes them.

### Webhook Statistics
```
GET /webhook/statistics?hours=24
```
Get webhook statistics for the specified time period (default: 24 hours).

### System Status
```
GET /status
```
Get detailed system status and configuration information.

### Health Check
```
GET /health
```
Returns the health status of the application and Airtable configuration.

### Ping
```
GET /ping
```
Simple ping endpoint for load balancers.

**Expected Payload:**
```json
{
  "event_type": "call_ended",
  "call_id": "call_123",
  "agent_id": "agent_456",
  "customer_id": "customer_789",
  "status": "completed",
  "transcript": "Hello, how can I help you?",
  "summary": "Customer inquired about product features",
  "sentiment": "positive",
  "duration": 120,
  "cost": 0.50
}
```

### Airtable Operations

#### Get All Records
```
GET /airtable/records
```

#### Create Record
```
POST /airtable/records
Content-Type: application/json

{
  "Field Name": "Field Value",
  "Another Field": "Another Value"
}
```

#### Update Record
```
PUT /airtable/records/{record_id}
Content-Type: application/json

{
  "Field Name": "Updated Value"
}
```

#### Delete Record
```
DELETE /airtable/records/{record_id}
```

#### Search Records
```
GET /airtable/records/search?field=Call ID&value=call_123
```
Search records by field value.

#### Get Specific Record
```
GET /airtable/records/{record_id}
```
Get a specific record by ID.

#### Batch Create Records
```
POST /airtable/records/batch
Content-Type: application/json

[
  {"Field Name": "Value 1"},
  {"Field Name": "Value 2"}
]
```
Create multiple records in batch.

## Retell AI Configuration

1. In your Retell AI dashboard, configure webhooks
2. Set the webhook URL to: `https://your-app-name.onrender.com/webhook/retell`
3. Configure the events you want to receive (e.g., call_ended, call_started)

## Customization

### Modifying Webhook Processing

Edit the `services/webhook_service.py` file to add your custom business logic:

```python
def _add_insights(self, webhook_data):
    # Add your custom processing logic here
    insights = {
        'call_processed': True,
        'processing_timestamp': datetime.now().isoformat(),
        'keywords_found': [],
        'priority_level': 'normal',
        'requires_followup': False
    }
    
    # Example: Custom keyword detection
    if webhook_data.get('transcript'):
        transcript = webhook_data['transcript'].lower()
        # Add your keyword detection logic
    
    return insights
```

### Modifying Airtable Schema

Update the field mappings in `services/webhook_service.py` to match your Airtable schema:

```python
airtable_record = {
    'Your Timestamp Field': webhook_data['timestamp'],
    'Your Event Type Field': webhook_data['event_type'],
    # ... other fields
}
```

### Adding New Services

To add new functionality, create new service files in the `services/` directory:

```python
# services/new_service.py
from utils.logger import get_logger

logger = get_logger(__name__)

class NewService:
    def __init__(self):
        # Initialize your service
        pass
    
    def your_method(self):
        # Your business logic here
        pass
```

### Adding New Routes

To add new API endpoints, create new route files in the `routes/` directory:

```python
# routes/new_routes.py
from flask import Blueprint, request, jsonify

new_bp = Blueprint('new', __name__, url_prefix='/new')

@new_bp.route('/endpoint', methods=['GET'])
def new_endpoint():
    # Your endpoint logic here
    return jsonify({'status': 'success'})
```

Then register the blueprint in `app.py`:

```python
from routes.new_routes import new_bp
app.register_blueprint(new_bp)
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `AIRTABLE_API_KEY` | Your Airtable API key | Yes |
| `AIRTABLE_BASE_ID` | Your Airtable base ID | Yes |
| `AIRTABLE_TABLE_NAME` | Your Airtable table name | No (defaults to "Main") |
| `FLASK_ENV` | Flask environment | No (defaults to production) |
| `FLASK_DEBUG` | Enable debug mode | No (defaults to False) |
| `LOG_LEVEL` | Logging level | No (defaults to INFO) |
| `SECRET_KEY` | Flask secret key | No (auto-generated in dev) |
| `PORT` | Port to run the application on | No (Render sets this automatically) |

## Troubleshooting

### Common Issues

1. **Airtable connection fails**
   - Verify your API key and base ID are correct
   - Check that your Airtable table exists and has the correct field names

2. **Webhook not receiving data**
   - Ensure the webhook URL is correct in Retell AI
   - Check that the webhook endpoint is publicly accessible
   - Verify the request format matches the expected JSON structure

3. **Deployment issues on Render**
   - Check the build logs for dependency issues
   - Verify all environment variables are set correctly
   - Ensure the start command is correct

### Logs

The application logs all webhook requests and Airtable operations. Check the logs in your Render dashboard for debugging information.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License. 