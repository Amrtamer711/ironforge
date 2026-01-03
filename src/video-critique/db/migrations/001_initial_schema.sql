-- =============================================================================
-- Video Critique Service - Initial Schema Migration
-- =============================================================================
-- Run this in your Supabase SQL Editor to create the required tables.
--
-- This migration creates:
-- 1. video_tasks - Live design request/video tasks
-- 2. completed_tasks - Archived/completed tasks
-- 3. approval_workflows - Multi-stage approval workflows
-- 4. video_config - Configuration storage (replaces JSON files)
-- 5. ai_costs - AI usage cost tracking
-- 6. chat_sessions - Web chat session persistence
-- =============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- VIDEO TASKS (Live Tasks)
-- =============================================================================
CREATE TABLE IF NOT EXISTS video_tasks (
    -- Primary key (auto-incrementing task number)
    task_number SERIAL PRIMARY KEY,

    -- Task details
    brand TEXT,
    campaign_start_date TEXT,  -- DD-MM-YYYY format
    campaign_end_date TEXT,    -- DD-MM-YYYY format
    reference_number TEXT,
    location TEXT,
    sales_person TEXT,
    submitted_by TEXT,

    -- Status and assignment
    status TEXT DEFAULT 'Not assigned yet',
    filming_date TEXT,  -- DD-MM-YYYY format
    videographer TEXT,
    task_type TEXT DEFAULT 'videography',
    time_block TEXT,  -- For Abu Dhabi scheduling

    -- Submission tracking
    submission_folder TEXT,
    current_version INTEGER DEFAULT 0,
    version_history JSONB DEFAULT '[]'::jsonb,

    -- Timestamps
    timestamp TEXT,  -- Creation timestamp (DD-MM-YYYY HH:MM:SS)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Status change timestamps
    pending_timestamps TEXT,
    submitted_timestamps TEXT,
    returned_timestamps TEXT,
    rejected_timestamps TEXT,
    accepted_timestamps TEXT
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_video_tasks_status ON video_tasks(status);
CREATE INDEX IF NOT EXISTS idx_video_tasks_videographer ON video_tasks(videographer);
CREATE INDEX IF NOT EXISTS idx_video_tasks_reference ON video_tasks(reference_number);
CREATE INDEX IF NOT EXISTS idx_video_tasks_filming_date ON video_tasks(filming_date);

-- =============================================================================
-- COMPLETED TASKS (Archived Tasks)
-- =============================================================================
CREATE TABLE IF NOT EXISTS completed_tasks (
    id SERIAL PRIMARY KEY,
    task_number INTEGER NOT NULL,

    -- Task details (same as video_tasks)
    brand TEXT,
    campaign_start_date TEXT,
    campaign_end_date TEXT,
    reference_number TEXT,
    location TEXT,
    sales_person TEXT,
    submitted_by TEXT,

    -- Status and assignment
    status TEXT,
    filming_date TEXT,
    videographer TEXT,
    task_type TEXT DEFAULT 'videography',
    time_block TEXT,

    -- Submission tracking
    submission_folder TEXT,
    current_version INTEGER DEFAULT 0,
    version_history JSONB DEFAULT '[]'::jsonb,

    -- Status change timestamps
    pending_timestamps TEXT,
    submitted_timestamps TEXT,
    returned_timestamps TEXT,
    rejected_timestamps TEXT,
    accepted_timestamps TEXT,

    -- Completion timestamp
    completed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for lookups
CREATE INDEX IF NOT EXISTS idx_completed_tasks_number ON completed_tasks(task_number);
CREATE INDEX IF NOT EXISTS idx_completed_tasks_reference ON completed_tasks(reference_number);

-- =============================================================================
-- APPROVAL WORKFLOWS
-- =============================================================================
CREATE TABLE IF NOT EXISTS approval_workflows (
    -- Primary key
    workflow_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Task reference
    task_number INTEGER REFERENCES video_tasks(task_number) ON DELETE CASCADE,

    -- Dropbox info
    folder_name TEXT,
    dropbox_path TEXT,

    -- Participants
    videographer_id TEXT,
    reviewer_id TEXT,
    hos_id TEXT,

    -- Slack message timestamps (for updating messages)
    reviewer_msg_ts TEXT,
    hos_msg_ts TEXT,

    -- Web notification IDs (for unified-ui)
    reviewer_notification_id TEXT,
    hos_notification_id TEXT,

    -- Approval status
    reviewer_approved BOOLEAN DEFAULT FALSE,
    hos_approved BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'pending',

    -- Stored data
    task_data JSONB DEFAULT '{}'::jsonb,
    version_info JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_approval_workflows_task ON approval_workflows(task_number);
CREATE INDEX IF NOT EXISTS idx_approval_workflows_status ON approval_workflows(status);

-- =============================================================================
-- VIDEO CONFIGURATION
-- =============================================================================
-- Replaces JSON-based configuration files (videographer_config.json, etc.)
CREATE TABLE IF NOT EXISTS video_config (
    id SERIAL PRIMARY KEY,

    -- Config type: 'videographer', 'location', 'salesperson', 'reviewer', 'head_of_sales', 'head_of_dept', 'general'
    config_type TEXT NOT NULL,

    -- Unique key within the config type
    config_key TEXT NOT NULL,

    -- Configuration data as JSON
    config_data JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique constraint on (config_type, config_key)
    UNIQUE(config_type, config_key)
);

-- Index for lookups
CREATE INDEX IF NOT EXISTS idx_video_config_type ON video_config(config_type);

-- =============================================================================
-- AI COSTS
-- =============================================================================
CREATE TABLE IF NOT EXISTS ai_costs (
    id SERIAL PRIMARY KEY,

    -- Call details
    call_type TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_cost DECIMAL(10, 6) DEFAULT 0,

    -- Context
    user_id TEXT,
    workflow TEXT,
    context TEXT,

    -- Timestamp
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Index for queries
CREATE INDEX IF NOT EXISTS idx_ai_costs_timestamp ON ai_costs(timestamp);
CREATE INDEX IF NOT EXISTS idx_ai_costs_workflow ON ai_costs(workflow);
CREATE INDEX IF NOT EXISTS idx_ai_costs_user ON ai_costs(user_id);

-- =============================================================================
-- CHAT SESSIONS (for Web Channel)
-- =============================================================================
CREATE TABLE IF NOT EXISTS chat_sessions (
    user_id TEXT PRIMARY KEY,
    session_id UUID DEFAULT uuid_generate_v4(),
    messages JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- ROW LEVEL SECURITY (RLS)
-- =============================================================================
-- Note: For service role access, RLS is bypassed. These policies are for
-- future use with user-level access or anon key access.

-- Enable RLS on all tables
ALTER TABLE video_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE completed_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_workflows ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_costs ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;

-- Service role can access everything (these policies are for documentation)
-- In practice, service_role key bypasses RLS

-- =============================================================================
-- FUNCTIONS AND TRIGGERS
-- =============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to tables with updated_at
CREATE TRIGGER update_video_tasks_updated_at
    BEFORE UPDATE ON video_tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_approval_workflows_updated_at
    BEFORE UPDATE ON approval_workflows
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_video_config_updated_at
    BEFORE UPDATE ON video_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_chat_sessions_updated_at
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- SAMPLE DATA: Initial Configuration
-- =============================================================================
-- You can uncomment and modify this section to seed initial configuration

-- Insert videographer configuration example:
-- INSERT INTO video_config (config_type, config_key, config_data) VALUES
-- ('videographer', 'John Doe', '{"name": "John Doe", "slack_user_id": "U12345", "active": true, "locations": ["Dubai", "Abu Dhabi"], "max_tasks": 5}'),
-- ('videographer', 'Jane Smith', '{"name": "Jane Smith", "slack_user_id": "U67890", "active": true, "locations": ["Dubai"], "max_tasks": 4}');

-- Insert reviewer configuration:
-- INSERT INTO video_config (config_type, config_key, config_data) VALUES
-- ('reviewer', 'default', '{"name": "Deaa", "slack_user_id": "U_REVIEWER", "active": true}');

-- Insert head of sales configuration:
-- INSERT INTO video_config (config_type, config_key, config_data) VALUES
-- ('head_of_sales', 'default', '{"name": "Sales Manager", "slack_user_id": "U_HOS", "active": true}');

-- =============================================================================
-- GRANTS
-- =============================================================================
-- Grant access to service role (already has full access)
-- Grant access to authenticated users if needed in the future

-- GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
-- GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
