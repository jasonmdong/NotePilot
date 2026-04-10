create extension if not exists pgcrypto;

create table if not exists public.app_users (
  id uuid primary key default gen_random_uuid(),
  username text not null unique,
  password_hash text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.app_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.app_users(id) on delete cascade,
  token_hash text not null unique,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

update public.scores
set created_at = now()
where created_at is null;

alter table public.scores
  alter column id set default gen_random_uuid();

alter table public.scores
  alter column created_at set default now();

alter table public.scores
  alter column created_at set not null;

alter table public.scores
  alter column user_id drop default;

alter table public.scores
  drop constraint if exists scores_user_id_fkey;

alter table public.scores
  add constraint scores_user_id_fkey
  foreign key (user_id) references public.app_users(id) on delete cascade;

create unique index if not exists scores_user_slug_idx
  on public.scores (user_id, slug);
