# IncidentBot CAMTEL

Automatisation de la **« Fiche de Relevé des Incidents sur le Mobile »** de CAMTEL :
le bot écoute un groupe WhatsApp, détecte les messages d'incident, remplit
automatiquement une fiche Word à partir d'un template figé, la renvoie sur
WhatsApp **et** la stocke dans Supabase — zéro copier/coller manuel.

Un **tableau de bord web** (Next.js) affiche l'historique en temps réel et
permet de télécharger chaque fiche générée.

## ✨ Fonctionnalités

- **Détection automatique** des messages d'incident dans un groupe WhatsApp
  (via Baileys, pas d'API officielle) — ignore le bruit du groupe
  (« Bien reçu », discussions…).
- **Extraction déterministe** des champs (TT, site, cause, impact, commentaires,
  états `NEW` / `UPDATE xx` / `END`…) par parsing regex.
- **Génération de la fiche Word** à partir du template officiel CAMTEL
  (placeholders `{{...}}`), avec polish IA **optionnel** (DeepSeek / OpenRouter).
- **Déduplication par TT** : `NEW` → `UPDATE…` → `END` met à jour la même ligne.
- **Stockage Supabase** (table `public.incidents`) + upload de chaque `.docx`
  dans le bucket Storage `fiches`.
- **Dashboard web en direct** : statistiques, filtres par état, modale de
  détail (`raw_message` + téléchargement de la fiche), rafraîchissement
  automatique (polling), crédits auteur.

## 🏗️ Architecture

```
WhatsApp (groupe incidents)
        │
        ▼
whatsapp-bot/bot.js   (Node + Baileys — connexion WhatsApp, envoi des fiches)
        │  POST /webhook (localhost:5000)
        ▼
whatsapp.py           (Python stdlib — filtre par groupe, déclenche la génération)
        │
        ▼
generator.py          (parsing + mapping + remplissage docx + polish IA optionnel)
        │
        ├─► output/*.docx ─────────► whatsapp-bot/bot.js ──► renvoi sur WhatsApp
        │
        └─► supabase_client.py ───► Supabase (table incidents + bucket fiches)
                                          ▲
                                          │
dashboard/ (Next.js) ◄── polling 6 s ◄────┘   liste + téléchargement des fiches
```

## 📁 Structure du repo

```
IncidentBot/
├── AGENT.md                    documentation de contexte (à lire avant toute modif)
├── LICENSE                     MIT © Hmksenpai 2026
├── parser.py                   extraction regex des messages → JSON
├── generator.py                mapping JSON → champs fiche + remplissage docx
├── whatsapp.py                 serveur webhook local (reçoit depuis bot.js)
├── whatsapp-bot/               le bot WhatsApp (Baileys) — bot.js + auth_info/
├── supabase_client.py          insertion + upload des fiches dans Supabase
├── supabase/migrations/        schéma SQL de la table `public.incidents`
├── templates/                  template Word officiel (fiche_template.docx)
├── incidents/                  jeu de données de test (messages réels)
└── dashboard/                  app Next.js 16 (Tableau de bord en direct)
```

## 🚀 Démarrage

### 1. Backend (génération + webhook)

```bash
pip install -r requirements.txt   # si présent, sinon zéro dépendance Python requise
cp env.example .env.local         # puis remplir les variables
python whatsapp.py                # écoute sur :5000
```

### 2. Bot WhatsApp

```bash
cd whatsapp-bot
npm install
npm start                         # scanner le QR au premier lancement
```

### 3. Dashboard web

```bash
cd dashboard
npm install
cp .env.example .env.local        # projet Supabase d'IncidentBot
npm run dev                       # http://localhost:3000
```

> ⚠️ **Vercel** : le dashboard vit dans le sous-dossier `dashboard/` → régler
> **Root Directory = `dashboard/`** et définir les variables dans
> Settings → Environment Variables (Vercel n'utilise pas `.env.local`).

## 🔐 Configuration

Copier `env.example` en `.env.local` (racine) :

| Variable | Usage |
|---|---|
| `TARGET_GROUP_JID` | JID du groupe WhatsApp source des incidents |
| `REPORT_TARGET_JID` | Destinataire des fiches (généralement soi-même) |
| `WEBHOOK_PORT` / `SEND_PORT` | Ports webhook (5000) et envoi de documents (5001) |
| `DEEPSEEK_API_KEY` / `OPENROUTER_API_KEY` | Polish IA optionnel (l'un ou l'autre) |
| `NEXT_PUBLIC_SUPABASE_URL` | URL du projet Supabase |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Clé anon (publique) |
| `SUPABASE_SERVICE_ROLE_KEY` | Clé `service_role` — **serveur uniquement** |

## 🗄️ Base de données

Les migrations SQL sont dans `supabase/migrations/`. La table `public.incidents`
doit exister pour que le dashboard fonctionne ; les politiques RLS couvrent
select / insert / update / delete (table et bucket Storage `fiches`).

## ⚠️ Avertissements

- **Risque de ban WhatsApp** : Baileys est un client non officiel. Usage à
  risque faible (lecture d'un groupe + envoi occasionnel à soi-même) mais pas
  nul — détails dans `AGENT.md` §3.
- **Ne jamais committer** `.env.local`, `whatsapp-bot/auth_info/`, `creds.json`
  (déjà couverts par `.gitignore`).
- Les secrets (`NEXT_PUBLIC_*`, `service_role`) restent côté serveur : le
  dashboard lit via Server Components et l'endpoint `/api/incidents`.

## 📄 Licence

MIT © Hmksenpai 2026 — voir [LICENSE](LICENSE).
