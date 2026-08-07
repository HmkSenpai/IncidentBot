"""
whatsapp.py
Serveur webhook local qui reçoit les évènements d'Evolution API en temps
réel, filtre les messages du groupe WhatsApp cible, et déclenche
generator.py pour chaque nouveau message.

Ne dépend que de la bibliothèque standard Python (http.server) - pas
d'installation supplémentaire nécessaire.

Configuration (dans .env.local, à côté de ce fichier) :
    TARGET_GROUP_JID=1203xxxxxxxxx@g.us   # JID du groupe WhatsApp à surveiller
    WEBHOOK_PORT=5000                     # port d'écoute local (optionnel)

Usage:
    python3 whatsapp.py

Puis configurez Evolution API pour pointer vers ce serveur (voir README).
"""

import os
import sys
import json
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import generator  # réutilise load_dotenv(), generate_from_block(), etc.

WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "5000"))
TARGET_GROUP_JID = os.environ.get("TARGET_GROUP_JID", "").strip()

# JID où envoyer les fiches générées (votre propre chat par défaut). Pour
# vous l'envoyer à vous-même, utilisez le format 237XXXXXXXXX@s.whatsapp.net
# (votre numéro complet avec indicatif pays, sans le +). Si non défini, la
# fiche n'est simplement pas renvoyée automatiquement.
REPORT_TARGET_JID = os.environ.get("REPORT_TARGET_JID", "").strip()
SEND_PORT = int(os.environ.get("SEND_PORT", "5001"))


def send_document_to_whatsapp(file_path: str, caption: str = ""):
    """Demande à bot.js (qui détient la session WhatsApp) d'envoyer le
    document généré. Échec silencieux (loggué) si bot.js n'est pas joignable
    - la fiche reste de toute façon disponible localement dans output/."""
    if not REPORT_TARGET_JID:
        return
    payload = json.dumps({
        "jid": REPORT_TARGET_JID,
        "filePath": os.path.abspath(file_path),
        "caption": caption,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"http://localhost:{SEND_PORT}/send-document",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        print(f"[whatsapp.py] Fiche envoyée sur WhatsApp à {REPORT_TARGET_JID}", file=sys.stderr)
    except Exception as e:
        print(f"[whatsapp.py] Échec de l'envoi WhatsApp de la fiche ({e}). "
              f"Elle reste disponible dans output/.", file=sys.stderr)


def extract_remote_jid(data: dict) -> str:
    return (data.get("key") or {}).get("remoteJid", "")


def extract_message_text(data: dict) -> str:
    """
    Les messages WhatsApp (protocole Baileys) peuvent arriver sous plusieurs
    formes selon comment ils ont été envoyés. On couvre les cas les plus
    courants pour un message texte simple.
    """
    message = data.get("message") or {}
    if "conversation" in message:
        return message["conversation"]
    if "extendedTextMessage" in message:
        return message["extendedTextMessage"].get("text", "")
    if "ephemeralMessage" in message:
        inner = message["ephemeralMessage"].get("message", {})
        return extract_message_text({"message": inner})
    return ""


class WebhookHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Réduit le bruit des logs par défaut de http.server
        print(f"[whatsapp.py] {args[0]} {args[1]}", file=sys.stderr)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length else b"{}"

        # On répond tout de suite pour ne jamais bloquer Evolution API.
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            print("[whatsapp.py] Payload JSON invalide, ignoré.", file=sys.stderr)
            return

        event = payload.get("event", "")
        if event.lower() not in ("messages.upsert", "messages_upsert"):
            return  # on ne traite que les nouveaux messages

        data = payload.get("data") or {}
        # data peut être un objet unique ou une liste selon la config
        entries = data if isinstance(data, list) else [data]

        for entry in entries:
            self.handle_message_entry(entry)

    def handle_message_entry(self, entry: dict):
        remote_jid = extract_remote_jid(entry)
        group_name = entry.get("groupName")
        from_me = entry.get("key", {}).get("fromMe", False)
        text_preview = extract_message_text(entry)[:60]
        label = f"{group_name!r}" if group_name else "(pas un groupe)"

        if not TARGET_GROUP_JID:
            print(f"[whatsapp.py] Message reçu - groupe: {label}  JID: {remote_jid}  "
                  f"fromMe: {from_me}  aperçu: {text_preview!r}", file=sys.stderr)
            return

        if remote_jid != TARGET_GROUP_JID:
            return  # autre groupe : ignoré silencieusement (trop de bruit sinon)

        text = extract_message_text(entry)
        if not text:
            return

        print(f"[whatsapp.py] Message du groupe cible (fromMe: {from_me}), "
              f"traitement : {text_preview!r}", file=sys.stderr)
        try:
            output_path = generator.generate_from_block(text)
        except Exception as e:
            print(f"[whatsapp.py] Erreur lors de la génération: {e}", file=sys.stderr)
            return

        if output_path:
            print(f"[whatsapp.py] Fiche générée: {os.path.basename(output_path)}", file=sys.stderr)
            # L'upsert Supabase (insert par TT + upload de la fiche) est déjà
            # réalisé dans generator.generate_from_block(). On envoie juste la
            # fiche sur WhatsApp.
            send_document_to_whatsapp(
                output_path,
                caption=f"Fiche générée automatiquement : {os.path.basename(output_path)}"
            )
        else:
            print("[whatsapp.py] Message ignoré (pas un incident).", file=sys.stderr)


def main():
    if not TARGET_GROUP_JID:
        print("ATTENTION: TARGET_GROUP_JID n'est pas défini dans .env.local.\n"
              "Le serveur va démarrer, mais aucun message ne sera traité tant que\n"
              "vous n'aurez pas configuré cette variable. En attendant, chaque\n"
              "message reçu affichera son JID dans cette console pour vous aider\n"
              "à identifier celui du bon groupe.\n", file=sys.stderr)

    server = HTTPServer(("0.0.0.0", WEBHOOK_PORT), WebhookHandler)
    print(f"[whatsapp.py] En écoute sur http://0.0.0.0:{WEBHOOK_PORT}/webhook", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[whatsapp.py] Arrêt.", file=sys.stderr)


if __name__ == "__main__":
    main()
