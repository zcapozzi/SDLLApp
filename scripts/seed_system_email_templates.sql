-- Seed system email templates for access requests
-- These templates are editable by admins through the email campaigns UI

-- Email verification for parent requests
INSERT INTO sdll_email_campaign_templates (
    name, code, description, category,
    subject_template, body_html_template, body_text_template,
    trigger_type, recipient_type, active
) VALUES (
    'Email Verification',
    'verify_email',
    'Sent to parents to verify their email address before account creation',
    'system',
    'Verify your email for SDLL',
    '<!DOCTYPE html>
<html>
<head></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: #228B22;">Verify Your Email</h2>
    <p>Hi {{first_name}},</p>
    <p>Thank you for requesting access to South Durham Little League. Please verify your email address by clicking the button below:</p>
    <p>
        <a href="{{verify_url}}"
           style="display: inline-block; padding: 12px 24px; background-color: #228B22; color: white;
                  text-decoration: none; border-radius: 4px; font-weight: bold;">
            Verify Email
        </a>
    </p>
    <p style="color: #666; font-size: 14px;">
        Or copy this link: <a href="{{verify_url}}">{{verify_url}}</a>
    </p>
    <p style="color: #666; font-size: 14px;">This link expires in 24 hours.</p>
    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
    <p style="color: #888; font-size: 12px;">South Durham Little League</p>
</body>
</html>',
    'Hi {{first_name}},

Thank you for requesting access to South Durham Little League.

Please verify your email address by clicking the link below:
{{verify_url}}

This link expires in 24 hours.

- South Durham Little League',
    'manual',
    'access_requester',
    1
);

-- Welcome email for verified parents
INSERT INTO sdll_email_campaign_templates (
    name, code, description, category,
    subject_template, body_html_template, body_text_template,
    trigger_type, recipient_type, active
) VALUES (
    'Welcome - Parent',
    'welcome_parent',
    'Sent to parents after email verification - includes password setup link',
    'system',
    'Welcome to SDLL - Set Your Password',
    '<!DOCTYPE html>
<html>
<head></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: #228B22;">Welcome to South Durham Little League!</h2>
    <p>Hi {{first_name}},</p>
    <p>Your email has been verified and your account has been created. You can now set your password to access SDLL.</p>
    <p>
        <a href="{{reset_url}}"
           style="display: inline-block; padding: 12px 24px; background-color: #228B22; color: white;
                  text-decoration: none; border-radius: 4px; font-weight: bold;">
            Set Your Password
        </a>
    </p>
    <p style="color: #666; font-size: 14px;">
        Or copy this link: <a href="{{reset_url}}">{{reset_url}}</a>
    </p>
    <p style="color: #666; font-size: 14px;">This link expires in 1 hour.</p>
    <p>Once you set your password, you can log in to view your child''s team schedule and other league information.</p>
    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
    <p style="color: #888; font-size: 12px;">South Durham Little League</p>
</body>
</html>',
    'Hi {{first_name}},

Welcome to South Durham Little League!

Your email has been verified and your account has been created.

Set your password here: {{reset_url}}

This link expires in 1 hour.

Once you set your password, you can log in to view your child''s team schedule and other league information.

- South Durham Little League',
    'manual',
    'access_requester',
    1
);

-- Welcome email for approved coaches
INSERT INTO sdll_email_campaign_templates (
    name, code, description, category,
    subject_template, body_html_template, body_text_template,
    trigger_type, recipient_type, active
) VALUES (
    'Welcome - Coach',
    'welcome_coach',
    'Sent to coaches after their access request is approved',
    'system',
    'Welcome to SDLL - Coach Access Approved',
    '<!DOCTYPE html>
<html>
<head></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: #228B22;">Welcome, Coach!</h2>
    <p>Hi {{first_name}},</p>
    <p>Your request for coach access has been approved. You have been assigned to team <strong>{{team_name}}</strong>.</p>
    <p>Please set your password to access your coach dashboard:</p>
    <p>
        <a href="{{reset_url}}"
           style="display: inline-block; padding: 12px 24px; background-color: #228B22; color: white;
                  text-decoration: none; border-radius: 4px; font-weight: bold;">
            Set Your Password
        </a>
    </p>
    <p style="color: #666; font-size: 14px;">
        Or copy this link: <a href="{{reset_url}}">{{reset_url}}</a>
    </p>
    <p style="color: #666; font-size: 14px;">This link expires in 1 hour.</p>
    <p>As a coach, you''ll have access to:</p>
    <ul>
        <li>Your team''s game and practice schedule</li>
        <li>Player roster and contact information</li>
        <li>League communications</li>
    </ul>
    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
    <p style="color: #888; font-size: 12px;">South Durham Little League</p>
</body>
</html>',
    'Hi {{first_name}},

Welcome, Coach!

Your request for coach access has been approved. You have been assigned to team {{team_name}}.

Set your password here: {{reset_url}}

This link expires in 1 hour.

As a coach, you''ll have access to:
- Your team''s game and practice schedule
- Player roster and contact information
- League communications

- South Durham Little League',
    'manual',
    'access_requester',
    1
);

