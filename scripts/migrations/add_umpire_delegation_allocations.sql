-- Migration: Add umpire delegation allocations table
-- This replaces the hardcoded academy_pct, diamond_pct, dynamic_pct columns
-- with a flexible allocation table that can support any number of partners.
--
-- Run with: mysql -u root -p sdll_local < scripts/migrations/add_umpire_delegation_allocations.sql

-- 1. Create new allocations table
CREATE TABLE IF NOT EXISTS `sdll_umpire_delegation_allocations` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `rule_id` INT NOT NULL,
    `partner_id` INT NOT NULL,
    `percentage` SMALLINT NOT NULL DEFAULT 0,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    FOREIGN KEY (`rule_id`) REFERENCES `sdll_umpire_delegation_rules`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`partner_id`) REFERENCES `sdll_umpire_partners`(`id`) ON DELETE CASCADE,
    UNIQUE KEY `uk_rule_partner` (`rule_id`, `partner_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Migrate existing data
-- Get partner IDs dynamically and insert allocations from existing rules

-- Insert SDL (Academy) allocations
INSERT INTO sdll_umpire_delegation_allocations (rule_id, partner_id, percentage)
SELECT r.id, p.id, r.academy_pct
FROM sdll_umpire_delegation_rules r
CROSS JOIN sdll_umpire_partners p
WHERE p.short_code = 'SDL'
  AND r.academy_pct > 0
  AND NOT EXISTS (
    SELECT 1 FROM sdll_umpire_delegation_allocations a
    WHERE a.rule_id = r.id AND a.partner_id = p.id
  );

-- Insert Diamond allocations
INSERT INTO sdll_umpire_delegation_allocations (rule_id, partner_id, percentage)
SELECT r.id, p.id, r.diamond_pct
FROM sdll_umpire_delegation_rules r
CROSS JOIN sdll_umpire_partners p
WHERE p.short_code = 'DIA'
  AND r.diamond_pct > 0
  AND NOT EXISTS (
    SELECT 1 FROM sdll_umpire_delegation_allocations a
    WHERE a.rule_id = r.id AND a.partner_id = p.id
  );

-- Insert Dynamic allocations
INSERT INTO sdll_umpire_delegation_allocations (rule_id, partner_id, percentage)
SELECT r.id, p.id, r.dynamic_pct
FROM sdll_umpire_delegation_rules r
CROSS JOIN sdll_umpire_partners p
WHERE p.short_code = 'DYN'
  AND r.dynamic_pct > 0
  AND NOT EXISTS (
    SELECT 1 FROM sdll_umpire_delegation_allocations a
    WHERE a.rule_id = r.id AND a.partner_id = p.id
  );

-- 3. Drop old columns (run these after verifying migration)
-- Using separate ALTER statements for MySQL compatibility
ALTER TABLE sdll_umpire_delegation_rules DROP COLUMN academy_pct;
ALTER TABLE sdll_umpire_delegation_rules DROP COLUMN diamond_pct;
ALTER TABLE sdll_umpire_delegation_rules DROP COLUMN dynamic_pct;
