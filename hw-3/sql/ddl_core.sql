-- Базовая схема: staging (как в CSV) и dds (матчи и факт ударов, исходный вариант без доп. индексов).
set client_min_messages = warning;
-- Одна строка факта = один удар (событие Shot), ключ (source_system, event_id), как в ДЗ-2.
-- Даты - календарная дата матча (match_date, без часового пояса), xG безразмерна: вероятность гола [0; 1].

create schema if not exists stage;
create schema if not exists dds;

drop table if exists stage.shots;
drop table if exists stage.matches;

create table stage.matches (
    match_id         bigint,
    match_date       date,
    competition_id   int,
    competition_name text,
    season_id        int,
    season_name      text,
    stage_name       text,
    home_team_id     bigint,
    home_team_name   text,
    away_team_id     bigint,
    away_team_name   text,
    home_score       int,
    away_score       int,
    last_updated     timestamp
);

create table stage.shots (
    row_no        bigint generated always as identity,   -- порядок строк в файле
    source_system text,
    event_id      uuid,
    match_id      bigint,
    match_date    date,
    team_id       bigint,
    team_name     text,
    player_id     bigint,
    player_name   text,
    period        smallint,
    minute        smallint,
    second        smallint,
    shot_type     text,
    outcome       text,
    body_part     text,
    xg            numeric(12, 10)
);

drop table if exists dds.fact_shot;
drop table if exists dds.match;

create table dds.match (
    source_system    text   not null,
    match_id         bigint not null,
    match_date       date   not null,
    competition_id   int    not null,
    competition_name text   not null,
    season_id        int    not null,
    season_name      text   not null,
    stage_name       text   not null,
    home_team_id     bigint not null,
    home_team_name   text   not null,
    away_team_id     bigint not null,
    away_team_name   text   not null,
    home_score       int    not null,
    away_score       int    not null,
    primary key (source_system, match_id)
);

create table dds.fact_shot (
    match_date    date          not null,
    source_system text          not null,
    event_id      uuid          not null,
    match_id      bigint        not null,
    team_id       bigint        not null,
    player_id     bigint        not null,
    period        smallint      not null check (period between 1 and 5),
    minute        smallint      not null,
    second        smallint      not null,
    shot_type     text          not null,
    outcome       text          not null,
    is_shootout   boolean       not null,   -- серия пенальти (period = 5), в витрину не попадает
    is_penalty    boolean       not null,
    is_on_target  boolean       not null,   -- Goal, Saved, Saved to Post
    is_goal       boolean       not null,
    xg            numeric(12, 10) not null check (xg between 0 and 1),
    primary key (source_system, event_id),
    foreign key (source_system, match_id) references dds.match (source_system, match_id)
);
