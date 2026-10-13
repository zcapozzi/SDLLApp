-- Migration: Add pitch count tracking feature
-- Run with: mysql -u root -p sdll_db < scripts/create_pitching_stats_table.sql
-- Or use --force flag to continue on errors if column/table already exists

-- ============================================================================
-- Phase 1: Add track_pitching_stats column to sdll_leagues
-- ============================================================================

ALTER TABLE sdll_leagues ADD COLUMN track_pitching_stats SMALLINT DEFAULT 0;

-- Enable pitching stats tracking for kid-pitch baseball leagues by default
UPDATE sdll_leagues
SET track_pitching_stats = 1
WHERE sport = 'baseball' AND pitch_type = 'kid_pitch';

-- ============================================================================
-- Phase 2: Create sdll_pitching_stats table
-- ============================================================================

CREATE TABLE sdll_pitching_stats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    report_id INT NOT NULL,                    -- FK to sdll_post_game_reports.id
    player_id INT NOT NULL,                    -- FK to sdll_players.id

    -- Core pitch tracking (required for Little League compliance)
    pitch_count SMALLINT NOT NULL DEFAULT 0,
    strikes SMALLINT,

    -- Innings pitched (e.g., 2.1 = 2 and 1/3 innings)
    innings_pitched DECIMAL(3,1),

    -- Results against
    batters_faced SMALLINT,
    hits_allowed SMALLINT,
    walks SMALLINT,                            -- BB
    strikeouts SMALLINT,                       -- K

    -- Runs
    runs_allowed SMALLINT,
    earned_runs SMALLINT,                      -- ER

    -- Metadata
    notes VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign keys
    CONSTRAINT fk_pitching_stats_report
        FOREIGN KEY (report_id)
        REFERENCES sdll_post_game_reports(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_pitching_stats_player
        FOREIGN KEY (player_id)
        REFERENCES sdll_players(id),

    -- One record per player per report
    CONSTRAINT uq_pitching_report_player UNIQUE (report_id, player_id)
);

-- Indexes for common queries
CREATE INDEX idx_pitching_stats_player ON sdll_pitching_stats(player_id);
CREATE INDEX idx_pitching_stats_report ON sdll_pitching_stats(report_id);

-- ============================================================================
-- Verification queries (uncomment to run)
-- ============================================================================

-- Check column was added:
-- SELECT ID, display_name, pitch_type, track_pitching_stats FROM sdll_leagues;

-- Check kid-pitch leagues have pitching stats enabled:
-- SELECT display_name, pitch_type, track_pitching_stats
-- FROM sdll_leagues
-- WHERE pitch_type = 'kid_pitch';

-- Check table was created:
-- DESCRIBE sdll_pitching_stats;
