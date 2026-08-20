# SDLL Privacy Approach

This document defines the privacy principles for the South Durham Little League web application. All contributors must adhere to these principles when implementing features that involve user data.

## Core Principles

### 1. First-Party Only

**We never share data with third parties.**

- All tracking data stays in our database
- No Google Analytics, Facebook Pixel, or similar third-party trackers
- No advertising networks (AdSense, etc.)
- No CDNs that track users (we self-host assets or use privacy-respecting CDNs)
- No embedded content from tracking-heavy sources (YouTube embeds, social widgets)

### 2. No Personally Identifiable Information (PII)

**We do not collect information that can identify individuals.**

What we DO NOT collect:
- Names
- Email addresses (except for admin accounts, which are voluntary)
- Phone numbers
- Physical addresses
- Photos of individuals
- Any data from children directly

What we MAY collect (anonymized):
- Hashed IP addresses (SHA-256, cannot be reversed)
- Anonymous session IDs (random UUID, not linked to identity)
- Device type and viewport size
- Page view timestamps
- Referrer URLs

### 3. No Cross-Site Tracking

**We only know what users do on our site.**

- Session cookies are first-party only (same-site)
- We do not participate in any cross-site tracking networks
- We cannot and do not want to know what users do elsewhere
- Our anonymous session IDs are meaningless outside our domain

### 4. Minimal Data Collection

**We only collect what we need for legitimate purposes.**

Legitimate purposes for this project:
- Understanding which team schedules are most viewed
- Knowing peak usage times for capacity planning
- Measuring engagement (are people actually reading the schedule?)
- Tracking ad impressions for sponsor reporting (if we have sponsors)

We do NOT collect data for:
- Building user profiles
- Behavioral targeting
- Selling to data brokers
- Any purpose beyond basic analytics

### 5. Transparency

**Users should understand what we collect and why.**

- Maintain a public privacy page explaining our approach in plain language
- Do not use dark patterns or confusing language
- Make this document available to anyone who asks

---

## Technical Implementation Guidelines

### Session Tracking

```python
# CORRECT: Anonymous session ID
session_id = str(uuid.uuid4())  # Random, meaningless outside our system

# WRONG: Do not use identifiable cookies
user_id = "john.smith@email.com"  # Never store PII in cookies
```

### IP Address Handling

```python
# CORRECT: Hash the IP immediately, never store raw
import hashlib
ip_hash = hashlib.sha256(request.remote_addr.encode()).hexdigest()

# WRONG: Do not store raw IP addresses
raw_ip = request.remote_addr  # This is PII, don't store it
```

### Data Retention

- Page views: Retain for 2 years (for year-over-year analysis)
- Ad impressions: Retain for 2 years
- Ad clicks: Retain for 2 years
- Consider implementing automatic purging of old data

### Third-Party Libraries

Before adding any JavaScript library or external service, verify:
1. Does it phone home to external servers? (If yes, don't use it)
2. Does it set cookies? (If yes, understand what they're for)
3. Is there a privacy-respecting alternative?

### COPPA Considerations

Since this is a Little League site:
- Assume children may visit the public pages
- Never collect PII from any visitor (this satisfies COPPA)
- Do not create accounts for children
- Admin accounts are for adults only

---

## What This Means in Practice

### Adding a New Public Feature

When adding a new public-facing feature, ask:
1. Does this require any user data? If not, great - no privacy concerns.
2. If yes, can we use anonymous/aggregated data instead of individual tracking?
3. Are we storing the minimum data needed?
4. Would we be comfortable explaining this to a parent?

### Adding Analytics

If you want to understand user behavior:
- Use our first-party PageView tracking
- Aggregate data for reporting (don't look at individual sessions)
- Delete or anonymize data after analysis if no longer needed

### Adding Advertisements

If displaying ads or sponsor content:
- Use our self-hosted ad system only
- Track impressions and clicks in our database
- Never integrate with ad networks
- Provide honest metrics to sponsors (no inflated numbers)

---

## Compliance Summary

| Regulation | Our Compliance |
|------------|----------------|
| **GDPR** | No PII collected, legitimate interest basis, no consent banner needed |
| **CCPA** | No personal information sold, no data broker involvement |
| **COPPA** | No PII collected from any user, including children |

---

## Review Process

Any feature that involves user data collection should be reviewed against this document before implementation. If unsure, default to collecting less data rather than more.

**Last updated:** August 2026
