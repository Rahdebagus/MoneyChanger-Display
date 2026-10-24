// ─── TV Player ────────────────────────────────────────────────────────────────
//
// Shows the PNG or MP4 the generator produced, nothing else. No watermark, no
// ticker, no re-drawn board: the file is displayed with object-fit: contain on
// a black background, so it is never stretched or cropped.
//
// Update protocol, in order:
//   1. read the assignment from the server
//   2. download the media
//   3. validate it by actually decoding/loading it
//   4. only then swap the picture over
//   5. acknowledge, carrying the publication revision and version id
//
// A download or decode failure leaves the previous picture untouched and is
// reported back as "failed" so the dashboard shows it.

import { useCallback, useEffect, useRef, useState } from "react";

import {
  DEVICE_TOKEN_KEY,
  deviceApi,
  fetchMediaBlob,
  openSocket,
  readStored,
  writeStored,
} from "../../services/apiClient.js";
import * as cache from "./mediaCache.js";
import PairingScreen from "./PairingScreen.jsx";
import { startPolling } from "../../utils/polling.js";

const DEFAULT_HEARTBEAT_MS = 30000;
const DEFAULT_POLL_MS = 5 * 60 * 1000;
const MAX_BACKOFF_MS = 60000;

/** Exponential backoff with jitter, so many TVs never reconnect in lockstep. */
function backoffDelay(attempt) {
  const base = Math.min(MAX_BACKOFF_MS, 2000 * 2 ** Math.min(attempt, 5));
  return base / 2 + Math.random() * (base / 2);
}

function isExpired(validUntil) {
  if (!validUntil) return false; // null means "show until replaced"
  const text = String(validUntil);
  const normalised = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(text) ? text : `${text}Z`;
  const parsed = new Date(normalised);
  if (Number.isNaN(parsed.getTime())) return false;
  return parsed.getTime() <= Date.now();
}

