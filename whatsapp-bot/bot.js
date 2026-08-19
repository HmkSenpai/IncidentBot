// bot.js
// Connexion directe à WhatsApp Web via Baileys, sans Docker, sans base de
// données. Relaie chaque message reçu vers whatsapp.py (serveur webhook
// Python local), qui se charge du filtrage par groupe et de la génération
// des fiches.
//
// Installation :
//   npm install
// Lancement :
//   npm start
//
// Au premier lancement, un QR code s'affiche dans ce terminal - scannez-le
// avec WhatsApp (Paramètres > Appareils connectés > Connecter un appareil).
// La session est ensuite sauvegardée localement (dossier auth_info/), plus
// besoin de rescanner aux lancements suivants.
//
// Pour RELANCER proprement (l'ancien process est tué automatiquement) :
//   npm run restart
//
// ⚠️ Ne jamais lancer deux instances de bot.js sur le même dossier
// auth_info/ : elles écraseraient mutuellement les clés de session et
// WhatsApp cesserait de livrer les messages. Un verrou (auth_info/bot.lock)
// empêche le second lancement.

import makeWASocket, {
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  DisconnectReason,
} from "@whiskeysockets/baileys";
import { Boom } from "@hapi/boom";
import pino from "pino";
import qrcodeTerminal from "qrcode-terminal";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import path from "node:path";

const WEBHOOK_URL = process.env.WEBHOOK_URL || "http://localhost:5000/webhook";
const SEND_PORT = parseInt(process.env.SEND_PORT || "5001", 10);
const LOG_LEVEL = process.env.LOG_LEVEL || "silent"; // mettre "debug" pour voir le trafic brut Baileys
const AUTH_DIR = process.env.AUTH_DIR || "auth_info";
const LOCK_FILE = path.join(AUTH_DIR, "bot.lock");
const RECONNECT_DELAY_MS = 3000;

let currentSock = null;
let shutdownRequested = false;

const groupNameCache = new Map();

function isProcessAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return err.code === "EPERM";
  }
}

function acquireLock() {
  if (!existsSync(LOCK_FILE)) return true;
  try {
    const pid = parseInt(readFileSync(LOCK_FILE, "utf8"), 10);
    if (Number.isInteger(pid) && pid > 0 && isProcessAlive(pid)) {
      return false;
    }
  } catch {
    // lock illisible ou corrompu : on le considère comme périmé
  }
  return true;
}

function releaseLock() {
  try {
    unlinkSync(LOCK_FILE);
  } catch {
    // déjà supprimé ou jamais créé
  }
}

async function getGroupName(sock, jid) {
  if (!jid.endsWith("@g.us")) return null;
  if (groupNameCache.has(jid)) return groupNameCache.get(jid);
  try {
    const metadata = await sock.groupMetadata(jid);
    groupNameCache.set(jid, metadata.subject);
    return metadata.subject;
  } catch {
    return null;
  }
}

async function forwardMessage(key, message, groupName) {
  try {
    const res = await fetch(WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event: "messages.upsert",
        data: { key, message, groupName },
      }),
    });
    console.log(`[bot.js] Réponse de whatsapp.py: HTTP ${res.status}`);
  } catch (err) {
    console.error(`[bot.js] Impossible de joindre whatsapp.py (${WEBHOOK_URL}) :`, err.message);
    console.error("[bot.js] Vérifiez que 'python3 whatsapp.py' tourne bien dans un autre terminal.");
  }
}

