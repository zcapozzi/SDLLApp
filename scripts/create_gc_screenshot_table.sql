-- GameChanger Screenshot Sessions Table
-- Tracks screenshot parsing sessions for post-game reports
-- Each upload attempt is recorded for audit and QC purposes

CREATE TABLE sdll_gc_screenshot_sessions (
    id INT PRIMARY KEY AUTO_INCREMENT,

    -- Session grouping (multiple attempts share same uuid)
    session_uuid VARCHAR(36) NOT NULL,
    attempt_number SMALLINT NOT NULL DEFAULT 1,

    -- Context
    game_id BIGINT NOT NULL,
    team_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,

    -- Image storage (base64)
    image_data MEDIUMTEXT,
    image_filename VARCHAR(255),
    image_content_type VARCHAR(50),

    -- LLM interaction
    prompt_sent TEXT,
    llm_response TEXT,
    parsed_json JSON,

    -- Final outcome
    final_submitted_json JSON,
    was_edited SMALLINT DEFAULT 0,
    edit_diff JSON,  -- Field-level diff: what changed and how
    submission_successful SMALLINT DEFAULT 0,

    -- Status: pending, parsing, parsed, error, submitted, abandoned
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,

    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    parsed_at DATETIME,
    submitted_at DATETIME,

    -- Foreign keys
    CONSTRAINT fk_gc_session_game FOREIGN KEY (game_id) REFERENCES sdll_games(ID) ON DELETE CASCADE,
    CONSTRAINT fk_gc_session_team FOREIGN KEY (team_id) REFERENCES sdll_team_seasons(team_ID) ON DELETE CASCADE,
    CONSTRAINT fk_gc_session_user FOREIGN KEY (user_id) REFERENCES sdll_users(ID) ON DELETE CASCADE,

    -- Indexes
    INDEX idx_session_uuid (session_uuid),
    INDEX idx_game_team (game_id, team_id),
    INDEX idx_user (user_id),
    INDEX idx_created (created_at),
    INDEX idx_status (status)
);
