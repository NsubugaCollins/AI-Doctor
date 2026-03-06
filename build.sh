#!/usr/bin/env bash

# 1. Install all Python packages listed in requirements.txt
pip install -r requirements.txt

# 2. Collect static files (like CSS, JS, images) into the STATIC_ROOT folder
python manage.py collectstatic --noinput

# 3. Apply database migrations
python manage.py migrate