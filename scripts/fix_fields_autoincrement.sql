-- Fix sdll_fields table to have AUTO_INCREMENT on ID column
-- First, find any records with NULL ID and assign them IDs

-- Get the max ID currently in the table
SET @max_id = (SELECT COALESCE(MAX(ID), 0) FROM sdll_fields);

-- Update any NULL IDs with sequential values
SET @row_num = 0;
UPDATE sdll_fields
SET ID = (@max_id + (@row_num := @row_num + 1))
WHERE ID IS NULL;

-- Now modify the column to be AUTO_INCREMENT
-- Note: This requires the column to be NOT NULL first
ALTER TABLE sdll_fields MODIFY COLUMN ID BIGINT NOT NULL AUTO_INCREMENT;

-- Set the auto_increment value to be higher than the max existing ID
SET @new_auto_inc = (SELECT MAX(ID) + 1 FROM sdll_fields);
SET @sql = CONCAT('ALTER TABLE sdll_fields AUTO_INCREMENT = ', @new_auto_inc);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
