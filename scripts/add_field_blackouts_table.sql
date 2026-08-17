-- Add field start date and field-specific blackout dates
-- Fields may not be available until a certain date (e.g., construction/renovation)
-- Or may be unavailable on specific dates (e.g., tournaments, maintenance)

-- Add start_date column to fields table (ignore error if already exists)
ALTER TABLE sdll_fields ADD COLUMN start_date DATE DEFAULT NULL;

-- Create field blackouts table
-- Note: Foreign key constraint removed due to sdll_fields table structure
-- Application enforces referential integrity
CREATE TABLE IF NOT EXISTS sdll_field_blackouts (
    ID BIGINT AUTO_INCREMENT PRIMARY KEY,
    field_ID BIGINT NOT NULL,
    blackout_date DATE NOT NULL,
    reason VARCHAR(200),
    active SMALLINT DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY unique_field_blackout (field_ID, blackout_date),
    INDEX idx_field (field_ID, active),
    INDEX idx_date (blackout_date)
);
