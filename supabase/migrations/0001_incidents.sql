-- 0001_incidents.sql
-- Table "incidents" : stocke chaque incident CAMTEL reçu depuis WhatsApp.
--
-- Deux groupes de colonnes, alignés sur le pipeline Python :
--   1) champs bruts extraits par parser.parse_incident()
--   2) champs mappés pour la fiche par generator.map_incident_to_fiche()
--
-- RLS activé mais ouvert pour l'instant (mono-utilisateur, clé service_role
-- utilisée côté pipeline). À resserrer le jour où l'on branche l'auth.

create extension if not exists pgcrypto;

create table public.incidents (
    id              uuid primary key default gen_random_uuid(),

    -- --- champs bruts (parser.py) -------------------------------------
    tt              text,
    etat            text,        -- NEW / UPDATE 01 / END ...
    is_end          boolean not null default false,
    debut           text,
    recu            text,
    fin             text,
    description     text,
    impact          text,
    cause           text,
    actions_menee   text,
    priorite        text,
    porteur         text,
    rfo             text,
    commentaires    jsonb not null default '[]'::jsonb,  -- [{date, text}, ...]

    -- --- champs mappés (fiche) -----------------------------------------
    etablissement           text,
    site                    text,
    localisation            text,
    date_incident           text,
    date_information        text,
    date_depart_terrain     text,
    clients_impactes        text,
    description_travaux     text,
    date_debut_intervention text,
    date_retablissement     text,
    date_fin_intervention   text,
    observations            text,
    equipe_intervention     text,

    -- --- méta ----------------------------------------------------------
    raw_message     text,                       -- message WhatsApp source complet
    docx_name       text,                       -- nom du fichier .docx généré
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- Index utiles pour tri/filtres du futur dashboard
create index incidents_created_at_idx   on public.incidents (created_at);
create index incidents_site_idx         on public.incidents (site);
create index incidents_is_end_idx       on public.incidents (is_end);
create index incidents_debut_idx        on public.incidents (debut);
create index incidents_tt_idx           on public.incidents (tt);

-- RLS
alter table public.incidents enable row level security;

-- Policies : lecture+insert autorisées. Dev mono-utilisateur (service_role
-- ignore RLS, mais on garde une policy "authenticated" pour le futur dashboard).
create policy "incidents_select_all" on public.incidents
    for select using (true);
create policy "incidents_insert_all" on public.incidents
    for insert with check (true);