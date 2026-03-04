# DocAssistant - Autonomous Multi-Agent Medical Consultation System

## System Overview

DocAssistant is an AI-powered autonomous medical consultation system that uses multiple specialized agents working sequentially to process patient symptoms, generate diagnoses, order lab tests, and create prescriptions.

## Architecture

### Core Components

1. **Blackboard (Shared Memory)**
   - Central data store using Redis (cache) + PostgreSQL (persistence)
   - Stores consultation state, symptoms, diagnosis, lab tests, and prescriptions
   - Implements locking mechanism to prevent race conditions
   - Location: `apps/blackboard/services.py`

2. **Autonomous Controller**
   - Orchestrates the multi-agent workflow
   - Runs continuously in background, monitoring consultation states
   - Triggers agents sequentially based on state machine
   - Location: `apps/agents/controller.py`

3. **Specialized Agents**
   - **Symptom Agent**: Analyzes and structures patient symptoms
   - **Diagnosis Agent**: Generates diagnosis using GPT-4 + RAG, creates lab test orders
   - **Lab Agent**: Coordinates with lab systems, retrieves results, sends prescriptions
   - Location: `apps/agents/`

4. **RAG System (Retrieval-Augmented Generation)**
   - Indexes medical PDF documents for knowledge retrieval
   - Uses FAISS vector database + SentenceTransformers
   - Provides context to diagnosis agent
   - Location: `apps/rag/services.py`

## Workflow States & Transitions

```
initial
  ↓ [SymptomAgent]
symptoms_collected
  ↓ [DiagnosisAgent - Phase 1: Initial Diagnosis + Lab Tests DOC]
diagnosis_complete
  ↓ [LabAgent - Send lab test DOC to lab]
lab_tests_ordered
  ↓ [LabAgent - Retrieve lab results]
lab_tests_complete
  ↓ [DiagnosisAgent - Phase 2: Final Diagnosis + Prescription]
final_diagnosis_ready
  ↓ [LabAgent - Send prescription to pharmacy & patient]
prescription_sent
  ↓
completed
```

## Detailed Agent Workflow

### 1. Symptom Agent (`symptom_agent.py`)
**Trigger**: User submits symptoms → State: `initial`

**Process**:
- Retrieves symptom data from blackboard
- Uses GPT-4 to analyze and structure symptoms
- Extracts: primary symptoms, duration, severity, urgent indicators
- Determines if clarification is needed

**Output to Blackboard**:
- `symptom_analysis`: Structured symptom data
- `current_state` → `symptoms_collected`

### 2. Diagnosis Agent - Phase 1 (`diagnosis_agent.py`)
**Trigger**: State changes to `symptoms_collected`

**Process**:
1. Retrieves symptoms from blackboard
2. **Queries RAG system** with symptoms to get relevant medical knowledge from PDFs
3. Sends symptoms + RAG context to GPT-4
4. GPT-4 generates:
   - Differential diagnosis with probabilities
   - Primary suspicion
   - Reasoning chain
   - Recommended lab tests with rationale
5. **Generates formal lab test document** for the lab

**Output to Blackboard**:
- `diagnosis`: Complete diagnosis data
- `lab_tests`: List of ordered tests
- `lab_tests_document`: Formal document for lab
- `current_state` → `diagnosis_complete`

### 3. Lab Agent - Send Tests (`lab_agent.py`)
**Trigger**: State changes to `diagnosis_complete`

**Process**:
1. Retrieves `lab_tests_document` from blackboard
2. Sends document to lab system (email/API in production)
3. Marks tests as "ordered" with timestamps

**Output to Blackboard**:
- Updated `lab_tests` with status="ordered"
- `lab_order_sent_at`: Timestamp
- `current_state` → `lab_tests_ordered`

### 4. Lab Agent - Retrieve Results (`lab_agent.py`)
**Trigger**: State = `lab_tests_ordered` (polling/webhook in production)

