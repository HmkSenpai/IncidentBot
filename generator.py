"""
generator.py
Prend les incidents parsés (parser.py) et génère un document Word par
incident, à partir du template contenant des placeholders {{...}}.

Règles de mapping : voir SKILL.md à la racine du projet.

Usage:
    python3 generator.py incidents/incidents.txt
"""

import os
import re
import sys
import json
import zipfile
import shutil
import urllib.request
import urllib.error
from datetime import datetime

from parser import split_incidents, is_real_incident, parse_incident
import supabase_client  # insertion optionnelle des incidents dans Supabase

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "fiche_template.docx")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

def load_dotenv(filenames=(".env.local", ".env")):
    """Charge les variables d'un fichier .env.local / .env dans os.environ,
    sans écraser une variable déjà définie dans l'environnement (ex: export
    manuel, ou variable définie par le système/CI)."""
    for filename in filenames:
        path = os.path.join(os.path.dirname(__file__), filename)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)


load_dotenv()


# ---------------------------------------------------------------------------
# Polish IA (optionnel) - DeepSeek et/ou OpenRouter, compatibles OpenAI
# ---------------------------------------------------------------------------

AI_TIMEOUT_SECONDS = int(os.environ.get("AI_TIMEOUT_SECONDS", "45"))

PROVIDERS = {
    "deepseek": {
        "url": "https://api.deepseek.com/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "model_env": "DEEPSEEK_MODEL",
        "default_model": "deepseek-v4-flash",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key_env": "OPENROUTER_API_KEY",
        "model_env": "OPENROUTER_MODEL",
        "default_model": "openai/gpt-oss-20b:free",
    },
}


def get_active_provider():
    """Détermine quel fournisseur IA utiliser, d'après AI_PROVIDER ou la
    première clé API trouvée dans l'environnement. Retourne None si aucune
    clé n'est configurée (repli déterministe utilisé partout)."""
    forced = os.environ.get("AI_PROVIDER", "").strip().lower()
    if forced:
        if forced not in PROVIDERS:
            print(f"[polish IA] AI_PROVIDER='{forced}' inconnu (deepseek/openrouter), ignoré.",
                  file=sys.stderr)
        elif os.environ.get(PROVIDERS[forced]["key_env"]):
            return forced
        return None

    for name, cfg in PROVIDERS.items():
        if os.environ.get(cfg["key_env"]):
            return name
    return None


DESCRIPTION_SYSTEM_PROMPT = (
    "Tu décris UNIQUEMENT les travaux effectués lors d'un incident télécom "
    "CAMTEL, à partir des actions et commentaires fournis. Ne garde QUE l'action "
    "de travail réalisée (ex: 'Reprise du support de transmission', 'Epissure des "
    "câbles FO'), en une phrase, sans l'état final du site ni le contexte de "
    "rétablissement (ex: retirer 'BTS UP', 'après le rétablissement du support de "
    "transmission'). Rédige en français professionnel, concis et correct "
    "grammaticalement. N'invente jamais d'information absente du texte source. "
    "Garde les sigles (BTS, CTT, FO, TT, IHS...) en majuscules. Réponds "
    "uniquement avec la phrase, sans préambule ni guillemets."
)

OBSERVATIONS_SYSTEM_PROMPT = (
    "Tu rédiges la section 'Observations' d'une fiche d'incident télécom CAMTEL. "
    "Ne garde QUE l'état final du site après l'intervention (ex: 'BTS UP après le "
    "rétablissement du support de transmission'), en 1 phrase maximum, concise et "
    "professionnelle. N'inclue NI la cause, NI la chronologie, NI les détails des "
    "travaux. Si aucune information d'état final (BTS UP/DOWN, rétabli, etc.) "
    "n'est présente dans le texte source, réponds par une chaîne vide. N'invente "
    "aucune information absente du texte source. Réponds uniquement avec la phrase, "
    "sans préambule ni guillemets."
)


