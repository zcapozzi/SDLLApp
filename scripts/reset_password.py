#!/usr/bin/env python3
"""Reset a user's password in the SDLL database.

Usage:
    python scripts/reset_password.py <user_id> <new_password>

Example:
    python scripts/reset_password.py 1 MyNewPassword123

Can be run locally or in Railway shell.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash


def get_db_connection():
    """Get database connection using environment variables."""
    import pymysql

    # Check for MYSQL_URL first (Railway)
    mysql_url = os.environ.get('MYSQL_URL') or os.environ.get('DATABASE_URL')

    if mysql_url:
        # Parse URL: mysql://user:pass@host:port/database
        from urllib.parse import urlparse
        parsed = urlparse(mysql_url)
        return pymysql.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path.lstrip('/'),
            charset='utf8mb4'
        )
    else:
        # Use individual env vars (local development)
        return pymysql.connect(
            host=os.environ.get('MYSQL_HOST', 'localhost'),
            port=int(os.environ.get('MYSQL_PORT', 3306)),
            user=os.environ.get('MYSQL_USER', 'root'),
            password=os.environ.get('MYSQL_PASSWORD', ''),
            database=os.environ.get('MYSQL_DB', 'sdll'),
            charset='utf8mb4'
        )


def list_users():
    """List all users in the database."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT ID, role, active, created_at FROM sdll_users")
            users = cursor.fetchall()

            print("\nExisting users:")
            print("-" * 50)
            print(f"{'ID':<5} {'Role':<20} {'Active':<8} {'Created'}")
            print("-" * 50)
            for user in users:
                print(f"{user[0]:<5} {user[1]:<20} {user[2]:<8} {user[3]}")
            print()
    finally:
        conn.close()


def reset_password(user_id: int, new_password: str):
    """Reset password for a user."""
    if len(new_password) < 8:
        print("Error: Password must be at least 8 characters")
        sys.exit(1)

    password_hash = generate_password_hash(new_password)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check if user exists
            cursor.execute("SELECT ID, role FROM sdll_users WHERE ID = %s", (user_id,))
            user = cursor.fetchone()

            if not user:
                print(f"Error: User with ID {user_id} not found")
                list_users()
                sys.exit(1)

            # Update password
            cursor.execute(
                "UPDATE sdll_users SET password_hash = %s WHERE ID = %s",
                (password_hash, user_id)
            )
            conn.commit()

            print(f"Password reset successfully for user ID {user_id} (role: {user[1]})")
    finally:
        conn.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nListing current users...\n")
        try:
            list_users()
        except Exception as e:
            print(f"Error connecting to database: {e}")
            print("\nMake sure environment variables are set:")
            print("  - MYSQL_URL (Railway) or")
            print("  - MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB (local)")
        sys.exit(1)

    if len(sys.argv) < 3:
        print("Error: Please provide both user_id and new_password")
        print("Usage: python scripts/reset_password.py <user_id> <new_password>")
        sys.exit(1)

    try:
        user_id = int(sys.argv[1])
    except ValueError:
        print("Error: user_id must be a number")
        sys.exit(1)

    new_password = sys.argv[2]

    reset_password(user_id, new_password)


if __name__ == '__main__':
    main()
