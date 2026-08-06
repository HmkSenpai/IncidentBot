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

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "fiche_template.docx")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

FALLBACK = "A déterminer"


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
# Polish IA (optionnel) — DeepSeek et/ou OpenRouter, compatibles OpenAI
# ---------------------------------------------------------------------------
# Activé automatiquement si une clé API est présente dans l'environnement
# (ou dans .env.local). Sinon, le script utilise silencieusement le texte
# déterministe (regex) en repli — aucune dépendance externe n'est requise
# pour fonctionner.
#
# Variables reconnues :
#   AI_PROVIDER          "deepseek" ou "openrouter" (auto-détecté si absent)
#   DEEPSEEK_API_KEY      clé DeepSeek
#   DEEPSEEK_MODEL        défaut: deepseek-v4-flash
#   OPENROUTER_API_KEY    clé OpenRouter
#   OPENROUTER_MODEL      défaut: z-ai/glm-4.5-air:free
#                         -> vérifiez le modèle gratuit actuel sur
#                            https://openrouter.ai/models (filtre "free"),
#                            le catalogue change régulièrement.

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
        # Le catalogue "free" d'OpenRouter change souvent. Vérifiez le slug
        # exact (champ "model" du snippet de code) sur la page du modèle
        # choisi, sur https://openrouter.ai/models (filtre "free"), et
        # surchargez avec OPENROUTER_MODEL dans .env.local au besoin.
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
    "Tu reformules des notes techniques d'incidents télécom CAMTEL en français "
    "professionnel, clair et concis (1 à 2 phrases). N'invente jamais d'information "
    "absente du texte source. Corrige la grammaire, la ponctuation et la casse, mais "
    "garde les sigles (BTS, CTT, FO, TT, IHS...) en majuscules. Réponds uniquement "
    "avec le texte reformulé, sans préambule ni guillemets."
)

OBSERVATIONS_SYSTEM_PROMPT = (
    "Tu rédiges la section 'Observations' d'une fiche d'incident télécom CAMTEL. "
    "À partir de la cause et de la chronologie de commentaires fournis, écris un "
    "paragraphe professionnel et concis en français (3 à 5 phrases) qui résume : la "
    "cause principale, les événements marquants, et la réparation effectuée le cas "
    "échéant. N'invente aucune information absente du texte source. Réponds "
    "uniquement avec le paragraphe, sans préambule ni guillemets."
)


def call_llm(prompt: str, system_prompt: str, max_tokens: int = 300):
    """Appelle le fournisseur IA actif (DeepSeek ou OpenRouter). Retourne None
    si aucune clé n'est configurée, ou en cas d'échec (réseau, quota,
    timeout...) — l'appelant doit alors utiliser un repli."""
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
        print(f"[polish IA] Échec de l'appel {provider} ({e}) — {detail}",
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
        return FALLBACK
    p = porteur.strip()
    m = re.search(r"CTT\s+.+", p, re.IGNORECASE)
    if m:
        return m.group(0).strip().upper()
    if p.upper().startswith("CMRF"):
        location = re.sub(r"^CMRF\s*/?\s*", "", p, flags=re.IGNORECASE).strip()
        return f"CTT {location.upper()}" if location else FALLBACK
    return p


KNOWN_SITE_SUFFIXES = {"IHS", "CRTV"}  # marqueurs techniques à ignorer, pas des noms de site


def extract_site(description):
    if not description:
        return FALLBACK
    s = description.strip()
    s = re.sub(r"\s+DOWN\s*$", "", s, flags=re.IGNORECASE).strip()
    parts = s.split("_")
    if len(parts) < 2:
        return s.upper() if s else FALLBACK
    parts = parts[1:]  # on retire le code site (1er segment)
    if len(parts) > 1 and parts[-1].strip().upper() in KNOWN_SITE_SUFFIXES:
        parts = parts[:-1]  # on retire le marqueur technique final (ex: IHS, CRTV)
    site = " ".join(p.strip() for p in parts if p.strip())
    return site.upper() if site else FALLBACK


def extract_localisation(description):
    return description.strip() if description else FALLBACK


def extract_cause(incident):
    if incident["is_end"]:
        cause = incident.get("cause")
        return format_sentence(cause) if cause else FALLBACK
    return "Investigation en cours"


def extract_clients_impactes(impact):
    return impact.strip() if impact else FALLBACK


def extract_description_travaux(incident):
    if not incident["is_end"]:
        return "Investigation en cours"
    actions = incident.get("actions_menee")
    comments = incident.get("commentaires") or []
    last_comment = comments[-1]["text"] if comments else None

    # Version déterministe (repli si pas de clé API / échec réseau)
    parts = []
    if actions:
        parts.append(format_sentence(actions))
    if last_comment and (not actions or last_comment.lower() not in actions.lower()):
        parts.append(format_sentence(last_comment))
    deterministic = " ".join(parts) if parts else "Investigation en cours"

    raw_combo = " ".join(p for p in [actions, last_comment] if p)
    if not raw_combo:
        return deterministic

    return polish_with_ai(raw_combo, DESCRIPTION_SYSTEM_PROMPT, deterministic, max_tokens=500)


def extract_observations(incident):
    comments = incident.get("commentaires") or []
    if incident["is_end"]:
        # Version déterministe (repli si pas de clé API / échec réseau)
        cause = incident.get("cause")
        pieces = []
        if cause:
            pieces.append(format_sentence(cause))
        for c in comments:
            pieces.append(format_sentence(c["text"]))
        deterministic = " ".join(pieces) if pieces else "En cours"

        cause_text = incident.get("cause") or ""
        comments_text = "\n".join(f"- {c['date']}: {c['text']}" for c in comments)
        prompt = f"Cause de l'incident : {cause_text}\n\nChronologie des commentaires :\n{comments_text}"
        if not cause_text and not comments_text:
            return deterministic

        return polish_with_ai(prompt, OBSERVATIONS_SYSTEM_PROMPT, deterministic, max_tokens=700)
    else:
        if comments:
            return format_sentence(comments[-1]["text"])
        return "Les investigations sont toujours en cours."


def extract_date_retablissement(incident):
    return incident["fin"] if incident["is_end"] and incident.get("fin") else "En cours"


def extract_date_fin_intervention(incident):
    return incident["fin"] if incident["is_end"] and incident.get("fin") else "En cours"


def map_incident_to_fiche(incident: dict) -> dict:
    """Applique toutes les règles de mapping du SKILL.md."""
    etablissement = extract_etablissement(incident.get("porteur"))
    return {
        "ETABLISSEMENT": etablissement,
        "SITE": extract_site(incident.get("description")),
        "DATE_INCIDENT": incident.get("debut") or FALLBACK,
        "DATE_INFORMATION": incident.get("recu") or FALLBACK,
        "DATE_DEPART_TERRAIN": "En attente",
        "LOCALISATION": extract_localisation(incident.get("description")),
        "CAUSE": extract_cause(incident),
        "CLIENTS_IMPACTES": extract_clients_impactes(incident.get("impact")),
        "DESCRIPTION_TRAVAUX": extract_description_travaux(incident),
        "DATE_DEBUT_INTERVENTION": "Non renseignée",
        "DATE_RETABLISSEMENT": extract_date_retablissement(incident),
        "DATE_FIN_INTERVENTION": extract_date_fin_intervention(incident),
        "OBSERVATIONS": extract_observations(incident),
        "EQUIPE_INTERVENTION": f"{etablissement} pour compétences",
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
    site = fiche_fields["SITE"].replace(" ", "_") if fiche_fields["SITE"] != FALLBACK else "SITE_INCONNU"
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
