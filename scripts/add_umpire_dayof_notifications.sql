-- Create table for day-of umpire pregame notifications
-- These are sent to Academy umpires on the day of their games

CREATE TABLE IF NOT EXISTS sdll_umpire_dayof_notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Game identification
    game_id BIGINT,
    assignr_game_id INT NOT NULL,

    -- Umpire identification (from Assignr)
    assignr_official_id INT NOT NULL,
    umpire_name VARCHAR(200) NOT NULL,

    -- Season tracking
    year INT NOT NULL,
    is_spring SMALLINT NOT NULL,

    -- Recipients (JSON array of email addresses)
    recipient_emails TEXT NOT NULL,

    -- Content
    subject VARCHAR(255) NOT NULL,
    body_html TEXT NOT NULL,

    -- Game details for display
    game_date DATETIME NOT NULL,
    game_location VARCHAR(100),
    game_league VARCHAR(50),
    home_team VARCHAR(100),
    away_team VARCHAR(100),

    -- Workflow
    status ENUM('draft', 'sent', 'skipped') NOT NULL DEFAULT 'draft',
    sent_at DATETIME,
    sent_by BIGINT,

    -- Foreign keys
    FOREIGN KEY (game_id) REFERENCES sdll_games(ID) ON DELETE SET NULL,
    FOREIGN KEY (sent_by) REFERENCES sdll_users(ID) ON DELETE SET NULL,

    -- One notification per game per umpire
    UNIQUE KEY uq_dayof_notification_game_official (assignr_game_id, assignr_official_id),

    -- Indexes
    INDEX idx_dayof_status (status),
    INDEX idx_dayof_game_date (game_date),
    INDEX idx_dayof_assignr_official (assignr_official_id)
);
