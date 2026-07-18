-- Add league restriction columns to sdll_fields
-- restriction_type: 'anyone' (default), 'exclude', 'only'
-- restricted_leagues: comma-separated list of league names

ALTER TABLE `sdll_fields`
ADD COLUMN `restriction_type` varchar(20) DEFAULT 'anyone' AFTER `is_owned`,
ADD COLUMN `restricted_leagues` varchar(500) DEFAULT NULL AFTER `restriction_type`;

-- Examples:
-- Anyone can use: restriction_type='anyone', restricted_leagues=NULL
-- Anyone except BB Majors: restriction_type='exclude', restricted_leagues='BB Majors'
-- Only SB leagues: restriction_type='only', restricted_leagues='SB Minors,SB Majors'
