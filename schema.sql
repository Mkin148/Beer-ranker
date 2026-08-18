-- Beer Ranker schema for Supabase (Postgres).
-- Paste into the Supabase SQL editor and run once.

create table if not exists beers (
    id          bigint generated always as identity primary key,
    name        text not null,
    style       text,
    origin      text,
    abv         real,
    description text,
    photo_url   text,
    created_at  timestamptz not null default now()
);

create table if not exists ratings (
    id           bigint generated always as identity primary key,
    beer_id      bigint not null references beers(id) on delete cascade,
    taster_email text not null,
    taster_name  text,
    packaging    real,
    look         real,
    smell        real,
    taste        real,
    drinkability real,
    notes        text,
    created_at   timestamptz not null default now(),
    unique (beer_id, taster_email)   -- one rating per taster per beer (upsert)
);

-- Lock the tables down. The app connects with the service_role key from
-- server-side secrets, which BYPASSES row-level security. Enabling RLS with no
-- policies means the public anon key can't read or write anything.
alter table beers   enable row level security;
alter table ratings enable row level security;
