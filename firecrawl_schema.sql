-- FireCrawl Database Schema
-- Creating the necessary tables and types for FireCrawl NUQ system

-- Create group status type for crawls
CREATE TYPE nuq.group_status AS ENUM ('active', 'completed', 'cancelled');

-- Create the main scrape queue table
CREATE TABLE IF NOT EXISTS nuq.queue_scrape (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status nuq.job_status NOT NULL DEFAULT 'queued',
    data JSONB,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    finished_at TIMESTAMP WITH TIME ZONE,
    listen_channel_id VARCHAR(255),
    returnvalue JSONB,
    failedreason TEXT,
    lock UUID,
    locked_at TIMESTAMP WITH TIME ZONE,
    owner_id VARCHAR(255),
    group_id UUID
);

-- Create backlog table for queue_scrape
CREATE TABLE IF NOT EXISTS nuq.queue_scrape_backlog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data JSONB,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    listen_channel_id VARCHAR(255),
    owner_id VARCHAR(255),
    group_id UUID,
    times_out_at TIMESTAMP WITH TIME ZONE
);

-- Create crawl finished queue table
CREATE TABLE IF NOT EXISTS nuq.queue_crawl_finished (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status nuq.job_status NOT NULL DEFAULT 'queued',
    data JSONB,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    finished_at TIMESTAMP WITH TIME ZONE,
    listen_channel_id VARCHAR(255),
    returnvalue JSONB,
    failedreason TEXT,
    lock UUID,
    locked_at TIMESTAMP WITH TIME ZONE,
    owner_id VARCHAR(255),
    group_id UUID
);

-- Create crawl group table
CREATE TABLE IF NOT EXISTS nuq.group_crawl (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status nuq.group_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    owner_id VARCHAR(255),
    ttl INTEGER DEFAULT 86400000,
    expires_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_queue_scrape_status_priority_created ON nuq.queue_scrape (status, priority ASC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_group_id ON nuq.queue_scrape (group_id);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_owner_id ON nuq.queue_scrape (owner_id);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_lock ON nuq.queue_scrape (lock) WHERE lock IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_queue_scrape_backlog_group_id ON nuq.queue_scrape_backlog (group_id);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_backlog_times_out ON nuq.queue_scrape_backlog (times_out_at) WHERE times_out_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_queue_crawl_finished_status_priority_created ON nuq.queue_crawl_finished (status, priority ASC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_queue_crawl_finished_group_id ON nuq.queue_crawl_finished (group_id);

CREATE INDEX IF NOT EXISTS idx_group_crawl_owner_status ON nuq.group_crawl (owner_id, status);
CREATE INDEX IF NOT EXISTS idx_group_crawl_expires ON nuq.group_crawl (expires_at) WHERE expires_at IS NOT NULL;

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA nuq TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA nuq TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA nuq TO postgres;
