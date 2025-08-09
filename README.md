# Siftly - Webhook & IVR Service

A Python Flask application that handles IVR flows, VAPI webhooks, and stores data in Supabase.

## Features

- **IVR and VAPI handlers**: Endpoints for IVR and VAPI integrations
- **Supabase-backed storage**: Reads/writes operational data to Supabase
- **Modular Architecture**: Clean separation of concerns with services, routes, and utilities
- **Deployment Ready**: Configured for easy deployment on Render

## Setup

### Prerequisites

- Python 3.8+

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
   - `SUPABASE_URL`: Your Supabase project URL
   - `SUPABASE_SERVICE_ROLE_KEY`: Your Supabase service role key

4. **Run the application**
   ```bash
   python app.py
   ```

The application will be available at `http://localhost:5000`

### Supabase Setup

Provide `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in your environment. Ensure your database schema matches the application’s expected tables (e.g., `client`, `twilio_number`, `client_dynamic_variables`, `language`, `caller`, `client_caller`, `twilio_call`, `vapi_webhook_event`, `vapi_workflow`, `opening_hours`, `timezone`, `client_ivr_language_configuration`, `client_ivr_language_configuration_language`, `client_language_agent_name`).

## Deployment on Render

### Option 1: Using render.yaml (Recommended)

1. Push your code to GitHub
2. Connect your GitHub repository to Render
3. Render will automatically detect the `render.yaml` file and configure the service
4. Add your environment variables in the Render dashboard:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`

### Option 2: Manual Setup

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Configure the service:
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn -c gunicorn.conf.py app:app`
4. Add environment variables as listed above

## API Endpoints

### Health Check
```
GET /health
```
Returns the health status of the application and Supabase configuration.

### System Status
```
GET /status
```
Get detailed system status and configuration information.

### Ping
```
GET /ping
```
Simple ping endpoint for load balancers.

## Customization

### Modifying Schema

Update the Supabase queries in `services/webhook_service.py`, `routes/ivr_routes.py`, and `routes/vapi_routes.py` if your schema changes.

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
| `SUPABASE_URL` | Supabase project URL | Yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | Yes |
| `FLASK_ENV` | Flask environment | No (defaults to production) |
| `FLASK_DEBUG` | Enable debug mode | No (defaults to False) |
| `LOG_LEVEL` | Logging level | No (defaults to INFO) |
| `SECRET_KEY` | Flask secret key | No (auto-generated in dev) |
| `PORT` | Port to run the application on | No (Render sets this automatically) |

## Troubleshooting

### Common Issues

1. **Supabase connection fails**
   - Verify your URL and service role key are correct
   - Ensure the referenced tables exist and have expected columns

2. **Webhook not receiving data**
   - Ensure the webhook endpoint is publicly accessible
   - Verify the request format matches the expected JSON structure

3. **Deployment issues on Render**
   - Check the build logs for dependency issues
   - Verify all environment variables are set correctly
   - Ensure the start command is correct

### Logs

The application logs webhook and IVR operations. Check the logs in your Render dashboard for debugging information.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License. 