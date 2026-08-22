-- Migration: Add field_id column to sdll_games table
-- This creates a proper FK relationship to sdll_fields

-- Step 1: Add the column (nullable initially)
ALTER TABLE sdll_games ADD COLUMN field_id BIGINT NULL;

-- Step 2: Create index for performance
CREATE INDEX idx_games_field_id ON sdll_games(field_id);

-- Step 3: Add foreign key constraint
ALTER TABLE sdll_games
ADD CONSTRAINT fk_games_field
FOREIGN KEY (field_id) REFERENCES sdll_fields(ID);

-- Step 4: Populate field_id from existing location strings
-- Match by location_title first
UPDATE sdll_games g
JOIN sdll_fields f ON g.location = f.location_title
SET g.field_id = f.ID
WHERE g.location IS NOT NULL AND g.field_id IS NULL;

-- Step 5: Try alternate field names for any remaining unmatched
UPDATE sdll_games g
JOIN sdll_alternate_field_names afn ON g.location = afn.alternate_name
JOIN sdll_fields f ON afn.field_ID = f.ID
SET g.field_id = f.ID
WHERE g.location IS NOT NULL AND g.field_id IS NULL;

-- Verify: Check for any games with location but no field_id
-- SELECT location, COUNT(*) FROM sdll_games
-- WHERE location IS NOT NULL AND field_id IS NULL
-- GROUP BY location;
