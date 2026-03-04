# DocAssistant – Steps to Get the Project Running

Follow these steps in order.

---

## 1. Prerequisites

- **Python 3.10+**
- **PostgreSQL** (running, with a database created)
- **Redis** (running; used for cache and Channels)
- **OpenAI API key** (for GPT-4 and agents)

---

## 2. Clone / Open Project & Virtual Environment

```powershell
cd d:\DocAssistant
```

Create and activate a virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

On Linux/macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

If you hit issues with `sentence-transformers` or `faiss-cpu`, install them separately:

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install sentence-transformers faiss-cpu
```

---

## 4. Environment Variables

Create or edit `.env` in the project root:

```env
# Required
DJANGO_SECRET_KEY=your-secret-key-here
OPENAI_API_KEY=sk-your-openai-api-key

# Database (PostgreSQL)
DB_NAME=doctor_assistant
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432

# Redis
REDIS_URL=redis://localhost:6379/0

# Optional
DEBUG=True
OPENAI_MODEL=gpt-4o-mini
```

---

## 5. Database

Create the PostgreSQL database (if it does not exist):

```sql
CREATE DATABASE doctor_assistant;
```

Run migrations:

```powershell
python manage.py makemigrations
python manage.py migrate
```

Create a superuser (for admin and testing):

```powershell
python manage.py createsuperuser
```

---

## 6. Static Files (optional for dev)

```powershell
python manage.py collectstatic --noinput
```

(Skip in development if you are not using production static serving.)

---

## 7. Start Redis

- **Windows:** Install Redis (e.g. via WSL or a Windows port) and start it, or use a cloud Redis.
- **Linux/macOS:**  
  `redis-server`  
  Or with Docker:  
  `docker run -d -p 6379:6379 redis:alpine`

Ensure Redis is reachable at the URL set in `REDIS_URL`.

---

## 8. Run the Django Server

```powershell
python manage.py runserver
```

App URLs:

- **Home:** http://127.0.0.1:8000/
- **Login/Signup:** http://127.0.0.1:8000/accounts/
- **Dashboard (after login):** http://127.0.0.1:8000/api/dashboard/
- **New consultation:** http://127.0.0.1:8000/api/new-consultation/
- **API (e.g. start consultation):** http://127.0.0.1:8000/api/consultations/start/

Note: Many app views live under `/api/` (e.g. dashboard, new consultation, consultation detail).

---

## 9. Run the Autonomous Controller

The controller drives the agent flow (symptom → diagnosis → lab → prescription). Run it in a **second terminal** (with the same venv and `.env`):

```powershell
cd d:\DocAssistant
.\venv\Scripts\Activate.ps1
python manage.py run_controller
```

Leave this running. You should see logs like “Async Autonomous Controller started” and “Controller loop started”.

---

## 10. Quick Test Flow

1. Open http://127.0.0.1:8000/ and log in (or sign up via `/accounts/signup/`).
2. Go to **New consultation** (e.g. http://127.0.0.1:8000/api/new-consultation/).
3. Enter symptoms and submit.
4. With the controller running, the system will:
   - SymptomAgent: analyze symptoms and write to shared memory
   - DiagnosisAgent: use RAG and produce diagnosis + lab test DOC
   - LabAgent: send lab doc to lab, then (simulated) results
   - DiagnosisAgent: generate prescription from lab results
   - LabAgent: send prescription to pharmacy and patient
5. Check the consultation detail page and/or dashboard for status and results.

---

## 11. Optional: RAG (Medical PDFs)

- Place PDFs under `data/medical_pdfs/` (or path set by `PDF_STORAGE_PATH`).
- RAG index is under `data/chroma_db/` (or `CHROMA_DB_PATH`).
- If no PDFs are present, RAG returns no context; diagnosis still runs with symptoms only.

---

## 12. Optional: Run Controller on App Startup

To start the controller with the app (e.g. in development), in `apps/consultations/views.py` uncomment:

```python
# start_controller()  # Uncomment if you want auto-start
```

For production, run the controller as a separate process (e.g. `python manage.py run_controller`) or via a process manager (systemd, supervisord, etc.).

---

## Troubleshooting

| Issue | What to check |
|-------|----------------|
| “OPENAI_API_KEY not set” | Set `OPENAI_API_KEY` in `.env` and restart. |
| Redis connection errors | Redis running? `REDIS_URL` correct? |
| Database errors | PostgreSQL running, DB created, credentials in `.env`, migrations applied. |
| “No module named …” | Activate venv and run `pip install -r requirements.txt`. |
| Agents not advancing | Controller must be running (`python manage.py run_controller`). |
| 404 on dashboard / new consultation | Use `/api/dashboard/` and `/api/new-consultation/`. |

---

## Summary Checklist

- [ ] Python 3.10+, PostgreSQL, Redis installed and running  
- [ ] Venv created and activated  
- [ ] `pip install -r requirements.txt`  
- [ ] `.env` with `DJANGO_SECRET_KEY`, `OPENAI_API_KEY`, DB, Redis  
- [ ] Database created, `migrate` and `createsuperuser`  
- [ ] `python manage.py runserver` (first terminal)  
- [ ] `python manage.py run_controller` (second terminal)  
- [ ] Log in and run a test consultation  
