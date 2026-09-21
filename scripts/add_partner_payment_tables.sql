-- Migration: Add partner payment and credit tracking tables
-- Date: 2026-09-21
-- Purpose: Track payments made to umpire partners and credits from postponed games

-- Add prepays_invoices flag to umpire_partners table
ALTER TABLE sdll_umpire_partners
ADD COLUMN prepays_invoices TINYINT(1) DEFAULT 0 COMMENT 'True if we prepay invoices for this partner and track credits';

-- Create partner payment records table
CREATE TABLE IF NOT EXISTS sdll_partner_payment_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    partner_id INT NOT NULL,

    -- Season context (optional)
    year INT,
    is_spring TINYINT(1),

    -- Invoice details
    invoice_number VARCHAR(50) COMMENT 'Partner invoice reference',
    invoice_date DATE COMMENT 'Date on invoice',
    invoice_amount DECIMAL(8,2) COMMENT 'Amount partner invoiced',

    -- What we calculated we owed
    calculated_games INT COMMENT 'Umpire-games we calculated',
    calculated_amount DECIMAL(8,2) COMMENT 'Amount we calculated',

    -- Payment details
    paid_amount DECIMAL(8,2) COMMENT 'What we actually paid',
    payment_date DATE COMMENT 'When paid',
    payment_method VARCHAR(30) COMMENT 'check, ach, venmo, etc.',
    payment_reference VARCHAR(100) COMMENT 'Check number, transaction ID',

    -- Credit tracking
    credit_applied DECIMAL(8,2) DEFAULT 0 COMMENT 'Credit from previous period',
    credit_generated DECIMAL(8,2) DEFAULT 0 COMMENT 'Credit for next period',

    -- Status: pending, paid, disputed, void
    status VARCHAR(20) DEFAULT 'pending',

    -- Notes
    notes TEXT,

    -- Audit
    created_by_user_id BIGINT,
    paid_by_user_id BIGINT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign keys
    CONSTRAINT fk_ppr_partner FOREIGN KEY (partner_id) REFERENCES sdll_umpire_partners(id),
    CONSTRAINT fk_ppr_created_by FOREIGN KEY (created_by_user_id) REFERENCES sdll_users(ID),
    CONSTRAINT fk_ppr_paid_by FOREIGN KEY (paid_by_user_id) REFERENCES sdll_users(ID),

    -- Indexes
    INDEX idx_ppr_partner (partner_id),
    INDEX idx_ppr_season (year, is_spring),
    INDEX idx_ppr_status (status),
    INDEX idx_ppr_invoice_date (invoice_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create partner credits table
CREATE TABLE IF NOT EXISTS sdll_partner_credits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    partner_id INT NOT NULL,

    -- Source of credit: postponed_game, unfulfilled, overpayment, adjustment
    source_type VARCHAR(30) NOT NULL,
    source_game_id BIGINT COMMENT 'If game-related',
    source_payment_id INT COMMENT 'If payment-related',

    -- Credit details
    amount DECIMAL(8,2) NOT NULL,
    umpire_games INT COMMENT 'Number of umpire-games if applicable',

    -- Season context
    season_year INT,
    season_is_spring TINYINT(1),

    -- Status: available, applied, expired, void
    status VARCHAR(20) DEFAULT 'available',
    applied_to_payment_id INT COMMENT 'Payment this credit was applied to',

    -- Notes and audit
    description VARCHAR(255),
    created_by_user_id BIGINT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Foreign keys
    CONSTRAINT fk_pc_partner FOREIGN KEY (partner_id) REFERENCES sdll_umpire_partners(id),
    CONSTRAINT fk_pc_game FOREIGN KEY (source_game_id) REFERENCES sdll_games(ID),
    CONSTRAINT fk_pc_source_payment FOREIGN KEY (source_payment_id) REFERENCES sdll_partner_payment_records(id),
    CONSTRAINT fk_pc_applied_payment FOREIGN KEY (applied_to_payment_id) REFERENCES sdll_partner_payment_records(id),
    CONSTRAINT fk_pc_created_by FOREIGN KEY (created_by_user_id) REFERENCES sdll_users(ID),

    -- Indexes
    INDEX idx_pc_partner (partner_id),
    INDEX idx_pc_status (status),
    INDEX idx_pc_season (season_year, season_is_spring),
    INDEX idx_pc_source_game (source_game_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Set Dynamic as prepay partner (by default)
UPDATE sdll_umpire_partners SET prepays_invoices = 1 WHERE short_code = 'DYN';
