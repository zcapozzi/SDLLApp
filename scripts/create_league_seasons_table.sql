-- Create league_seasons table for league configuration per season
-- Stores playoff format and other league-specific settings for each season

CREATE TABLE IF NOT EXISTS `sdll_league_seasons` (
    `ID` bigint PRIMARY KEY AUTO_INCREMENT,
    `active` tinyint DEFAULT 1,
    `year` int NOT NULL,
    `is_spring` tinyint NOT NULL,
    `league` varchar(50) NOT NULL,
    `playoff_format` varchar(30) DEFAULT 'single_elimination',
    `notes` varchar(200) DEFAULT NULL,
    `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY `idx_league_season` (`year`, `is_spring`, `league`),
    KEY `idx_league_seasons_season` (`year`, `is_spring`)
);

-- Playoff format values:
-- 'single_elimination' - Single elimination bracket
-- 'double_elimination' - Double elimination bracket
-- 'round_robin_knockout' - Round robin pool play followed by knockout rounds
