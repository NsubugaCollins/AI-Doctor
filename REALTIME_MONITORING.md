# Real-Time Consultation Monitoring Guide

## Overview

Your DocAssistant system now provides **real-time visibility** into the AI agent processing workflow. Both developers (terminal) and patients (web interface) can see exactly what's happening as agents process consultations.

---

## 🖥️ Developer View (Terminal)

### Starting the Controller

```bash
python manage.py run_controller
```

### What You'll See

When a consultation is submitted, the terminal shows detailed agent activity:

```
🤖 DocAssistant Autonomous Controller
======================================================================
Polling interval: 2s
Press Ctrl+C to stop

✅ Controller started. Monitoring consultations...

🤒 SymptomAgent running for consultation abc-123-def
✅ SymptomAgent completed for abc-123-def

🧠 DiagnosisAgent running for consultation abc-123-def
   📚 Querying RAG system with symptoms...
   🤖 Sending to GPT-4 for diagnosis...
   ✅ Generated differential diagnosis
   📝 Created lab test document
✅ DiagnosisAgent succeeded for abc-123-def -> diagnosis_complete

🔬 LabAgent running for consultation abc-123-def
   📧 Sending lab test document to lab...
✅ LabAgent succeeded for abc-123-def -> lab_tests_ordered

🔬 LabAgent running for consultation abc-123-def
   📊 Retrieving lab results...
✅ LabAgent succeeded for abc-123-def -> lab_tests_complete

🧠 DiagnosisAgent running for consultation abc-123-def
   📚 Querying RAG system with diagnosis + results...
   🤖 Sending to GPT-4 for final prescription...
   💊 Generated prescription
✅ DiagnosisAgent succeeded for abc-123-def -> final_diagnosis_ready

🔬 LabAgent running for consultation abc-123-def
   📧 Sending prescription to pharmacy...
   📧 Sending prescription to patient...
✅ LabAgent succeeded for abc-123-def -> prescription_sent

✅ Consultation abc-123-def completed
```

### Log Levels

The controller logs at different levels:
- `INFO`: Normal agent activity
- `WARNING`: Recoverable issues (locks, retries)
- `ERROR`: Failures and exceptions
- `DEBUG`: Detailed internal operations

---

## 👤 Patient View (Web Interface)

### What Patients See

When a patient submits symptoms, they're redirected to a **real-time progress page** that shows:

### 1. **Progress Bar**
Visual progress indicator showing current stage:
```
[✓] Symptoms → [🔄] Analysis → [ ] Diagnosis → [ ] Lab Tests → [ ] Results → [ ] Prescription → [ ] Complete
```

- ✓ Green = Completed
- 🔄 Blue (pulsing) = Currently processing
- Gray = Not started yet

### 2. **Live Agent Activity Log**
Real-time feed of agent actions:

```
┌─────────────────────────────────────────────────┐
│ 🤖 AI Agent Activity                            │
├─────────────────────────────────────────────────┤
│ ✓ Symptom Agent                                 │
│   Symptoms analyzed and structured              │
│   16:30:45                                      │
│                                                 │
│ 🔄 Diagnosis Agent                              │
│   Analyzing symptoms with medical knowledge...  │
│   16:30:48                                      │
│                                                 │
│ 💭 Diagnosis Agent                              │
│   Querying medical literature from PDFs...      │
│   16:30:50                                      │
└─────────────────────────────────────────────────┘
```

### 3. **Dynamic Content Sections**

As agents complete their work, sections appear with results:

#### **Diagnosis Section** (appears after DiagnosisAgent Phase 1)
- Primary suspicion
- Differential diagnosis list with probabilities
- Reasoning

#### **Lab Tests Document** (appears after DiagnosisAgent Phase 1)
- Formal lab test order
- List of tests with rationale
- Priority levels
- Test status (Pending → Processing → Completed)

#### **Lab Results** (appears after LabAgent retrieves results)
- Test name
- Results data
- Interpretation

