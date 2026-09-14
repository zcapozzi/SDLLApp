-- Add is_managed_by_org field to umpire_partners table
-- This field distinguishes internal (SDL Academy) from external partners (Diamond, Dynamic)
-- Internal partners (is_managed_by_org=1) get individual umpire digests
-- External partners (is_managed_by_org=0) get a single partner digest

-- Add the column
ALTER TABLE sdll_umpire_partners ADD COLUMN is_managed_by_org TINYINT DEFAULT 0;

-- Set SDL Academy as managed by org
UPDATE sdll_umpire_partners SET is_managed_by_org = 1 WHERE short_code = 'SDL';

-- Verify
SELECT id, name, short_code, is_managed_by_org FROM sdll_umpire_partners WHERE active = 1;
