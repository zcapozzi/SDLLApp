-- Migration: Add umpire-specific contact fields to sdll_umpire_profiles
-- These fields store the umpire's own email/phone (separate from parent contact info)

-- Add umpire email field (encrypted)
ALTER TABLE sdll_umpire_profiles
    ADD COLUMN umpire_email VARCHAR(500) DEFAULT NULL;

-- Add umpire email hash for lookups
ALTER TABLE sdll_umpire_profiles
    ADD COLUMN umpire_email_hash VARCHAR(64) DEFAULT NULL;

-- Add umpire phone field (encrypted)
ALTER TABLE sdll_umpire_profiles
    ADD COLUMN umpire_phone VARCHAR(500) DEFAULT NULL;

-- Add index on umpire_email_hash for fast lookups
CREATE INDEX idx_umpire_profiles_umpire_email_hash
    ON sdll_umpire_profiles(umpire_email_hash);
