-- Supabase schema for raga ingestion + phrase libraries
-- This is designed to mirror the metadata produced by extract_phrases.py
-- and enriched by raga_scorer.py / phrase_indexer.py.

create extension if not exists "uuid-ossp";

-- ─────────────────────────────────────────────────────────────────────────────
-- Collections (playlists, albums, archives) used to discover top recordings
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists source_collections (
  id uuid primary key default uuid_generate_v4(),
  source_key text unique,
  raga text not null,
  title text not null,
  url text not null,
  source_platform text,
  license_type text default 'unknown',
  rights_status text default 'reference_only',
  expected_count int,
  notes text,
  created_at timestamptz default now()
);

create index if not exists source_collections_raga_idx
  on source_collections (raga);

-- ─────────────────────────────────────────────────────────────────────────────
-- Individual recordings (top-50 targets per raga)
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists recording_sources (
  id uuid primary key default uuid_generate_v4(),
  source_key text unique,
  raga text not null,
  artist text,
  title text not null,
  performance_type text, -- vocal, sitar, sarangi, bansuri, etc.
  link text not null,
  source_platform text,
  duration_sec numeric,
  license_type text default 'unknown',
  rights_status text default 'reference_only',
  collection_id uuid references source_collections(id) on delete set null,
  rank int,
  tags jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

create index if not exists recording_sources_raga_idx
  on recording_sources (raga);

create index if not exists recording_sources_rights_idx
  on recording_sources (rights_status);

-- ─────────────────────────────────────────────────────────────────────────────
-- Downloaded assets + normalized audio
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists recording_assets (
  id uuid primary key default uuid_generate_v4(),
  source_id uuid not null references recording_sources(id) on delete cascade,
  storage_path_raw text,
  storage_path_wav text,
  duration_sec numeric,
  sample_rate int,
  channels int,
  checksum_sha256 text,
  raw_checksum_sha256 text,
  raw_size_mb numeric,
  wav_size_mb numeric,
  ingest_warnings jsonb default '[]'::jsonb,
  created_at timestamptz default now()
);

create index if not exists recording_assets_source_idx
  on recording_assets (source_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Extraction jobs (tracking batch runs)
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists extraction_jobs (
  id uuid primary key default uuid_generate_v4(),
  source_id uuid not null references recording_sources(id) on delete cascade,
  status text default 'pending', -- pending, running, done, failed
  params jsonb default '{}'::jsonb,
  output_dir text,
  extracted_count int default 0,
  started_at timestamptz,
  finished_at timestamptz,
  error text,
  created_at timestamptz default now()
);

create index if not exists extraction_jobs_source_idx
  on extraction_jobs (source_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Phrase assets (library entries) + intelligence scores
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists phrase_assets (
  id uuid primary key default uuid_generate_v4(),
  source_id uuid not null references recording_sources(id) on delete cascade,
  phrase_id text not null,
  storage_path text not null,
  duration_sec numeric,
  notes_sequence text[],
  notes_detected text[],
  starts_with text,
  ends_with text,
  energy_level numeric,
  quality_score numeric,
  authenticity_score numeric,
  library_tier text default 'standard', -- standard, gold
  source_type text default 'library',   -- library, generated
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

create index if not exists phrase_assets_source_idx
  on phrase_assets (source_id);

create index if not exists phrase_assets_raga_idx
  on phrase_assets (source_id, library_tier);

-- ─────────────────────────────────────────────────────────────────────────────
-- Quality metrics (optional; can be stored in metadata too)
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists quality_metrics (
  id uuid primary key default uuid_generate_v4(),
  phrase_asset_id uuid not null references phrase_assets(id) on delete cascade,
  lufs numeric,
  true_peak numeric,
  dynamic_range numeric,
  noise_floor numeric,
  spectral_balance jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

create index if not exists quality_metrics_phrase_idx
  on quality_metrics (phrase_asset_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Seeding QA reports (aggregate checks for candidate pools)
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists seeding_reports (
  id uuid primary key default uuid_generate_v4(),
  report_key text unique,
  raga text,
  report jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

create index if not exists seeding_reports_raga_idx
  on seeding_reports (raga);

-- ─────────────────────────────────────────────────────────────────────────────
-- AI events (prompt parsing, explanations, variations)
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists ai_events (
  id uuid primary key default uuid_generate_v4(),
  event_type text not null,
  prompt text,
  input jsonb default '{}'::jsonb,
  output jsonb default '{}'::jsonb,
  model text,
  latency_ms int,
  created_at timestamptz default now()
);

create index if not exists ai_events_type_idx
  on ai_events (event_type);

-- ─────────────────────────────────────────────────────────────────────────────
-- Arrangement plans + user feedback (intelligence loop)
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists arrangement_plans (
  id uuid primary key default uuid_generate_v4(),
  track_id text,
  raga text,
  style text,
  duration_sec numeric,
  source text,
  intent_tags text[],
  constraints jsonb default '{}'::jsonb,
  metrics jsonb default '{}'::jsonb,
  plan jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

create index if not exists arrangement_plans_raga_idx
  on arrangement_plans (raga);

create table if not exists user_feedback (
  id uuid primary key default uuid_generate_v4(),
  plan_id uuid references arrangement_plans(id) on delete set null,
  track_id text,
  rating int,
  feedback text,
  tags text[],
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

create index if not exists user_feedback_plan_idx
  on user_feedback (plan_id);
