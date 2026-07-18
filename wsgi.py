"""Production WSGI entry point for Railway/Gunicorn."""

import sys
import os

print("WSGI: Starting...", flush=True)
print(f"WSGI: Python version: {sys.version}", flush=True)
print(f"WSGI: MYSQL_URL present: {'MYSQL_URL' in os.environ}", flush=True)
print(f"WSGI: SECRET_KEY present: {'SECRET_KEY' in os.environ}", flush=True)

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("WSGI: Importing app...", flush=True)
try:
    from app import create_app
    print("WSGI: App imported successfully", flush=True)
except Exception as e:
    print(f"WSGI: Import error: {e}", flush=True)
    raise

# Create the app with production config
print("WSGI: Creating app...", flush=True)
try:
    app = create_app(os.environ.get('FLASK_CONFIG', 'production'))
    print("WSGI: App created successfully", flush=True)
except Exception as e:
    print(f"WSGI: App creation error: {e}", flush=True)
    raise
