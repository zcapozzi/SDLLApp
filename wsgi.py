"""Production WSGI entry point for Railway/Gunicorn."""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app import create_app

# Create the app with production config
app = create_app(os.environ.get('FLASK_CONFIG', 'production'))