def call_llm(prompt: str, system_prompt: str, max_tokens: int = 300):
    """Appelle le fournisseur IA actif (DeepSeek ou OpenRouter). Retourne None
    si aucune clé n'est configurée, ou en cas d'échec (réseau, quota,
    timeout...) - l'appelant doit alors utiliser un repli."""
    provider = get_active_provider()
    if not provider or not prompt:
        return None

    cfg = PROVIDERS[provider]
    api_key = os.environ.get(cfg["key_env"])
    model = os.environ.get(cfg["model_env"], cfg["default_model"])

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if provider == "openrouter":
        # Recommandé par OpenRouter, sans impact si absent.
        headers["HTTP-Referer"] = "https://camtel.cm"
        headers["X-Title"] = "IncidentBot CAMTEL"

    req = urllib.request.Request(
        cfg["url"],
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=AI_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"].get("content")
        if not content:
            # Certains modèles "reasoning" (gratuits notamment) consomment
            # tout le budget de tokens dans leur raisonnement interne et ne
            # laissent rien pour la réponse finale -> on considère ça comme
            # un échec et on utilisera le repli déterministe.
            finish_reason = body["choices"][0].get("finish_reason", "?")
            print(f"[polish IA] Réponse vide de {provider} (finish_reason={finish_reason}), "
                  f"repli sur la version déterministe. Essayez d'augmenter max_tokens "
                  f"ou AI_TIMEOUT_SECONDS, ou changez de modèle.", file=sys.stderr)
            return None
        return content.strip()
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        print(f"[polish IA] Échec de l'appel {provider} ({e}) - {detail}",
              file=sys.stderr)
        return None
    except (urllib.error.URLError, KeyError, TimeoutError, ValueError) as e:
        print(f"[polish IA] Échec de l'appel {provider}, repli sur la version déterministe ({e})",
              file=sys.stderr)
        return None


def polish_with_ai(prompt: str, system_prompt: str, fallback: str, max_tokens: int = 300) -> str:
    result = call_llm(prompt, system_prompt, max_tokens=max_tokens)
    return result if result else fallback


# ---------------------------------------------------------------------------
# Règles de mapping (SKILL.md)
# ---------------------------------------------------------------------------

def format_sentence(text: str) -> str:
    """Met une majuscule en début de phrase et un point final si besoin."""
    if not text:
        return text
    text = text.strip()
    text = text[0].upper() + text[1:] if text else text
    if not text.endswith((".", "!", "?")):
        text += "."
    return text


def extract_etablissement(porteur):
    if not porteur:
        return ""
    p = porteur.strip()
    m = re.search(r"CTT\s+.+", p, re.IGNORECASE)
    if m:
        return m.group(0).strip().upper()
    if p.upper().startswith("CMRF"):
        location = re.sub(r"^CMRF\s*/?\s*", "", p, flags=re.IGNORECASE).strip()
        return f"CTT {location.upper()}" if location else ""
    return p


KNOWN_SITE_SUFFIXES = {"IHS", "CRTV"}  # marqueurs techniques à ignorer, pas des noms de site


def extract_site(description):
    if not description:
        return ""
    s = description.strip()
    # "DOWN" / "UP" est l'état du site, pas le nom de la localisation
    s = re.sub(r"\s+(DOWN|UP)\s*$", "", s, flags=re.IGNORECASE).strip()
    parts = s.split("_")
    if len(parts) < 2:
        return s.upper() if s else ""
    parts = parts[1:]  # on retire le code site (1er segment)
    if len(parts) > 1 and parts[-1].strip().upper() in KNOWN_SITE_SUFFIXES:
        parts = parts[:-1]  # on retire le marqueur technique final (ex: IHS, CRTV)
    site = " ".join(p.strip() for p in parts if p.strip())
    return site.upper() if site else ""


def extract_localisation(description):
    if not description:
        return ""
    s = description.strip()
    # "DOWN" / "UP" est un état du site, pas une localisation
    s = re.sub(r"\s+(DOWN|UP)\s*$", "", s, flags=re.IGNORECASE).strip()
    return s


def extract_cause(incident):
    if incident["is_end"]:
        cause = incident.get("cause")
        return format_sentence(cause) if cause else ""
    return ""


def extract_clients_impactes(impact):
    return impact.strip() if impact else ""


# Marqueurs d'état final du site à séparer de l'action réalisée (repli regex).
# L'IA fait ce tri avec beaucoup plus de robustesse ; ici c'est un best-effort.
_STATE_MARKERS = (
    "bts up", "bts down",
    "après le rétablissement", "apres le retablissement",
    "après rétablissement", "apres retablissement",
    "rétablissement du support", "retablissement du support",
    "after restoration", "restored",
)


def split_action_state(text: str):
    """Sépare grossièrement l'action réalisée de l'état final du site.
    Retourne (action, etat). Repli déterministe quand l'IA est indisponible."""
    if not text:
        return text, ""
    s = text.strip()
    lower = s.lower()
    # État en tête de phrase (ex: "UP après les travaux de raccordement...")
    m_head = re.match(r"^(BTS\s+)?(UP|DOWN)\s+apr[eè]s\b(.+)$", s, re.IGNORECASE)
    if m_head:
        action = m_head.group(3).strip().lstrip(" :").strip()
        return action, f"{m_head.group(1) or ''}{m_head.group(2)}".strip()
    for marker in _STATE_MARKERS:
        idx = lower.find(marker)
        if idx > 0:
            return s[:idx].rstrip(" ,;-").strip(), s[idx:].strip()
    # "UP" / "DOWN" isolé en fin de phrase (ex: "... raccordement câbles FO UP")
    m = re.search(r"^(.*?)\s+(?:UP|DOWN)\b\s*$", s, re.IGNORECASE)
    if m:
        return m.group(1).strip(), s[m.start(1) + len(m.group(1)):].strip()
    return s, ""


def extract_description_travaux(incident):
    if not incident["is_end"]:
        return ""
    actions = incident.get("actions_menee")
    comments = incident.get("commentaires") or []
    last_comment = comments[-1]["text"] if comments else None

    # Version déterministe (repli si pas de clé API / échec réseau)
    action_only, _ = split_action_state(actions) if actions else (None, "")
    parts = []
    if action_only:
        parts.append(format_sentence(action_only))
    if last_comment and (not action_only or last_comment.lower() not in action_only.lower()):
        parts.append(format_sentence(last_comment))
    deterministic = " ".join(parts) if parts else ""

    raw_combo = " ".join(p for p in [action_only, last_comment] if p)
    if not raw_combo:
        return deterministic

    return polish_with_ai(raw_combo, DESCRIPTION_SYSTEM_PROMPT, deterministic, max_tokens=500)


def extract_observations(incident):
    comments = incident.get("commentaires") or []
    if incident["is_end"]:
        # Version déterministe (repli si pas de clé API / échec réseau) :
        # on ne garde QUE l'état final du site (ex: "BTS UP après..."),
        # extrait du dernier commentaire si un marqueur d'état y est présent.
        last_comment = comments[-1]["text"] if comments else None
        state = ""
        if last_comment:
            _, state = split_action_state(last_comment)
        deterministic = format_sentence(state) if state else ""

        cause_text = incident.get("cause") or ""
        comments_text = "\n".join(f"- {c['date']}: {c['text']}" for c in comments)
        prompt = f"Cause de l'incident : {cause_text}\n\nChronologie des commentaires :\n{comments_text}"
        if not comments_text:
            return deterministic

        return polish_with_ai(prompt, OBSERVATIONS_SYSTEM_PROMPT, deterministic, max_tokens=700)
    else:
        if comments:
            return format_sentence(comments[-1]["text"])
        return ""


def extract_date_retablissement(incident):
    return incident["fin"] if incident["is_end"] and incident.get("fin") else ""


def extract_date_fin_intervention(incident):
    return incident["fin"] if incident["is_end"] and incident.get("fin") else ""


# Longueur maximale (caractères) des champs texte libres, pour garantir que
# la fiche tienne TOUJOURS sur une seule page A4.
FIELD_MAX_LEN = 130


def truncate_field(text: str, max_len: int = FIELD_MAX_LEN) -> str:
    """Tronque un champ trop long sans couper au milieu d'un mot."""
    if not text or len(text) <= max_len:
        return text
    cut = text[:max_len]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-") + "…"


def map_incident_to_fiche(incident: dict) -> dict:
    """Applique toutes les règles de mapping du SKILL.md."""
    etablissement = extract_etablissement(incident.get("porteur"))
    return {
        "ETABLISSEMENT": etablissement,
        "SITE": truncate_field(extract_site(incident.get("description")), 60),
        "DATE_INCIDENT": incident.get("debut") or "",
        "DATE_INFORMATION": incident.get("recu") or "",
        "DATE_DEPART_TERRAIN": "",
        "LOCALISATION": truncate_field(extract_localisation(incident.get("description"))),
        "CAUSE": truncate_field(extract_cause(incident)),
        "CLIENTS_IMPACTES": truncate_field(extract_clients_impactes(incident.get("impact")), 120),
        "DESCRIPTION_TRAVAUX": truncate_field(extract_description_travaux(incident)),
        "DATE_DEBUT_INTERVENTION": "",
        "DATE_RETABLISSEMENT": extract_date_retablissement(incident),
        "DATE_FIN_INTERVENTION": extract_date_fin_intervention(incident),
        "OBSERVATIONS": truncate_field(extract_observations(incident), 160),
        "EQUIPE_INTERVENTION": etablissement,
    }


# ---------------------------------------------------------------------------
# Génération du document Word
# ---------------------------------------------------------------------------

def xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def fill_template(fiche_fields: dict, output_path: str):
    """Copie le template et remplace les placeholders {{CLE}} par leur valeur."""
    tmp_dir = output_path + "_tmp"
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir)

    with zipfile.ZipFile(TEMPLATE_PATH, "r") as z:
        z.extractall(tmp_dir)

    doc_xml_path = os.path.join(tmp_dir, "word", "document.xml")
    with open(doc_xml_path, encoding="utf-8") as f:
        content = f.read()

    for key, value in fiche_fields.items():
        placeholder = "{{" + key + "}}"
        content = content.replace(placeholder, xml_escape(str(value)))

    with open(doc_xml_path, "w", encoding="utf-8") as f:
        f.write(content)

    if os.path.exists(output_path):
        os.remove(output_path)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(tmp_dir):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, tmp_dir)
                zf.write(full_path, arcname)

    shutil.rmtree(tmp_dir)


