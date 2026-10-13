#!/usr/bin/env python
"""Test script to verify Anthropic API connectivity.

Run this directly to test if the API key and endpoint work:
    python scripts/test_anthropic_api.py
"""

import os
import sys
import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env file
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    load_dotenv(env_path)
    print(f"Loaded .env from: {env_path}")
except ImportError:
    print("python-dotenv not installed, using environment variables only")

def test_anthropic_api():
    """Test a simple API call to Anthropic."""

    api_key = os.environ.get('ANTHROPIC_API_KEY')

    print("=" * 60)
    print("Anthropic API Test")
    print("=" * 60)

    # Check API key
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set")
        print("\nTo set it, run:")
        print("  set ANTHROPIC_API_KEY=sk-ant-...")
        return False

    print(f"API Key present: Yes")
    print(f"API Key prefix: {api_key[:15]}...")
    print(f"API Key length: {len(api_key)} characters")

    # Test simple message (no image)
    url = "https://api.anthropic.com/v1/messages"
    model = "claude-haiku-5-5"

    headers = {
        'Content-Type': 'application/json',
        'x-api-key': api_key,
        'anthropic-version': '2023-06-01'
    }

    payload = {
        "model": model,
        "max_tokens": 50,
        "messages": [
            {
                "role": "user",
                "content": "Say hello in exactly 3 words."
            }
        ]
    }

    print(f"\nEndpoint: {url}")
    print(f"Model: {model}")
    print(f"Headers: {list(headers.keys())}")

    print("\nSending request...")

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )

        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Headers:")
        for key, value in response.headers.items():
            if key.lower() in ['content-type', 'x-request-id', 'anthropic-ratelimit-requests-remaining']:
                print(f"  {key}: {value}")

        if response.status_code == 200:
            result = response.json()
            content = result.get('content', [{}])[0].get('text', '')
            print(f"\nAPI Response: {content}")
            print("\n[PASS] API connection successful!")
            return True
        else:
            print(f"\nError Response Body:")
            print(response.text[:1000])
            print("\n[FAIL] API call failed")
            return False

    except requests.exceptions.Timeout:
        print("\n[FAIL] Request timed out")
        return False
    except requests.exceptions.RequestException as e:
        print(f"\n[FAIL] Request failed: {type(e).__name__}: {e}")
        return False
    except Exception as e:
        print(f"\n[FAIL] Unexpected error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_anthropic_api()
    sys.exit(0 if success else 1)
