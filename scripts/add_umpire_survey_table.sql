-- Migration: Add umpire survey tables
-- Purpose: Store end-of-season feedback from Academy umpires and track email sends

-- Survey responses table
CREATE TABLE IF NOT EXISTS sdll_umpire_survey_responses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    umpire_profile_id INT NOT NULL,
    user_id BIGINT,
    org_season_id BIGINT NOT NULL,
    wanted_more_games TINYINT(1),
    returning_next_season TINYINT(1),
    feedback TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_survey_umpire_profile
        FOREIGN KEY (umpire_profile_id) REFERENCES sdll_umpire_profiles(id),
    CONSTRAINT fk_survey_user
        FOREIGN KEY (user_id) REFERENCES sdll_users(ID),
    CONSTRAINT fk_survey_org_season
        FOREIGN KEY (org_season_id) REFERENCES sdll_org_seasons(ID),

    -- Each umpire can only submit one survey per season
    UNIQUE KEY unique_umpire_season (umpire_profile_id, org_season_id)
);

-- Index for looking up survey responses by season
CREATE INDEX idx_survey_org_season ON sdll_umpire_survey_responses(org_season_id);

-- Survey email sends tracking table
CREATE TABLE IF NOT EXISTS sdll_umpire_survey_sends (
    id INT AUTO_INCREMENT PRIMARY KEY,
    umpire_profile_id INT NOT NULL,
    org_season_id BIGINT NOT NULL,
    sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_by_user_id BIGINT,

    CONSTRAINT fk_survey_send_umpire_profile
        FOREIGN KEY (umpire_profile_id) REFERENCES sdll_umpire_profiles(id),
    CONSTRAINT fk_survey_send_org_season
        FOREIGN KEY (org_season_id) REFERENCES sdll_org_seasons(ID),
    CONSTRAINT fk_survey_send_user
        FOREIGN KEY (sent_by_user_id) REFERENCES sdll_users(ID),

    INDEX idx_survey_send_season (org_season_id),
    INDEX idx_survey_send_umpire (umpire_profile_id)
);
