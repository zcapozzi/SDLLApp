-- Migration: Add league_id foreign key columns
-- Phase 1: Add nullable columns with indexes and FK constraints
-- Run this on production database first, then deploy code changes

-- ============================================
-- PHASE 1A: Add league_id columns (nullable)
-- ============================================

-- Games table (core)
ALTER TABLE sdll_games
    ADD COLUMN league_id BIGINT NULL;

-- Team seasons table (core)
ALTER TABLE sdll_team_seasons
    ADD COLUMN league_id BIGINT NULL;

-- League seasons table (core - configuration)
ALTER TABLE sdll_league_seasons
    ADD COLUMN league_id BIGINT NULL;

-- Field slots table
ALTER TABLE sdll_field_slots
    ADD COLUMN league_id BIGINT NULL;

-- Field allocations specific table
ALTER TABLE sdll_field_allocations_specific
    ADD COLUMN league_id BIGINT NULL;

-- Org events table
ALTER TABLE sdll_org_events
    ADD COLUMN league_id BIGINT NULL;

-- ============================================
-- PHASE 1B: Add indexes
-- ============================================

CREATE INDEX idx_games_league_id ON sdll_games(league_id);
CREATE INDEX idx_team_seasons_league_id ON sdll_team_seasons(league_id);
CREATE INDEX idx_league_seasons_league_id ON sdll_league_seasons(league_id);
CREATE INDEX idx_field_slots_league_id ON sdll_field_slots(league_id);
CREATE INDEX idx_field_alloc_specific_league_id ON sdll_field_allocations_specific(league_id);
CREATE INDEX idx_org_events_league_id ON sdll_org_events(league_id);

-- ============================================
-- PHASE 1C: Add foreign key constraints
-- ============================================

ALTER TABLE sdll_games
    ADD CONSTRAINT fk_games_league_id
    FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID);

ALTER TABLE sdll_team_seasons
    ADD CONSTRAINT fk_team_seasons_league_id
    FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID);

ALTER TABLE sdll_league_seasons
    ADD CONSTRAINT fk_league_seasons_league_id
    FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID);

ALTER TABLE sdll_field_slots
    ADD CONSTRAINT fk_field_slots_league_id
    FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID);

ALTER TABLE sdll_field_allocations_specific
    ADD CONSTRAINT fk_field_alloc_specific_league_id
    FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID);

ALTER TABLE sdll_org_events
    ADD CONSTRAINT fk_org_events_league_id
    FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID);

-- ============================================
-- PHASE 2: Populate league_id from existing strings
-- ============================================

-- Games table - match on display_name OR fall_display_name
UPDATE sdll_games g
LEFT JOIN sdll_leagues l ON (
    g.league = l.display_name OR g.league = l.fall_display_name
)
SET g.league_id = l.ID
WHERE g.league IS NOT NULL AND g.league_id IS NULL;

-- Team seasons
UPDATE sdll_team_seasons ts
LEFT JOIN sdll_leagues l ON (
    ts.league = l.display_name OR ts.league = l.fall_display_name
)
SET ts.league_id = l.ID
WHERE ts.league IS NOT NULL AND ts.league_id IS NULL;

-- League seasons
UPDATE sdll_league_seasons ls
LEFT JOIN sdll_leagues l ON (
    ls.league = l.display_name OR ls.league = l.fall_display_name
)
SET ls.league_id = l.ID
WHERE ls.league IS NOT NULL AND ls.league_id IS NULL;

-- Field slots
UPDATE sdll_field_slots fs
LEFT JOIN sdll_leagues l ON (
    fs.league = l.display_name OR fs.league = l.fall_display_name
)
SET fs.league_id = l.ID
WHERE fs.league IS NOT NULL AND fs.league_id IS NULL;

-- Field allocations specific
UPDATE sdll_field_allocations_specific fas
LEFT JOIN sdll_leagues l ON (
    fas.league = l.display_name OR fas.league = l.fall_display_name
)
SET fas.league_id = l.ID
WHERE fas.league IS NOT NULL AND fas.league_id IS NULL;

-- Org events
UPDATE sdll_org_events oe
LEFT JOIN sdll_leagues l ON (
    oe.league = l.display_name OR oe.league = l.fall_display_name
)
SET oe.league_id = l.ID
WHERE oe.league IS NOT NULL AND oe.league_id IS NULL;

-- ============================================
-- VERIFICATION QUERIES
-- Run these to check for unmatched records
-- ============================================

SELECT 'sdll_games' as tbl, league, COUNT(*) as cnt
FROM sdll_games
WHERE league IS NOT NULL AND league_id IS NULL
GROUP BY league
UNION ALL
SELECT 'sdll_team_seasons', league, COUNT(*)
FROM sdll_team_seasons
WHERE league IS NOT NULL AND league_id IS NULL
GROUP BY league
UNION ALL
SELECT 'sdll_league_seasons', league, COUNT(*)
FROM sdll_league_seasons
WHERE league IS NOT NULL AND league_id IS NULL
GROUP BY league
UNION ALL
SELECT 'sdll_field_slots', league, COUNT(*)
FROM sdll_field_slots
WHERE league IS NOT NULL AND league_id IS NULL
GROUP BY league
UNION ALL
SELECT 'sdll_field_allocations_specific', league, COUNT(*)
FROM sdll_field_allocations_specific
WHERE league IS NOT NULL AND league_id IS NULL
GROUP BY league
UNION ALL
SELECT 'sdll_org_events', league, COUNT(*)
FROM sdll_org_events
WHERE league IS NOT NULL AND league_id IS NULL
GROUP BY league;

Select * from sdll_leagues;
Select * from sdll_games where league_id IS NULL;
UPDATE sdll_team_seasons set league_id=6 where league='BB A' and league_id IS NULL;
UPDATE sdll_field_slots set league_id=6 where league='BB A' and league_id IS NULL;