**Process**:
1. Checks lab system for completed tests
2. Retrieves results when available
3. Stores results in blackboard

**Output to Blackboard**:
- `lab_results`: Complete test results
- `lab_tests`: Updated with results
- `current_state` → `lab_tests_complete`

### 5. Diagnosis Agent - Phase 2 (`diagnosis_agent.py`)
**Trigger**: State changes to `lab_tests_complete`

**Process**:
1. Retrieves initial diagnosis + lab results from blackboard
2. **Queries RAG system** with diagnosis + results
3. Sends to GPT-4: symptoms + initial diagnosis + lab results + RAG context
4. GPT-4 reasons again with lab evidence and generates:
   - Confirmed diagnosis
   - Treatment plan
   - Prescription (medications, dosages, instructions)

**Output to Blackboard**:
- `prescription`: Complete prescription data
- `current_state` → `final_diagnosis_ready`

### 6. Lab Agent - Send Prescription (`lab_agent.py`)
**Trigger**: State changes to `final_diagnosis_ready`

**Process**:
1. Retrieves prescription from blackboard
2. Formats prescription document
3. **Sends to pharmacy** (email/API)
4. **Sends to patient** (email/patient portal)

**Output to Blackboard**:
- Updated `prescription` with sent_to_pharmacy=True, sent_to_patient=True
- `current_state` → `prescription_sent`

### 7. Completion
**Trigger**: State changes to `prescription_sent`

**Process**:
- Controller marks consultation as `completed`
- Stores final timestamps
- No further processing needed

## Key Features

### 1. Autonomous Operation
- Controller runs continuously in background
- Automatically picks up consultations in any state
- Processes them through the workflow without manual intervention

### 2. State Machine
- Clear state transitions prevent confusion
- Each state maps to specific agent actions
- Lock mechanism prevents concurrent processing of same consultation

### 3. RAG Integration
- Medical PDFs are indexed using FAISS
- Diagnosis agent queries relevant knowledge
- Citations from medical literature included in reasoning

### 4. Session Management
- Every agent run creates a session record
- Tracks: input, output, processing time, cost, tokens used
- GPT-4 interactions logged for audit trail

### 5. Real-Time Updates
- WebSocket notifications for state changes
- Frontend can display live progress
- Patients see updates as agents work

### 6. Error Handling
- Failed agents transition to error states
- Errors logged with timestamps and details
- System can retry or alert human operators

## Technology Stack

- **Backend**: Django 6.0 (Python)
- **Async Framework**: ASGI + asyncio
- **AI Model**: OpenAI GPT-4
- **Vector DB**: FAISS (local) + SentenceTransformers
- **Cache**: Redis
- **Database**: PostgreSQL
- **Real-time**: Django Channels (WebSocket)
- **Task Queue**: Celery (optional for async tasks)

## Data Models

### Consultation
```python
- id: UUID
- patient: ForeignKey
- current_state: CharField (state machine)
- symptoms: JSONField
- diagnosis: JSONField
- lab_tests: JSONField
- prescription: JSONField
- created_at, updated_at, completed_at
```

### Blackboard Entry
```python
- consultation_id: CharField
- agent_name: CharField
- state: JSONField (complete consultation state)
- lock_acquired: Boolean
- lock_owner: CharField
- created_at, updated_at
```

### Agent Session
```python
- consultation_id: UUID
- agent_type: CharField
- input_data: JSONField
- output_data: JSONField
- status: CharField (processing/completed/failed)
- processing_time: Float
- tokens_used: Integer
- cost: Decimal
```

### GPT Interaction Log
```python
- session: ForeignKey (AgentSession)
- model_used: CharField
- prompt: TextField
- response: TextField
- prompt_tokens, completion_tokens, total_tokens: Integer
- cost: Decimal
- response_time: Float
- success: Boolean
```

## Starting the System

### 1. Load Medical PDFs (One-time setup)
```bash
python manage.py load_pdfs
```

