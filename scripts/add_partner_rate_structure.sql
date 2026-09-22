-- Migration: Add enhanced rate structure for umpire partners
-- Date: 2026-09-21
-- Purpose: Support per-umpire vs flat rates, per-game and per-season booking fees

-- Add is_flat_rate flag (True = rate is per-game, False = rate is per-umpire)
ALTER TABLE sdll_umpire_partners
ADD COLUMN is_flat_rate TINYINT(1) DEFAULT 0 COMMENT 'True if rate_normal is per-game flat rate, False if per-umpire';

-- Add per-game booking fee
ALTER TABLE sdll_umpire_partners
ADD COLUMN booking_fee_per_game DECIMAL(8,2) DEFAULT 0 COMMENT 'Per-game booking fee (e.g., Diamond $18/game)';

-- Add per-season booking fee
ALTER TABLE sdll_umpire_partners
ADD COLUMN booking_fee_per_season DECIMAL(8,2) DEFAULT 0 COMMENT 'Per-season booking fee (e.g., Dynamic $1000/season)';

-- Widen rate_normal and rate_ntl columns to DECIMAL(8,2) for consistency
ALTER TABLE sdll_umpire_partners
MODIFY COLUMN rate_normal DECIMAL(8,2) COMMENT 'Normal game rate (per-umpire or flat depending on is_flat_rate)';

ALTER TABLE sdll_umpire_partners
MODIFY COLUMN rate_ntl DECIMAL(8,2) COMMENT 'No-time-limit game rate (per-umpire or flat depending on is_flat_rate)';

-- Set up Diamond rates: $85/umpire + $18/game booking fee
UPDATE sdll_umpire_partners
SET rate_normal = 85.00,
    rate_ntl = 85.00,
    is_flat_rate = 0,
    booking_fee_per_game = 18.00,
    booking_fee_per_season = 0
WHERE short_code = 'DIA';

-- Set up Dynamic rates: $100/umpire + $1000/season
UPDATE sdll_umpire_partners
SET rate_normal = 100.00,
    rate_ntl = 100.00,
    is_flat_rate = 0,
    booking_fee_per_game = 0,
    booking_fee_per_season = 1000.00
WHERE short_code = 'DYN';
