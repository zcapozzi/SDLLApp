-- Add user_id column to sdll_page_views for tracking authenticated users
-- This column is optional (nullable) - anonymous users are still tracked via session_id
--
-- Run with: mysql -u root -p railway < scripts/add_pageview_user_id.sql
-- Or on Railway: mysql $MYSQL_URL < scripts/add_pageview_user_id.sql

-- Add the user_id column
ALTER TABLE sdll_page_views ADD COLUMN user_id BIGINT DEFAULT NULL;

-- Add index for querying by user
CREATE INDEX idx_pageview_user_id ON sdll_page_views(user_id);
