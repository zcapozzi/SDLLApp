-- Migration: Add Partner League Rates Table
-- Purpose: Store league-specific rate overrides for umpire partners
-- Example: Diamond charges $85/umpire for Majors but $75 for AA

CREATE TABLE IF NOT EXISTS sdll_partner_league_rates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    partner_id INT NOT NULL,
    league_id BIGINT NOT NULL,

    -- Rates (NULL = use partner default)
    rate_normal DECIMAL(8,2),
    rate_ntl DECIMAL(8,2),

    -- Optional season scope (NULL = all seasons)
    org_season_id BIGINT,

    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign keys
    FOREIGN KEY (partner_id) REFERENCES sdll_umpire_partners(id) ON DELETE CASCADE,
    FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID) ON DELETE CASCADE,
    FOREIGN KEY (org_season_id) REFERENCES sdll_org_seasons(ID) ON DELETE SET NULL,

    -- Unique: one rate per partner/league/season combo
    UNIQUE KEY uq_partner_league_season (partner_id, league_id, org_season_id)
);

-- Add indexes for common lookups
CREATE INDEX idx_plr_partner ON sdll_partner_league_rates(partner_id);
CREATE INDEX idx_plr_league ON sdll_partner_league_rates(league_id);
