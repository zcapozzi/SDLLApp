-- Migration: Remove deprecated location column from sdll_games
-- Date: 2026-08-26
-- Purpose: Games now use field_id (FK to sdll_fields) instead of location string
--
-- Prerequisites:
--   - All games with locations should already have field_id set
--   - Run verification queries below before executing DROP COLUMN
--
-- IMPORTANT: Follow MySQL compatibility guidelines from CLAUDE.md
-- Do NOT use IF EXISTS syntax - it's MariaDB only

-- ============================================================================
-- STEP 1: VERIFICATION (Run these before migration)
-- ============================================================================

-- Check for any games that have location but no field_id
-- If count > 0, run Step 2 first
-- SELECT COUNT(*) AS games_needing_migration
-- FROM sdll_games
-- WHERE field_id IS NULL AND location IS NOT NULL;

-- ============================================================================
-- STEP 2: DATA MIGRATION (Only if Step 1 shows games needing migration)
-- ============================================================================

-- Migrate any games with location string but no field_id
-- This matches games to fields by name
UPDATE sdll_games g
JOIN sdll_fields f ON g.location = f.location_title
SET g.field_id = f.ID
WHERE g.field_id IS NULL
  AND g.location IS NOT NULL;

-- ============================================================================
-- STEP 3: REMOVE COLUMN
-- ============================================================================

-- Remove the deprecated location column
-- NOTE: This will fail if column doesn't exist, which is expected behavior
ALTER TABLE sdll_games DROP COLUMN location;

-- ============================================================================
-- ROLLBACK SCRIPT (Keep for emergency use)
-- ============================================================================
--
-- If issues arise, recreate the column and repopulate:
--
-- ALTER TABLE sdll_games ADD COLUMN location VARCHAR(100) AFTER field_id;
--
-- UPDATE sdll_games g
-- JOIN sdll_fields f ON g.field_id = f.ID
-- SET g.location = f.location_title;
