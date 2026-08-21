-- Migration: Add umpire eligibility fields and field addresses
-- Run this on production database to enable new features
-- Note: If a column already exists, that statement will error but you can continue

-- =============================================================================
-- 1. Umpire Profile Eligibility Fields
-- =============================================================================

-- max_baseball_age_rank: NULL = not eligible for baseball, value = max age_rank they can work
-- max_softball_age_rank: NULL = not eligible for softball, value = max age_rank they can work
-- excluded_leagues: comma-separated list of league IDs they won't see as available

ALTER TABLE sdll_umpire_profiles ADD COLUMN max_baseball_age_rank SMALLINT DEFAULT NULL;
ALTER TABLE sdll_umpire_profiles ADD COLUMN max_softball_age_rank SMALLINT DEFAULT NULL;
ALTER TABLE sdll_umpire_profiles ADD COLUMN excluded_leagues VARCHAR(200) DEFAULT NULL;

-- =============================================================================
-- 2. Field Address Fields (for Google Maps directions)
-- =============================================================================

ALTER TABLE sdll_fields ADD COLUMN address VARCHAR(200) DEFAULT NULL;
ALTER TABLE sdll_fields ADD COLUMN city VARCHAR(100) DEFAULT NULL;
ALTER TABLE sdll_fields ADD COLUMN state VARCHAR(50) DEFAULT NULL;
ALTER TABLE sdll_fields ADD COLUMN zip_code VARCHAR(20) DEFAULT NULL;

-- Set default city/state for existing fields
UPDATE sdll_fields SET city = 'Durham', state = 'NC' WHERE city IS NULL;

-- =============================================================================
-- 3. League Sport and Age Rank Fields (if not already added)
-- =============================================================================

ALTER TABLE sdll_leagues ADD COLUMN sport VARCHAR(20) DEFAULT 'baseball';
ALTER TABLE sdll_leagues ADD COLUMN age_rank SMALLINT DEFAULT NULL;

-- =============================================================================
-- Notes for Production
-- =============================================================================
-- After running this migration:
-- 1. Go to /fields/addresses to add addresses for each field
-- 2. Go to /umpires/<id>/edit to set eligibility for each umpire
-- 3. Set sport='softball' for softball leagues: UPDATE sdll_leagues SET sport='softball' WHERE display_name LIKE 'SB%';
-- 4. Set age_rank values (1=youngest, 2, 3... oldest) for proper eligibility filtering
