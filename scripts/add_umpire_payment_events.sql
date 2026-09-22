-- Migration: Add Umpire Payment Events Table
-- Purpose: Track standalone payment events decoupled from game lifecycle
-- Use cases: Rainout arrivals, bonuses, adjustments, etc.

CREATE TABLE IF NOT EXISTS sdll_umpire_payment_events (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- Event type: rainout_arrival, cancelled_arrival, completed, bonus, adjustment
    event_type VARCHAR(30) NOT NULL,

    -- Original game snapshot (NOT a FK - game may be rescheduled/deleted)
    original_game_id BIGINT,
    original_assignr_id VARCHAR(15),
    original_date DATE NOT NULL,
    original_time TIME,
    original_field_id BIGINT,
    original_field_name VARCHAR(100),
    original_league VARCHAR(30),
    original_home_team VARCHAR(100),
    original_away_team VARCHAR(100),

    -- Who gets paid (mutually exclusive)
    umpire_profile_id INT,
    partner_id INT,

    -- Assignment details
    umpire_count SMALLINT DEFAULT 1,
    position VARCHAR(20),

    -- Payment calculation
    rate_applied DECIMAL(8,2),
    booking_fee_applied DECIMAL(8,2) DEFAULT 0,
    amount DECIMAL(8,2) NOT NULL,
    umpire_showed_up BOOLEAN DEFAULT TRUE,

    -- Status workflow: pending -> approved -> paid (or voided)
    status VARCHAR(20) DEFAULT 'pending',
    reason VARCHAR(255),
    notes TEXT,

    -- Season context
    org_season_id BIGINT,

    -- Audit trail
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by_user_id BIGINT,
    approved_at DATETIME,
    approved_by_user_id BIGINT,
    paid_at DATETIME,
    paid_by_user_id BIGINT,
    voided_at DATETIME,
    voided_by_user_id BIGINT,

    -- Foreign keys
    FOREIGN KEY (umpire_profile_id) REFERENCES sdll_umpire_profiles(id) ON DELETE SET NULL,
    FOREIGN KEY (partner_id) REFERENCES sdll_umpire_partners(id) ON DELETE SET NULL,
    FOREIGN KEY (org_season_id) REFERENCES sdll_org_seasons(ID) ON DELETE SET NULL,
    FOREIGN KEY (created_by_user_id) REFERENCES sdll_users(ID) ON DELETE SET NULL,
    FOREIGN KEY (approved_by_user_id) REFERENCES sdll_users(ID) ON DELETE SET NULL,
    FOREIGN KEY (paid_by_user_id) REFERENCES sdll_users(ID) ON DELETE SET NULL,
    FOREIGN KEY (voided_by_user_id) REFERENCES sdll_users(ID) ON DELETE SET NULL
);

-- Add indexes for common queries
CREATE INDEX idx_pe_date ON sdll_umpire_payment_events(original_date);
CREATE INDEX idx_pe_game ON sdll_umpire_payment_events(original_game_id);
CREATE INDEX idx_pe_umpire ON sdll_umpire_payment_events(umpire_profile_id);
CREATE INDEX idx_pe_partner ON sdll_umpire_payment_events(partner_id);
CREATE INDEX idx_pe_status ON sdll_umpire_payment_events(status);
CREATE INDEX idx_pe_season ON sdll_umpire_payment_events(org_season_id);
CREATE INDEX idx_pe_event_type ON sdll_umpire_payment_events(event_type);
