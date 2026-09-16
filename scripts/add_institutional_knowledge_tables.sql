-- Migration: Add institutional knowledge and email routing tables
-- Run with: mysql -u root -p sdll < scripts/add_institutional_knowledge_tables.sql

-- =====================================================
-- EMAIL ROUTING CONFIGURATION
-- =====================================================
CREATE TABLE IF NOT EXISTS sdll_email_routing_configs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    org_id BIGINT NOT NULL,

    -- Which email type this applies to
    email_type VARCHAR(50) NOT NULL,

    -- Routing configuration
    from_name VARCHAR(100),
    from_email VARCHAR(255),
    reply_to_email VARCHAR(255),
    cc_emails TEXT,
    bcc_emails TEXT,

    -- Optional role-based routing
    reply_to_role VARCHAR(50),
    cc_roles VARCHAR(255),

    active TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    -- Unique constraint: one config per org per email type
    UNIQUE KEY uq_email_routing_org_type (org_id, email_type),

    FOREIGN KEY (org_id) REFERENCES sdll_organizations(ID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- ARTIFACTS / KNOWLEDGE BASE
-- =====================================================
CREATE TABLE IF NOT EXISTS sdll_artifacts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    org_id BIGINT NOT NULL,

    -- Classification
    artifact_type VARCHAR(30) NOT NULL,
    category VARCHAR(50),

    -- Content
    title VARCHAR(200) NOT NULL,
    description TEXT,
    content LONGTEXT,
    external_url VARCHAR(500),
    file_path VARCHAR(500),

    -- Access control
    visibility VARCHAR(20) DEFAULT 'role',
    allowed_roles VARCHAR(255),

    -- Metadata
    tags VARCHAR(255),
    sort_order INT DEFAULT 0,

    -- Audit
    created_by_user_id BIGINT,
    updated_by_user_id BIGINT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (org_id) REFERENCES sdll_organizations(ID) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id) REFERENCES sdll_users(ID) ON DELETE SET NULL,
    FOREIGN KEY (updated_by_user_id) REFERENCES sdll_users(ID) ON DELETE SET NULL,

    INDEX idx_artifact_type (artifact_type),
    INDEX idx_artifact_category (category),
    INDEX idx_artifact_visibility (visibility)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- ROLE TASK TEMPLATES
