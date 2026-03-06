#!/bin/bash

export PYTHONUNBUFFERED=1

# Apply migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Start controller in background
python manage.py run_controller &

# Start Daphne (main web process)
daphne -b 0.0.0.0 -p $PORT core.asgi:application