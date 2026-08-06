-- 0003_storage_update_policy.sql
-- Rattrape : l'écrasement (upsert:true) d'une fiche déjà présente dans le
-- bucket "fiches" exige une policy UPDATE sur storage.objects.
-- Sans elle, la régénération d'une fiche (cas UPDATE d'incident) échoue
-- avec un 403 "violates row-level security policy".

create policy "fiches_public_update" on storage.objects
  for update with check (bucket_id = 'fiches');