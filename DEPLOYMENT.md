# Deploying SDLL to Railway

## Production URL

**Live Site**: https://www.southdurhamlittleleague.org

## Architecture Overview

```
[Browser] → [Railway Web Service (Gunicorn/Flask)] → [Railway MySQL Database]
```

- **Web Service**: Python Flask app served by Gunicorn
- **Database**: MySQL 8.x hosted on Railway
- **Domain**: Custom domain with CNAME pointing to Railway

## Quick Start (New Deployment)

1. **Create Railway Account**: Go to [railway.app](https://railway.app) and sign up with GitHub.

2. **Create New Project**:
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose the SDLLApp repository

3. **Add MySQL Database**:
   - In your project, click "New" → "Database" → "MySQL"
   - Railway automatically creates `MYSQL_URL` environment variable
   - **Important**: Ensure the MySQL service is linked to your web service

4. **Set Environment Variables** (see detailed section below)

5. **Import Database**:
   - Use the latest SQL dump from the repository
   - See "Database Import" section below

6. **Deploy**: Railway auto-deploys on every push to main branch.

## Environment Variables

**Critical**: These must be set correctly in Railway dashboard → Web Service → Variables

| Variable | Required | Value | Notes |
|----------|----------|-------|-------|
| `FLASK_CONFIG` | **Yes** | `production` | **Must be exactly `production`** - not "development" or "deployment" |
| `SECRET_KEY` | **Yes** | 32+ char secret | Flask session encryption |
| `ENCRYPTION_KEY` | **Yes** | Fernet key | **Must match the key used to encrypt existing user data** |
| `MYSQL_URL` | Auto | `mysql://...` | Auto-created by Railway MySQL plugin |

### ENCRYPTION_KEY Warning

User emails and PII are encrypted with Fernet symmetric encryption. If you change the `ENCRYPTION_KEY`:
- **All existing user logins will break** (emails can't be decrypted/matched)
- You would need to re-encrypt all user data or create new users

The current production encryption key is stored securely. Contact the project admin if you need it.

### Generating New Keys

```bash
# For SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# For ENCRYPTION_KEY (Fernet format)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Database Import

### First-time Setup or Data Refresh

1. Find the latest SQL dump in the repo (e.g., `Dump20260718.sql`)

2. Get Railway MySQL credentials from dashboard:
   - Click on MySQL service → "Connect" tab
   - Copy the connection details

3. Import from local machine:
   ```bash
   mysql -h <MYSQLHOST> -P <MYSQLPORT> -u <MYSQLUSER> -p<MYSQLPASSWORD> <MYSQLDATABASE> < Dump20260718.sql
   ```

4. Or from Railway shell (if dump is in repo):
   ```bash
   mysql -h $MYSQLHOST -P $MYSQLPORT -u $MYSQLUSER -p$MYSQLPASSWORD $MYSQLDATABASE < Dump20260718.sql
   ```

### Creating New SQL Dumps

From local MySQL:
```bash
mysqldump -h localhost -u <user> -p <database> > Dump$(date +%Y%m%d).sql
```

## Custom Domain Setup

Current domain: `southdurhamlittleleague.org`

1. In Railway project → Settings → Domains
2. Add custom domain
3. At your DNS registrar, add CNAME record:
   - Name: `www` (or `@` for root)
   - Target: Railway's provided domain (e.g., `xxx.up.railway.app`)

## Monitoring & Logs

### Viewing Logs

**Railway Dashboard** (recommended):
1. Go to your project
2. Click on the web service
3. Click "Logs" tab (not the shell)

**Railway CLI**:
```bash
railway logs
```

### Health Check

The app exposes a health endpoint:
```
GET https://www.southdurhamlittleleague.org/health
```

Returns `{"status": "healthy"}` when the app is running.

### Error Logging

The app has a global error handler that logs full stack traces to stderr. When a 500 error occurs:
1. The user sees a simple error page with the exception message
2. Full traceback is logged to Railway logs

## Troubleshooting

### 500 Error on Login

**Symptom**: Login page returns 500 error

**Check these in order**:

1. **FLASK_CONFIG**: Must be exactly `production`
   ```bash
   # In Railway shell
   echo $FLASK_CONFIG
   ```
   - If set to `development`, app tries to connect to `localhost` MySQL (fails)
   - If set to anything other than `production`, `testing`, or `development`, app may crash

2. **MYSQL_URL**: Must be set
   ```bash
   # In Railway shell
   echo $MYSQL_URL
   ```
   - Should look like `mysql://user:pass@host:port/database`
   - If missing, link the MySQL service to your web service in Railway dashboard

3. **ENCRYPTION_KEY**: Must match original key
   - If wrong, user email lookup fails silently (no matching hash)
   - Check Railway logs for decryption errors

4. **Database tables**: Ensure `sdll_users` table exists
   ```bash
   # In Railway shell
   mysql -h $MYSQLHOST -P $MYSQLPORT -u $MYSQLUSER -p$MYSQLPASSWORD $MYSQLDATABASE -e "SHOW TABLES;"
   ```

### App Won't Start

- Check "Logs" tab (not shell) for startup errors
- Verify all required environment variables are set
- Check that `requirements.txt` dependencies installed successfully

### Database Connection Refused

Error: `Can't connect to MySQL server on 'localhost'`

**Cause**: `FLASK_CONFIG` is not set to `production`

**Fix**: Set `FLASK_CONFIG=production` in Railway variables

### Railway Shell vs Logs

- **Shell** (`root@xxx:/app#`): Interactive terminal for debugging - your app runs separately
- **Logs**: Output from your running Gunicorn/Flask app - this is where errors appear

## Configuration Files

| File | Purpose |
|------|---------|
| `Procfile` | Tells Railway how to start the app |
| `railway.toml` | Railway-specific config (start command, health check) |
| `requirements.txt` | Python dependencies |
| `wsgi.py` | Gunicorn entry point |
| `app/config.py` | Flask configuration classes |

## Cost Estimate

Railway pricing (as of 2026):
- **Starter plan**: $5/month base + usage
- **Typical usage for SDLL**: ~$15-25/month total
  - Web service: ~$5-10/month
  - MySQL database: ~$10-15/month

**Annual estimate: $180-300/year**

## Rollback

If a deployment breaks:
1. Railway dashboard → Deployments tab
2. Click on a previous successful deployment
3. Click "Redeploy"

## Local Development

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your local MySQL credentials and keys

# Install dependencies
pip install -r requirements.txt

# Run locally
python run.py
```

App runs at http://localhost:8084

## Key Contacts

- **Repository**: [GitHub - SDLLApp]
- **Hosting**: Railway.app
- **Domain Registrar**: [Your registrar]
