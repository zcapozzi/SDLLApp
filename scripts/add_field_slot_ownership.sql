-- Add ownership tracking to field slots
-- is_owned: 1 = SDLL owns this slot (can schedule home games)
--           0 = Another league owns this slot (away games only)

ALTER TABLE `sdll_field_slots`
ADD COLUMN `is_owned` tinyint DEFAULT 1 AFTER `league`;

-- Optionally, you can also track ownership at the field level
-- for fields that are never ours to use
ALTER TABLE `sdll_fields`
ADD COLUMN `is_owned` tinyint DEFAULT 1;
