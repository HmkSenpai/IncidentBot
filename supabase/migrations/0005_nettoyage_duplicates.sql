-- 0005_dedupe_incidents.sql
-- Nettoyage unique : certains TT ont été insérés plusieurs fois avant que
-- l'upsert par TT ne soit mis en place. On garde la ligne la plus récente
-- (par created_at) de chaque TT et on supprime les doublons plus anciens.

with ranked as (
    select id,
           row_number() over (partition by tt order by created_at desc) as rn
    from public.incidents
    where tt is not null and tt <> ''
)
delete from public.incidents
where id in (select id from ranked where rn > 1);