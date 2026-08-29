-- Migration: Add first_name and last_name columns to umpire profiles
-- Replace single _name column with separate _first_name and _last_name

-- Add the new columns
ALTER TABLE sdll_umpire_profiles
ADD COLUMN _first_name VARCHAR(500) DEFAULT NULL AFTER user_id;

ALTER TABLE sdll_umpire_profiles
ADD COLUMN _last_name VARCHAR(500) DEFAULT NULL AFTER _first_name;

-- Drop the old _name column (if it exists and has no data worth preserving)
-- Note: If there's existing data in _name, you may want to migrate it first
ALTER TABLE sdll_umpire_profiles
DROP COLUMN _name;
