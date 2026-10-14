-- Add LLM response time tracking to GC screenshot sessions
-- This enables timeout detection using statistical thresholds (3 std dev)

ALTER TABLE sdll_gc_screenshot_sessions
ADD COLUMN llm_response_time_ms INT DEFAULT NULL
COMMENT 'LLM API response time in milliseconds (for timeout detection)';

-- Index for efficient statistical queries
ALTER TABLE sdll_gc_screenshot_sessions
ADD INDEX idx_response_time (llm_response_time_ms);
