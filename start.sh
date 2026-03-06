#!/bin/bash
# Activate environment (if needed)
export PYTHONUNBUFFERED=1

# Apply migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Run Daphne (Channels) on port 10000
# & runs the controller loop in the background
daphne -b 0.0.0.0 -p 10000 core.asgi:application &

# Run your controller loop
python manage.py run_controller