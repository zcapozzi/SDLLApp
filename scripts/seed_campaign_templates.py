"""Seed email campaign templates.

Run with: python scripts/seed_campaign_templates.py

Creates the pre-defined campaign templates for partner coordination,
prospective umpire outreach, returning umpire retention, and admin marketing.
"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.email_campaign_template import EmailCampaignTemplate


TEMPLATES = [
    # Partner Coordination
    {
        'name': 'Partner Rate Confirmation',
        'code': 'partner_rate_confirm',
        'description': 'Confirm game rates and fees with partner organizations before the season starts.',
        'category': 'partner',
        'subject_template': 'SDLL {{season_name}} - Confirm Umpire Rates',
        'body_html_template': '''
<p>Hi {{recipient_name}},</p>

<p>As we prepare for the {{season_name}} season at South Durham Little League, I wanted to confirm our umpire game rates with {{partner_name}}.</p>

<p><strong>Season Dates:</strong></p>
<ul>
    <li>First Practice: {{first_practice_date}}</li>
    <li>Opening Day: {{opening_day_date}}</li>
    <li>Season End: {{season_end_date}}</li>
</ul>

<p>Please confirm that the rates we have on file are still accurate, or let us know of any changes.</p>

<p>Looking forward to another great season!</p>

<p>Best regards,<br>
SDLL Umpire Coordination<br>
{{coordinator_email}}</p>
''',
        'body_text_template': '''Hi {{recipient_name}},

As we prepare for the {{season_name}} season at South Durham Little League, I wanted to confirm our umpire game rates with {{partner_name}}.

Season Dates:
- First Practice: {{first_practice_date}}
- Opening Day: {{opening_day_date}}
- Season End: {{season_end_date}}

Please confirm that the rates we have on file are still accurate, or let us know of any changes.

Looking forward to another great season!

Best regards,
SDLL Umpire Coordination
{{coordinator_email}}
''',
        'trigger_type': 'milestone',
        'trigger_milestone': 'first_practice',
        'trigger_days_offset': -28,  # 4 weeks before
        'recipient_type': 'partner',
    },

    # Prospective Umpire - Training Announcement
    {
        'name': 'Training Session Announcement',
        'code': 'prospect_training_announce',
        'description': 'Announce training session details to prospective umpires.',
        'category': 'prospective',
        'subject_template': 'SDLL {{season_name}} Umpire Training - Mark Your Calendar!',
        'body_html_template': '''
<p>Hi {{recipient_name}},</p>

<p>Thank you for your interest in umpiring for South Durham Little League this {{season_name}}!</p>

<p>We're excited to announce our umpire training session:</p>

<p style="background: #f5f5f5; padding: 15px; border-radius: 8px;">
<strong>Training Date:</strong> {{training_date}}<br>
<strong>Location:</strong> SDLL Fields, Durham NC
</p>

<p>Before attending training, please complete the required Abuse Awareness training online. We'll send more details about this shortly.</p>

<p>Questions? Just reply to this email.</p>

<p>Best regards,<br>
SDLL Umpire Coordination<br>
{{coordinator_email}}</p>
''',
        'body_text_template': '''Hi {{recipient_name}},

Thank you for your interest in umpiring for South Durham Little League this {{season_name}}!

We're excited to announce our umpire training session:

Training Date: {{training_date}}
Location: SDLL Fields, Durham NC

Before attending training, please complete the required Abuse Awareness training online. We'll send more details about this shortly.

Questions? Just reply to this email.

Best regards,
SDLL Umpire Coordination
{{coordinator_email}}
''',
        'trigger_type': 'milestone',
        'trigger_milestone': 'first_practice',
        'trigger_days_offset': -21,  # 3 weeks before
        'recipient_type': 'lead',
        'recipient_status_filter': 'prospective,contacted',
    },

    # Prospective Umpire - Training RSVP Reminder
    {
        'name': 'Training RSVP Reminder',
        'code': 'prospect_training_rsvp',
        'description': 'Remind prospective umpires to RSVP for training.',
        'category': 'prospective',
        'subject_template': 'Reminder: SDLL Umpire Training on {{training_date}}',
        'body_html_template': '''
<p>Hi {{recipient_name}},</p>

<p>Just a quick reminder that our umpire training session is coming up!</p>

<p style="background: #f5f5f5; padding: 15px; border-radius: 8px;">
<strong>When:</strong> {{training_date}}<br>
<strong>Where:</strong> SDLL Fields, Durham NC
</p>

<p>Please reply to confirm your attendance, or let us know if you're unable to make it.</p>

<p>See you soon!</p>

<p>Best regards,<br>
SDLL Umpire Coordination<br>
{{coordinator_email}}</p>
''',
        'body_text_template': '''Hi {{recipient_name}},

Just a quick reminder that our umpire training session is coming up!

When: {{training_date}}
Where: SDLL Fields, Durham NC

Please reply to confirm your attendance, or let us know if you're unable to make it.

See you soon!

Best regards,
SDLL Umpire Coordination
{{coordinator_email}}
''',
        'trigger_type': 'milestone',
        'trigger_milestone': 'training_date',
        'trigger_days_offset': -5,  # 5 days before training
        'recipient_type': 'lead',
        'recipient_status_filter': 'prospective,contacted',
    },

    # Prospective Umpire - Abuse Awareness Training
    {
        'name': 'Abuse Awareness Training Reminder',
        'code': 'prospect_abuse_training',
        'description': 'Remind prospective umpires to complete required abuse awareness training.',
        'category': 'prospective',
        'subject_template': 'Required: Complete Abuse Awareness Training for {{season_name}}',
        'body_html_template': '''
<p>Hi {{recipient_name}},</p>

<p>Before you can umpire games for SDLL, you must complete the Little League Abuse Awareness training. This is a league requirement for all adult volunteers.</p>

<p><strong>How to complete it:</strong></p>
<ol>
    <li>Go to <a href="https://www.littleleague.org/player-safety/child-protection-program/">Little League Abuse Awareness Training</a></li>
    <li>Complete the online module (about 30 minutes)</li>
    <li>Save your completion certificate</li>
    <li>Reply to this email with a screenshot or forward your certificate</li>
</ol>

<p>Please complete this before the season starts on {{opening_day_date}}.</p>

<p>Questions? Just reply to this email.</p>

<p>Best regards,<br>
SDLL Umpire Coordination<br>
{{coordinator_email}}</p>
''',
        'body_text_template': '''Hi {{recipient_name}},

Before you can umpire games for SDLL, you must complete the Little League Abuse Awareness training. This is a league requirement for all adult volunteers.

How to complete it:
1. Go to https://www.littleleague.org/player-safety/child-protection-program/
2. Complete the online module (about 30 minutes)
3. Save your completion certificate
4. Reply to this email with a screenshot or forward your certificate

Please complete this before the season starts on {{opening_day_date}}.

Questions? Just reply to this email.

Best regards,
SDLL Umpire Coordination
{{coordinator_email}}
''',
        'trigger_type': 'milestone',
        'trigger_milestone': 'first_practice',
        'trigger_days_offset': -7,  # 1 week before
        'recipient_type': 'lead',
        'recipient_status_filter': 'prospective,contacted',
    },

    # Prospective Umpire - Payment Info
    {
        'name': 'Payment Information',
        'code': 'prospect_payment_info',
        'description': 'Send payment information to new umpires after they start working games.',
        'category': 'prospective',
        'subject_template': 'SDLL Umpire Payment Information',
        'body_html_template': '''
<p>Hi {{recipient_name}},</p>

<p>Now that you've started umpiring games for SDLL, here's how to request payment:</p>

<ol>
    <li>Keep track of the games you work (date, time, league)</li>
    <li>At the end of each month, submit your game log to {{coordinator_email}}</li>
    <li>Payment will be processed within 2 weeks</li>
</ol>

<p>If you have any questions about rates or the payment process, just reply to this email.</p>

<p>Thank you for umpiring!</p>

<p>Best regards,<br>
SDLL Umpire Coordination<br>
{{coordinator_email}}</p>
''',
        'body_text_template': '''Hi {{recipient_name}},

Now that you've started umpiring games for SDLL, here's how to request payment:

1. Keep track of the games you work (date, time, league)
2. At the end of each month, submit your game log to {{coordinator_email}}
3. Payment will be processed within 2 weeks

If you have any questions about rates or the payment process, just reply to this email.

Thank you for umpiring!

Best regards,
SDLL Umpire Coordination
{{coordinator_email}}
''',
        'trigger_type': 'milestone',
        'trigger_milestone': 'opening_day',
        'trigger_days_offset': 14,  # 2 weeks after opening day
        'recipient_type': 'active_umpire',
    },

    # Returning Umpire Outreach
    {
        'name': 'Returning Umpire Outreach',
        'code': 'returning_outreach',
        'description': 'Reach out to previous season umpires about returning.',
        'category': 'returning',
        'subject_template': 'Umpire for SDLL Again This {{season_name}}?',
        'body_html_template': '''
<p>Hi {{recipient_name}},</p>

<p>Hope you've been doing well! As we prepare for the {{season_name}} season at South Durham Little League, we wanted to reach out to see if you'd be interested in umpiring again.</p>

<p><strong>Key Dates:</strong></p>
<ul>
    <li>Training: {{training_date}}</li>
    <li>First Games: {{opening_day_date}}</li>
</ul>

<p>If you're interested, just reply to this email and we'll get you set up for the new season. If your schedule has changed or you're unable to commit this season, we understand - just let us know.</p>

<p>Thanks for all your help in previous seasons!</p>

<p>Best regards,<br>
SDLL Umpire Coordination<br>
{{coordinator_email}}</p>
''',
        'body_text_template': '''Hi {{recipient_name}},

Hope you've been doing well! As we prepare for the {{season_name}} season at South Durham Little League, we wanted to reach out to see if you'd be interested in umpiring again.

Key Dates:
- Training: {{training_date}}
- First Games: {{opening_day_date}}

If you're interested, just reply to this email and we'll get you set up for the new season. If your schedule has changed or you're unable to commit this season, we understand - just let us know.

Thanks for all your help in previous seasons!

Best regards,
SDLL Umpire Coordination
{{coordinator_email}}
''',
        'trigger_type': 'milestone',
        'trigger_milestone': 'first_practice',
        'trigger_days_offset': -42,  # 6 weeks before
        'recipient_type': 'lead',
        'recipient_status_filter': 'prospective',  # Leads marked as returning
    },

    # League Admin Marketing
    {
        'name': 'Umpire Academy Marketing',
        'code': 'admin_umpire_marketing',
        'description': 'Request league admins to include umpire recruitment in their communications.',
        'category': 'admin_marketing',
        'subject_template': 'Help Us Recruit Umpires for {{season_name}}',
        'body_html_template': '''
<p>Hi {{recipient_name}},</p>

<p>As we prepare for {{season_name}}, we need your help recruiting umpires for our Umpire Academy!</p>

<p>Could you please include the following in your next league email to parents?</p>

<hr>

<p><strong>Become an SDLL Umpire!</strong></p>

<p>South Durham Little League is looking for umpires for the upcoming season. This is a great opportunity for:</p>
<ul>
    <li>Youth ages 13+ looking to earn money</li>
    <li>Adults who want to stay involved in the game</li>
    <li>Anyone who wants to give back to the community</li>
</ul>

<p>Free training provided! Sign up at: [link to interest form]</p>

<hr>

<p>Thanks for helping spread the word!</p>

<p>Best regards,<br>
SDLL Umpire Coordination<br>
{{coordinator_email}}</p>
''',
        'body_text_template': '''Hi {{recipient_name}},

As we prepare for {{season_name}}, we need your help recruiting umpires for our Umpire Academy!

Could you please include the following in your next league email to parents?

---

BECOME AN SDLL UMPIRE!

South Durham Little League is looking for umpires for the upcoming season. This is a great opportunity for:
- Youth ages 13+ looking to earn money
- Adults who want to stay involved in the game
- Anyone who wants to give back to the community

Free training provided! Sign up at: [link to interest form]

---

Thanks for helping spread the word!

Best regards,
SDLL Umpire Coordination
{{coordinator_email}}
''',
        'trigger_type': 'milestone',
        'trigger_milestone': 'first_practice',
        'trigger_days_offset': -42,  # 6 weeks before
        'recipient_type': 'league_admin',
    },
]


def seed_templates():
    """Create or update all campaign templates."""
    app = create_app()

    with app.app_context():
        created = 0
        updated = 0

        for data in TEMPLATES:
            # Check if exists
            existing = EmailCampaignTemplate.get_by_code(data['code'])

            if existing:
                # Update existing
                for key, value in data.items():
                    setattr(existing, key, value)
                updated += 1
                print(f"Updated: {data['name']}")
            else:
                # Create new
                template = EmailCampaignTemplate(**data)
                db.session.add(template)
                created += 1
                print(f"Created: {data['name']}")

        db.session.commit()
        print(f"\nDone! Created {created}, updated {updated} templates.")


if __name__ == '__main__':
    seed_templates()
