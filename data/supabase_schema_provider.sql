-- Provider portal schema additions for Supabase
-- Run this in Supabase SQL editor after supabase_schema.sql

create table if not exists providers (
  id uuid primary key default uuid_generate_v4(),
  name text not null,
  email text unique,
  gharana text,
  instruments text[],
  training_lineage text,
  bio text,
  verified boolean default false,
  status text default 'pending',
  created_at timestamptz default now()
);

create index if not exists providers_email_idx
  on providers (email);

create table if not exists provider_uploads (
  id uuid primary key default uuid_generate_v4(),
  provider_id uuid references providers(id) on delete set null,
  raga text not null,
  declared_sa text,
  file_path text,
  original_filename text,
  file_format text,
  duration_sec numeric,
  file_size_mb numeric,
  status text default 'uploaded',
  ai_review jsonb default '{}'::jsonb,
  phrase_count int,
  phrases_approved int,
  avg_authenticity numeric,
  current_gold_avg numeric,
  exceeded_gold_standard boolean default false,
  gold_delta numeric,
  reviewer_notes text,
  created_at timestamptz default now()
);

create index if not exists provider_uploads_provider_idx
  on provider_uploads (provider_id);

create index if not exists provider_uploads_raga_idx
  on provider_uploads (raga);
