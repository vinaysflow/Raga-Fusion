-- Schema patch for Supabase (seeding QA + AI logging + feedback)

alter table if exists recording_assets
  add column if not exists raw_checksum_sha256 text,
  add column if not exists raw_size_mb numeric,
  add column if not exists wav_size_mb numeric,
  add column if not exists ingest_warnings jsonb default '[]'::jsonb;

create table if not exists seeding_reports (
  id uuid primary key default uuid_generate_v4(),
  report_key text unique,
  raga text,
  report jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);
create index if not exists seeding_reports_raga_idx on seeding_reports (raga);

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
create index if not exists ai_events_type_idx on ai_events (event_type);

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
create index if not exists arrangement_plans_raga_idx on arrangement_plans (raga);

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
create index if not exists user_feedback_plan_idx on user_feedback (plan_id);
