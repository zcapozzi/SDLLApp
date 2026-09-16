-- Seed email template for post-game report reminders
-- Date: 2026-09-15

-- Insert the postgame_reminder email campaign template
INSERT INTO sdll_email_campaign_templates (
    code,
    name,
    description,
    category,
    subject_template,
    body_text_template,
    body_html_template,
    trigger_type,
    recipient_type,
    active,
    created_at
) VALUES (
    'postgame_reminder',
    'Post-Game Report Reminder',
    'Sent to coaches 105 minutes after game start time to collect post-game data (score, umpire evaluation)',
    'system',
    'Post-Game Report: {{home_team}} vs {{away_team}} - {{game_date}}',
    'Hi {{coach_name}},

Please submit the post-game report for today''s game:

{{team_name}} vs {{opponent_name}}
Date: {{game_date}}
Time: {{game_time}}
Field: {{field_name}}

Click here to submit your report:
{{submit_url}}

If the game was not played (rainout, cancelled, etc.), please indicate that on the form.

Thanks,
SDLL',
    '<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h2 style="color: #228B22;">Post-Game Report</h2>

    <p>Hi {{coach_name}},</p>

    <p>Please submit the post-game report for today''s game:</p>

    <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
        <p><strong>{{team_name}}</strong> vs <strong>{{opponent_name}}</strong></p>
        <p>Date: {{game_date}}<br>
        Time: {{game_time}}<br>
        Field: {{field_name}}</p>
    </div>

    <p style="text-align: center;">
        <a href="{{submit_url}}" style="display: inline-block; background: #228B22; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
            Complete Post-Game Report
        </a>
    </p>

    <p style="color: #666; font-size: 14px;">
        If the game was not played (rainout, cancelled, etc.), please indicate that on the form.
    </p>

    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
    <p style="color: #888; font-size: 12px;">South Durham Little League</p>
</body>
</html>',
    'manual',
    'coach',
    1,
    CURRENT_TIMESTAMP
) ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    description = VALUES(description),
    subject_template = VALUES(subject_template),
    body_text_template = VALUES(body_text_template),
    body_html_template = VALUES(body_html_template);
