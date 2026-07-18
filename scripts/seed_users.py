#!/usr/bin/env python
"""Seed initial users for SDLL Web Application

Run this script to create the initial admin users specified in the implementation plan.

Usage:
    python scripts/seed_users.py
"""

import os
import sys

# Add parent directory to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Load .env file from project root
from dotenv import load_dotenv
env_path = os.path.join(project_root, '.env')
load_dotenv(env_path)

from cryptography.fernet import Fernet

# Set encryption key if not set (fallback for development)
if not os.environ.get('ENCRYPTION_KEY'):
    print("Warning: ENCRYPTION_KEY not set in .env, generating temporary key")
    os.environ['ENCRYPTION_KEY'] = Fernet.generate_key().decode()

from app import create_app, db
from app.models.user import User


def seed_users():
    """Create initial users"""
    app = create_app('development')

    with app.app_context():
        # Users to create as specified in the plan
        users_to_create = [
            {
                'email': 'schedule.sdll@gmail.com',
                'password': 'changeme123',  # Should be changed after first login
                'name': 'Janna Price',
                'phone': '123-456-7890',
                'role': 'scheduler'
            },
            {
                'email': 'sdll.umpires@gmail.com',
                'password': 'changeme123',  # Should be changed after first login
                'name': 'Zack Capozzi',
                'phone': '773-420-6844',
                'role': 'umpire_coordinator'
            }
        ]

        created = []
        skipped = []

        for user_data in users_to_create:
            existing = User.get_by_email(user_data['email'])
            if existing:
                skipped.append(user_data['email'])
                print(f"Skipped: {user_data['email']} (already exists)")
                continue

            try:
                user = User.create_user(
                    email=user_data['email'],
                    password=user_data['password'],
                    name=user_data['name'],
                    phone=user_data.get('phone'),
                    role=user_data['role']
                )
                created.append(user_data['email'])
                print(f"Created: {user_data['email']} ({user_data['role']})")
            except Exception as e:
                print(f"Error creating {user_data['email']}: {e}")

        print(f"\nSummary: {len(created)} created, {len(skipped)} skipped")

        if created:
            print("\nIMPORTANT: Default password is 'changeme123'")
            print("Please change passwords after first login!")


if __name__ == '__main__':
    seed_users()
