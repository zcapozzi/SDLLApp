-- Fix duplicate field records
-- This script helps identify and merge duplicate field names

-- ============================================
-- STEP 1: Find ALL duplicate field names
-- ============================================
SELECT
    location_title,
    COUNT(*) as count,
    GROUP_CONCAT(ID ORDER BY ID) as field_ids,
    GROUP_CONCAT(active ORDER BY ID) as active_status
FROM sdll_fields
GROUP BY location_title
HAVING COUNT(*) > 1;

-- ============================================
-- STEP 2: Check specific duplicate (e.g., Pearsontown)
-- ============================================
SELECT ID, location_title, active FROM sdll_fields WHERE location_title LIKE '%Pearson%';

-- Check how many games are assigned to each
SELECT
    f.ID as field_id,
    f.location_title,
    f.active,
    COUNT(g.ID) as game_count
FROM sdll_fields f
LEFT JOIN sdll_games g ON g.field_id = f.ID
WHERE f.location_title LIKE '%Pearson%'
GROUP BY f.ID, f.location_title, f.active;

-- ============================================
-- STEP 3: Merge duplicates (UNCOMMENT TO RUN)
-- Replace 29 and 30 with your actual field IDs
-- ============================================

-- Option A: Keep field ID 29, move games from 30 to 29
-- UPDATE sdll_games SET field_id = 29 WHERE field_id = 30;
-- UPDATE sdll_fields SET active = 0 WHERE ID = 30;

-- Option B: Keep field ID 30, move games from 29 to 30
-- UPDATE sdll_games SET field_id = 30 WHERE field_id = 29;
-- UPDATE sdll_fields SET active = 0 WHERE ID = 29;

-- ============================================
-- STEP 4: Verify the fix
-- ============================================
-- After running the merge, check that only one active field remains:
-- SELECT ID, location_title, active FROM sdll_fields WHERE location_title LIKE '%Pearson%';

-- And verify all games now point to the correct field:
-- SELECT COUNT(*) as game_count, field_id FROM sdll_games WHERE field_id IN (29, 30) GROUP BY field_id;
