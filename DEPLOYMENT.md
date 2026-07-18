# Deploying SDLL to Railway

## Quick Start

1. **Create Railway Account**: Go to [railway.app](https://railway.app) and sign up with GitHub.

2. **Create New Project**:
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose the SDLLApp repository

3. **Add MySQL Database**:
   - In your project, click "New" → "Database" → "MySQL"
   - Railway automatically creates `MYSQL_URL` environment variable

4. **Set Environment Variables**:
   In the web service settings, add:
   ```
   FLASK_CONFIG=production
   SECRET_KEY=<generate-a-strong-secret>
   ENCRYPTION_KEY=<generate-a-strong-key>
   ```

   Generate keys with:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

5. **Deploy**: Railway auto-deploys on every push to main branch.

6. **Import Database** (first time):
   - Get the MySQL connection details from Railway dashboard
   - Import your SQL dump:
     ```bash
     mysql -h <host> -P <port> -u <user> -p<password> <database> < Dump20260702.sql
     ```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FLASK_CONFIG` | Yes | Set to `production` |
| `SECRET_KEY` | Yes | Flask session secret (32+ hex chars) |
| `ENCRYPTION_KEY` | Yes | PII encryption key (32+ hex chars) |
| `MYSQL_URL` | Auto | Set automatically by Railway MySQL plugin |

## Custom Domain

1. In Railway project settings, go to "Settings" → "Domains"
2. Add custom domain: `southdurhamlittleleague.org`
3. Update DNS records at your registrar:
   - Add CNAME record pointing to Railway's provided domain

## Monitoring

- **Logs**: Railway dashboard → Select service → "Logs" tab
- **Metrics**: Railway dashboard → "Metrics" tab shows CPU/memory usage

## Database Management

Access MySQL from Railway dashboard:
1. Click on MySQL service
2. Click "Connect" → "MySQL CLI" or use provided credentials

Or use a local client:
```bash
mysql -h <MYSQLHOST> -P <MYSQLPORT> -u <MYSQLUSER> -p<MYSQLPASSWORD> <MYSQLDATABASE>
```

## Troubleshooting

### App won't start
- Check logs for errors
- Verify all required environment variables are set
- Ensure `MYSQL_URL` is properly linked

### Database connection errors
- Check that MySQL service is running
- Verify `MYSQL_URL` environment variable exists
- Check MySQL service logs

### Static files not loading
- Clear browser cache
- Check that `app/static/` is properly served

## Cost Estimate

Railway pricing (as of 2024):
- **Starter plan**: $5/month base + usage
- **Typical usage for SDLL**: ~$15-25/month total
  - Web service: ~$5-10/month
  - MySQL database: ~$10-15/month

Annual estimate: **$180-300/year**

## Rollback

If a deployment breaks:
1. Railway dashboard → Deployments tab
2. Click on a previous successful deployment
3. Click "Redeploy"

## Local Development

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your local MySQL credentials

# Install dependencies
pip install -r requirements.txt

# Run locally
python run.py
```

App runs at http://localhost:8084
