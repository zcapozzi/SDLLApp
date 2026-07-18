-- Create field_slots table for managing field allocations
-- A field slot represents an available time slot at a specific field for a season

CREATE TABLE IF NOT EXISTS `sdll_field_slots` (
    `slot_ID` bigint PRIMARY KEY AUTO_INCREMENT,
    `active` tinyint DEFAULT 1,
    `field_ID` bigint NOT NULL,
    `year` int NOT NULL,
    `is_spring` tinyint NOT NULL,
    `day_of_week` tinyint NOT NULL,  -- 0=Monday, 1=Tuesday, ..., 6=Sunday
    `start_time` time NOT NULL,
    `end_time` time NOT NULL,
    `league` varchar(50) DEFAULT NULL,  -- NULL means any league can use it
    `notes` varchar(200) DEFAULT NULL,
    `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    KEY `idx_field_slots_season` (`year`, `is_spring`),
    KEY `idx_field_slots_field` (`field_ID`),
    KEY `idx_field_slots_day` (`day_of_week`)
    -- Note: No FK constraint - sdll_fields.ID lacks primary key index
    -- Referential integrity maintained at application level
);

-- Example: Herndon 1, Fall 2025, Monday at 5:30pm-7:00pm for BB Majors
-- INSERT INTO sdll_field_slots (field_ID, year, is_spring, day_of_week, start_time, end_time, league)
-- VALUES (1, 2025, 0, 0, '17:30:00', '19:00:00', 'BB Majors');
