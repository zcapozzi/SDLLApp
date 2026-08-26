-- Migration: Add umpire_was_unassigned field to sdll_games
-- This field tracks games that were assigned to a partner in error
-- When set to 1:
--   - Game still shows on partner's schedule (with "NO UMPIRE" indicator)
--   - Game is excluded from delegation report counts
--   - Notification is triggered to inform partner

ALTER TABLE sdll_games
ADD COLUMN umpire_was_unassigned TINYINT DEFAULT 0
AFTER umpire_count_override;
