# Local Development Iteration Guide

This guide explains how to run a local version of the SDLL app using production data from `railway_backup.sql` to test and verify changes before deploying.

## Prerequisites

- **Python 3.11+** installed
- **MySQL 8.x** installed and running locally
- **Git** for version control

## Initial Setup (One-Time)

### 1. Create Local MySQL Database

```bash
# Connect to MySQL as root
mysql -u root -p

# Create the local database
CREATE DATABASE sdll;

# Exit MySQL
exit
```

### 2. Configure Environment Variables

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Edit `.env` with your local settings:

```env
FLASK_CONFIG=development
SECRET_KEY=dev-secret-key-for-local-testing
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your-local-mysql-password
MYSQL_DB=sdll
ENCRYPTION_KEY=your-encryption-key-here
```

**Important**: For testing with production data, the `ENCRYPTION_KEY` must match the production key (stored securely). Without the correct key, user logins will not work because emails are encrypted.

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

## Importing Production Data

### Option A: Fresh Import from railway_backup.sql

Use this when you want to reset your local database to match production:

```bash
# Drop and recreate the database (DESTRUCTIVE - loses local changes)
mysql -u root -p -e "DROP DATABASE IF EXISTS sdll; CREATE DATABASE sdll;"

# Import the backup
mysql -u root -p sdll < railway_backup.sql
```

### Option B: Selective Import

If you only need certain tables refreshed:

```bash
# Connect to MySQL and selectively import
mysql -u root -p sdll

# Example: Import only specific tables by extracting from the dump
# This requires manual extraction from railway_backup.sql
```

### Verifying the Import

```bash
mysql -u root -p sdll -e "SHOW TABLES;"
```

Expected tables include: `fields`, `field_slots`, `games`, `leagues`, `teams`, `sdll_users`, etc.

## Running the Local Server

### Start the Development Server

```bash
python run.py
```

The app runs at: **http://localhost:8084**

### What to Verify on Startup

1. No database connection errors in the console
2. App loads without import errors
3. Can navigate to the home page

## Development Iteration Workflow

### Typical Workflow for Making Changes

1. **Pull latest production data** (if needed):
   ```bash
   # Get a fresh backup from Railway if data has changed
   # Then import locally:
   mysql -u root -p sdll < railway_backup.sql
   ```

2. **Start the local server**:
   ```bash
   python run.py
   ```

3. **Make your code changes** in the `app/` directory

4. **Test the changes** in your browser at http://localhost:8084
   - Flask debug mode auto-reloads on file changes
   - No need to restart the server for most Python changes

5. **Verify the behavior** by navigating to affected pages

6. **Run automated tests** (if applicable):
   ```bash
   python run_tests.py
   ```

### Verifying Specific Features

| Feature Area | What to Test | URL Path |
|--------------|--------------|----------|
| Scheduling | View/generate schedules | `/seasons/2026/1/schedule` |
| Field Management | View/edit fields | `/fields/` |
| Team Management | View/edit teams | `/seasons/2026/1/teams` |
| League Settings | Schedule settings | `/seasons/2026/1/schedule-settings` |
| Playoffs | Bracket management | `/seasons/2026/1/playoffs/<league>` |

### Testing Schedule Generation

The scheduler is the most complex feature. To test it:

1. Navigate to a league's schedule page
2. Check the "Generate Schedule" functionality
3. Verify games appear correctly
4. Check for any constraint violations (field restrictions, time limits)

## Troubleshooting

### "Can't connect to MySQL server"

- Ensure MySQL service is running: `net start mysql` (Windows) or `brew services start mysql` (Mac)
- Verify credentials in `.env` match your local MySQL setup

### "Encryption key mismatch" / Login doesn't work

- You need the production `ENCRYPTION_KEY` to test with production user data
- Alternative: Create a new test user locally with `scripts/seed_users.py`

### "Table doesn't exist" errors

- Import hasn't completed or was interrupted
- Re-run the full import: `mysql -u root -p sdll < railway_backup.sql`

### Changes not appearing

- Check for Python syntax errors in the console
- Hard refresh browser (Ctrl+Shift+R) to clear cache
- Restart the server if templates were added/removed

## Creating a Fresh Backup from Railway

If you need to pull the latest production data:

```bash
# Using Railway CLI (if installed)
railway run mysqldump -u $MYSQLUSER -p$MYSQLPASSWORD $MYSQLDATABASE > railway_backup.sql

# Or manually with Railway credentials from dashboard
mysqldump -h <MYSQLHOST> -P <MYSQLPORT> -u <MYSQLUSER> -p<MYSQLPASSWORD> <MYSQLDATABASE> > railway_backup.sql
```

## Quick Reference

| Action | Command |
|--------|---------|
| Start server | `python run.py` |
| Run tests | `python run_tests.py` |
| Import backup | `mysql -u root -p sdll < railway_backup.sql` |
| View app | http://localhost:8084 |
| Stop server | `Ctrl+C` |

## Git Workflow After Changes

Once your changes are verified locally:

```bash
# Check what changed
git status
git diff

# Stage and commit
git add <specific-files>
git commit -m "Description of changes"

# Push to trigger Railway deployment
git push origin main
```

Railway auto-deploys on push to `main`, so the production site updates automatically.
