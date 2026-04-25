/**
 * bridge.js — SIFTA WhatsApp Bridge
 *
 * Connects your WhatsApp to the SIFTA Swarm Voice via Baileys.
 * - Scan QR once → session saved → never scan again
 * - Routes your incoming messages to Python SIFTA server (port 7434)
 * - Auto-reconnects after normal stream resets (code 515 post-pairing)
 *
 * No external frameworks. Just the raw Baileys wire.
 */

import makeWASocket, {
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion
} from "@whiskeysockets/baileys";
import qrcode from "qrcode-terminal";
import http from "http";
import fs from "fs";
import crypto from "crypto";

process.on("unhandledRejection", (err) => {
  console.error("[BRIDGE] Unhandled async error kept alive:", err?.message || err);
});

process.on("uncaughtException", (err) => {
  console.error("[BRIDGE] Uncaught error kept alive:", err?.message || err);
});

const SIFTA_SERVER = "http://localhost:7434/swarm_message";
const SESSION_DIR = process.env.SIFTA_WHATSAPP_SESSION_DIR || "./whatsapp_session";
const MAX_WA_TEXT_TO_SIFTA = 8192;
const MAX_INJECT_BODY = 16384;
const INJECT_KEY = process.env.SIFTA_BRIDGE_INJECT_KEY || "";
const TRIGGER_WORD = (process.env.SIFTA_WHATSAPP_TRIGGER || "alice").trim().toLowerCase();
const REQUIRE_TRIGGER = process.env.SIFTA_WHATSAPP_REQUIRE_TRIGGER !== "0";
const ALLOW_GROUPS = process.env.SIFTA_WHATSAPP_ALLOW_GROUPS === "1";
const SEND_REPLIES = process.env.SIFTA_WHATSAPP_SEND_REPLIES !== "0";
const ENABLE_INJECT = process.env.SIFTA_WHATSAPP_ENABLE_INJECT === "1";
const ALLOWED_JIDS = new Set(
  (process.env.SIFTA_WHATSAPP_ALLOWED_JIDS || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
);
const ALLOWED_ALIASES = new Set(
  (process.env.SIFTA_WHATSAPP_ALLOWED_ALIASES || "")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean)
);
const ALIASES_FILE = "../../.sifta_state/whatsapp_alice_aliases.json";
const CONTACTS_FILE = "../../.sifta_state/whatsapp_contacts.json";
const DEBUG_FILE = "../../.sifta_state/whatsapp_bridge_debug.jsonl";
let lastKnownHuman = null;

function shortHash(value) {
  return crypto.createHash("sha256").update(String(value || "")).digest("hex").slice(0, 12);
}

function logDebug(event, details = {}) {
  const row = {
    ts: Date.now() / 1000,
    event,
    ...details,
  };
  try {
    fs.mkdirSync("../../.sifta_state", { recursive: true });
    fs.appendFileSync(DEBUG_FILE, JSON.stringify(row) + "\n", { mode: 0o600 });
  } catch {
    // Debug logging must never break the bridge.
  }
  const printable = { ...row };
  if (printable.text_preview) printable.text_preview = String(printable.text_preview).slice(0, 80);
  console.log(`[WA DEBUG] ${JSON.stringify(printable)}`);
}

