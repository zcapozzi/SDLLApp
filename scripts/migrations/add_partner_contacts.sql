-- Migration: Add partner contacts table for multiple contacts per partner
-- Run with: mysql --force sdll < add_partner_contacts.sql

-- Create the partner contacts table
CREATE TABLE `sdll_partner_contacts` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `partner_id` INT NOT NULL,
  `user_id` BIGINT DEFAULT NULL,

  -- Contact info (used if not linked to a user)
  `name` VARCHAR(200) DEFAULT NULL,
  `email` VARCHAR(255) NOT NULL,
  `phone` VARCHAR(50) DEFAULT NULL,

  -- Message type subscriptions (pipe-delimited, e.g., "weeklyDigest|recentChanges")
  `message_types` VARCHAR(255) NOT NULL DEFAULT 'weeklyDigest|recentChanges',

  -- Is this the primary contact for display purposes?
  `is_primary` TINYINT DEFAULT 0,

  -- Status
  `active` TINYINT DEFAULT 1,

  -- Timestamps
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  KEY `idx_partner` (`partner_id`),
  KEY `idx_user` (`user_id`),
  KEY `idx_active` (`active`),
  KEY `idx_message_types` (`message_types`),
  CONSTRAINT `fk_partner_contact_partner` FOREIGN KEY (`partner_id`)
    REFERENCES `sdll_umpire_partners` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_partner_contact_user` FOREIGN KEY (`user_id`)
    REFERENCES `sdll_users` (`ID`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Migrate existing contact data to new table
INSERT INTO `sdll_partner_contacts` (`partner_id`, `name`, `email`, `phone`, `message_types`, `is_primary`, `active`)
SELECT
  `id`,
  `contact_name`,
  `contact_email`,
  `contact_phone`,
  'weeklyDigest|recentChanges',
  1,
  1
FROM `sdll_umpire_partners`
WHERE `contact_email` IS NOT NULL AND `contact_email` != '';

-- Drop the old contact columns from partners table
-- Note: Running with --force will continue even if these fail
ALTER TABLE `sdll_umpire_partners` DROP COLUMN `contact_name`;
ALTER TABLE `sdll_umpire_partners` DROP COLUMN `contact_email`;
ALTER TABLE `sdll_umpire_partners` DROP COLUMN `contact_phone`;
