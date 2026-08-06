# AGENT.md — IncidentBot CAMTEL

Documentation de contexte pour tout agent IA (Claude Code, Cursor, etc.) qui
reprendrait ce projet. Lis ce fichier en entier avant de modifier quoi que ce
soit — plusieurs décisions ne sont pas évidentes en lisant juste le code.

## 1. Objectif du projet

Automatiser le remplissage de la "Fiche de Relevé des Incidents sur le
Mobile" de CAMTEL (Yaoundé, Cameroun), remplie manuellement par l'auteur
(stagiaire) à chaque incident réseau signalé sur un groupe WhatsApp interne.

**Contrainte fondatrice : zéro copier/coller manuel.** Le pipeline doit
détecter automatiquement les nouveaux messages d'incident dans le groupe
WhatsApp, ignorer le bruit ("Bien reçu", discussions...), extraire les
champs, remplir un document Word à partir d'un template figé, et renvoyer
la fiche générée — sans intervention humaine.

**Vision à moyen terme (pas encore commencée) :** transformer ce script
personnel en une vraie petite plateforme (dashboard web, base de données
Supabase, historique des incidents, multi-utilisateurs). Tout ce qui suit
décrit l'état "MVP script local" actuel, qui doit rester fonctionnel
pendant la migration.

## 2. Architecture actuelle

```
WhatsApp (groupe incidents)
        │
        ▼
whatsapp-bot/bot.js  (Node.js + Baileys — connexion WhatsApp Web directe,
        │             PAS d'API officielle, PAS de Docker)
        │  POST http://localhost:5000/webhook
        ▼
whatsapp.py  (Python stdlib, serveur HTTP local — filtre par groupe,
        │     déclenche la génération)
        │  appelle generator.generate_from_block(text)
        ▼
generator.py  (parsing + mapping + remplissage docx + polish IA optionnel)
        │  utilise parser.py (regex, extraction déterministe)
        │  utilise templates/fiche_template.docx (placeholders {{...}})
        ▼
output/*.docx  (une fiche par incident)
        │
        │  POST http://localhost:5001/send-document
        ▼
whatsapp-bot/bot.js  (même process Node, renvoie le .docx sur WhatsApp
                       vers REPORT_TARGET_JID — généralement soi-même)
```

