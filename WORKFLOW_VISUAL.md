# Agent Workflow Visual Guide

## Sequential Multi-Agent Workflow

```
┌─────────────────────────────────────────────────────────────────────┐
│                      PATIENT INTERACTION                             │
│                                                                      │
│  User submits symptoms → POST /api/consultations/start/             │
│  Consultation created with state="initial"                          │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
                    ┌──────────────────┐
                    │   BLACKBOARD     │
                    │ (Shared Memory)  │
                    │  Redis + Postgres│
                    └──────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                  AUTONOMOUS CONTROLLER                               │
│                                                                      │
│  Continuously monitors blackboard states (every 2 seconds)          │
│  Triggers appropriate agent based on current state                  │
│  Manages locks to prevent race conditions                           │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
╔═════════════════════════════════════════════════════════════════════╗
║                    AGENT PROCESSING SEQUENCE                         ║
╚═════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────┐
│ [1] SYMPTOM AGENT                            State: initial         │
├─────────────────────────────────────────────────────────────────────┤
│ Input:  Raw symptoms from user                                      │
│ Process:                                                             │
│   • Retrieves symptoms from blackboard                              │
│   • Sends to GPT-4 for analysis                                     │
│   • Extracts: primary symptoms, duration, severity                  │
│   • Identifies urgent indicators                                    │
│   • Structures data                                                 │
│ Output: symptom_analysis → blackboard                               │
│ Next State: symptoms_collected                                      │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ [2] DIAGNOSIS AGENT (Phase 1)      State: symptoms_collected       │
├─────────────────────────────────────────────────────────────────────┤
│ Input:  Structured symptoms from blackboard                         │
│ Process:                                                             │
│   • Queries RAG system with symptoms                                │
│     └─→ Searches medical PDF knowledge base                         │
│     └─→ Retrieves relevant medical literature                       │
│   • Sends to GPT-4:                                                 │
│     └─→ Symptoms                                                    │
│     └─→ RAG context (medical knowledge)                             │
│     └─→ Patient history                                             │
│   • GPT-4 generates:                                                │
│     └─→ Differential diagnosis (multiple possibilities)             │
│     └─→ Primary suspicion                                           │
│     └─→ Reasoning chain                                             │
│     └─→ Recommended lab tests with rationale                        │
│   • Creates formal lab test document                                │
│ Output:                                                              │
│   • diagnosis → blackboard                                          │
│   • lab_tests → blackboard                                          │
│   • lab_tests_document → blackboard                                 │
│ Next State: diagnosis_complete                                      │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ [3] LAB AGENT (Send Tests)          State: diagnosis_complete      │
├─────────────────────────────────────────────────────────────────────┤
│ Input:  lab_tests_document from blackboard                          │
│ Process:                                                             │
│   • Formats lab test document                                       │
│   • Sends to lab system (email/API)                                 │
│     └─→ In production: HL7/FHIR integration                         │
│     └─→ In dev: Mock email send                                     │
│   • Marks each test as "ordered"                                    │
│   • Adds timestamps                                                 │
│ Output:                                                              │
│   • Updated lab_tests (status=ordered) → blackboard                 │
│   • lab_order_sent_at timestamp → blackboard                        │
│ Next State: lab_tests_ordered                                       │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
                    ⏱️  WAITING FOR LAB
                    (Polling or Webhook)
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ [4] LAB AGENT (Retrieve Results)    State: lab_tests_ordered       │
├─────────────────────────────────────────────────────────────────────┤
│ Input:  None (polls lab system)                                     │
│ Process:                                                             │
│   • Polls lab API for completed tests                               │
│     └─→ In production: HL7/FHIR result retrieval                    │
│     └─→ In dev: Mock results generation                             │
│   • Retrieves results when available                                │
│   • Validates data                                                  │
│   • Stores in structured format                                     │
│ Output:                                                              │
│   • lab_results → blackboard                                        │
│   • Updated lab_tests (status=completed, results) → blackboard      │
│ Next State: lab_tests_complete                                      │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ [5] DIAGNOSIS AGENT (Phase 2)       State: lab_tests_complete      │
├─────────────────────────────────────────────────────────────────────┤
│ Input:  Initial diagnosis + lab_results from blackboard             │
│ Process:                                                             │
│   • Retrieves initial diagnosis                                     │
│   • Retrieves lab results                                           │
│   • Queries RAG system again                                        │
│     └─→ Searches for treatment guidelines                           │
│     └─→ Retrieves medication protocols                              │
│   • Sends to GPT-4:                                                 │
│     └─→ Initial symptoms                                            │
│     └─→ Initial diagnosis                                           │
│     └─→ Lab results (evidence)                                      │
│     └─→ RAG context (treatment knowledge)                           │
│   • GPT-4 reasons with lab evidence:                                │
│     └─→ Confirms or adjusts diagnosis                               │
│     └─→ Generates treatment plan                                    │
│     └─→ Creates prescription:                                       │
│         • Medications (name, dosage, frequency)                     │
│         • Instructions                                              │
│         • Follow-up recommendations                                 │
│ Output:                                                              │
│   • prescription → blackboard                                       │
│   • Updated diagnosis (final) → blackboard                          │
│ Next State: final_diagnosis_ready                                   │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ [6] LAB AGENT (Send Prescription)   State: final_diagnosis_ready   │
├─────────────────────────────────────────────────────────────────────┤
│ Input:  prescription from blackboard                                 │
│ Process:                                                             │
│   • Formats prescription document                                   │
│   • Sends to PHARMACY:                                              │
│     └─→ Email with prescription details                             │
│     └─→ PDF attachment                                              │
│     └─→ In production: Pharmacy API integration                     │
│   • Sends to PATIENT:                                               │
│     └─→ Email with instructions                                     │
│     └─→ PDF prescription                                            │
│     └─→ Follow-up reminders                                         │
│   • Updates prescription record                                     │
│ Output:                                                              │
│   • Updated prescription (sent=true) → blackboard                   │
│   • pharmacy_order_id → blackboard                                  │
│   • sent_timestamps → blackboard                                    │
│ Next State: prescription_sent                                       │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ [7] CONTROLLER (Completion)          State: prescription_sent       │
├─────────────────────────────────────────────────────────────────────┤
│ Process:                                                             │
│   • Marks consultation as completed                                 │
│   • Adds final timestamps                                           │
│   • Sends completion notification                                   │
│   • Archives data                                                   │
│ Next State: completed ✅                                            │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
                         WORKFLOW END

╔═════════════════════════════════════════════════════════════════════╗
║                    PARALLEL ACTIVITIES                               ║
╚═════════════════════════════════════════════════════════════════════╝

Throughout the workflow:

[Session Management]
• Each agent run creates AgentSession record
• Tracks: input, output, processing time, status
• Links to consultation_id

[GPT Interaction Logging]
• Every GPT-4 call logged
• Tracks: prompt, response, tokens, cost
• Enables audit trail and cost analysis

[WebSocket Updates]
• Real-time notifications sent to frontend
• Patient sees live progress
• Events: symptom_processed, diagnosis_complete, etc.

[Blackboard Updates]
• All data stored in shared memory
• Redis for fast access
• PostgreSQL for persistence
• Locking prevents race conditions

[Error Handling]
• Failed agents transition to error states
• Errors logged with details
• System can retry or alert operators

╔═════════════════════════════════════════════════════════════════════╗
║                    DATA FLOW SUMMARY                                 ║
╚═════════════════════════════════════════════════════════════════════╝

User Input (Symptoms)
    ↓
SymptomAgent → Structured Analysis
    ↓
DiagnosisAgent + RAG → Initial Diagnosis + Lab Test DOC
    ↓
LabAgent → Send to Lab
    ↓
[Wait for Results]
    ↓
LabAgent → Retrieve Lab Results
    ↓
DiagnosisAgent + RAG + Results → Final Diagnosis + Prescription
    ↓
LabAgent → Send to Pharmacy & Patient
    ↓
Completed ✅

╔═════════════════════════════════════════════════════════════════════╗
║                 KEY TECHNOLOGIES                                     ║
╚═════════════════════════════════════════════════════════════════════╝

• OpenAI GPT-4: Diagnosis reasoning and prescription generation
• RAG (FAISS + SentenceTransformers): Medical knowledge retrieval
• Redis: Fast blackboard state cache
• PostgreSQL: Persistent storage
• Django Channels: WebSocket for real-time updates
• Asyncio: Async agent coordination

╔═════════════════════════════════════════════════════════════════════╗
║                STATE MACHINE REFERENCE                               ║
╚═════════════════════════════════════════════════════════════════════╝

States:
• initial                → SymptomAgent processes
• symptoms_collected     → DiagnosisAgent phase 1
• diagnosis_complete     → LabAgent sends tests
• lab_tests_ordered      → LabAgent polls for results
• lab_tests_complete     → DiagnosisAgent phase 2
• final_diagnosis_ready  → LabAgent sends prescription
• prescription_sent      → Completed
• completed              → End state ✅

Error States:
• diagnosis_failed
• lab_failed
• prescription_failed
• failed

Each state transition is automatic and handled by the controller!
```

## Monitoring Points

```
┌──────────────────────────────────────────────────────────────┐
│                    MONITORING DASHBOARD                       │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  📊 Agent Sessions:                                          │
│     • Total runs: 1,234                                      │
│     • Success rate: 98.5%                                    │
│     • Avg processing time: 12.3s                             │
│                                                               │
│  💰 OpenAI Costs:                                            │
│     • Total cost: $45.67                                     │
│     • Avg per consultation: $0.37                            │
│     • Total tokens: 2.3M                                     │
│                                                               │
│  🔬 Consultations:                                           │
│     • Completed: 987                                         │
│     • In progress: 23                                        │
│     • Failed: 15                                             │
│                                                               │
│  📚 RAG System:                                              │
│     • Loaded PDFs: 45                                        │
│     • Total chunks: 12,456                                   │
│     • Avg retrieval time: 0.8s                               │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

This workflow is fully automated. Once a user submits symptoms, the controller handles everything!
