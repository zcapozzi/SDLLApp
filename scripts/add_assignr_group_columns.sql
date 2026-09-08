-- Create umpire group assignments table for tracking Assignr group memberships
-- This replaces hard-coded columns with a flexible many-to-many relationship
-- Run with: mysql -u user -p database < scripts/add_assignr_group_columns.sql

CREATE TABLE IF NOT EXISTS sdll_umpire_group_assignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    umpire_profile_id INT NOT NULL,
    assignr_group_id INT NOT NULL,
    assignr_group_name VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (umpire_profile_id) REFERENCES sdll_umpire_profiles(id) ON DELETE CASCADE,
    UNIQUE KEY uq_umpire_group (umpire_profile_id, assignr_group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SELECT 'Created sdll_umpire_group_assignments table' AS status;
