"""
parser.py
Transforme les messages bruts d'incidents CAMTEL (format WhatsApp) en objets
JSON structurés, à l'aide d'expressions régulières uniquement (pas d'IA).

Usage:
    python3 parser.py incidents/incidents.txt
"""

import re
import sys
import json


# Un bloc "incident" commence par une ligne du type:
# "Incident GSM/UMTS/LTE/CDMA | END"  ou  "... | UPDATE 01"
INCIDENT_START_RE = re.compile(
    r"^Incident\s+GSM/UMTS/LTE/CDMA\s*\|\s*(?P<etat>.+)$",
    re.MULTILINE | re.IGNORECASE,
)

# Champs simples "CLE: valeur" (une seule ligne)
FIELD_RE = re.compile(r"^([A-ZÉÈÀÂÊÎÔÛa-z ()/]+?):[ \t]*(.*)$")


def is_real_incident(block_text: str) -> bool:
    """Un message est un incident s'il contient l'en-tête attendu."""
    return INCIDENT_START_RE.search(block_text) is not None


def split_incidents(raw_text: str):
    """Découpe le texte brut en blocs, un par incident détecté."""
    # On découpe juste avant chaque nouvelle ligne "Incident ... | ETAT"
    positions = [m.start() for m in INCIDENT_START_RE.finditer(raw_text)]
    positions.append(len(raw_text))
    blocks = []
    for i in range(len(positions) - 1):
        block = raw_text[positions[i]:positions[i + 1]].strip()
        if block:
            blocks.append(block)
    return blocks


def parse_comments(block_text: str) -> list:
    """
    Extrait les commentaires chronologiques du bloc COMMENTAIRES.
    Format attendu par ligne: - [DD/MM/YYYY HH:MM] texte...
    """
    comments = []
    comment_line_re = re.compile(
        r"^-\s*\[(?P<date>\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})\]\s*(?P<text>.+)$"
    )
    for line in block_text.splitlines():
        m = comment_line_re.match(line.strip())
        if m:
            comments.append({
                "date": m.group("date"),
                "text": m.group("text").strip(),
            })
    return comments


def parse_incident(block_text: str) -> dict:
    """Parse un seul bloc incident et retourne un dict structuré."""

    header_match = INCIDENT_START_RE.search(block_text)
    etat_brut = header_match.group("etat").strip() if header_match else ""

    # Champs à extraire (nom_json -> motif de clé dans le texte brut)
    simple_fields = {
        "debut": r"DÉBUT",
        "recu": r"REÇU",
        "fin": r"FIN",
        "description": r"DESCRIPTION",
        "impact": r"IMPACT",
        "cause": r"CAUSE",
        "actions_menee": r"ACTIONS MENEE|ACTION EN COURS",
        "tt": r"TT",
        "priorite": r"PRIORITÉ",
        "porteur": r"PORTEUR",
        "rfo": r"RFO",
    }

    data = {}
    for json_key, label_pattern in simple_fields.items():
        pattern = re.compile(
            rf"^(?:{label_pattern}):[ \t]*(.*)$", re.MULTILINE
        )
        m = pattern.search(block_text)
        data[json_key] = m.group(1).strip() if m and m.group(1).strip() else None

    # Bloc COMMENTAIRES : tout ce qui suit "COMMENTAIRES:" jusqu'à "RFO:"
    # ou la fin du bloc.
    com_match = re.search(
        r"COMMENTAIRES:[ \t]*(?:.*\n)?(?P<body>(?:^-\s*\[.*\n?)*)",
        block_text,
        re.MULTILINE,
    )
    comments = parse_comments(com_match.group("body")) if com_match else []
    data["commentaires"] = comments

    # Etat: True si incident terminé (END), False sinon (UPDATE/en cours)
    data["etat"] = etat_brut
    data["is_end"] = etat_brut.upper() == "END"

    return data


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 parser.py <fichier_incidents.txt>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        raw_text = f.read()

    blocks = split_incidents(raw_text)
    incidents = []
    ignored = 0

    for block in blocks:
        if not is_real_incident(block):
            ignored += 1
            continue
        incidents.append(parse_incident(block))

    print(json.dumps(incidents, ensure_ascii=False, indent=2))
    print(f"\n# {len(incidents)} incident(s) détecté(s), {ignored} message(s) ignoré(s).",
          file=sys.stderr)


if __name__ == "__main__":
    main()
