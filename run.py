"""Development server entry point"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

from app import create_app

app = create_app(os.environ.get('FLASK_CONFIG', 'development'))

if __name__ == '__main__':
    # Run on port 8084 as specified in CLAUDE.md
    app.run(
        host='localhost',
        port=8084,
        debug=True
    )
