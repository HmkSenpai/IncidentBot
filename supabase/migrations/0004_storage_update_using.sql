-- 0004_storage_update_using.sql
-- Corrige la policy UPDATE du bucket "fiches".
-- Pour écraser (upsert/overwrite) un objet déjà présent, Supabase Storage
-- évalue la policy UPDATE avec une clause `using` (ligne existante) ET une
-- `with check` (ligne écrite). La policy 0003 ne fournissait que `with check`,
-- d'où un 403 "violates row-level security policy" à l'écrasement.

drop policy if exists "fiches_public_update" on storage.objects;

create policy "fiches_public_update" on storage.objects
  for update
  using (bucket_id = 'fiches')
  with check (bucket_id = 'fiches');