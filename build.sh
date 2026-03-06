#!/bin/bash
# ---------------------------------------
# build.sh for Render deployment
# ---------------------------------------

# Exit immediately if a command fails
set -e

echo "✅ Starting Build Script"

# ---------------------------------------
# 1. Activate virtual environment (if needed)
# ---------------------------------------
if [ -f ".venv/bin/activate" ]; then
    echo "🔹 Activating virtual environment"
    source .venv/bin/activate
fi

# ---------------------------------------
# 2. Install dependencies
# ---------------------------------------
echo "🔹 Installing dependencies"
pip install --upgrade pip
pip install -r requirements.txt

# ---------------------------------------
# 3. Apply database migrations
# ---------------------------------------
echo "🔹 Applying database migrations"
python manage.py migrate --noinput

# ---------------------------------------
# 4. Collect static files
# ---------------------------------------
echo "🔹 Collecting static files"
python manage.py collectstatic --noinput

# ---------------------------------------
# 5. Optional: Check if LLM API keys are set
# ---------------------------------------
if [ -z "$OPENAI_API_KEY" ] && [ -z "$DEEPSEEK_API_KEY" ] && [ -z "$GROQ_API_KEY" ]; then
    echo "⚠️ WARNING: No LLM API key set. AI features will not work."
fi

# ---------------------------------------
# 6. Start Gunicorn server
# ---------------------------------------
echo "🔹 Starting Gunicorn server"
# Port provided by Render is $PORT
exec gunicorn core.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 3 \
    --log-level info