def build_filename(incident: dict, fiche_fields: dict) -> str:
    tt = incident.get("tt") or "TTinconnu"
    debut = incident.get("debut") or ""
    date_part = ""
    heure_part = ""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})", debut)
    if m:
        date_part = f"{m.group(1)}{m.group(2)}{m.group(3)}"
        heure_part = f"{m.group(4)}h{m.group(5)}"
    site = fiche_fields["SITE"].replace(" ", "_") if fiche_fields["SITE"] else "SITE_INCONNU"
    parts = [f"Fiche de releve des incidents sur le mobile TT{tt}", date_part]
    if heure_part:
        parts.append(heure_part)
    parts.append(site)
    return "_".join(parts) + ".docx"


def generate_from_block(block_text: str):
    """
    Traite UN bloc de texte (un message WhatsApp). Retourne le chemin du
    fichier généré si c'était un incident, sinon None (message ignoré).
    Réutilisable aussi bien par le traitement en lot (fichier .txt) que par
    le webhook temps réel (whatsapp.py).
    """
    if not is_real_incident(block_text):
        return None
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    incident = parse_incident(block_text)
    fiche_fields = map_incident_to_fiche(incident)
    filename = build_filename(incident, fiche_fields)
    output_path = os.path.join(OUTPUT_DIR, filename)
    fill_template(fiche_fields, output_path)
    # Upsert optionnel dans Supabase (jamais bloquant) : insère si la TT est
    # nouvelle, sinon met à jour la fiche existante ET la ré-téléverse.
    try:
        supabase_client.upsert_incident(
            incident, fiche_fields,
            docx_name=filename,
            raw_message=block_text,
            docx_path_local=output_path,
        )
    except Exception as e:
        print(f"[generator] Erreur lors de l'écriture Supabase: {e}", file=sys.stderr)
    return output_path


def generate_from_file(path: str):
    with open(path, encoding="utf-8") as f:
        raw_text = f.read()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    count = 0
    for block in split_incidents(raw_text):
        output_path = generate_from_block(block)
        if output_path:
            print(f"Généré: {os.path.basename(output_path)}")
            count += 1
    print(f"\n{count} fiche(s) générée(s) dans {OUTPUT_DIR}/")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generator.py <fichier_incidents.txt>")
        sys.exit(1)
    generate_from_file(sys.argv[1])


if __name__ == "__main__":
    main()
