-- Add Assignr group membership columns to sdll_umpire_profiles
-- These columns track which Assignr groups each umpire belongs to
-- Run with: mysql -u user -p database < scripts/add_assignr_group_columns.sql

-- Add assignr_active column (for "Active Umpires" group)
ALTER TABLE sdll_umpire_profiles
ADD COLUMN assignr_active TINYINT(1) DEFAULT 0;

-- Add assignr_plate_trained column (for "Behind-the-plate Trained" group)
ALTER TABLE sdll_umpire_profiles
ADD COLUMN assignr_plate_trained TINYINT(1) DEFAULT 0;

-- Show result
SELECT 'Added assignr_active and assignr_plate_trained columns to sdll_umpire_profiles' AS status;