**Pourquoi cette architecture et pas Evolution API / Docker :**
On a commencé avec Evolution API (Docker + Postgres + Redis), qui a causé
une boucle infinie de reconnexion (bug connu, voir issue GitHub
EvolutionAPI/evolution-api#2437) et a fait crasher la machine par
surconsommation de ressources. Evolution API est conçu pour du multi-tenant
SaaS — complètement surdimensionné pour un seul utilisateur/une seule
instance. On est descendu directement sur **Baileys**, la librairie que
Evolution API utilise en interne, sans toute la couche infra autour. Plus
léger, zéro Docker, session persistée localement dans `auth_info/`.

## 3. ⚠️ Risque de ban WhatsApp — À NE PAS OUBLIER

Baileys est un client **non officiel** (reverse-engineering du protocole
WhatsApp Web). Ce n'est PAS l'API Business officielle de Meta.

- Le risque de ban existe **dès la connexion**, pas seulement à l'envoi.
- Si le compte est banni via un client non-officiel, c'est généralement
  **permanent** (taux de succès des appels ~2%).
- Le profil de risque actuel (lecture d'un groupe + envoi occasionnel à
  soi-même, faible volume, pas d'inconnus contactés) est dans la catégorie
  "usage personnel à faible risque", mais **pas risque zéro**.
- Décision prise avec l'utilisateur (stagiaire) : accepter ce risque sur son
  numéro personnel pour l'instant. Si ça devient un vrai problème, deux
  options de repli déjà identifiées :
  1. Utiliser une carte SIM dédiée/secondaire pour le bot
  2. Garder Baileys uniquement en lecture, basculer l'envoi de fiches vers
     Telegram (API officielle, zéro risque)
- **Ne pas** ajouter de fonctionnalités qui augmentent le volume de messages
  envoyés ou qui contactent des numéros inconnus sans en discuter d'abord
  avec l'utilisateur — ça change le profil de risque.

## 4. Fichiers du projet

```
IncidentBot/
├── AGENT.md                    ce fichier
├── parser.py                   extraction regex des messages bruts → JSON
├── generator.py                mapping JSON → champs fiche + remplissage docx
├── whatsapp.py                 serveur webhook local (reçoit depuis bot.js)
├── .env.local                  secrets/config (JAMAIS commité, voir §6)
├── templates/
│   └── fiche_template.docx     template Word avec placeholders {{CLE}}
├── incidents/
│   └── incidents.txt           jeu de données de test (12 incidents réels)
├── output/                     fiches .docx générées (créé au runtime)
├── whatsapp-bot/                le bot WhatsApp (Baileys) — anciennement evolution-api/
│   ├── package.json
│   ├── bot.js                  — connexion WhatsApp (Baileys) + envoi de docs
│   └── auth_info/              session WhatsApp persistée (JAMAIS commité)
├── supabase_client.py           insertion optionnelle des incidents dans Supabase
└── supabase/
    └── migrations/
        └── 0001_incidents.sql  schéma de la table `public.incidents`
```

## 5. Détail de chaque composant

### 5.1 `parser.py`

Découpe le texte brut en blocs (un par en-tête `Incident GSM/UMTS/LTE/CDMA |
ETAT`) et extrait les champs par regex simple `CLE: valeur`. États rencontrés
dans les vrais messages CAMTEL : `NEW`, `UPDATE 01`, `UPDATE 02`..., `END`.
Seul `END` est traité comme "terminé" (`is_end = True`) ; tout le reste est
traité comme "en cours" avec les mêmes règles de repli.

Champs extraits : `debut`, `recu`, `fin`, `description`, `impact`, `cause`,
`actions_menee`, `tt`, `priorite`, `porteur`, `rfo`, `commentaires` (liste
chronologique `{date, text}`), `etat`, `is_end`.

`is_real_incident(block)` : vrai si le bloc matche l'en-tête `Incident
GSM/UMTS/LTE/CDMA | ...`. Tout le reste ("Bien reçu", discussions...) est
ignoré silencieusement.

### 5.2 `generator.py`

**Mapping des champs (règles métier, à ne pas modifier sans valider avec
l'utilisateur — chaque règle vient d'exemples réels qu'il a fournis) :**

| Champ fiche | Règle |
|---|---|
| `ETABLISSEMENT` | Extrait de `PORTEUR`. `CMRF / CTT X` ou `CTT X` → `CTT X`. `CMRF X` (sans CTT) → `CTT X`. |
| `SITE` | Extrait de `DESCRIPTION` (format `CODE_NOM[_MARQUEUR] DOWN`). On retire `DOWN`, on retire le code du 1er segment, on retire un marqueur technique connu en fin (`IHS`, `CRTV` — liste dans `KNOWN_SITE_SUFFIXES`, à étendre si de nouveaux marqueurs apparaissent). |
| `LOCALISATION` | La `DESCRIPTION` brute, telle quelle (pas la version nettoyée du SITE). |
| `DATE_INCIDENT` / `DATE_INFORMATION` | `DEBUT` / `REÇU` directement. |
| `DATE_DEPART_TERRAIN` | Toujours `"En attente"` (jamais dispo dans les messages sources). |
| `CAUSE` | Si `END` : champ `CAUSE` brut, sinon `"A déterminer"`. Si pas `END` : toujours `"Investigation en cours"` (choix strict, voir note ci-dessous). |
| `CLIENTS_IMPACTES` | Champ `IMPACT` directement. |
| `DESCRIPTION_TRAVAUX` | Si pas `END` : `"Investigation en cours"`. Si `END` : `ACTIONS_MENEE` + dernier commentaire (si différent), avec polish IA optionnel (§5.2.1). |
| `DATE_DEBUT_INTERVENTION` | Toujours `"Non renseignée"` (jamais fiable dans les commentaires bruts). |
| `DATE_RETABLISSEMENT` / `DATE_FIN_INTERVENTION` | `FIN` si `END`, sinon `"En cours"`. |
| `OBSERVATIONS` | Si `END` : synthèse de la cause + tous les commentaires, avec polish IA optionnel. Si pas `END` : dernier commentaire tel quel, ou message générique. |
| `EQUIPE_INTERVENTION` | `{ETABLISSEMENT} pour compétences`. |

> **Note sur CAUSE pour les incidents non terminés :** actuellement on
> affiche toujours `"Investigation en cours"`, même si le message source
> contient déjà une cause plausible (ex: `"Coupure d'énergie électrique"`
> sur un `UPDATE`). C'est un choix délibéré pour rester strictement
> déterministe, mais l'utilisateur pourrait vouloir revenir dessus — si un
> futur agent voit cette règle remise en question, c'est le contexte.

#### 5.2.1 Polish IA optionnel (`call_llm` / `polish_with_ai`)

Les champs `DESCRIPTION_TRAVAUX` et `OBSERVATIONS` (uniquement pour les
incidents `END`) peuvent être reformulés par un LLM externe pour un rendu
plus professionnel (le texte source est parfois TOUT EN MAJUSCULES, sans
ponctuation soignée). **Entièrement optionnel** : si aucune clé API n'est
configurée, le script utilise une version déterministe (concaténation +
capitalisation basique) — zéro dépendance externe obligatoire.

Fournisseurs supportés, abstraction dans `PROVIDERS` (dict) :
- **DeepSeek** (`DEEPSEEK_API_KEY`) — payant mais très bon marché
- **OpenRouter** (`OPENROUTER_API_KEY`) — permet des modèles gratuits
  (`:free`), catalogue changeant, vérifier le slug exact sur
  openrouter.ai/models avant de configurer `OPENROUTER_MODEL`

Sélection auto via `get_active_provider()` : `AI_PROVIDER` si forcé, sinon
première clé trouvée. En cas d'échec réseau/timeout/réponse vide (fréquent
avec les modèles "reasoning" gratuits qui consomment leur budget de tokens
en réflexion interne sans laisser de place à la réponse), repli automatique
sur la version déterministe — **ne doit jamais faire planter la
génération**.

### 5.3 `templates/fiche_template.docx`

**Ne jamais régénérer ce fichier depuis zéro.** Il a été construit à partir
d'une vraie fiche remplie fournie par l'utilisateur (mise en forme Word
exacte : polices, tableau d'en-tête, pied de page CAMTEL), avec uniquement
les valeurs remplacées par des placeholders `{{CLE}}` dans `word/document.xml`
(en éditant le XML directement après `unzip`, pas via python-docx qui aurait
pu introduire des différences de rendu). Validé par comparaison XML avec
l'original (`validate.py --original`) et rendu visuel LibreOffice → aucune
différence de mise en forme.

Placeholders présents : `ETABLISSEMENT`, `SITE`, `DATE_INCIDENT`,
`DATE_INFORMATION`, `DATE_DEPART_TERRAIN`, `LOCALISATION`, `CAUSE`,
`CLIENTS_IMPACTES`, `DESCRIPTION_TRAVAUX`, `DATE_DEBUT_INTERVENTION`,
`DATE_RETABLISSEMENT`, `DATE_FIN_INTERVENTION`, `OBSERVATIONS`,
`EQUIPE_INTERVENTION`.

`fill_template()` dans `generator.py` fait un simple remplacement texte
`{{CLE}}` → valeur (échappée XML) dans `word/document.xml`, puis re-zippe.
Si on ajoute un nouveau champ un jour, il faut l'ajouter au template ET au
dict retourné par `map_incident_to_fiche()`.

### 5.4 `whatsapp.py`

Serveur HTTP stdlib (pas de Flask, volontairement zéro dépendance) qui
écoute sur `WEBHOOK_PORT` (défaut 5000). Reçoit les évènements de `bot.js`,
filtre par `TARGET_GROUP_JID`, ignore les messages `fromMe`, appelle
`generator.generate_from_block()`, puis si une fiche a été générée,
`send_document_to_whatsapp()` pour la renvoyer via `bot.js`.

**Mode debug intégré :** si `TARGET_GROUP_JID` n'est pas configuré, chaque
message reçu (y compris les vôtres) affiche son JID + nom de groupe + aperçu
du texte dans la console — sert à identifier le bon groupe avant de figer la
config. Ne pas retirer ce comportement, il a été ajouté exprès après une
itération où l'utilisateur avait plusieurs groupes candidats.

### 5.5 `bot.js` (dans `whatsapp-bot/`)

Connexion Baileys (`useMultiFileAuthState`, session dans `auth_info/`). Au
premier lancement, affiche un QR code ASCII dans le terminal à scanner.
Reconnexion automatique sauf si `loggedOut`.

Deux rôles dans le même process :
1. **Écoute** (`messages.upsert`) → POST vers `whatsapp.py` (`WEBHOOK_URL`,
   défaut `http://localhost:5000/webhook`), avec le nom du groupe résolu
   via `sock.groupMetadata()` (mis en cache dans `groupNameCache`).
2. **Serveur d'envoi** (`startSendServer`, démarré une seule fois à la
   connexion) : écoute sur `SEND_PORT` (défaut 5001), route
   `POST /send-document`, envoie un document WhatsApp via
   `sock.sendMessage(jid, {document, fileName, mimetype, caption})`.

### 5.6 Note historique `evolution-api/`

L'ancienne piste "E volution API" (Docker + Postgres + Redis) a été **abandonnée**
et le dossier a depuis été renommé/absorbé dans `whatsapp-bot/`. Ne pas recréer
un dossier `evolution-api/` : le bot Baileys en direct (`whatsapp-bot/bot.js`)
est la solution retenue.

## 6. Configuration (`.env.local`)

Chargé automatiquement par `generator.py` (`load_dotenv()`, stdlib only,
sans écraser des variables déjà exportées dans le shell) — **doit être à la
racine d'`IncidentBot/`**, au même niveau que `generator.py` et
`whatsapp.py`. `whatsapp-bot/bot.js` lit ses propres variables via
`process.env` (pas de `.env.local` séparé pour Node actuellement — à
uniformiser si ça devient pénible).

```env
# --- WhatsApp / filtrage ---
TARGET_GROUP_JID=120363xxxxxxxxxx@g.us    # groupe source des incidents
REPORT_TARGET_JID=2376xxxxxxxx@s.whatsapp.net  # destinataire des fiches (soi-même)
WEBHOOK_PORT=5000                          # whatsapp.py
SEND_PORT=5001                             # bot.js (envoi de documents)

# --- Polish IA (optionnel, l'un OU l'autre) ---
AI_PROVIDER=openrouter                     # force le fournisseur (sinon auto-détecté)
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-v4-flash
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openai/gpt-oss-20b:free   # vérifier le slug exact sur openrouter.ai/models
AI_TIMEOUT_SECONDS=45                      # augmenter si modèles gratuits lents
```

**JAMAIS commiter `.env.local` ni `whatsapp-bot/auth_info/`** (session
WhatsApp) — ajouter les deux à `.gitignore` avant tout `git init`/push, ça
n'a pas encore été fait explicitement.

## 7. Comment lancer le projet (état actuel)

Trois process séparés, dans cet ordre :

```bash
# Terminal 1 — génération/webhook
cd IncidentBot
python3 whatsapp.py

# Terminal 2 — connexion WhatsApp
cd IncidentBot/whatsapp-bot
npm install   # une seule fois
npm start
```

Scanner le QR affiché au premier lancement de `bot.js`. Écrire un message
dans le groupe cible pour vérifier le JID dans les logs de `whatsapp.py`
avant de figer `TARGET_GROUP_JID`.

Test en lot hors WhatsApp (sur le fichier `incidents/incidents.txt`) :
```bash
python3 generator.py incidents/incidents.txt
```

## 8. Roadmap — vision plateforme (EN COURS)

> **Renommage acté :** le dossier du bot s'appelle désormais **`whatsapp-bot/`**
> (plus d'`evolution-api/`). Si un ancien commit/doc parle d'`evolution-api/`,
> lire `whatsapp-bot/`. **Ne pas** recréer de dossier `evolution-api/`.

L'utilisateur veut évoluer vers une vraie plateforme avec **Supabase**.
**Décisions actées avec l'utilisateur :**

- **Base cible = le projet Supabase de `.env.local`** (ref `wkfzvr...`,
  URL `https://wkfzvrrcmznysaqovics.supabase.co`). ⚠️ Attention : certains
  serveurs MCP Supabase pointent sur un AUTRE projet (jeu de matchmaking avec
  tables `users, matches, submissions, matchmaking_queue, friend_requests,
  scenario_templates, challenges`) — ne PAS y créer le schéma incidents.
  Toute migration/schéma doit aller vers le projet `.env.local`
  (`NEXT_PUBLIC_SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`).
- **Ordre de construction : 1) DB + migration `incidents` d'abord ✅ (fait),
  2) dashboard web ensuite (prévu, non fait), 3) auth/storage à réévaluer
  plus tard.**