export default function PlayerPage() {
  const [deviceToken, setDeviceToken] = useState(() => readStored(DEVICE_TOKEN_KEY));
  const [content, setContent] = useState(null); // { url, kind, revision, versionId, validUntil }
  const [status, setStatus] = useState("starting");
  const [online, setOnline] = useState(navigator.onLine);
  const [fatal, setFatal] = useState(null);

  const objectUrl = useRef(null);
  const applying = useRef(false);
  const syncing = useRef(false);
  const contentRef = useRef(null);
  const currentRevision = useRef(0);
  const timers = useRef({ reconnect: null, expiry: null });
  const socket = useRef(null);
  const mounted = useRef(true);
  const mediaRequest = useRef(null);
  const pendingAck = useRef(null);
  const acknowledging = useRef(false);

  const showContent = useCallback((nextContent) => {
    contentRef.current = nextContent;
    setContent(nextContent);
  }, []);

  // Retry only unconfirmed completion, using the existing heartbeat timer.
  const flushAcknowledgment = useCallback(async () => {
    const payload = pendingAck.current;
    if (!payload || acknowledging.current || !mounted.current || !navigator.onLine) return;
    acknowledging.current = true;
    try {
      await deviceApi.acknowledge(payload);
      if (pendingAck.current === payload) pendingAck.current = null;
    } catch {
      // Keep it pending; a lost response must not leave the dashboard stale.
    } finally {
      acknowledging.current = false;
    }
  }, []);

  // ── Restore whatever was on screen before a reload, before any network ────
  useEffect(() => {
    mounted.current = true;
    let cancelled = false;
    const saved = cache.readState();
    const restored = saved?.mediaUrl ? cache.getMedia(saved.mediaUrl) : Promise.resolve(null);
    restored.then((blob) => {
      if (cancelled || objectUrl.current || applying.current) return;
      if (!blob) {
        setStatus(readStored(DEVICE_TOKEN_KEY) ? "syncing" : "pairing");
        return;
      }
      if (isExpired(saved.validUntil)) {
        setStatus("expired");
        return;
      }
      const url = URL.createObjectURL(blob);
      objectUrl.current = url;
      currentRevision.current = saved.revision || 0;
      pendingAck.current = {
        revision: saved.revision, version_id: saved.versionId, state: "displayed",
      };
      showContent({
        url,
        kind: saved.kind,
        revision: saved.revision,
        versionId: saved.versionId,
        validUntil: saved.validUntil,
      });
      setStatus("showing");
    });

    return () => {
      cancelled = true;
      mounted.current = false;
      mediaRequest.current?.abort();
    };
  }, [showContent]);

  // ── Expiry watchdog ───────────────────────────────────────────────────────
  useEffect(() => {
    const handles = timers.current;
    clearTimeout(handles.expiry);
    if (!content?.validUntil) return undefined;

    const text = String(content.validUntil);
    const normalised = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(text) ? text : `${text}Z`;
    const expiresAt = new Date(normalised).getTime();
    const delay = expiresAt - Date.now();

    handles.expiry = setTimeout(() => {
      // Past its stated validity, the board stops being truthful. Show a
      // neutral holding screen rather than yesterday's rates.
      setStatus("expired");
    }, Math.max(0, Math.min(delay, 2147483000)));

    return () => clearTimeout(handles.expiry);
  }, [content?.validUntil]);

  /** Download, validate, then swap. Never swaps on failure. */
  const applyAssignment = useCallback(async (assignment) => {
    if (applying.current) return;
    if (!assignment?.has_assignment) return;

    // Ignore anything older than what is already on screen.
    if (assignment.revision <= currentRevision.current && contentRef.current) return;

    const media =
      assignment.media.find((item) => item.kind === "board_png") ||
      assignment.media.find((item) => item.kind === "board_mp4");

    if (!media) return;

    applying.current = true;
    const controller = new AbortController();
    mediaRequest.current = controller;
    let nextUrl = null;
    setStatus(contentRef.current ? "updating" : "loading");

    try {
      await deviceApi
        .acknowledge({
          revision: assignment.revision,
          version_id: assignment.version_id,
          state: "downloading",
        })
        .catch(() => {});

      let blob = await cache.getMedia(media.url);
      if (!blob) {
        blob = await fetchMediaBlob(media.url, { tokenKey: DEVICE_TOKEN_KEY, signal: controller.signal });
        await cache.putMedia(media.url, blob);
      }

      await deviceApi
        .acknowledge({
          revision: assignment.revision,
          version_id: assignment.version_id,
          state: "loading",
        })
        .catch(() => {});

      nextUrl = URL.createObjectURL(blob);

      // Validate by actually decoding. A truncated PNG or an MP4 this device
      // cannot play must not replace a working picture.
      await validateMedia(nextUrl, media.kind);
      if (!mounted.current || controller.signal.aborted) return;

      const previousUrl = objectUrl.current;
      objectUrl.current = nextUrl;
      currentRevision.current = assignment.revision;

      showContent({
        url: nextUrl,
        kind: media.kind,
        revision: assignment.revision,
        versionId: assignment.version_id,
        validUntil: assignment.valid_until,
      });
      setStatus(isExpired(assignment.valid_until) ? "expired" : "showing");

      cache.writeState({
        mediaUrl: media.url,
        kind: media.kind,
        revision: assignment.revision,
        versionId: assignment.version_id,
        validUntil: assignment.valid_until,
      });
      cache.evictExcept([media.url]);

      if (previousUrl) URL.revokeObjectURL(previousUrl);
      nextUrl = null; // Ownership moved to objectUrl; release it on replacement.

      pendingAck.current = {
        revision: assignment.revision,
        version_id: assignment.version_id,
        state: "displayed",
      };
      await flushAcknowledgment();
    } catch (err) {
      if (!mounted.current || controller.signal.aborted) return;
      // The old picture stays exactly where it was.
      setStatus(contentRef.current ? "showing" : "error");
      await deviceApi
        .acknowledge({
          revision: assignment.revision,
          version_id: assignment.version_id,
          state: "failed",
          error_message: String(err?.message || err).slice(0, 300),
        })
        .catch(() => {});
    } finally {
      if (nextUrl) URL.revokeObjectURL(nextUrl);
      applying.current = false;
    }
  }, [showContent, flushAcknowledgment]);

  const syncAssignment = useCallback(
    async (reason = "poll", signal) => {
      if (!readStored(DEVICE_TOKEN_KEY) || syncing.current || !navigator.onLine) return;
      syncing.current = true;

      try {
        const assignment = await deviceApi.assignment({ signal });
        if (!mounted.current || signal?.aborted) return;
        setOnline(true);

        if (assignment.pending_command?.command === "refresh") {
          // Acknowledge first, so a reload cannot re-run the same command.
          await deviceApi.acknowledgeCommand(assignment.pending_command.id);
          window.location.reload();
          return;
        }

        if (!assignment.has_assignment) {
          if (!contentRef.current) setStatus("waiting");
          return;
        }

        await applyAssignment(assignment);
      } catch (err) {
        if (!mounted.current || signal?.aborted) return;
        if (err?.status === 401) {
          // Revoked or re-paired elsewhere: drop the credential and show the
          // pairing screen rather than retrying forever.
          writeStored(DEVICE_TOKEN_KEY, null);
          setDeviceToken(null);
          setStatus("pairing");
          return;
        }
        setOnline(false);
        if (!contentRef.current) setStatus(reason === "startup" ? "offline-empty" : "offline");
      } finally {
        syncing.current = false;
      }
    },
    [applyAssignment]
  );

  // ── Network awareness ─────────────────────────────────────────────────────
  // Declared after syncAssignment so the callback it closes over already
  // exists, rather than relying on effect timing.
  useEffect(() => {
    const goOnline = () => {
      setOnline(true);
      syncAssignment("reconnect");
    };
    const goOffline = () => setOnline(false);

    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, [syncAssignment]);

  // ── Heartbeat + polling fallback ──────────────────────────────────────────
  useEffect(() => {
    if (!deviceToken) return undefined;

    const beat = async (signal) => {
      try {
        const response = await deviceApi.heartbeat({
          revision: currentRevision.current,
          version_id: contentRef.current?.versionId ?? null,
        }, { signal });
        if (signal.aborted) return;
        setOnline(true);
        if (response.needs_update || response.pending_command) {
          syncAssignment("heartbeat");
        }
        await flushAcknowledgment();
      } catch (err) {
        if (signal.aborted) return;
        if (err?.status === 401) {
          writeStored(DEVICE_TOKEN_KEY, null);
          setDeviceToken(null);
          return;
        }
        setOnline(false);
      }
    };

    const heartbeat = startPolling(beat, {
      intervalMs: DEFAULT_HEARTBEAT_MS, pauseWhenHidden: false,
    });
    const assignment = startPolling((signal) => syncAssignment("poll", signal), {
      intervalMs: DEFAULT_POLL_MS, pauseWhenHidden: false,
    });

    return () => {
      heartbeat.stop();
      assignment.stop();
    };
  }, [deviceToken, syncAssignment, flushAcknowledgment]);

  // ── Websocket for instant updates ─────────────────────────────────────────
  useEffect(() => {
    if (!deviceToken) return undefined;

    const handles = timers.current;
    let attempt = 0;
    let closed = false;

    const connect = () => {
      if (closed) return;
      // Never stack sockets: close any previous one before opening a new one.
      if (socket.current) {
        try {
          socket.current.close();
        } catch {
          /* ignore */
        }
        socket.current = null;
      }

      let ws;
      try {
        ws = openSocket("/api/ws/device", deviceToken);
      } catch {
        handles.reconnect = setTimeout(connect, backoffDelay(attempt++));
        return;
      }
      socket.current = ws;

      ws.onopen = () => {
        attempt = 0;
        setOnline(true);
        // The socket only ever says "something changed"; the database is the
        // source of truth, so always re-read the assignment.
        syncAssignment("socket-open");
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (["display.assignment", "display.command", "display.revoked"].includes(message.type)) {
            syncAssignment("socket");
          }
        } catch {
          /* ignore malformed frames */
        }
      };

      ws.onclose = () => {
        socket.current = null;
        if (closed) return;
        handles.reconnect = setTimeout(connect, backoffDelay(attempt++));
      };

      ws.onerror = () => {
        try {
          ws.close();
        } catch {
          /* onclose handles the retry */
        }
      };
    };

    connect();

    return () => {
      closed = true;
      clearTimeout(handles.reconnect);
      if (socket.current) {
        try {
          socket.current.close();
        } catch {
          /* ignore */
        }
        socket.current = null;
      }
    };
  }, [deviceToken, syncAssignment]);

  // Release the object URL when the player unmounts.
  useEffect(
    () => () => {
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    },
    []
  );

  const handlePaired = (token) => {
    writeStored(DEVICE_TOKEN_KEY, token);
    setDeviceToken(token);
    setStatus("syncing");
  };

  if (!deviceToken) {
    return <PairingScreen onPaired={handlePaired} />;
  }

  return (
    <Stage>
      {content && status !== "expired" ? (
        content.kind === "board_mp4" ? (
          <video
            key={content.url}
            src={content.url}
            autoPlay
            muted
            loop
            playsInline
            style={mediaStyle}
            onError={() => setStatus("error")}
          />
        ) : (
          <img
            key={content.url}
            src={content.url}
            alt="Rate board"
            style={mediaStyle}
          />
        )
      ) : (
        <Notice status={status} online={online} />
      )}

      <ConnectionDot online={online} />
      {fatal && <ErrorToast message={fatal} onDismiss={() => setFatal(null)} />}
    </Stage>
  );
}

