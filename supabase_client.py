"""
supabase_client.py
Branche le pipeline IncidentBot vers Supabase : pousse un incident généré
(parser + fiche) dans la table `public.incidents` du projet configuré dans
.env.local.

Par design, cet accès est OPTIONNEL et non bloquant :
  - si SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY sont absents -> renvoie False
  - si Supabase est injoignable ou renvoie une erreur -> log et renvoie False
La génération des fiches .docx ne doit JAMAIS dépendre du succès de cet
insert (même philosophie que l'envoi WhatsApp dans whatsapp.py).
"""

import os
import re
import sys

# Le client supabase-py est une dépendance optionnelle : si elle n'est pas
# installée, le reste du pipeline (generator, whatsapp) continue de
# fonctionner sans lui.
try:
    from supabase import create_client, ClientOptions
    _SUPABASE_IMPORTABLE = True
except Exception:
    _SUPABASE_IMPORTABLE = False

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Valeurs "vide" côté fiche : on préfère laisser la colonne à NULL que
# stocker un placeholder qui pollue les stats du dashboard.
_EMPTY_PLACEHOLDERS = {"", "A déterminer", "En attente", "En cours",
                       "Investigation en cours", "Non renseignée"}

_client_cache = None


def _load_dotenv_local():
    """Recharge SUPABASE_* depuis .env.local de façon idempotente."""
    path = os.path.join(_PROJECT_DIR, ".env.local")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_client():
    """Retourne un client Supabase configuré, ou None si indisponible."""
    global _client_cache
    if _client_cache is not None:
        return _client_cache

    if not _SUPABASE_IMPORTABLE:
        return None

    _load_dotenv_local()
    url = os.environ.get("SUPABASE_URL", "").strip() or \
        os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip() or \
        os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "").strip()

    if not url or not key:
        print("[supabase_client] SUPABASE_URL ou clé manquante - stockage "
              "Supabase désactivé.", file=sys.stderr)
        return None

    try:
        _client_cache = create_client(
            url, key,
            options=ClientOptions(postgrest_client_timeout=10),
        )
    except Exception as e:
        print(f"[supabase_client] Impossible de créer le client Supabase ({e}).",
              file=sys.stderr)
        _client_cache = None
    return _client_cache


def _parse_commentaires(commentaires):
    """Normalise la liste de commentaires pour le JSONB (robuste si None)."""
    if not commentaires:
        return []
    out = []
    for c in commentaires:
        if isinstance(c, dict):
            out.append({"date": c.get("date"), "text": c.get("text")})
        elif isinstance(c, str):
            out.append({"date": None, "text": c})
    return out


def _build_row(incident, fiche, docx_name, raw_message, docx_url=None, docx_path=None):
    row = {
        # champs bruts (parser.py)
        "tt": incident.get("tt"),
        "etat": incident.get("etat"),
        "is_end": bool(incident.get("is_end")),
        "debut": incident.get("debut"),
        "recu": incident.get("recu"),
        "fin": incident.get("fin"),
        "description": incident.get("description"),
        "impact": incident.get("impact"),
        "cause": incident.get("cause"),
        "actions_menee": incident.get("actions_menee"),
        "priorite": incident.get("priorite"),
        "porteur": incident.get("porteur"),
        "rfo": incident.get("rfo"),
        "commentaires": _parse_commentaires(incident.get("commentaires")),
        # méta
        "docx_name": docx_name,
        "raw_message": raw_message or "",
    }

    # lien de téléchargement de la fiche .docx (bucket "fiches")
    if docx_url:
        row["docx_url"] = docx_url
    if docx_path:
        row["docx_path"] = docx_path

    # champs mappés (fiche) -> colonnes de la table
    if fiche:
        mapping = {
            "ETABLISSEMENT": "etablissement",
            "SITE": "site",
            "LOCALISATION": "localisation",
            "DATE_INCIDENT": "date_incident",
            "DATE_INFORMATION": "date_information",
            "DATE_DEPART_TERRAIN": "date_depart_terrain",
            "CLIENTS_IMPACTES": "clients_impactes",
            "DESCRIPTION_TRAVAUX": "description_travaux",
            "DATE_DEBUT_INTERVENTION": "date_debut_intervention",
            "DATE_RETABLISSEMENT": "date_retablissement",
            "DATE_FIN_INTERVENTION": "date_fin_intervention",
            "OBSERVATIONS": "observations",
            "EQUIPE_INTERVENTION": "equipe_intervention",
        }
        for fiche_key, col in mapping.items():
            val = (fiche.get(fiche_key) or "").strip()
            if val and val not in _EMPTY_PLACEHOLDERS:
                row[col] = val

    return row


