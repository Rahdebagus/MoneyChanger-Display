// ─── Pairing Screen ───────────────────────────────────────────────────────────
//
// Shown on a TV that has no device credential yet. It displays a short code
// for an admin to type into the dashboard, then claims its own credential.
// The admin never handles the device secret, and no admin account is ever
// entered on the TV.
//
// Fullscreen is offered as a button. A browser only grants it from a real user
// gesture, so the page cannot promise to go fullscreen on its own - for an
// unattended install, the browser's own kiosk mode is the right answer.

import { useCallback, useEffect, useRef, useState } from "react";

import { deviceApi } from "../../services/apiClient.js";

const POLL_MS = 3000;

export default function PairingScreen({ onPaired }) {
  const [code, setCode] = useState(null);
  const [session, setSession] = useState(null);
  const [expiresIn, setExpiresIn] = useState(0);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(true);

  const pollTimer = useRef(null);
  const countdownTimer = useRef(null);
  const mounted = useRef(true);

  const startPairing = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await deviceApi.startPairing();
      if (!mounted.current) return;
      setCode(result.code);
      setSession(result.device_session);
      setExpiresIn(result.expires_in);
    } catch (err) {
      if (mounted.current) {
        setError(
          err?.status === 0
            ? "Tidak dapat menghubungi server. Periksa jaringan TV ini."
            : err.displayMessage || err.message
        );
      }
    } finally {
      if (mounted.current) setBusy(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    const startup = setTimeout(startPairing, 0);
    return () => {
      mounted.current = false;
      clearTimeout(startup);
      clearTimeout(pollTimer.current);
      clearInterval(countdownTimer.current);
    };
  }, [startPairing]);

  // Countdown, and request a fresh code once this one expires.
  useEffect(() => {
    clearInterval(countdownTimer.current);
    if (!expiresIn) return undefined;

    countdownTimer.current = setInterval(() => {
      setExpiresIn((value) => {
        if (value <= 1) {
          clearInterval(countdownTimer.current);
          startPairing();
          return 0;
        }
        return value - 1;
      });
    }, 1000);

    return () => clearInterval(countdownTimer.current);
  }, [expiresIn, startPairing]);

  // Poll until an admin approves, then claim the credential exactly once.
  useEffect(() => {
    if (!session) return undefined;

    const poll = async () => {
      try {
        const status = await deviceApi.pairingStatus(session);

        if (status.state === "approved") {
          const claim = await deviceApi.claim(session);
          if (mounted.current) onPaired(claim.device_token);
          return;
        }

        if (status.state === "expired") {
          startPairing();
          return;
        }
      } catch {
        /* keep polling: a transient network blip must not strand the TV */
      }

      if (mounted.current) {
        pollTimer.current = setTimeout(poll, POLL_MS);
      }
    };

    pollTimer.current = setTimeout(poll, POLL_MS);
    return () => clearTimeout(pollTimer.current);
  }, [session, onPaired, startPairing]);

  const goFullscreen = () => {
    const element = document.documentElement;
    const request =
      element.requestFullscreen ||
      element.webkitRequestFullscreen ||
      element.msRequestFullscreen;
    if (request) {
      request.call(element).catch(() => {
        setError(
          "Browser menolak mode layar penuh. Gunakan mode kiosk pada browser TV."
        );
      });
    }
  };

  const minutes = Math.floor(expiresIn / 60);
  const seconds = String(expiresIn % 60).padStart(2, "0");

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "linear-gradient(140deg, #0A1F6B, #0D47A1 55%, #1565C0)",
        color: "#fff",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "'Segoe UI', system-ui, sans-serif",
        padding: "5vmin",
        textAlign: "center",
        gap: "2.4vmin",
      }}
    >
      <div style={{ fontSize: "2.6vmin", opacity: 0.82, letterSpacing: 2 }}>
        PAM MONEY CHANGER · RATE DISPLAY
      </div>

      <div style={{ fontSize: "4vmin", fontWeight: 800 }}>
        Perangkat belum terdaftar
      </div>

      {error ? (
        <div
          style={{
            background: "rgba(198,40,40,0.25)",
            border: "1px solid rgba(255,205,210,0.5)",
            borderRadius: 12,
            padding: "2.4vmin 3.4vmin",
            fontSize: "2.2vmin",
            maxWidth: "70vw",
          }}
        >
          {error}
          <div style={{ marginTop: "1.6vmin" }}>
            <button onClick={startPairing} style={buttonStyle}>
              Coba Lagi
            </button>
          </div>
        </div>
      ) : busy && !code ? (
        <div style={{ fontSize: "2.4vmin", opacity: 0.8 }}>Meminta kode pairing...</div>
      ) : (
        <>
          <div style={{ fontSize: "2.2vmin", opacity: 0.8, maxWidth: "70vw" }}>
            Masukkan kode berikut pada dashboard admin:
            <br />
            Display → Pasangkan Display Baru
          </div>

          <div
            style={{
              fontSize: "13vmin",
              fontWeight: 900,
              letterSpacing: "1.6vmin",
              fontVariantNumeric: "tabular-nums",
              background: "rgba(255,255,255,0.1)",
              borderRadius: "2vmin",
              padding: "2vmin 4vmin 2vmin 5.6vmin",
              border: "2px solid rgba(255,255,255,0.25)",
            }}
          >
            {code}
          </div>

          <div style={{ fontSize: "2vmin", opacity: 0.65 }}>
            Kode berlaku {minutes}:{seconds} · diperbarui otomatis
          </div>

          <div style={{ fontSize: "1.9vmin", opacity: 0.55, maxWidth: "60vw" }}>
            Layar ini akan berganti sendiri begitu admin menyetujui. Tidak perlu
            memasukkan akun admin di TV.
          </div>
        </>
      )}

      <button onClick={goFullscreen} style={{ ...buttonStyle, marginTop: "2vmin" }}>
        Layar Penuh
      </button>
    </div>
  );
}

const buttonStyle = {
  background: "rgba(255,255,255,0.14)",
  border: "1.5px solid rgba(255,255,255,0.4)",
  color: "#fff",
  borderRadius: 10,
  padding: "1.4vmin 3vmin",
  fontSize: "2vmin",
  fontWeight: 700,
  cursor: "pointer",
};