/** Decode the media before it is allowed on screen. */
function validateMedia(url, kind) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("Media timeout")), 30000);

    if (kind === "board_mp4") {
      const video = document.createElement("video");
      video.muted = true;
      video.preload = "auto";
      video.onloadeddata = () => {
        clearTimeout(timeout);
        resolve();
      };
      video.onerror = () => {
        clearTimeout(timeout);
        reject(new Error("Video tidak dapat diputar di perangkat ini"));
      };
      video.src = url;
      return;
    }

    const image = new Image();
    image.onload = () => {
      clearTimeout(timeout);
      if (!image.naturalWidth) {
        reject(new Error("Gambar rusak"));
        return;
      }
      resolve();
    };
    image.onerror = () => {
      clearTimeout(timeout);
      reject(new Error("Gambar tidak dapat dibaca"));
    };
    image.src = url;
  });
}

const mediaStyle = {
  width: "100%",
  height: "100%",
  // contain, never cover: the board is never cropped or stretched.
  objectFit: "contain",
  display: "block",
  background: "#000",
};

function Stage({ children }) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "#000",
        overflow: "hidden",
        fontFamily: "'Segoe UI', system-ui, sans-serif",
      }}
    >
      {children}
    </div>
  );
}

const NOTICES = {
  starting: { icon: "⏳", title: "Menyiapkan layar...", body: "" },
  syncing: { icon: "⏳", title: "Mengambil rate terbaru...", body: "" },
  loading: { icon: "⏳", title: "Memuat rate board...", body: "" },
  updating: { icon: "⏳", title: "Memperbarui...", body: "" },
  waiting: {
    icon: "📺",
    title: "Perangkat siap",
    body: "Belum ada rate board yang ditayangkan ke layar ini. Admin dapat menayangkannya dari dashboard.",
  },
  expired: {
    icon: "🕒",
    title: "Rate sedang diperbarui",
    body: "Rate yang terakhir ditampilkan sudah melewati masa berlakunya.",
  },
  offline: {
    icon: "📡",
    title: "Koneksi terputus",
    body: "Menampilkan rate terakhir yang tersimpan. Akan otomatis tersambung kembali.",
  },
  "offline-empty": {
    icon: "📡",
    title: "Tidak ada koneksi",
    body: "Perangkat belum pernah menerima rate board, jadi belum ada yang bisa ditampilkan. Periksa jaringan.",
  },
  error: {
    icon: "⚠️",
    title: "Gagal memuat rate board",
    body: "Perangkat akan mencoba lagi secara otomatis. Admin sudah menerima laporan kegagalan ini.",
  },
};

