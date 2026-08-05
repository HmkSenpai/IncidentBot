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
import zipfile
import shutil
from datetime import datetime

from parser import split_incidents, is_real_incident, parse_incident

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "fiche_template.docx")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

FALLBACK = "A déterminer"


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

    parts = []
    if actions:
        parts.append(format_sentence(actions))
    if last_comment and (not actions or last_comment.lower() not in actions.lower()):
        parts.append(format_sentence(last_comment))

    return " ".join(parts) if parts else "Investigation en cours"


def extract_observations(incident):
    comments = incident.get("commentaires") or []
    if incident["is_end"]:
        cause = incident.get("cause")
        pieces = []
        if cause:
            pieces.append(format_sentence(cause))
        for c in comments:
            pieces.append(format_sentence(c["text"]))
        return " ".join(pieces) if pieces else "En cours"
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
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", debut)
    if m:
        date_part = f"{m.group(1)}{m.group(2)}{m.group(3)}"
    site = fiche_fields["SITE"].replace(" ", "_") if fiche_fields["SITE"] != FALLBACK else "SITE_INCONNU"
    return f"Fiche de releve des incidents sur le mobile TT{tt}_{date_part}_{site}.docx"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generator.py <fichier_incidents.txt>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        raw_text = f.read()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    blocks = split_incidents(raw_text)
    count = 0
    for block in blocks:
        if not is_real_incident(block):
            continue
        incident = parse_incident(block)
        fiche_fields = map_incident_to_fiche(incident)
        filename = build_filename(incident, fiche_fields)
        output_path = os.path.join(OUTPUT_DIR, filename)
        fill_template(fiche_fields, output_path)
        print(f"Généré: {filename}")
        count += 1

    print(f"\n{count} fiche(s) générée(s) dans {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