def upload_docx(client, local_path: str, docx_name: str):
    """Upload un .docx généré dans le bucket public 'fiches'.
    Retourne (docx_url, docx_path) ou (None, None) en cas d'échec.
    N'échoue jamais : un échec ici signifie juste que la fiche n'aura pas
    de lien de téléchargement côté dashboard.

    Le nom stocké est sanitizé (espaces et caractères non-URL -> '_') :
    les chemins avec espaces font échouer le contrôle RLS de Supabase
    Storage sur `bucket_id` (comparaison sur le chemin encodé)."""
    storage_name = re.sub(r"[^A-Za-z0-9_.\-]+", "_", docx_name)
    try:
        with open(local_path, "rb") as f:
            content = f.read()
    except OSError as e:
        print(f"[supabase_client] Impossible de lire le docx local ({e}).",
              file=sys.stderr)
        return None, None

    if not content:
        return None, None

    try:
        # "upsert": "true" écrase une fiche déjà présente (cas d'un UPDATE).
        # Nécessite une policy UPDATE (using + with check) sur storage.objects,
        # fournie par les migrations 0002/0003/0004.
        client.storage.from_("fiches").upload(
            storage_name, content,
            {"content-type":
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             "upsert": "true"},
        )
    except Exception as e:
        print(f"[supabase_client] Échec de l'upload de la fiche ({e}).",
              file=sys.stderr)
        return None, None

    url = os.environ.get("SUPABASE_URL", "").strip() or \
        os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").strip()
    url = url.rstrip("/")
    docx_path = f"fiches/{storage_name}"
    docx_url = f"{url}/storage/v1/object/public/{docx_path}"
    print(f"[supabase_client] Fiche téléversée : {docx_url}", file=sys.stderr)
    return docx_url, docx_path


def fetch_incident_by_tt(client, tt: str):
    """Retourne la ligne Supabase d'une TT donnée, ou None si absente.
    La TT est l'identité d'un incident (NEW -> UPDATE... -> END)."""
    if not tt:
        return None
    try:
        res = client.table("incidents").select("id, etat, is_end").eq("tt", tt).limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        print(f"[supabase_client] Échec de la lecture par TT ({tt}) : {e}",
              file=sys.stderr)
        return None


def upsert_incident(incident: dict, fiche: dict = None,
                    docx_name: str = None, raw_message: str = "",
                    docx_path_local: str = None):
    """
    Insère OU met à jour un incident dans Supabase, selon sa TT.
    Retourne True si *tentée* (pas nécessairement réussie), False si
    désactivé / échec. N'échoue jamais.

    Une TT qui revient (UPDATE 01, UPDATE 02, ... END) met à jour la ligne
    existante au lieu d'en créer une nouvelle : la TT est l'identité.
    """
    client = get_client()
    if client is None:
        return False

    docx_url = docx_path = None
    if docx_path_local and docx_name:
        docx_url, docx_path = upload_docx(client, docx_path_local, docx_name)

    row = _build_row(incident, fiche, docx_name, raw_message,
                     docx_url=docx_url, docx_path=docx_path)

    try:
        existing = fetch_incident_by_tt(client, incident.get("tt"))
        if existing:
            client.table("incidents").update(row).eq("id", existing["id"]).execute()
            print(f"[supabase_client] Incident mis à jour (TT {row.get('tt')}).",
                  file=sys.stderr)
            return True
        client.table("incidents").insert(row).execute()
        print(f"[supabase_client] Incident inséré (TT {row.get('tt')}).",
              file=sys.stderr)
        return True
    except Exception as e:
        print(f"[supabase_client] Échec de l'écriture Supabase ({e}). "
              f"La fiche reste disponible localement.", file=sys.stderr)
        return False


def insert_incident(incident: dict, fiche: dict = None,
                    docx_name: str = None, raw_message: str = "",
                    docx_path_local: str = None):
    """Alias rétrocompatible vers upsert_incident()."""
    return upsert_incident(incident, fiche, docx_name, raw_message,
                           docx_path_local=docx_path_local)


if __name__ == "__main__":
    # Smoke test minimal : juste vérifier que l'import / le client se crée.
    c = get_client()
    print("Client Supabase:", "OK" if c is not None else "indisponible")