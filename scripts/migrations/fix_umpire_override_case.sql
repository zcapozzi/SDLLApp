-- Migration: Fix umpire_override case sensitivity
-- All umpire_override values should be uppercase for consistent matching
-- Run this to fix existing data after code changes are deployed

-- View current state
SELECT umpire_override, COUNT(*) as count
FROM sdll_games
WHERE umpire_override IS NOT NULL
GROUP BY umpire_override;

-- Fix: Convert all umpire_override values to uppercase
UPDATE sdll_games
SET umpire_override = UPPER(umpire_override)
WHERE umpire_override IS NOT NULL;

-- Verify fix
SELECT umpire_override, COUNT(*) as count
FROM sdll_games
WHERE umpire_override IS NOT NULL
GROUP BY umpire_override;
