# IncidentBot - Dashboard CAMTEL

Tableau de bord web (Next.js + Supabase) de l'application IncidentBot :
consulte l'historique des fiches d'incidents CAMTEL générées automatiquement
depuis WhatsApp et stockées dans la table `public.incidents`.

Affiche des statistiques (total / terminés / en cours / sites), un tableau
filtrable par état (Toutes / Terminés / En cours), une modale de détail
(`raw_message` + téléchargement de la fiche) — et se **rafraîchit en direct**
(polling de `GET /api/incidents` toutes les 6 s, sans recharger la page).

## Lancer en local

```bash
cd dashboard
npm install

# Créez .env.local à partir de .env.example (project Supabase d'IncidentBot)
cp .env.example .env.local

npm run dev      # http://localhost:3000
```

## Variables d'environnement

| Variable | Usage |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | URL du projet Supabase |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Clé anon (publique) |
| `SUPABASE_SERVICE_ROLE_KEY` | Clé service_role - **serveur uniquement**, jamais envoyée au client |

## Prérequis

La table `public.incidents` doit exister (voir `supabase/migrations/` à la
racine du repo). Tant qu'elle n'est pas créée, le dashboard s'affiche mais
avec zéro incident et un avertissement dans les logs.

## Sécurité

Les données sont lues dans des Server Components (`lib/incidents.ts`,
`lib/supabase.ts`, marqués `server-only`) ou via l'endpoint
`/api/incidents` (route serveur `force-dynamic`) qui alimente le polling
client. La clé `service_role` n'est jamais sérialisée dans le bundle client.

## Déploiement Vercel

Le dashboard étant un sous-dossier du repo, régler **Root Directory = `dashboard/`**
(sinon Vercel build à la racine Python → 404) et définir les variables Supabase
dans Settings → Environment Variables (**Vercel n'utilise pas `.env.local`**).