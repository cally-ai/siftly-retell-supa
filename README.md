# Siftly - Retell AI Webhook Handler

A Python Flask application that handles Retell AI webhooks, IVR flows, and stores data in Supabase.

## Features

- **Retell AI webhook handlers**: Endpoints for Retell AI integrations
- **Intent Classification**: AI-powered intent classification with OpenAI/OpenRouter
- **Knowledge Base Q&A**: Dynamic FAQ answering for general questions
- **Vector Search**: Semantic search using OpenAI embeddings
- **Contact Collection**: Dynamic Typeform integration for contact collection
- **Business Hours**: Intelligent business hours checking and routing
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
   - `OPENAI_API_KEY`: Your OpenAI API key for embeddings and LLM
   - `OPENROUTER_API_KEY`: Your OpenRouter API key (fallback for LLM)
   - `TYPEFORM_ACCESS_TOKEN`: Your Typeform access token for contact collection

4. **Run the application**
   ```bash
   python app.py
   ```

The application will be available at `http://localhost:5000`

### Supabase Setup

Provide `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in your environment. Ensure your database schema matches the application’s expected tables (e.g., `client`, `twilio_number`, `client_workflow_configuration`, `language`, `caller`, `client_caller`, `twilio_call`, `retell_event`, `opening_hours`, `timezone`, `client_ivr_language_configuration`, `client_ivr_language_configuration_language`, `client_language_agent_name`).

## Deployment on Render

### Option 1: Using render.yaml (Recommended)

1. Push your code to GitHub
2. Connect your GitHub repository to Render
3. Render will automatically detect the `render.yaml` file and configure the service
4. Add your environment variables in the Render dashboard:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `OPENAI_API_KEY`
   - `OPENROUTER_API_KEY` (optional)
   - `TYPEFORM_ACCESS_TOKEN` (optional)

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

### Intent Classification
```
POST /classify-intent
```
AI-powered intent classification using OpenAI/OpenRouter. Returns intent classification with confidence scores and routing information.

### Typeform Integration
```
POST /typeform/create-typeform
```
Creates dynamic Typeform for contact collection based on client configuration.

```
POST /typeform/webhook
```
Handles Typeform submission webhooks and stores contact data.

### Webhook Handlers
```
POST /webhook/inbound
```
Handles Retell AI inbound webhook events.

```
POST /webhook/started
```
Handles Retell AI call started events.

## Customization

### Modifying Schema

Update the Supabase queries in `services/webhook_service.py` and `routes/webhook_routes.py` if your schema changes.

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
| `OPENAI_API_KEY` | OpenAI API key for embeddings and LLM | Yes |
| `OPENROUTER_API_KEY` | OpenRouter API key (fallback for LLM) | No |
| `TYPEFORM_ACCESS_TOKEN` | Typeform access token for contact collection | No |
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

## Intent Classification System

### Overview

The system uses AI-powered intent classification to route calls to the appropriate handling. It combines:

- **Vector Search**: Semantic similarity using OpenAI embeddings
- **LLM Classification**: OpenAI GPT-4o-mini (primary) with OpenRouter fallback
- **Knowledge Base Integration**: Direct FAQ answering for general questions
- **Dynamic Routing**: Context-aware routing based on intent confidence

### Performance Optimizations

- **TOP_K=5**: Reduced from 7 for faster vector search
- **Parallel Processing**: KB prefetch runs alongside LLM classification
- **Caching**: Intent lookups are cached for performance
- **Fallback Strategy**: OpenRouter as backup when OpenAI fails

### Response Format

```json
{
  "call_id": "call_123",
  "intent_id": "uuid",
  "intent_name": "Human Readable Name",
  "confidence": 0.9,
  "needs_clarification": "no",
  "clarify_question": "",
  "action_policy": "route_to_agent",
  "category_name": "sales_queue",
  "transfer_number": "+1234567890",
  "acknowledgment_text": "I understand your concern...",
  "telemetry": {
    "embedding_top1_sim": 0.614,
    "topK": [
      {"rank": 1, "intent_name": "Heat Pump Not Heating/Cooling", "sim": 0.614},
      {"rank": 2, "intent_name": "Warranty Claim", "sim": 0.525}
    ]
  }
}
```

## KB Q&A Runbook (Ops)

### What this does

* Stores FAQs per tenant in `kb_documents` (one row) + `kb_chunks` (text + **pgvector** embedding).
* Answers **General Question** calls directly from the KB.
* Keeps normal routing (collect, transfer, schedule) for transactional intents.

### Daily use

#### Add / update a single FAQ

Run your script (generates embedding, upserts the doc+chunk):

```bash
python faq_upsert.py
```

#### Batch import from CSV

Use `csv_ingest.py` (supports `--client-id` or a `client_id` column):

```bash
python csv_ingest.py faq.csv --client-id <TENANT_UUID>
```

#### Verify latest docs

```sql
select d.id, d.title, d.locale, c.chunk_index, left(c.content,100) as preview
from kb_documents d
join kb_chunks c on c.doc_id = d.id
where d.client_id = '<TENANT_UUID>'
order by d.updated_at desc
limit 10;
```

### How "General Question" works

1. On each turn your backend runs **in parallel**:

   * **Intent classifier** (LLM, temp=0) over a shortlist of your tenant's intents **plus** `general_question`.
   * **KB lookup** (embed user text → `kb_search`) so the answer is ready.
2. If the best intent is **General Question**:

   * You **don't** return transactional routing.
   * You return a small payload (`qa_prefetch`) with `title/content/score` (and optionally `action_policy: "answer_from_kb"`).
   * The next node simply speaks that answer.
3. If best intent is **not** General:

   * You ignore the KB result and return normal routing (e.g., `collect_contact` → `warranty_queue`).

### Confidence & clarifying

* Use a KB score threshold (start at **0.70**).
* If no KB hit ≥ threshold → set `"needs_clarification": "yes"` and return **one** short clarifying question.

### Multilingual

* Ingest docs with the proper `locale` (e.g., `nl`, `fr`).
* Search with `p_locale` first; fallback to null if no good hit.
* The embedding model is multilingual (`text-embedding-3-small`), so cross-language works, but same-language is best.

### Keys & safety

* `kb_documents.client_id` is a **UUID FK** → every doc belongs to a real tenant.
* Service role key stays server-side only (never in clients).
* After big ingests: `ANALYZE public.kb_chunks;`

### Troubleshooting

* **"invalid input syntax for type vector"**: you passed a placeholder. Send a real `'[n1,...,n1536]'` or use the array→vector RPC.
* **"foreign key violation"**: wrong tenant UUID; create the tenant first or fix the id.
* **Classifier picks a transactional intent for an FAQ**: ensure the `general_question` candidate is always appended and add 2–5 examples

## License

This project is licensed under the MIT License. 