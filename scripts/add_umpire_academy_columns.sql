-- Migration: Add umpire academy registration columns
-- Run with: mysql --force database < scripts/add_umpire_academy_columns.sql
-- Note: Using plain ALTER TABLE (MySQL compatible), not IF NOT EXISTS (MariaDB only)

-- Registration token for completing multi-phase registration
ALTER TABLE sdll_umpire_profiles ADD COLUMN registration_token VARCHAR(64) DEFAULT NULL;
ALTER TABLE sdll_umpire_profiles ADD COLUMN registration_token_expires DATETIME DEFAULT NULL;

-- Profile completion fields
ALTER TABLE sdll_umpire_profiles ADD COLUMN shirt_size VARCHAR(10) DEFAULT NULL;
ALTER TABLE sdll_umpire_profiles ADD COLUMN seasons_played SMALLINT DEFAULT NULL;
ALTER TABLE sdll_umpire_profiles ADD COLUMN highest_level_played VARCHAR(50) DEFAULT NULL;
ALTER TABLE sdll_umpire_profiles ADD COLUMN interested_sports VARCHAR(20) DEFAULT NULL;
ALTER TABLE sdll_umpire_profiles ADD COLUMN kid_pitch_interest SMALLINT DEFAULT NULL;
ALTER TABLE sdll_umpire_profiles ADD COLUMN availability_notes TEXT DEFAULT NULL;
ALTER TABLE sdll_umpire_profiles ADD COLUMN registration_completed_at DATETIME DEFAULT NULL;

-- Index for token lookup
CREATE INDEX idx_umpire_registration_token ON sdll_umpire_profiles(registration_token);
