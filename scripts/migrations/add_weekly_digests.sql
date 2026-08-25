-- Migration: Add weekly digest system for umpire partner notifications
-- Run this on Railway MySQL

-- Create the weekly digests table
CREATE TABLE IF NOT EXISTS `sdll_weekly_digests` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  -- Targeting
  `partner_code` VARCHAR(10) NOT NULL,
  `partner_name` VARCHAR(100) NOT NULL,
  `week_start` DATE NOT NULL,
  `year` INT NOT NULL,
  `is_spring` SMALLINT NOT NULL,

  -- Recipients
  `recipient_emails` TEXT NOT NULL,

  -- Content
  `subject` VARCHAR(255) NOT NULL,
  `body_html` TEXT NOT NULL,
  `game_count` INT NOT NULL DEFAULT 0,

  -- Workflow
  `status` ENUM('draft', 'ready', 'sent', 'skipped') NOT NULL DEFAULT 'draft',
  `reviewed_by` BIGINT DEFAULT NULL,
  `reviewed_at` DATETIME DEFAULT NULL,
  `sent_at` DATETIME DEFAULT NULL,
  `sent_by` BIGINT DEFAULT NULL,

  -- Reminders
  `reminder_sent` TINYINT DEFAULT 0,

  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_partner_week` (`partner_code`, `week_start`),
  KEY `idx_status` (`status`),
  KEY `idx_week` (`week_start`),
  CONSTRAINT `fk_digest_reviewed_by` FOREIGN KEY (`reviewed_by`) REFERENCES `sdll_users` (`ID`) ON DELETE SET NULL,
  CONSTRAINT `fk_digest_sent_by` FOREIGN KEY (`sent_by`) REFERENCES `sdll_users` (`ID`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Add auto_send_digest column to umpire partners
-- Note: Using plain ALTER TABLE without IF EXISTS for MySQL compatibility
-- Run with mysql --force to continue on errors if column already exists
ALTER TABLE sdll_umpire_partners
ADD COLUMN auto_send_digest TINYINT DEFAULT 0;
