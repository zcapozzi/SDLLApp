-- Migration: Add delegation proposals tables
-- This enables the workflow for reviewing and accepting umpire delegations for new games.
--
-- Run with: mysql -u root -p sdll_database < scripts/migrations/add_delegation_proposals.sql

-- 1. Create delegation proposals table
CREATE TABLE IF NOT EXISTS `sdll_delegation_proposals` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `created_by` BIGINT DEFAULT NULL,
    `year` INT NOT NULL,
    `is_spring` SMALLINT NOT NULL,
    `status` ENUM('pending', 'accepted', 'rejected') NOT NULL DEFAULT 'pending',
    `accepted_at` DATETIME DEFAULT NULL,
    `accepted_by` BIGINT DEFAULT NULL,
    `game_count` INT NOT NULL DEFAULT 0,
    `tier1_violations` INT NOT NULL DEFAULT 0,
    `tier2_violations` INT NOT NULL DEFAULT 0,
    `summary_json` TEXT,
    PRIMARY KEY (`id`),
    KEY `idx_year_spring_status` (`year`, `is_spring`, `status`),
    FOREIGN KEY (`created_by`) REFERENCES `sdll_users`(`ID`) ON DELETE SET NULL,
    FOREIGN KEY (`accepted_by`) REFERENCES `sdll_users`(`ID`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Create delegation proposal games table
CREATE TABLE IF NOT EXISTS `sdll_delegation_proposal_games` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `proposal_id` INT NOT NULL,
    `game_id` BIGINT NOT NULL,
    `suggested_partner_id` INT NOT NULL,
    `final_partner_id` INT DEFAULT NULL,
    `is_back_to_back` TINYINT DEFAULT 0,
    `sequence_id` INT DEFAULT NULL,
    PRIMARY KEY (`id`),
    FOREIGN KEY (`proposal_id`) REFERENCES `sdll_delegation_proposals`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`game_id`) REFERENCES `sdll_games`(`ID`) ON DELETE CASCADE,
    FOREIGN KEY (`suggested_partner_id`) REFERENCES `sdll_umpire_partners`(`id`),
    FOREIGN KEY (`final_partner_id`) REFERENCES `sdll_umpire_partners`(`id`),
    UNIQUE KEY `uk_proposal_game` (`proposal_id`, `game_id`),
    KEY `idx_proposal_id` (`proposal_id`),
    KEY `idx_sequence_id` (`sequence_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
