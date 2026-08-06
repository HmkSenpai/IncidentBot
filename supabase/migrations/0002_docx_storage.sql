-- 0002_docx_storage.sql
-- Deux ajouts pour supporter les "updates" d'incident et le téléchargement
-- des fiches depuis le dashboard :
--
--   1. Bucket de stockage public "fiches" : reçoit les .docx générés.
--      Le dashboard peut alors servir un lien de téléchargement direct
--      (https://<projet>.supabase.co/storage/v1/object/public/fiches/...),
--      SANS dépendre d'un fichier resté sur le PC (source de vérité = Supabase).
--
--   2. Colonnes docx_url / docx_path sur incidents + politique UPDATE.
--      Une même TT traversant NEW → UPDATE... → END est mise à jour en place
--      (pas de doublon de ligne).

-- --- Bucket de stockage des fiches (partagé entre type) --------------------
insert into storage.buckets (id, name, public)
values ('fiches', 'fiches', true)
on conflict (id) do nothing;

-- Ensembles de politiques de stockage (RLS storage actif sur les objets).
create policy "fiches_public_read" on storage.objects
  for select using (bucket_id = 'fiches');
create policy "fiches_public_insert" on storage.objects
  for insert with check (bucket_id = 'fiches');

-- --- Colonnes de lien vers la fiche --------------------------------------------
alter table public.incidents add column if not exists docx_url text;
alter table public.incidents add column if not exists docx_path text;

-- --- Autoriser la MAJ (update) d'une ligne existante depuis le pipeline -------
create policy "incidents_update_all" on public.incidents
  for update using (true) with check (true);