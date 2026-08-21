-- Add rules_doc_url column to leagues table
ALTER TABLE sdll_leagues ADD COLUMN rules_doc_url VARCHAR(500) DEFAULT NULL;
