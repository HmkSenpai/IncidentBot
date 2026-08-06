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
        print("[supabase_client] SUPABASE_URL ou clé manquante — stockage "
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


def _build_row(incident, fiche, docx_name, raw_message):
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


def insert_incident(incident: dict, fiche: dict = None,
                    docx_name: str = None, raw_message: str = ""):
    """
    Insère un incident dans Supabase. Retourne True si *tentée* (pas
    nécessairement réussie), False si désactivé / échec. N'échoue jamais.
    """
    client = get_client()
    if client is None:
        return False

    row = _build_row(incident, fiche, docx_name, raw_message)
    try:
        client.table("incidents").insert(row).execute()
        print(f"[supabase_client] Incident inséré (TT {row.get('tt')}).",
              file=sys.stderr)
        return True
    except Exception as e:
        print(f"[supabase_client] Échec de l'insertion Supabase ({e}). "
              f"La fiche reste disponible localement.", file=sys.stderr)
        return False


if __name__ == "__main__":
    # Smoke test minimal : juste vérifier que l'import / le client se crée.
    c = get_client()
    print("Client Supabase:", "OK" if c is not None else "indisponible")