-- =====================================================
CREATE TABLE IF NOT EXISTS sdll_role_task_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    org_id BIGINT NOT NULL,

    -- What role this applies to
    role VARCHAR(50) NOT NULL,

    -- Task details
    title VARCHAR(200) NOT NULL,
    description TEXT,

    -- Timing - relative to milestone
    trigger_milestone VARCHAR(50) NOT NULL,
    days_offset INT DEFAULT 0,

    -- Linked artifact (optional)
    artifact_id INT,

    -- Reminder settings
    reminder_days_before VARCHAR(50),

    -- Metadata
    sort_order INT DEFAULT 0,
    active TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (org_id) REFERENCES sdll_organizations(ID) ON DELETE CASCADE,
    FOREIGN KEY (artifact_id) REFERENCES sdll_artifacts(id) ON DELETE SET NULL,

    INDEX idx_task_template_role (role),
    INDEX idx_task_template_milestone (trigger_milestone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- ROLE TASK INSTANCES
-- =====================================================
CREATE TABLE IF NOT EXISTS sdll_role_task_instances (
    id INT AUTO_INCREMENT PRIMARY KEY,
    template_id INT NOT NULL,

    -- Season context
    year INT NOT NULL,
    is_spring TINYINT(1) NOT NULL,

    -- Computed due date
    due_date DATE,

    -- Status tracking
    status VARCHAR(20) DEFAULT 'pending',
    completed_at DATETIME,
    completed_by_user_id BIGINT,

    -- Notes
    notes TEXT,

    -- Reminder tracking
    last_reminder_sent DATETIME,
    reminder_count INT DEFAULT 0,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (template_id) REFERENCES sdll_role_task_templates(id) ON DELETE CASCADE,
    FOREIGN KEY (completed_by_user_id) REFERENCES sdll_users(ID) ON DELETE SET NULL,

    -- Unique: one instance per template per season
    UNIQUE KEY uq_role_task_season (template_id, year, is_spring),

    INDEX idx_task_instance_status (status),
    INDEX idx_task_instance_due_date (due_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- DEFAULT EMAIL ROUTING CONFIGURATIONS
-- =====================================================
INSERT INTO sdll_email_routing_configs (org_id, email_type, reply_to_role, active) VALUES
(1, 'weekly_digest', 'scheduler', 1),
(1, 'umpire_assignment', 'umpire_coordinator', 1),
(1, 'umpire_campaign', 'umpire_coordinator', 1),
(1, 'coach_welcome', 'coaching_coordinator', 1),
(1, 'rainout_notification', 'scheduler', 1),
(1, 'access_request', 'admin', 1),
(1, 'postgame_reminder', NULL, 1)
ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;

-- =====================================================
-- SEED DEFAULT ROLE TASK TEMPLATES
-- =====================================================

-- Umpire Coordinator Tasks
INSERT INTO sdll_role_task_templates (org_id, role, title, description, trigger_milestone, days_offset, reminder_days_before, sort_order) VALUES
(1, 'umpire_coordinator', 'Confirm rates with partner umpire orgs',
    'Contact partner umpire organizations to confirm per-game rates for the upcoming season. Update delegation rules if rates have changed.',
    'registration_opens', 0, '7,3', 1),
(1, 'umpire_coordinator', 'Send Academy Training email to registrants',
    'Send the umpire academy training invitation to all registered umpires. Include training dates, location, and what to bring.',
    'registration_opens', 0, '7,3', 2),
(1, 'umpire_coordinator', 'Send Academy Training email to non-registrant recent umpires',
    'Reach out to umpires who worked last season but haven''t registered yet. Encourage them to sign up for training.',
    'registration_opens', 7, '7,3', 3),
(1, 'umpire_coordinator', 'Send Academy Quiz to Prospective Umpires',
    'Send the online quiz to all prospective umpires who need to complete certification before working games.',
    'training', 0, '7,3,1', 4),
(1, 'umpire_coordinator', 'Verify partner organization contacts',
    'Confirm contact information for all partner umpire organizations. Update partner contacts in the system.',
    'first_practice', -14, '7,3', 5),
(1, 'umpire_coordinator', 'Review and assign opening day umpires',
    'Ensure all opening day games have umpire assignments. Prioritize experienced umpires for high-visibility games.',
    'opening_day', -7, '7,3,1', 6);

-- Scheduler Tasks
INSERT INTO sdll_role_task_templates (org_id, role, title, description, trigger_milestone, days_offset, reminder_days_before, sort_order) VALUES
(1, 'scheduler', 'Confirm field allocations with facilities',
    'Verify all field allocations are correct for the season. Confirm any shared-use agreements with parks & rec.',
    'registration_opens', 7, '7,3', 1),
(1, 'scheduler', 'Generate draft schedule',
    'Create initial schedule draft after teams are finalized. Include all regular season games.',
    'draft', 3, '7,3', 2),
(1, 'scheduler', 'Review schedule conflicts',
    'Check for any scheduling conflicts, blackout violations, or field double-bookings. Resolve before publishing.',
    'first_practice', -10, '7,3', 3),
(1, 'scheduler', 'Publish initial schedule',
    'Make the schedule visible to coaches and parents. Send notification about schedule availability.',
    'first_practice', -7, '7,3,1', 4),
(1, 'scheduler', 'Set up playoff brackets',
    'Create playoff bracket structure for all leagues. Confirm playoff dates with facilities.',
    'season_end', -21, '7,3', 5);

-- Coaching Coordinator Tasks
INSERT INTO sdll_role_task_templates (org_id, role, title, description, trigger_milestone, days_offset, reminder_days_before, sort_order) VALUES
(1, 'coaching_coordinator', 'Send coach welcome emails',
    'Welcome new coaches and provide onboarding information. Include links to training resources and key contacts.',
    'registration_opens', 14, '7,3', 1),
(1, 'coaching_coordinator', 'Schedule coach training sessions',
    'Coordinate with trainers to schedule coach clinics. Ensure all leagues are covered.',
    'first_practice', -21, '7,3', 2),
(1, 'coaching_coordinator', 'Verify background checks completed',
    'Ensure all coaches have completed required background checks before practices begin.',
    'first_practice', -7, '3,1', 3),
(1, 'coaching_coordinator', 'Distribute equipment to teams',
    'Coordinate equipment distribution. Ensure all teams have balls, bases, and safety equipment.',
    'first_practice', -3, '3,1', 4);

-- Admin Tasks
INSERT INTO sdll_role_task_templates (org_id, role, title, description, trigger_milestone, days_offset, reminder_days_before, sort_order) VALUES
(1, 'admin', 'Update website for new season',
    'Update league website with new season information. Clear old announcements and update dates.',
    'registration_opens', -7, '7,3', 1),
(1, 'admin', 'Review and update board member roles',
    'Verify all board members have correct system access. Update roles for new board members.',
    'registration_opens', 0, '7,3', 2),
(1, 'admin', 'Archive previous season data',
    'Create backups of previous season data. Archive old schedules and reports.',
    'registration_opens', 14, '7,3', 3);
