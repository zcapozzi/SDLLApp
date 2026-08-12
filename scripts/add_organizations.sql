-- Migration: Add organizations table for external teams support
-- Date: 2026-08-12
-- Purpose: Enable tracking of external organizations (Bull City, Morrisville, etc.)
--          for inter-league games

-- 1. Create the organizations table
CREATE TABLE IF NOT EXISTS sdll_organizations (
    ID BIGINT AUTO_INCREMENT PRIMARY KEY,
    active SMALLINT DEFAULT 1,
    name VARCHAR(100) NOT NULL,
    short_name VARCHAR(30),
    location VARCHAR(100),
    is_home_org SMALLINT DEFAULT 0,
    notes VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Add organization_id column to team_seasons (allows NULL for SDLL teams)
ALTER TABLE sdll_team_seasons
ADD COLUMN organization_id BIGINT NULL,
ADD CONSTRAINT fk_team_organization
    FOREIGN KEY (organization_id)
    REFERENCES sdll_organizations(ID)
    ON DELETE SET NULL;

-- 3. Insert SDLL as the home organization
INSERT INTO sdll_organizations (name, short_name, location, is_home_org, notes)
VALUES ('South Durham Little League', 'SDLL', 'Durham, NC', 1, 'Home organization');

-- 4. Insert some common external organizations (can be added to later)
INSERT INTO sdll_organizations (name, short_name, location, notes)
VALUES
    ('Bull City Little League', 'Bull City', 'Durham, NC', 'Local inter-league partner'),
    ('Morrisville Little League', 'Morrisville', 'Morrisville, NC', 'Local inter-league partner');

-- Verification query
-- SELECT * FROM sdll_organizations;
-- SELECT team_ID, display_name, organization_id FROM sdll_team_seasons LIMIT 5;