### 8.1 Fait : schéma + branchement Supabase

- `supabase/migrations/0001_incidents.sql` : crée la table `public.incidents`.
  Colonnes alignées sur `parse_incident()` (champs bruts) + `map_incident_to_fiche()`
  (champs fiche), plus `commentaires` (jsonb), `raw_message`, `docx_name`,
  `created_at`, `updated_at`. RLS activé avec policies select/insert (dev mono-
  utilisateur).
- `supabase_client.py` : wrapper `insert_incident(incident, fiche, docx_name,
  raw_message)` utilisant le client officiel `supabase` (supabase-py). **Jamais
  bloquant** : si `SUPABASE_URL`/clé manque ou si le réseau échoue, il log et
  renvoie `False` — la génération `.docx` et l'envoi WhatsApp continuent.
- Branché dans :
  - `whatsapp.py` : l'insert est déclenché après `generate_from_block()` quand
    une fiche est produite.
  - `generator.generate_from_block()` : insère aussi en mode batch
    (`generator.py incidents/incidents.txt`).
- **Pour appliquer le schéma au projet :** envoie le contenu de
  `supabase/migrations/0001_incidents.sql` via le SQL Editor de la console
  Supabase du projet `wkfzvr...` (ou `supabase db push` avec la CLI pointée
  sur ce projet). Le fichier seul ne s'exécute pas tout seul.