async function connect() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: LOG_LEVEL }), // LOG_LEVEL=debug pour diagnostiquer
  });
  currentSock = sock;

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log("\n[bot.js] Scannez ce QR code avec WhatsApp :\n");
      qrcodeTerminal.generate(qr, { small: true });
    }

    if (connection === "close") {
      const statusCode = (lastDisconnect?.error instanceof Boom)
        ? lastDisconnect.error.output?.statusCode
        : undefined;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      console.log(
        `[bot.js] Connexion fermée (${statusCode ?? "raison inconnue"}). ` +
        `Reconnexion : ${shouldReconnect}`
      );

      if (statusCode === DisconnectReason.loggedOut) {
        releaseLock();
        console.log("[bot.js] Déconnecté (logged out). Supprimez le dossier "
          + "auth_info/ et relancez pour rescanner un nouveau QR code.");
        return;
      }

      if (shutdownRequested) {
        releaseLock();
        return;
      }

      console.log(`[bot.js] Nouvelle tentative de connexion dans ${RECONNECT_DELAY_MS / 1000}s...`);
      setTimeout(() => {
        connect().catch((err) => {
          console.error("[bot.js] Erreur au reconnect :", err);
          process.exit(1);
        });
      }, RECONNECT_DELAY_MS);
    } else if (connection === "open") {
      console.log("[bot.js] ✅ Connecté à WhatsApp.");
      startSendServer();
      startHeartbeat();
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    console.log(`[bot.js] messages.upsert reçu - type=${type}, count=${messages.length}`);
    if (type !== "notify") {
      console.log(`[bot.js] Ignoré (type != "notify")`);
      return;
    }
    for (const msg of messages) {
      if (!msg.message) {
        console.log(`[bot.js] Message sans contenu (protocole/réaction/etc.), ignoré. remoteJid=${msg.key?.remoteJid}`);
        continue;
      }
      console.log(`[bot.js] Message de ${msg.key.remoteJid} (fromMe=${msg.key.fromMe}), envoi vers whatsapp.py...`);
      const groupName = await getGroupName(sock, msg.key.remoteJid);
      await forwardMessage(msg.key, msg.message, groupName);
      console.log(`[bot.js] Transmis à whatsapp.py.`);
    }
  });
}

let heartbeatStarted = false;

function startHeartbeat() {
  if (heartbeatStarted) return;
  heartbeatStarted = true;
  setInterval(() => {
    console.log(`[bot.js] (toujours actif, ${new Date().toLocaleTimeString()})`);
  }, 20000);
}

let sendServerStarted = false;

function startSendServer() {
  if (sendServerStarted) return; // un seul serveur HTTP pour le process entier
  sendServerStarted = true;

  const server = createServer(async (req, res) => {
    if (req.method !== "POST" || req.url !== "/send-document") {
      res.writeHead(404);
      res.end();
      return;
    }

    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", async () => {
      try {
        const { jid, filePath, caption } = JSON.parse(body);
        if (!jid || !filePath) {
          res.writeHead(400, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "jid et filePath sont requis" }));
          return;
        }

        if (!currentSock) {
          res.writeHead(503, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "Session WhatsApp pas encore connectée" }));
          return;
        }

        const buffer = await readFile(filePath);
        await currentSock.sendMessage(jid, {
          document: buffer,
          fileName: path.basename(filePath),
          mimetype: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          caption: caption || undefined,
        });

        console.log(`[bot.js] Document envoyé à ${jid} : ${path.basename(filePath)}`);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ status: "ok" }));
      } catch (err) {
        console.error("[bot.js] Échec de l'envoi du document :", err.message);
        res.writeHead(500, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: err.message }));
      }
    });
  });

  server.on("error", (err) => {
    if (err.code === "EADDRINUSE") {
      console.error(
        `[bot.js] Le port ${SEND_PORT} est déjà utilisé par un autre process ` +
        `(ancien bot.js pas fermé ? copie en double du fichier ?). ` +
        `L'envoi automatique de documents est désactivé pour cette session, ` +
        `mais la réception des messages continue de fonctionner normalement.`
      );
    } else {
      console.error("[bot.js] Erreur du serveur d'envoi de documents :", err.message);
    }
  });

  server.listen(SEND_PORT, () => {
    console.log(`[bot.js] Serveur d'envoi de documents sur http://localhost:${SEND_PORT}/send-document`);
  });
}

async function main() {
  mkdirSync(AUTH_DIR, { recursive: true });

  if (!acquireLock()) {
    console.error("[bot.js] Abandon : une autre instance de bot.js utilise déjà la");
    console.error(`[bot.js] session (dossier ${AUTH_DIR}/). Les deux instances se`);
    console.error("[bot.js] voleraient les clés WhatsApp et les messages ne seraient");
    console.error("[bot.js] plus reçus. Fermez l'autre processus node 'bot.js' puis");
    console.error("[bot.js] relancez (ou utilisez 'npm run restart' qui le fait pour vous).");
    process.exit(1);
  }
  writeFileSync(LOCK_FILE, String(process.pid));

  const gracefulShutdown = () => {
    shutdownRequested = true;
    if (currentSock) {
      try {
        currentSock.end(new Error("Arrêt du bot"));
      } catch {
        // socket déjà fermée
      }
    }
    setTimeout(() => {
      releaseLock();
      process.exit(0);
    }, 300);
  };
  process.once("SIGINT", gracefulShutdown);
  process.once("SIGTERM", gracefulShutdown);
  process.once("exit", releaseLock);

  await connect();
}

main().catch((err) => {
  console.error("[bot.js] Erreur fatale au démarrage :", err);
  releaseLock();
  process.exit(1);
});