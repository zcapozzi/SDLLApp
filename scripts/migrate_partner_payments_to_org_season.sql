-- Migration: Add org_season_id to existing partner payment tables
-- Date: 2026-09-22
-- Purpose: Migrate from year/is_spring columns to org_season_id foreign key

-- Add org_season_id column to partner_payment_records if it doesn't exist
ALTER TABLE sdll_partner_payment_records
ADD COLUMN org_season_id INT COMMENT 'Links to sdll_org_seasons.ID';

-- Populate org_season_id from existing year/is_spring data
UPDATE sdll_partner_payment_records ppr
JOIN sdll_org_seasons os ON os.year = ppr.year AND os.is_spring = ppr.is_spring
SET ppr.org_season_id = os.ID
WHERE ppr.org_season_id IS NULL AND ppr.year IS NOT NULL;

-- Add foreign key constraint
ALTER TABLE sdll_partner_payment_records
ADD CONSTRAINT fk_ppr_org_season FOREIGN KEY (org_season_id) REFERENCES sdll_org_seasons(ID);

-- Add index
ALTER TABLE sdll_partner_payment_records
ADD INDEX idx_ppr_org_season (org_season_id);

-- Add org_season_id column to partner_credits if it doesn't exist
ALTER TABLE sdll_partner_credits
ADD COLUMN org_season_id INT COMMENT 'Links to sdll_org_seasons.ID';

-- Populate org_season_id from existing season_year/season_is_spring data
UPDATE sdll_partner_credits pc
JOIN sdll_org_seasons os ON os.year = pc.season_year AND os.is_spring = pc.season_is_spring
SET pc.org_season_id = os.ID
WHERE pc.org_season_id IS NULL AND pc.season_year IS NOT NULL;

-- Add foreign key constraint
ALTER TABLE sdll_partner_credits
ADD CONSTRAINT fk_pc_org_season FOREIGN KEY (org_season_id) REFERENCES sdll_org_seasons(ID);

-- Add index
ALTER TABLE sdll_partner_credits
ADD INDEX idx_pc_org_season (org_season_id);

-- Note: Old columns (year, is_spring, season_year, season_is_spring) can be dropped later
-- after confirming migration is complete