function Notice({ status, online }) {
  const notice = NOTICES[status] || NOTICES.starting;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        color: "#fff",
        padding: "6vmin",
        gap: "1.6vmin",
      }}
    >
      <div style={{ fontSize: "9vmin" }}>{notice.icon}</div>
      <div style={{ fontSize: "4vmin", fontWeight: 800 }}>{notice.title}</div>
      {notice.body && (
        <div
          style={{
            fontSize: "2.2vmin",
            color: "rgba(255,255,255,0.72)",
            maxWidth: "70vw",
            lineHeight: 1.6,
          }}
        >
          {notice.body}
        </div>
      )}
      {!online && status !== "offline" && status !== "offline-empty" && (
        <div style={{ fontSize: "1.8vmin", color: "rgba(255,255,255,0.5)" }}>
          Sedang offline
        </div>
      )}
    </div>
  );
}

function ConnectionDot({ online }) {
  return (
    <div
      title={online ? "Tersambung" : "Terputus"}
      style={{
        position: "absolute",
        right: 14,
        bottom: 14,
        width: 9,
        height: 9,
        borderRadius: "50%",
        background: online ? "rgba(76,175,80,0.65)" : "rgba(244,67,54,0.75)",
        boxShadow: "0 0 6px rgba(0,0,0,0.6)",
      }}
    />
  );
}

function ErrorToast({ message, onDismiss }) {
  return (
    <div
      onClick={onDismiss}
      style={{
        position: "absolute",
        left: "50%",
        bottom: 24,
        transform: "translateX(-50%)",
        background: "rgba(198,40,40,0.92)",
        color: "#fff",
        padding: "9px 18px",
        borderRadius: 8,
        fontSize: 13,
        cursor: "pointer",
      }}
    >
      {message}
    </div>
  );
}
