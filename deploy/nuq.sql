-- Create schema and types
CREATE SCHEMA IF NOT EXISTS nuq;

CREATE TYPE nuq.job_status AS ENUM (
  'waiting',
  'queued',
  'active',
  'completed',
  'failed',
  'delayed',
  'waiting-children',
  'prioritized'
);

CREATE TYPE nuq.group_status AS ENUM (
  'active',
  'completed'
);

-- Function to auto-queue jobs stuck in waiting
CREATE OR REPLACE FUNCTION nuq.auto_queue_job() RETURNS TRIGGER AS $$
BEGIN
  IF NEW.status = 'waiting' THEN
    NEW.status := 'queued';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-queue jobs
CREATE TRIGGER trigger_auto_queue_job
BEFORE INSERT ON nuq.queue_scrape
FOR EACH ROW
EXECUTE FUNCTION nuq.auto_queue_job();

-- Main queue table for scraping jobs
CREATE TABLE IF NOT EXISTS nuq.queue_scrape (
  id TEXT PRIMARY KEY,
  status nuq.job_status NOT NULL DEFAULT 'waiting',
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  priority INTEGER NOT NULL DEFAULT 0,
  lock TEXT,
  locked_at TIMESTAMPTZ,
  stalls INTEGER NOT NULL DEFAULT 0,
  finished_at TIMESTAMPTZ,
  listen_channel_id TEXT,
  returnvalue JSONB,
  failedreason TEXT,
  owner_id TEXT,
  group_id TEXT
);

-- Backlog queue table
CREATE TABLE IF NOT EXISTS nuq.queue_scrape_backlog (
  id TEXT PRIMARY KEY,
  status nuq.job_status NOT NULL DEFAULT 'waiting',
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  priority INTEGER NOT NULL DEFAULT 0,
  lock TEXT,
  locked_at TIMESTAMPTZ,
  stalls INTEGER NOT NULL DEFAULT 0,
  finished_at TIMESTAMPTZ,
  listen_channel_id TEXT,
  returnvalue JSONB,
  failedreason TEXT,
  owner_id TEXT,
  group_id TEXT
);

-- Crawl finished queue table
CREATE TABLE IF NOT EXISTS nuq.queue_crawl_finished (
  id TEXT PRIMARY KEY,
  status nuq.job_status NOT NULL DEFAULT 'waiting',
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  priority INTEGER NOT NULL DEFAULT 0,
  lock TEXT,
  locked_at TIMESTAMPTZ,
  stalls INTEGER NOT NULL DEFAULT 0,
  finished_at TIMESTAMPTZ,
  listen_channel_id TEXT,
  returnvalue JSONB,
  failedreason TEXT,
  owner_id TEXT,
  group_id TEXT
);

-- Group crawl table
CREATE TABLE IF NOT EXISTS nuq.group_crawl (
  id TEXT PRIMARY KEY,
  status nuq.group_status NOT NULL DEFAULT 'active',
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  returnvalue JSONB,
  failedreason TEXT
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_queue_scrape_status ON nuq.queue_scrape (status);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_priority ON nuq.queue_scrape (priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_locked_at ON nuq.queue_scrape (locked_at);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_finished_at ON nuq.queue_scrape (finished_at);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_owner_id ON nuq.queue_scrape (owner_id);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_group_id ON nuq.queue_scrape (group_id);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_listen_channel ON nuq.queue_scrape (listen_channel_id);

CREATE INDEX IF NOT EXISTS idx_queue_scrape_backlog_status ON nuq.queue_scrape_backlog (status);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_backlog_priority ON nuq.queue_scrape_backlog (priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_backlog_locked_at ON nuq.queue_scrape_backlog (locked_at);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_backlog_finished_at ON nuq.queue_scrape_backlog (finished_at);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_backlog_owner_id ON nuq.queue_scrape_backlog (owner_id);
CREATE INDEX IF NOT EXISTS idx_queue_scrape_backlog_group_id ON nuq.queue_scrape_backlog (group_id);

CREATE INDEX IF NOT EXISTS idx_queue_crawl_finished_status ON nuq.queue_crawl_finished (status);
CREATE INDEX IF NOT EXISTS idx_queue_crawl_finished_priority ON nuq.queue_crawl_finished (priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_queue_crawl_finished_locked_at ON nuq.queue_crawl_finished (locked_at);

CREATE INDEX IF NOT EXISTS idx_group_crawl_status ON nuq.group_crawl (status);

-- Enable pg_cron extension for scheduled cleanup
-- CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Schedule cleanup jobs (runs every 5 minutes to clean up old completed jobs)
-- SELECT cron.schedule(
--   'cleanup-queue-scrape',
--   '*/5 * * * *',
--   $$DELETE FROM nuq.queue_scrape WHERE status = 'completed' AND finished_at < NOW() - INTERVAL '24 hours'$$
-- );

-- SELECT cron.schedule(
--   'cleanup-queue-scrape-backlog',
--   '*/5 * * * *',
--   $$DELETE FROM nuq.queue_scrape_backlog WHERE status = 'completed' AND finished_at < NOW() - INTERVAL '24 hours'$$
-- );

-- SELECT cron.schedule(
--   'cleanup-queue-crawl-finished',
--   '*/5 * * * *',
--   $$DELETE FROM nuq.queue_crawl_finished WHERE status = 'completed' AND finished_at < NOW() - INTERVAL '24 hours'$$
-- );

-- Schedule lock reaping (runs every 15 seconds to unlock stale locks)
-- SELECT cron.schedule(
--   'reap-locks-queue-scrape',
--   '*/15 * * * * *',
--   $$UPDATE nuq.queue_scrape SET lock = NULL, locked_at = NULL WHERE locked_at < NOW() - INTERVAL '5 minutes'$$
-- );

-- SELECT cron.schedule(
--   'reap-locks-queue-scrape-backlog',
--   '*/15 * * * * *',
--   $$UPDATE nuq.queue_scrape_backlog SET lock = NULL, locked_at = NULL WHERE locked_at < NOW() - INTERVAL '5 minutes'$$
-- );

-- SELECT cron.schedule(
--   'reap-locks-queue-crawl-finished',
--   '*/15 * * * * *',
--   $$UPDATE nuq.queue_crawl_finished SET lock = NULL, locked_at = NULL WHERE locked_at < NOW() - INTERVAL '5 minutes'$$
-- );

-- Schedule periodic reindexing (runs daily at 2 AM)
-- Requires pg_cron extension which might not be available in all images
-- SELECT cron.schedule(
--   'reindex-queue-scrape',
--   '0 2 * * *',
--   $$REINDEX TABLE nuq.queue_scrape$$
-- );

-- SELECT cron.schedule(
--   'reindex-queue-scrape-backlog',
--   '0 2 * * *',
--   $$REINDEX TABLE nuq.queue_scrape_backlog$$
-- );
