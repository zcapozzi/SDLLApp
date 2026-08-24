# Cron Jobs

This project uses [cron-job.org](https://cron-job.org) (free tier) to trigger scheduled tasks via HTTP endpoints.

## How It Works

1. Cron endpoints are defined in `app/main/routes.py` under the `/cron/` prefix
2. Each endpoint is protected by a secret token (`CRON_SECRET` environment variable)
3. cron-job.org calls these endpoints on a schedule
4. The endpoint performs the task and optionally sends email alerts

## Security

All cron endpoints require a `token` query parameter that must match the `CRON_SECRET` environment variable.

```
https://www.southdurhamlittleleague.org/cron/ENDPOINT?token=YOUR_CRON_SECRET
```

**Never expose the CRON_SECRET in client-side code or public documentation.**

## Current Cron Endpoints

### 1. Check New Games
**Endpoint:** `/cron/check-new-games`

Checks for games added recently in leagues that require umpires. Sends an email alert if any are found.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `token` | required | CRON_SECRET for authentication |
| `hours` | 2 | How many hours back to check |
| `recipient` | sdll.umpires@gmail.com | Email recipient |

**Example URL:**
```
https://www.southdurhamlittleleague.org/cron/check-new-games?token=SECRET&hours=2
```

**Recommended schedule:** Every 2 hours

---

### 2. Unassigned Umpires
**Endpoint:** `/cron/unassigned-umpires`

Checks for upcoming games that need umpires but don't have assignments. Finds games where:
- League requires umpires (`umpire_count > 0`)
- No `umpire_override` set (no delegation decision made)
- Not flagged as no-umpires (`umpire_count_override != 0`)
- Fewer assignments than required

| Parameter | Default | Description |
|-----------|---------|-------------|
| `token` | required | CRON_SECRET for authentication |
| `days` | 7 | How many days ahead to check |
| `recipient` | sdll.umpires@gmail.com | Email recipient |

**Example URL:**
```
https://www.southdurhamlittleleague.org/cron/unassigned-umpires?token=SECRET&days=7
```

**Recommended schedule:** Daily at 8:00 AM

---

## Setting Up cron-job.org

1. Create a free account at [cron-job.org](https://cron-job.org)
2. Click "Create cronjob"
3. Configure:
   - **Title:** Descriptive name (e.g., "SDLL New Games Alert")
   - **URL:** Full endpoint URL with token
   - **Schedule:** Use the visual scheduler or cron expression
   - **Request method:** GET
   - **Notifications:** Enable failure notifications (optional)
4. Save and enable the job

### Cron Expressions

| Schedule | Expression |
|----------|------------|
| Every 2 hours | `0 */2 * * *` |
| Daily at 8 AM | `0 8 * * *` |
| Every 6 hours | `0 */6 * * *` |
| Weekdays at 9 AM | `0 9 * * 1-5` |

---

## Adding a New Cron Endpoint

### 1. Create the endpoint in `app/main/routes.py`:

```python
@main_bp.route('/cron/your-new-task')
def cron_your_new_task():
    """
    Description of what this cron job does.

    Call with ?token=YOUR_SECRET&param=value
    """
    import os
    from datetime import datetime, timedelta
    from app.services.notification_service import GmailService

    # Verify secret token
    expected_token = os.environ.get('CRON_SECRET')
    provided_token = request.args.get('token')

    if not expected_token:
        return jsonify({'error': 'CRON_SECRET not configured'}), 500

    if provided_token != expected_token:
        return jsonify({'error': 'Invalid token'}), 403

    # Get parameters
    param = request.args.get('param', 'default_value')
    recipient = request.args.get('recipient', 'sdll.umpires@gmail.com')

    # Do your work here...
    results = do_something()

    if not results:
        return jsonify({
            'status': 'ok',
            'message': 'Nothing to report'
        }), 200

    # Send email if needed
    gmail = GmailService()
    if not gmail.is_configured:
        return jsonify({'error': 'Email service not configured'}), 500

    try:
        gmail.send_email(recipient, subject, body_text, body_html)
        return jsonify({
            'status': 'ok',
            'message': 'Alert sent'
        }), 200
    except Exception as e:
        return jsonify({'error': f'Failed to send email: {str(e)}'}), 500
```

### 2. Test locally:

```bash
curl "http://localhost:8084/cron/your-new-task?token=YOUR_LOCAL_CRON_SECRET"
```

### 3. Deploy and add to cron-job.org

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CRON_SECRET` | Secret token for authenticating cron requests |
| `RESEND_API_KEY` | Resend API key for sending emails |
| `GMAIL_SENDER` | From address for emails |

---

## Monitoring

- cron-job.org shows execution history and response codes
- Check Railway logs for detailed error messages
- Each endpoint returns JSON with status information

### Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success (check `status` field in JSON) |
| 403 | Invalid or missing token |
| 500 | Server error (check logs) |