#### **Prescription** (appears after DiagnosisAgent Phase 2)
- Medications with dosage, frequency, duration
- Treatment plan
- Follow-up instructions

---

## 🔌 WebSocket Connection

### How It Works

1. Patient submits symptoms
2. Browser connects to WebSocket: `ws://localhost:8000/ws/consultation/{id}/`
3. Controller sends updates as agents process
4. Frontend updates in real-time

### Connection Status

Shown in the sidebar:
- 🟢 Green dot (pulsing) = Connected
- 🔴 Red dot = Disconnected (auto-reconnects)

### Message Types

The WebSocket sends different message types:

```javascript
// Agent started processing
{
  type: 'agent_started',
  agent: 'diagnosis_agent',
  message: 'Diagnosis Agent started processing'
}

// Agent progress update
{
  type: 'agent_progress',
  agent: 'diagnosis_agent',
  message: 'Querying medical knowledge base...',
  progress: 50
}

// Agent completed
{
  type: 'agent_completed',
  agent: 'diagnosis_agent',
  message: 'Diagnosis Agent completed successfully',
  data: {
    diagnosis: {...},
    lab_tests: [...],
    lab_tests_document: "..."
  }
}

// State changed
{
  type: 'state_changed',
  old_state: 'symptoms_collected',
  new_state: 'diagnosis_complete',
  message: 'Moved to diagnosis_complete'
}
```

---

## 📊 Complete Workflow Visibility

### Stage 1: Patient Submits Symptoms

**Terminal:**
```
🤒 SymptomAgent running for consultation abc-123
```

**Patient sees:**
```
🔄 Symptom Agent
   Analyzing your symptoms...
```

---

### Stage 2: Symptom Analysis Complete

**Terminal:**
```
✅ SymptomAgent completed for abc-123
   - Primary symptoms: headache, nausea
   - Severity: 8/10
   - Duration: 2 days
```

**Patient sees:**
```
✓ Symptom Agent
  Symptoms analyzed and structured
  
Progress: [✓ Symptoms] [🔄 Analysis] ...
```

---

### Stage 3: Initial Diagnosis

**Terminal:**
```
🧠 DiagnosisAgent running for consultation abc-123
   📚 Querying RAG: searching medical PDFs...
   📚 Found 5 relevant medical sources
   🤖 Calling GPT-4 with symptoms + RAG context...
   ✅ Generated differential diagnosis
   📝 Created lab test document (3 tests)
```

**Patient sees:**
```
🔄 Diagnosis Agent
  Consulting medical knowledge base...
  
💭 Diagnosis Agent
  AI is reasoning about your symptoms...
  
✓ Diagnosis Agent
  Initial diagnosis generated

[New Section Appears]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🩺 AI Diagnosis

Primary Suspicion: Migraine

Differential Diagnosis:
• Migraine (85%)
• Tension headache (10%)
• Cluster headache (5%)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔬 Lab Tests Ordered

LABORATORY TEST ORDER
═══════════════════════════════
Patient ID: PAT-123
Ordered by: Diagnosis Agent (AI)
Date: 2026-03-02 16:35

TESTS REQUESTED:
────────────────────────────────
1. Complete Blood Count (CBC)
   Type: blood | Priority: routine
   Rationale: Rule out infection

2. Metabolic Panel
   Type: blood | Priority: routine
   Rationale: Check electrolyte balance

3. CT Scan - Head
   Type: imaging | Priority: urgent
   Rationale: Rule out structural issues
═══════════════════════════════
```

---

### Stage 4: Lab Tests Sent

**Terminal:**
```
🔬 LabAgent running for consultation abc-123
   📧 Sending lab test document to lab system...
   ✅ Lab order sent successfully
```

**Patient sees:**
```
✓ Lab Agent
  Lab tests sent to laboratory
  
Progress: [✓] [✓] [✓] [🔄 Lab Tests] ...

[Tests show status]
1. CBC - Status: Pending
2. Metabolic Panel - Status: Pending
3. CT Scan - Status: Pending
```

---

### Stage 5: Lab Results Retrieved

