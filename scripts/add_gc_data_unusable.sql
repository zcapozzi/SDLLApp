-- Add gc_data_unusable columns to post_game_reports table
-- Run this migration to support marking GameChanger data as unusable

ALTER TABLE sdll_post_game_reports
ADD COLUMN gc_data_unusable TINYINT(1) DEFAULT 0;

ALTER TABLE sdll_post_game_reports
ADD COLUMN gc_data_unusable_reason VARCHAR(200) DEFAULT NULL;