function loadJsonFile(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function writeJsonFile(file, data) {
  try {
    fs.mkdirSync("../../.sifta_state", { recursive: true });
    const tmp = `${file}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(data, null, 2) + "\n", { mode: 0o600 });
    fs.renameSync(tmp, file);
  } catch (err) {
    console.error(`[CONTACT CACHE] Failed to write ${file}:`, err?.message || err);
  }
}

function cleanName(value) {
  return (typeof value === "string" ? value : "").replace(/\s+/g, " ").trim();
}

function mergeNames(existing, candidates) {
  const names = new Set(Array.isArray(existing) ? existing.filter(Boolean) : []);
  for (const item of candidates) {
    const name = cleanName(item);
    if (name) names.add(name);
  }
  return [...names].sort((a, b) => a.localeCompare(b));
}

function cacheContact(jid, fields = {}, source = "unknown") {
  const id = cleanName(jid);
  if (!id || !id.includes("@")) return;
  const data = loadJsonFile(CONTACTS_FILE, { schema_version: 1, contacts: {} });
  if (!data.contacts || typeof data.contacts !== "object") data.contacts = {};
  const prior = data.contacts[id] || {};
  const displayNames = mergeNames(prior.display_names, [
    fields.name,
    fields.notify,
    fields.pushName,
    fields.verifiedName,
    fields.subject,
    fields.displayName,
  ]);
  const sourceList = new Set(Array.isArray(prior.sources) ? prior.sources : []);
  sourceList.add(source);
  data.contacts[id] = {
    jid: id,
    display_names: displayNames,
    name: displayNames[0] || prior.name || "",
    is_group: Boolean(fields.isGroup || id.endsWith("@g.us")),
    last_seen_at: Date.now() / 1000,
    sources: [...sourceList].sort(),
  };
  data.updated_at = Date.now() / 1000;
  writeJsonFile(CONTACTS_FILE, data);
}

function aliasAllowedTargets() {
  if (ALLOWED_ALIASES.size === 0) return new Set();
  try {
    const raw = JSON.parse(fs.readFileSync(ALIASES_FILE, "utf8"));
    const targets = new Set();
    for (const alias of ALLOWED_ALIASES) {
      const jid = raw?.[alias]?.jid;
      if (typeof jid === "string" && jid.trim()) targets.add(jid.trim());
    }
    return targets;
  } catch {
    return new Set();
  }
}

function isAllowedChat(from, participant = "") {
  const aliasTargets = aliasAllowedTargets();
  if (ALLOWED_JIDS.size === 0 && aliasTargets.size === 0) return true;
  return (
    ALLOWED_JIDS.has(from) ||
    aliasTargets.has(from) ||
    (participant && (ALLOWED_JIDS.has(participant) || aliasTargets.has(participant)))
  );
}

function validateSafetyConfig() {
  const riskyBroadcast = SEND_REPLIES && ALLOWED_JIDS.size === 0 && ALLOWED_ALIASES.size === 0 && (!REQUIRE_TRIGGER || ALLOW_GROUPS);
  const riskyInject = ENABLE_INJECT && ALLOWED_JIDS.size === 0 && ALLOWED_ALIASES.size === 0;
  if (riskyBroadcast) {
    console.error("[SIFTA SAFETY] Refusing wide-open WhatsApp replies.");
    console.error("[SIFTA SAFETY] Use trigger words, set SIFTA_WHATSAPP_SEND_REPLIES=0, or set SIFTA_WHATSAPP_ALLOWED_JIDS.");
    process.exit(2);
  }
  if (riskyInject) {
    console.error("[SIFTA SAFETY] Refusing outbound injection without SIFTA_WHATSAPP_ALLOWED_JIDS or SIFTA_WHATSAPP_ALLOWED_ALIASES.");
    process.exit(2);
  }
}

function stripTrigger(text) {
  const trimmed = (text || "").trim();
  if (!REQUIRE_TRIGGER) return { ok: true, text: trimmed };
  const lower = trimmed.toLowerCase();
  const variants = [
    `/${TRIGGER_WORD}`,
    `@${TRIGGER_WORD}`,
    TRIGGER_WORD,
  ];
  for (const variant of variants) {
    if (lower === variant) return { ok: true, text: "hello" };
    if (lower.startsWith(`${variant} `)) return { ok: true, text: trimmed.slice(variant.length).trim() };
    if (lower.startsWith(`${variant},`)) return { ok: true, text: trimmed.slice(variant.length + 1).trim() };
    if (lower.startsWith(`${variant}:`)) return { ok: true, text: trimmed.slice(variant.length + 1).trim() };
  }
  return { ok: false, text: trimmed };
}

async function connectToWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: false,
  });

  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log("\n╔══════════════════════════════════════════╗");
      console.log("║  SIFTA SWARM — WhatsApp Pairing QR Code  ║");
      console.log("║  Open WhatsApp → Linked Devices → Scan  ║");
      console.log("╚══════════════════════════════════════════╝\n");
      qrcode.generate(qr, { small: true });
    }

    if (connection === "open") {
      logDebug("connection_open", { require_trigger: REQUIRE_TRIGGER, allow_groups: ALLOW_GROUPS });
      console.log("\n[🌊 SWARM BRIDGE] WhatsApp connected in reply-only mode.");
      console.log(`[🌊 SWARM BRIDGE] Say "${TRIGGER_WORD} ..." in a chat to ask Alice.`);
      if (!ALLOW_GROUPS) console.log("[🌊 SWARM BRIDGE] Group chats are muted by default.\n");
    }

    if (connection === "close") {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const loggedOut = statusCode === DisconnectReason.loggedOut;

      if (!loggedOut) {
        // Code 515 = normal post-pairing restart. All other non-logout codes → reconnect.
        logDebug("connection_close_reconnect", { statusCode });
        console.log(`[BRIDGE] Stream closed (code ${statusCode}). Reconnecting in 2s...`);
        setTimeout(connectToWhatsApp, 2000);
      } else {
        logDebug("connection_logged_out", { statusCode });
        console.log(`[BRIDGE] Logged out from WhatsApp. Clear ${SESSION_DIR} and re-run to re-pair.`);
        process.exit(1);
      }
    }
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("contacts.upsert", (contacts) => {
    for (const contact of contacts || []) {
      cacheContact(contact.id, contact, "contacts.upsert");
    }
  });

  sock.ev.on("contacts.update", (contacts) => {
    for (const contact of contacts || []) {
      cacheContact(contact.id, contact, "contacts.update");
    }
  });

  sock.ev.on("chats.upsert", (chats) => {
    for (const chat of chats || []) {
      cacheContact(chat.id, { ...chat, isGroup: String(chat.id || "").endsWith("@g.us") }, "chats.upsert");
    }
  });

  sock.ev.on("chats.update", (chats) => {
    for (const chat of chats || []) {
      cacheContact(chat.id, { ...chat, isGroup: String(chat.id || "").endsWith("@g.us") }, "chats.update");
    }
  });

  // Track IDs of messages the Swarm sent, to avoid replying to its own replies
  const sentBySwarm = new Set();

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    // Accept both 'notify' (new) and 'append' (self-chat on iOS)
    if (type !== "notify" && type !== "append") return;

    for (const msg of messages) {
      const msgId = msg.key.id;

      // Skip only messages the Swarm itself sent (echo prevention)
      if (sentBySwarm.has(msgId)) { sentBySwarm.delete(msgId); continue; }

      const from = msg.key.remoteJid;
      const fromMe = Boolean(msg.key.fromMe);
      const isGroup = Boolean(from && from.endsWith("@g.us"));
      const participant = msg.key.participant || "";
      cacheContact(from, { pushName: msg.pushName, isGroup }, "messages.upsert");
      if (participant) {
        cacheContact(participant, { pushName: msg.pushName, isGroup: false }, "messages.upsert.participant");
      }
      const text =
        msg.message?.conversation ||
        msg.message?.extendedTextMessage?.text ||
        msg.message?.imageMessage?.caption ||
        "";

      logDebug("message_seen", {
        type,
        from_hash: shortHash(from),
        participant_hash: participant ? shortHash(participant) : "",
        fromMe,
        isGroup,
        hasText: Boolean(text),
        text_preview: text,
      });
      if (!text) {
        logDebug("message_skipped_no_text", { type, from_hash: shortHash(from), isGroup, fromMe });
        continue;
      }
      if (isGroup && !ALLOW_GROUPS) {
        logDebug("message_skipped_group_muted", { from_hash: shortHash(from), text_preview: text });
        continue;
      }
      if (!isAllowedChat(from, participant)) {
        logDebug("message_skipped_not_allowlisted", { from_hash: shortHash(from), participant_hash: participant ? shortHash(participant) : "" });
        continue;
      }
      const trigger = stripTrigger(text);
      if (!trigger.ok) {
        logDebug("message_skipped_missing_trigger", { from_hash: shortHash(from), text_preview: text });
        continue;
      }
      const safeText =
        trigger.text.length > MAX_WA_TEXT_TO_SIFTA
          ? trigger.text.slice(0, MAX_WA_TEXT_TO_SIFTA)
          : trigger.text;

      lastKnownHuman = from;
      
      // Infinite loop prevention for offline kernel errors and multi-node echoing
      if (text.includes("🔴 SIFTA kernel is offline")) continue;
      if (text.startsWith("[M1THER]") || text.startsWith("[M5QUEEN]") || text.startsWith("[SIFTA]")) continue;
      if (text.startsWith("🌊") || text.startsWith("🧠📡")) continue;

      console.log(`\n[📲 INCOMING] type=${type} fromMe=${fromMe} group=${isGroup} from=${from}`);
      console.log(`  Message to Alice: "${safeText}"`);
      logDebug("message_forwarding_to_alice", { from_hash: shortHash(from), isGroup, fromMe, text_preview: safeText });

      const payload = JSON.stringify({
        from,
        text: safeText,
        rawText: text,
        fromMe,
        isGroup,
        participant,
      });

      const req = http.request(SIFTA_SERVER, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(payload),
        },
      }, (res) => {
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", async () => {
          try {
            const response = JSON.parse(data);
            const rawVoice = response.swarm_voice || response.reply;
            if (rawVoice === "_SILENT_") {
              console.log("  [SWARM IS SILENT]");
              logDebug("alice_returned_silent", { from_hash: shortHash(from) });
              return;
            }
            const reply = rawVoice || "🌊";
            if (!SEND_REPLIES) {
              console.log(`  [ALICE REPLY SUPPRESSED] "${reply.substring(0, 80)}..."`);
              return;
            }
            // Show "typing..." like a real conversation
            await sock.sendPresenceUpdate("composing", from);
            await new Promise(r => setTimeout(r, 1200));
            await sock.sendPresenceUpdate("paused", from);
            const sent = await sock.sendMessage(from, { text: reply });
            if (sent?.key?.id) sentBySwarm.add(sent.key.id);
            console.log(`  [SWARM REPLIED] "${reply.substring(0, 80)}..."`);
            logDebug("reply_sent", { from_hash: shortHash(from), reply_preview: reply });
          } catch (e) {
            console.error("[BRIDGE] Failed to parse SIFTA response:", e);
            logDebug("reply_parse_failed", { from_hash: shortHash(from), error: e?.message || String(e) });
          }
        });
      });

      req.on("error", () => {
        logDebug("alice_server_request_error", { from_hash: shortHash(from) });
        if (SEND_REPLIES) {
          sock.sendMessage(from, {
            text: "Alice's local bridge is offline. Restart scripts/start_swarm_whatsapp.sh.",
          });
        }
      });

      req.write(payload);
      req.end();
    }
  });

  // ── Optional injection server. Disabled by default; reply-only is safer.
  if (!ENABLE_INJECT) {
    console.log("[🌊 SWARM BRIDGE] Outbound injection server disabled (reply-only).");
    return;
  }
  if (!INJECT_KEY) {
    console.log("[🌊 SWARM BRIDGE] Injection requested, but SIFTA_BRIDGE_INJECT_KEY is missing. Staying reply-only.");
    return;
  }
  const injectServer = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/system_inject') {
        if (req.headers["x-sifta-inject-key"] !== INJECT_KEY) {
          res.writeHead(401, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ ok: false, error: "unauthorized" }));
          return;
        }
        let body = '';
        req.on('data', (chunk) => {
          if (body.length < MAX_INJECT_BODY) body += chunk.toString();
        });
        req.on('end', async () => {
            try {
                const data = JSON.parse(body);
                const target = (typeof data.to === "string" && data.to.trim()) ? data.to.trim() : lastKnownHuman;
                if (target && typeof data.text === "string" && data.text.trim() && isAllowedChat(target)) {
                    await sock.sendPresenceUpdate("composing", target);
                    await new Promise(r => setTimeout(r, 1200));
                    await sock.sendPresenceUpdate("paused", target);
                    const sent = await sock.sendMessage(target, { text: data.text });
                    if (sent?.key?.id) {
                        sentBySwarm.add(sent.key.id);
                    }
                    console.log(`\n[INJECT] Pushed explicit message to WhatsApp target=${target}: ${data.text.substring(0,60)}...`);
                } else {
                    console.log(`\n[INJECT] Failed. Missing target/text or target is not allowlisted.`);
                }
                res.writeHead(200, {"Content-Type": "application/json"});
                res.end(JSON.stringify({ok: true}));
            } catch(e) {
                console.error(`[INJECT ERROR] ${e}`);
                res.writeHead(500);
                res.end('Error');
            }
        });
    } else {
        res.writeHead(404);
        res.end();
    }
  });
  
  injectServer.listen(3001, "127.0.0.1", () => {
      console.log("[🌊 SWARM BRIDGE] Explicit Injection Server on 127.0.0.1:3001");
  });
}

console.log("[🌊 SIFTA BRIDGE] Booting WhatsApp connection...");
console.log(`[🌊 SIFTA BRIDGE] Session dir: ${SESSION_DIR}`);
validateSafetyConfig();
connectToWhatsApp();
