# UUID Serialization Fix

## Issue Fixed

**Error**: `Object of type UUID is not JSON serializable`

**Root Cause**: UUID objects from Django models were being passed through the system without being converted to strings, causing JSON serialization errors.

## Changes Made

### 1. **Symptom Agent** (`apps/agents/symptom_agent.py`)
Added UUID to string conversion at the start of `run()` method:
```python
async def run(self, consultation_id: str) -> Dict[str, Any]:
    # Ensure consultation_id is a string
    consultation_id = str(consultation_id)
    ...
```

### 2. **Diagnosis Agent** (`apps/agents/diagnosis_agent.py`)
Added UUID to string conversion:
```python
def run(self, consultation_id: str) -> Dict[str, Any]:
    # Ensure consultation_id is a string
    consultation_id = str(consultation_id)
    ...
```

### 3. **Lab Agent** (`apps/agents/lab_agent.py`)
Added UUID to string conversion:
```python
def run(self, consultation_id: str) -> Dict[str, Any]:
    # Ensure consultation_id is a string
    consultation_id = str(consultation_id)
    ...
```

### 4. **Controller** (`apps/agents/controller.py`)
Ensures consultation IDs are strings when processing:
```python
for consultation_id in consultations:
    # Ensure consultation_id is a string
    await self._process_consultation(str(consultation_id))
```

### 5. **Session Manager** (`apps/agents/agent_session.py`)
Ensures consultation_id is always stored as string:
```python
def __init__(self, agent_type: str, consultation_id: str):
    self.agent_type = agent_type
    # Ensure consultation_id is a string
    self.consultation_id = str(consultation_id)
    ...
```

### 6. **Blackboard Service** (`apps/blackboard/services.py`)
Added string conversion in all methods:
```python
def create_consultation(self, patient_data, consultation_id=None):
    consultation_id = str(consultation_id or uuid.uuid4())
    ...

def read(self, consultation_id):
    consultation_id = str(consultation_id)
    ...

def write(self, consultation_id, updates, agent_name):
    consultation_id = str(consultation_id)
    ...
```

## Why This Happened

Django's UUID fields return Python `UUID` objects, not strings. When these objects are:
1. Passed to JSON serialization (for Redis/cache storage)
2. Used in log messages
3. Sent via WebSocket

They need to be converted to strings first, as JSON cannot natively serialize UUID objects.

## Solution

We now explicitly convert all UUID objects to strings at the entry points of each agent and service method. This ensures:
- ✅ JSON serialization works
- ✅ WebSocket messages work
- ✅ Redis caching works
- ✅ Logging works
- ✅ No more UUID errors

## Testing

The system should now work without UUID serialization errors. Try:

1. Start the controller:
   ```bash
   python manage.py run_controller
   ```

2. Submit a consultation from the web interface

3. Watch the terminal - you should see:
   ```
   🤒 SymptomAgent running for consultation abc-123-def-456
   ✅ SymptomAgent completed for abc-123-def-456
   
   🧠 DiagnosisAgent running for consultation abc-123-def-456
   ...
   ```

No UUID errors should appear!

## Prevention

Going forward, always convert UUIDs to strings when:
- Passing to JSON serialization
- Using in cache keys
- Sending via WebSocket
- Logging

Use: `str(uuid_object)` or `str(consultation.id)`
