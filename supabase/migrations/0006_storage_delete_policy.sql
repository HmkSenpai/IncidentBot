-- 0006_storage_delete_and_table_policies.sql
-- 1) Policy DELETE sur storage.objects (bucket "fiches") pour permettre le
--    remplacement propre des fiches (suppression de l'ancienne puis upload).
-- 2) Policy DELETE sur public.incidents pour un éventuel nettoyage.

create policy "fiches_public_delete" on storage.objects
  for delete using (bucket_id = 'fiches');

create policy "incidents_delete_all" on public.incidents
  for delete using (true);