### 2. Start Django Server (ASGI)
```bash
python manage.py runserver
# or for production:
daphne -b 0.0.0.0 -p 8000 core.asgi:application
```

### 3. Start Autonomous Controller
```bash
python manage.py run_controller
```

### 4. Start Celery Workers (Optional)
```bash
celery -A core worker -l info
```

## API Endpoints

### Consultation Flow
```
POST /api/consultations/start/
  → Creates consultation, adds to blackboard
  → Controller picks it up automatically

POST /api/consultation/{id}/add-symptoms/
  → Adds symptoms to existing consultation

GET /api/consultation/{id}/status/
  → Get current state and progress

GET /api/consultation/{id}/
  → View complete consultation details
```

## Configuration

### Environment Variables (.env)
```bash
# Django
DJANGO_SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_NAME=doctor_assistant
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432

# Redis
REDIS_URL=redis://localhost:6379/0

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_TOKENS=4000
OPENAI_TEMPERATURE=0.3
```

## Monitoring & Debugging

### View Agent Sessions
```python
from apps.agents.models import AgentSession
sessions = AgentSession.objects.filter(consultation_id='...')
```

### View GPT Interactions
```python
from apps.agents.models import GPTInteractionLog
logs = GPTInteractionLog.objects.filter(session__consultation_id='...')
total_cost = logs.aggregate(Sum('cost'))
```

### Check Blackboard State
```python
from apps.blackboard.services import BlackboardService
bb = BlackboardService()
data = bb.read('consultation_id')
```

### View Consultation Progress
Dashboard shows:
- Current state
- Agent activity history
- Symptoms, diagnosis, lab tests, prescription
- Real-time updates

## Production Considerations

1. **Lab Integration**
   - Replace mock lab methods with real API calls
   - Implement HL7/FHIR integration
   - Use webhooks for result notifications

2. **Email/SMS Notifications**
   - Configure SMTP for email delivery
   - Integrate Twilio for SMS alerts
   - Send prescription PDFs to pharmacy

3. **Scaling**
   - Run controller in separate container
   - Use Celery for long-running tasks
   - Scale horizontally with load balancer

4. **Security**
   - HIPAA compliance for patient data
   - Encrypt sensitive fields
   - Audit logs for all access
   - Role-based access control

5. **Monitoring**
   - APM tools (DataDog, NewRelic)
   - Error tracking (Sentry)
   - Cost monitoring for OpenAI API

## Troubleshooting

### Controller Not Running
```bash
# Check if controller is started
ps aux | grep run_controller

# Start manually
python manage.py run_controller
```

### Agents Not Processing
```bash
# Check blackboard locks
from apps.blackboard.services import BlackboardService
bb = BlackboardService()
# Release stuck locks manually if needed
```

### High OpenAI Costs
```bash
# Monitor token usage
from apps.agents.models import GPTInteractionLog
from django.db.models import Sum
cost = GPTInteractionLog.objects.aggregate(Sum('cost'))
print(f"Total cost: ${cost['cost__sum']}")
```

## Future Enhancements

1. **Multi-modal Input**: Image analysis (X-rays, skin conditions)
2. **Voice Interface**: Real-time voice-to-text with Whisper
3. **Tele health**: Video consultation integration
4. **Appointment Scheduling**: Auto-schedule follow-ups
5. **EHR Integration**: Connect with Epic, Cerner
6. **Mobile Apps**: React Native iOS/Android apps
7. **Predictive Analytics**: Predict complications, readmissions
8. **Multi-language**: Support for non-English consultations

## License & Disclaimer

⚠️ **Medical Disclaimer**: This is an AI-powered clinical decision support tool. All diagnoses and prescriptions should be reviewed and approved by licensed healthcare professionals. Not a substitute for professional medical advice.

## Support

For questions or issues, contact: [your-email@domain.com]

---

**Version**: 1.0.0  
**Last Updated**: March 2, 2026
