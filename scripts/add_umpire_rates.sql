-- Add umpire payment rate columns
-- Organization defaults and League overrides

-- Add default rates to Organization table
ALTER TABLE sdll_organizations
ADD COLUMN umpire_rate_plate DECIMAL(6,2) DEFAULT 45.00,
ADD COLUMN umpire_rate_base DECIMAL(6,2) DEFAULT 40.00;

-- Add override rates to League table (NULL = use org defaults)
ALTER TABLE sdll_leagues
ADD COLUMN umpire_rate_plate_override DECIMAL(6,2) DEFAULT NULL,
ADD COLUMN umpire_rate_base_override DECIMAL(6,2) DEFAULT NULL;

-- Set initial values for home org (SDLL)
UPDATE sdll_organizations
SET umpire_rate_plate = 45.00,
    umpire_rate_base = 40.00
WHERE is_home_org = 1;