**Terminal:**
```
🔬 LabAgent running for consultation abc-123
   📊 Checking lab system for results...
   ✅ Retrieved 3 test results
```

**Patient sees:**
```
✓ Lab Agent
  Lab results received
  
[New Section Appears]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧪 Lab Results Received

Complete Blood Count (CBC)
{
  "wbc": "7.5 K/uL",
  "rbc": "4.8 M/uL",
  "hemoglobin": "14.2 g/dL",
  "interpretation": "Within normal limits"
}

Metabolic Panel
{
  "glucose": "95 mg/dL",
  "interpretation": "Normal"
}

CT Scan - Head
{
  "result": "No abnormalities detected"
}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Stage 6: Final Diagnosis & Prescription

**Terminal:**
```
🧠 DiagnosisAgent running for consultation abc-123
   📚 Querying RAG with diagnosis + lab results...
   🤖 GPT-4 reasoning with evidence...
   💊 Generated prescription
```

**Patient sees:**
```
🔄 Diagnosis Agent
  Reviewing lab results and finalizing diagnosis...
  
✓ Diagnosis Agent
  Final diagnosis and prescription ready
  
[New Section Appears]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💊 Your Prescription

Medications:
────────────
• Sumatriptan
  50mg - Take as needed at onset
  Duration: 30 days
  Instructions: Take with water at first sign
  
• Ondansetron
  4mg - Take as needed for nausea
  Duration: 30 days
  
Treatment Plan:
Rest in dark, quiet room. Apply cold compress.
Avoid triggers (bright lights, loud noises).

Follow-up:
Contact doctor if symptoms worsen or persist
beyond 72 hours.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Stage 7: Prescription Sent

**Terminal:**
```
🔬 LabAgent running for consultation abc-123
   📧 Formatting prescription for pharmacy...
   📧 Sending to pharmacy...
   📧 Sending to patient email...
   ✅ Prescription sent successfully
```

**Patient sees:**
```
✓ Lab Agent
  Prescription sent to pharmacy and your email
  
Progress: [✓][✓][✓][✓][✓][✓][✓ Complete]

🎉 Consultation Complete!
Your prescription has been sent to:
• Your registered pharmacy
• Your email address

Check your inbox for the full prescription document.
```

---

## 🔧 Configuration

### Enable WebSocket Support

Make sure you have in `settings.py`:

```python
INSTALLED_APPS = [
    ...
    'channels',
    ...
]

ASGI_APPLICATION = 'core.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('localhost', 6379)],
        },
    },
}
```

### Start Redis (Required for WebSockets)

```bash
redis-server
```

---

## 🐛 Troubleshooting

### WebSocket Not Connecting

**Symptom**: Connection status shows 🔴 Disconnected

**Solutions**:
1. Check Redis is running: `redis-cli ping` → should return "PONG"
2. Check channels is installed: `pip install channels channels-redis`
3. Check browser console for errors
4. Verify ASGI app is running (not WSGI)

### No Real-Time Updates

**Symptom**: Page doesn't update as agents work

**Solutions**:
1. Check controller is running: `python manage.py run_controller`
2. Refresh the page
3. Check terminal for agent logs
4. Verify consultation is not in a stuck state

### Agents Not Processing

**Symptom**: Consultation stuck in "initial" state

**Solutions**:
1. Check controller terminal for errors
2. Check Redis connection
3. Clear stuck locks in Django shell:
   ```python
   from django.core.cache import cache
   cache.delete_pattern("lock:*")
   ```

---

## 📈 Monitoring Tips

1. **Keep controller terminal visible** - See real-time agent activity
2. **Monitor WebSocket connection** - Check green dot in UI
3. **Watch progress bar** - Know which stage is active
4. **Read activity log** - See detailed agent operations
5. **Refresh if needed** - Button available in sidebar

---

**Your system now provides complete transparency into the AI consultation process!** 🎉

Both you (developer) and your patients can see exactly what's happening, building trust and providing visibility into the autonomous AI workflow.
