# DocAssistant - Quick Start Guide

This guide will help you get the DocAssistant autonomous multi-agent system up and running.

## Prerequisites

- Python 3.10+
- PostgreSQL 14+
- Redis 6+
- OpenAI API key

## Installation Steps

### 1. Clone and Setup Environment

```bash
cd D:\DocAssistant

# Create virtual environment (if not exists)
python -m venv venv

# Activate virtual environment
.\venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create/update `.env` file:

```bash
# Django
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_NAME=doctor_assistant
DB_USER=postgres
DB_PASSWORD=your-postgres-password
DB_HOST=localhost
DB_PORT=5432

# Redis
REDIS_URL=redis://localhost:6379/0

# OpenAI
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_TOKENS=4000
OPENAI_TEMPERATURE=0.3
```

### 3. Setup Database

```bash
# Create PostgreSQL database
psql -U postgres
CREATE DATABASE doctor_assistant;
\q

# Run migrations
python manage.py makemigrations
python manage.py migrate
```

### 4. Create Superuser

```bash
python manage.py createsuperuser
```

### 5. Load Medical PDFs (Important!)

```bash
# Create PDF directory if not exists
mkdir -p data/medical_pdfs

# Add your medical PDF files to data/medical_pdfs/
# Then load them into the RAG system:
python manage.py load_pdfs

# Or load a specific file:
python manage.py load_pdfs --file path/to/medical_guide.pdf

# Or load from a different directory:
python manage.py load_pdfs --directory path/to/pdfs
```

**Note**: The diagnosis agent uses RAG (Retrieval-Augmented Generation) to query medical knowledge from PDFs. Without PDFs, the agent will still work but won't have medical reference material.

### 6. Start Redis (if not running)

```bash
# Windows (if installed as service)
redis-server

# Linux/Mac
redis-server --daemonize yes

# Or using Docker
docker run -d -p 6379:6379 redis:latest
```

### 7. Start the Django Server

```bash
# Development server (ASGI)
python manage.py runserver

# The server will start at http://localhost:8000
```

### 8. Start the Autonomous Controller

**Open a NEW terminal window** and run:

```bash
cd D:\DocAssistant
.\venv\Scripts\activate
python manage.py run_controller
```

You should see:

```
======================================================================
🤖 DocAssistant Autonomous Controller
======================================================================
Polling interval: 2s
Press Ctrl+C to stop

✅ Controller started. Monitoring consultations...
```

## Testing the System

### 1. Access the Application

Open your browser and go to: http://localhost:8000

### 2. Create an Account / Login

- Click "Sign Up" to create a new account
- Or login with your superuser credentials

### 3. Start a Consultation

1. Click **"New Consultation"**
2. Enter symptoms (text or voice):
   ```
   I have a severe headache that started 2 days ago. 
   The pain is on the right side and gets worse with light. 
   I also feel nauseous.
   ```
3. Set duration: "2 days"
4. Set severity: 8/10
5. Click **"Submit Symptoms"**

### 4. Watch the Agents Work!

The autonomous controller will automatically:

1. **SymptomAgent** → Analyzes symptoms
2. **DiagnosisAgent** → Generates diagnosis + orders lab tests
3. **LabAgent** → Sends lab tests to "lab"
4. **LabAgent** → Retrieves mock lab results
5. **DiagnosisAgent** → Reviews results + generates prescription
6. **LabAgent** → Sends prescription to "pharmacy" and patient

You can:
- View the consultation detail page to see progress
- Check the terminal where the controller is running to see agent logs
- View the dashboard to see all consultations

## System Components

### Terminal 1: Django Server
```bash
python manage.py runserver
```
- Handles web requests
- Serves frontend
- Provides API endpoints

### Terminal 2: Autonomous Controller
```bash
python manage.py run_controller
```
- Monitors consultation states
- Triggers agents sequentially
- Coordinates the workflow

### Optional Terminal 3: Celery Worker (for background tasks)
```bash
celery -A core worker -l info
```

## Monitoring

### Check Agent Activity

```bash
# In Django shell
python manage.py shell

from apps.agents.models import AgentSession, GPTInteractionLog

# View recent sessions
sessions = AgentSession.objects.all().order_by('-created_at')[:10]
for s in sessions:
    print(f"{s.agent_type}: {s.status} - {s.processing_time}s")

# View GPT costs
from django.db.models import Sum
total_cost = GPTInteractionLog.objects.aggregate(Sum('cost'))
print(f"Total OpenAI cost: ${total_cost['cost__sum']}")
```

### Check Blackboard State

```bash
python manage.py shell

from apps.blackboard.services import BlackboardService
bb = BlackboardService()

# Get consultation data
consultation_id = "your-consultation-id"
data = bb.read(consultation_id)
print(data['current_state'])
```

## Troubleshooting

### Controller Not Processing

**Symptom**: Consultations stuck in "initial" or "symptoms_collected" state

**Solution**:
1. Check controller is running: Look at Terminal 2
2. Check Redis is running: `redis-cli ping` should return "PONG"
3. Check blackboard locks:
   ```python
   from django.core.cache import cache
   cache.keys("lock:*")  # Should be empty if no active processing
   ```

### No Diagnosis Generated

**Symptom**: Agent runs but no diagnosis appears

**Solution**:
1. Check OpenAI API key is valid
2. Check PDFs are loaded: `python manage.py load_pdfs`
3. Check agent logs in controller terminal for errors

### High API Costs

**Symptom**: OpenAI costs are high

**Solution**:
1. Reduce `OPENAI_MAX_TOKENS` in `.env`
2. Use `gpt-3.5-turbo` instead of `gpt-4` for testing
3. Monitor token usage in admin panel

## Admin Panel

Access the admin panel at: http://localhost:8000/admin

You can view:
- Agent Sessions
- GPT Interaction Logs
- Consultations
- Blackboard Entries
- Token usage and costs

## Production Deployment

For production, see `SYSTEM_ARCHITECTURE.md` section on "Production Considerations".

Key changes needed:
1. Use Daphne or Uvicorn for ASGI
2. Run controller as a systemd service
3. Use proper SMTP for emails
4. Integrate real lab API
5. Add monitoring (Sentry, DataDog)
6. Use environment-specific settings

## Quick Commands Reference

```bash
# Start everything
python manage.py runserver          # Terminal 1
python manage.py run_controller     # Terminal 2

# Load PDFs
python manage.py load_pdfs

# Database
python manage.py migrate
python manage.py createsuperuser

# Shell
python manage.py shell

# Check logs
tail -f logs/agents.log  # If configured
```

## Getting Help

- Check `SYSTEM_ARCHITECTURE.md` for detailed system docs
- Review agent code in `apps/agents/`
- Check Django logs in terminal
- View controller logs in Terminal 2

## Next Steps

1. ✅ System is running
2. Load medical PDFs for better diagnoses
3. Test with various symptoms
4. Monitor agent performance
5. Customize system prompts in agent files
6. Add your own agents or modify workflow

---

**Enjoy building with DocAssistant! 🚀**
