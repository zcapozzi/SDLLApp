-- Migration: Add specific-date field allocations table
-- Unlike sdll_field_slots (recurring weekly), this table stores one-off allocations for specific dates

CREATE TABLE IF NOT EXISTS sdll_field_allocations_specific (
    ID BIGINT AUTO_INCREMENT PRIMARY KEY,
    active SMALLINT DEFAULT 1,
    field_ID BIGINT NOT NULL,
    year INT NOT NULL,
    is_spring SMALLINT NOT NULL,
    allocation_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    league VARCHAR(50) DEFAULT NULL,
    is_owned SMALLINT DEFAULT 1,
    notes VARCHAR(200) DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (field_ID) REFERENCES sdll_fields(ID),
    INDEX idx_season (year, is_spring),
    INDEX idx_date (allocation_date),
    INDEX idx_field_date (field_ID, allocation_date)
);