### 8.2 Fait : dashboard web (Next.js)

- **`dashboard/`** — application **Next.js 16.3** (App Router, TypeScript) qui lit
  `public.incidents` et affiche : statistiques (total / terminés / en cours /
  sites distincts), et un tableau de l'historique (TT, site, état, début, fin,
  porteur, cause, date).
- **Sécurité** : les données sont lues via un **Server Component**
  (`lib/incidents.ts` + `lib/supabase.ts`, libellé `server-only`). La clé
  `SUPABASE_SERVICE_ROLE_KEY` reste côté serveur, jamais envoyée au client.
  La page est `force-dynamic` → rendue à chaque requête, pas de pré-render.
- **Config** : `dashboard/.env.local` = copie des variables Supabase du
  `.env.local` racine (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`,
  `SUPABASE_SERVICE_ROLE_KEY`). Voir `dashboard/.env.example`. JAMAI commité.
- **Lancer** : `cd dashboard && npm install && npm run dev` puis ouvrir
  `http://localhost:3000`.

### 8.3 À venir

- **Filters / pagination** sur le tableau (site, date, état) et détail d'un
  incident (commentaires, observations, raw_message).
- **Téléchargement des fiches .docx**.
- **Auth Supabase** si multi-utilisateurs (actuellement mono-utilisateur,
  l'auteur lui-même).
- **Stockage des .docx** : Supabase Storage plutôt que le dossier `output/`
  local, pour survivre aux redémarrages/déploiements.
- **Déduplication** : les messages `UPDATE` / `END` du même incident (`TT`)
  devraient mettre à jour la même ligne plutôt que créer un doublon —
  pas encore traité.
- Réfléchir à si `whatsapp-bot/bot.js` doit tourner sur un serveur distant
  (VPS) plutôt qu'en local pour une vraie plateforme — implique de repenser
  la persistance de `auth_info/` et la stabilité 24/7 de la session
  WhatsApp (voir risques de ban, §3, qui deviennent plus importants avec un
  usage prolongé/continu).

**Méthode éprouvée :** construire une brique à la fois et la valider avant de
passer à la suivante (parser → générateur → WhatsApp → envoi → Supabase →
dashboard).

## 9. Ce qui a déjà été testé et validé

- Parser : 12/12 incidents réels détectés sur `incidents.txt` (états `END`,
  `UPDATE`, `NEW`), 0 faux positif sur les messages de bruit.
- Template : comparaison XML + rendu visuel LibreOffice, mise en forme
  identique à l'original.
- Génération bout en bout : webhook simulé → parsing → mapping → docx →
  (simulation) envoi WhatsApp — chaîne complète fonctionnelle.
- En conditions réelles (vraie session WhatsApp de l'utilisateur) : réception
  des messages du groupe confirmée fonctionnelle par l'utilisateur.
  L'envoi automatique du docx généré n'a pas encore été confirmé en
  conditions réelles au moment de la rédaction de ce fichier — à vérifier
  en premier si un agent reprend le projet ici.
