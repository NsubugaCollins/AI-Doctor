# 🚀 DocAssistant - Quick Reference Card

## Start the System (3 Commands)

```bash
# Terminal 1: Redis (Required for real-time)
redis-server

# Terminal 2: Django Server
python manage.py runserver

# Terminal 3: Autonomous Controller
python manage.py run_controller
```

**That's it!** System is now running with full real-time monitoring.

---

## 📊 What Happens When Patient Submits

```
Patient enters symptoms → Submit
    ↓
Real-time monitoring page opens
    ↓
WebSocket connects (see green dot)
    ↓
Progress bar shows stages
    ↓
Activity log updates live
    ↓
Content sections appear as ready:
    • Diagnosis
    • Lab test document
    • Lab results
    • Prescription
    ↓
Consultation complete! 🎉
```

---

## 👀 What You See (Developer)

### Terminal Output:
```
🤒 SymptomAgent running...
✅ SymptomAgent completed

🧠 DiagnosisAgent running...
   📚 Querying RAG...
   🤖 Calling GPT-4...
✅ DiagnosisAgent succeeded

🔬 LabAgent running...
   📧 Sending to lab...
✅ LabAgent succeeded

[... continues through workflow ...]

✅ Consultation completed
```

---

## 👤 What Patient Sees

### Progress Bar:
```
[✓] Symptoms → [🔄] Analysis → [ ] Diagnosis → [ ] Lab Tests ...
```

### Activity Log:
```
🤖 Symptom Agent
   Started processing          16:30:45

💭 Symptom Agent
   Analyzing symptoms...        16:30:46

✓ Symptom Agent
   Completed successfully       16:30:48
```

### Dynamic Content:
- Sections fade in as agents complete
- Diagnosis appears with reasoning
- Lab document shows tests ordered
- Results appear when received
- Prescription shows medications

---

## 🔧 Common Commands

```bash
# Load medical PDFs
python manage.py load_pdfs

# Check agent activity
python manage.py shell
>>> from apps.agents.models import AgentSession
>>> AgentSession.objects.all().order_by('-created_at')[:5]

# Check OpenAI costs
>>> from apps.agents.models import GPTInteractionLog
>>> from django.db.models import Sum
>>> GPTInteractionLog.objects.aggregate(Sum('cost'))

# Clear stuck locks (if needed)
>>> from django.core.cache import cache
>>> cache.delete_pattern("lock:*")
```

---

## 🐛 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| WebSocket not connecting | Check Redis: `redis-cli ping` |
| No real-time updates | Check controller is running |
| Agents not processing | Restart controller |
| Stuck consultation | Clear locks (see above) |

---

## 📱 URLs

- **Home**: http://localhost:8000
- **Dashboard**: http://localhost:8000/dashboard
- **New Consultation**: http://localhost:8000/new-consultation
- **Admin**: http://localhost:8000/admin

---

## 🎯 Test the System

1. Go to http://localhost:8000
2. Login (or sign up)
3. Click "New Consultation"
4. Enter symptoms:
   ```
   Severe headache on right side for 2 days,
   worse with light, nausea present
   ```
5. Submit and watch!

---

## 📊 Agent Workflow

```
Symptoms → SymptomAgent → Analysis
    ↓
DiagnosisAgent + RAG → Diagnosis + Lab Test DOC
    ↓
LabAgent → Send Tests to Lab
    ↓
LabAgent → Retrieve Lab Results
    ↓
DiagnosisAgent + RAG + Results → Prescription
    ↓
LabAgent → Send to Pharmacy & Patient
    ↓
Complete! ✅
```

---

## 💡 Key Features

✅ Fully autonomous (no manual intervention)  
✅ Real-time WebSocket updates  
✅ Beautiful patient interface  
✅ Detailed developer logs  
✅ RAG-powered diagnosis  
✅ GPT-4 reasoning  
✅ Complete transparency  
✅ Professional presentation  

---

## 📚 Documentation Files

- **QUICKSTART.md** - Detailed setup guide
- **SYSTEM_ARCHITECTURE.md** - Technical documentation
- **WORKFLOW_VISUAL.md** - Visual diagrams
- **REALTIME_MONITORING.md** - Real-time features
- **REALTIME_COMPLETE.md** - Implementation summary

---

## ✅ System Status

🟢 **All Systems Operational**

- ✅ Async context fixed
- ✅ Templates created
- ✅ WebSocket enabled
- ✅ Real-time monitoring working
- ✅ Full workflow functional
- ✅ Documentation complete

---

## 🎉 You're Ready!

Start the three terminals and you have a fully functional, autonomous, real-time AI medical consultation system!

**Enjoy! 🚀**
