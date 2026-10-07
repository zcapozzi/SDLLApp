-- Add field_guide_url column to sdll_organizations
-- This stores a URL to the field guide document shown to coaches on team schedule pages

ALTER TABLE sdll_organizations
ADD COLUMN field_guide_url VARCHAR(500) DEFAULT NULL;

-- Set the current field guide URL for the home org (SDLL)
UPDATE sdll_organizations
SET field_guide_url = 'https://docs.google.com/document/d/10SgqmmCzdqYFWPSyMbzDon-2kfzwuQ8I/edit?usp=drivesdk&ouid=104852418410065331619&rtpof=true&sd=true'
WHERE is_home_org = 1;
