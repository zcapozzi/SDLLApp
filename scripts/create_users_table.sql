-- Create sdll_users table for authentication
-- Run this script against your MySQL database

-- Drop existing table if you need to recreate with new column sizes
-- DROP TABLE IF EXISTS `sdll_users`;

CREATE TABLE IF NOT EXISTS `sdll_users` (
    `ID` bigint NOT NULL AUTO_INCREMENT,
    `active` tinyint DEFAULT 1,
    `email` varchar(500) NOT NULL,         -- Encrypted with Fernet (needs more space)
    `email_hash` varchar(64) NOT NULL,     -- SHA256 hash for lookup
    `password_hash` varchar(256) NOT NULL, -- Werkzeug password hash
    `name` varchar(500),                   -- Encrypted with Fernet (needs more space)
    `phone` varchar(500),                  -- Encrypted with Fernet (needs more space)
    `role` varchar(50) DEFAULT 'viewer',   -- admin, scheduler, umpire_coordinator, viewer
    `org_ID` bigint DEFAULT 1,
    `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
    `last_login` datetime,
    `password_reset_token` varchar(100),
    `password_reset_expiry` datetime,
    PRIMARY KEY (`ID`),
    UNIQUE KEY `email_hash_unique` (`email_hash`),
    KEY `idx_org_id` (`org_ID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
