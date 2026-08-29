-- Migration: Add support for managed umpires (youth umpires managed by parents)
-- This allows parents to manage multiple children's umpire profiles from one account

-- Add name field to umpire profiles (for managed umpires without their own User account)
ALTER TABLE sdll_umpire_profiles
ADD COLUMN _name VARCHAR(500) DEFAULT NULL AFTER user_id;

-- Make user_id nullable (managed umpires won't have their own user)
ALTER TABLE sdll_umpire_profiles
MODIFY COLUMN user_id BIGINT NULL;

-- Remove unique constraint on user_id (a user can now have their own profile AND manage others)
-- Note: This may fail if constraint doesn't exist, which is fine
ALTER TABLE sdll_umpire_profiles
DROP INDEX user_id;

-- Create guardian relationship table
CREATE TABLE IF NOT EXISTS sdll_umpire_guardians (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    guardian_user_id BIGINT NOT NULL,
    umpire_profile_id INT NOT NULL,
    relationship VARCHAR(50) DEFAULT 'parent',
    is_primary SMALLINT DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (guardian_user_id) REFERENCES sdll_users(ID) ON DELETE CASCADE,
    FOREIGN KEY (umpire_profile_id) REFERENCES sdll_umpire_profiles(id) ON DELETE CASCADE,
    UNIQUE KEY unique_guardian_umpire (guardian_user_id, umpire_profile_id),
    INDEX idx_guardian (guardian_user_id),
    INDEX idx_profile (umpire_profile_id)
);
