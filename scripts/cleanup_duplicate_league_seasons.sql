-- Script to clean up duplicate LeagueSeason entries
-- These duplicates can occur when teams have both spring and fall names

-- First, identify duplicates (same year, is_spring, league_id but different IDs)
SELECT
    ls1.ID as keep_id,
    ls2.ID as delete_id,
    ls1.year,
    ls1.is_spring,
    ls1.league_id,
    l.display_name,
    l.fall_display_name
FROM sdll_league_seasons ls1
JOIN sdll_league_seasons ls2 ON
    ls1.year = ls2.year
    AND ls1.is_spring = ls2.is_spring
    AND ls1.league_id = ls2.league_id
    AND ls1.ID < ls2.ID  -- Keep the one with lower ID
JOIN sdll_leagues l ON l.ID = ls1.league_id;

-- Delete the duplicates (keeping the one with the lower ID)
-- UNCOMMENT TO EXECUTE:
-- DELETE ls2 FROM sdll_league_seasons ls2
-- INNER JOIN sdll_league_seasons ls1 ON
--     ls1.year = ls2.year
--     AND ls1.is_spring = ls2.is_spring
--     AND ls1.league_id = ls2.league_id
--     AND ls1.ID < ls2.ID;

-- Simpler approach: Delete all except the first entry per (year, is_spring, league_id)
DELETE FROM sdll_league_seasons
WHERE ID NOT IN (
    SELECT MIN(ID) FROM (
        SELECT MIN(ID) as ID
        FROM sdll_league_seasons
        GROUP BY year, is_spring, league_id
    ) AS keep_ids
);