-- Welcome email for approved league admins
INSERT INTO sdll_email_campaign_templates (
    name, code, description, category,
    subject_template, body_html_template, body_text_template,
    trigger_type, recipient_type, active
) VALUES (
    'Welcome - League Admin',
    'welcome_admin',
    'Sent to league admins after their access request is approved with assigned roles',
    'system',
    'Welcome to SDLL - Admin Access Approved',
    '<!DOCTYPE html>
<html>
<head></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: #228B22;">Welcome to the SDLL Admin Team!</h2>
    <p>Hi {{first_name}},</p>
    <p>Your request for admin access has been approved. You have been assigned the following roles:</p>
    <p><strong>{{roles}}</strong></p>
    <p>Please set your password to access the admin dashboard:</p>
    <p>
        <a href="{{reset_url}}"
           style="display: inline-block; padding: 12px 24px; background-color: #228B22; color: white;
                  text-decoration: none; border-radius: 4px; font-weight: bold;">
            Set Your Password
        </a>
    </p>
    <p style="color: #666; font-size: 14px;">
        Or copy this link: <a href="{{reset_url}}">{{reset_url}}</a>
    </p>
    <p style="color: #666; font-size: 14px;">This link expires in 1 hour.</p>
    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
    <p style="color: #888; font-size: 12px;">South Durham Little League</p>
</body>
</html>',
    'Hi {{first_name}},

Welcome to the SDLL Admin Team!

Your request for admin access has been approved. You have been assigned the following roles:
{{roles}}

Set your password here: {{reset_url}}

This link expires in 1 hour.

- South Durham Little League',
    'manual',
    'access_requester',
    1
);

-- Notification to admins about new access request pending review
INSERT INTO sdll_email_campaign_templates (
    name, code, description, category,
    subject_template, body_html_template, body_text_template,
    trigger_type, recipient_type, active
) VALUES (
    'Access Request Pending',
    'access_request_pending',
    'Sent to site admins when a new coach or admin request needs review',
    'system',
    'SDLL Access Request: {{request_type}} - {{requester_name}}',
    '<!DOCTYPE html>
<html>
<head></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: #228B22;">New Access Request</h2>
    <p>A new {{request_type}} access request has been submitted and requires your review.</p>
    <table style="border-collapse: collapse; margin: 20px 0;">
        <tr>
            <td style="padding: 8px; font-weight: bold;">Name:</td>
            <td style="padding: 8px;">{{requester_name}}</td>
        </tr>
        <tr>
            <td style="padding: 8px; font-weight: bold;">Request Type:</td>
            <td style="padding: 8px;">{{request_type}}</td>
        </tr>
        <tr>
            <td style="padding: 8px; font-weight: bold;">Team:</td>
            <td style="padding: 8px;">{{team_name}}</td>
        </tr>
        <tr>
            <td style="padding: 8px; font-weight: bold;">Requested Roles:</td>
            <td style="padding: 8px;">{{requested_roles}}</td>
        </tr>
    </table>
    <p>
        <a href="{{review_url}}"
           style="display: inline-block; padding: 12px 24px; background-color: #228B22; color: white;
                  text-decoration: none; border-radius: 4px; font-weight: bold;">
            Review Request
        </a>
    </p>
    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
    <p style="color: #888; font-size: 12px;">South Durham Little League - Admin Notification</p>
</body>
</html>',
    'New Access Request

A new {{request_type}} access request has been submitted and requires your review.

Name: {{requester_name}}
Request Type: {{request_type}}
Team: {{team_name}}
Requested Roles: {{requested_roles}}

Review the request here: {{review_url}}

- South Durham Little League',
    'manual',
    'site_admin',
    1
);

-- Rejection notification
INSERT INTO sdll_email_campaign_templates (
    name, code, description, category,
    subject_template, body_html_template, body_text_template,
    trigger_type, recipient_type, active
) VALUES (
    'Access Request Rejected',
    'access_request_rejected',
    'Sent to requesters when their access request is rejected',
    'system',
    'SDLL Access Request Update',
    '<!DOCTYPE html>
<html>
<head></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: #228B22;">Access Request Update</h2>
    <p>Hi {{first_name}},</p>
    <p>Thank you for your interest in South Durham Little League. Unfortunately, we are unable to approve your access request at this time.</p>
    {{#if reason}}
    <p><strong>Reason:</strong> {{reason}}</p>
    {{/if}}
    <p>If you believe this was in error or have questions, please contact us at <a href="mailto:info@sdll.org">info@sdll.org</a>.</p>
    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
    <p style="color: #888; font-size: 12px;">South Durham Little League</p>
</body>
</html>',
    'Hi {{first_name}},

Thank you for your interest in South Durham Little League. Unfortunately, we are unable to approve your access request at this time.

{{#if reason}}
Reason: {{reason}}
{{/if}}

If you believe this was in error or have questions, please contact us at info@sdll.org.

- South Durham Little League',
    'manual',
    'access_requester',
    1
);

-- Daily digest of new parent accounts (for admins)
INSERT INTO sdll_email_campaign_templates (
    name, code, description, category,
    subject_template, body_html_template, body_text_template,
    trigger_type, recipient_type, active
) VALUES (
    'Daily Parent Digest',
    'daily_parent_digest',
    'Daily summary of new parent accounts created (sent to site admins)',
    'system',
    'SDLL Daily Summary: {{count}} New Parent Accounts',
    '<!DOCTYPE html>
<html>
<head></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: #228B22;">Daily Account Summary</h2>
    <p>{{count}} new parent accounts were created in the past 24 hours:</p>
    <table style="border-collapse: collapse; width: 100%; margin: 20px 0;">
        <thead>
            <tr style="background-color: #f5f5f5;">
                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Name</th>
                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Email</th>
                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Time</th>
            </tr>
        </thead>
        <tbody>
            {{accounts_table}}
        </tbody>
    </table>
    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
    <p style="color: #888; font-size: 12px;">South Durham Little League - Admin Notification</p>
</body>
</html>',
    'SDLL Daily Summary: {{count}} New Parent Accounts

{{count}} new parent accounts were created in the past 24 hours:

{{accounts_list}}

- South Durham Little League',
    'manual',
    'site_admin',
    1
);
