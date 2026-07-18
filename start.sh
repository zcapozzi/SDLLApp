#!/bin/bash
echo "=== Starting SDLL App ==="
echo "PORT: $PORT"
echo "PWD: $(pwd)"
echo "Python: $(which python)"
echo "Gunicorn: $(which gunicorn)"
echo "=== Testing Python import ==="
python -c "from app import create_app; print('Import OK')" 2>&1
echo "=== Starting Gunicorn ==="
exec gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
