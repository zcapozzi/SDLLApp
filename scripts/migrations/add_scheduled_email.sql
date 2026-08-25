-- Migration: Add scheduled_emails table for email blast feature
-- Date: 2026-08-25
-- Purpose: Support scheduled/immediate email blasts to coaches

CREATE TABLE IF NOT EXISTS `sdll_scheduled_emails` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `created_by` BIGINT NOT NULL,

  -- Email type for flexibility
  `email_type` VARCHAR(50) NOT NULL DEFAULT 'coach_blast',

  -- Targeting (for coach_blast type)
  `year` INT DEFAULT NULL,
  `is_spring` SMALLINT DEFAULT NULL,
  `leagues` TEXT DEFAULT NULL,

  -- Recipients
  `recipients` TEXT NOT NULL,
  `manual_recipients` TEXT DEFAULT NULL,

  -- Send mode
  `send_mode` ENUM('cc', 'bcc', 'individual') NOT NULL DEFAULT 'cc',

  -- Content
  `subject` VARCHAR(255) NOT NULL,
  `body_html` TEXT NOT NULL,
  `body_text` TEXT NOT NULL,
  `reply_to` VARCHAR(255) NOT NULL,

  -- Scheduling
  `scheduled_for` DATETIME DEFAULT NULL,
  `status` ENUM('pending', 'sending', 'sent', 'partial', 'failed') NOT NULL DEFAULT 'pending',
  `sent_at` DATETIME DEFAULT NULL,
  `attempted_at` DATETIME DEFAULT NULL,

  -- Results
  `recipient_count` INT DEFAULT 0,
  `sent_count` INT DEFAULT 0,
  `failed_count` INT DEFAULT 0,
  `error_message` TEXT,
  `failure_notified` TINYINT DEFAULT 0,

  PRIMARY KEY (`id`),
  KEY `idx_status_scheduled` (`status`, `scheduled_for`),
  KEY `idx_attempted` (`attempted_at`),
  CONSTRAINT `fk_scheduled_email_created_by` FOREIGN KEY (`created_by`) REFERENCES `sdll_users` (`ID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
