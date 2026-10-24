// ─── Login ────────────────────────────────────────────────────────────────────
//
// There is no public registration. Accounts come from an admin or the
// bootstrap command, which is why this page offers no "sign up" path.

import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import pamLogo from "../../assets/pam_logo.png";
import { Button, Card, ErrorBanner, Field } from "../../components/common/ui.jsx";
import { COLORS, inputStyle } from "../../components/common/theme.js";
import { useAuth } from "../../hooks/useAuth.js";
import { APP_COMPANY } from "../../constants/currencies.js";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const redirectTo = location.state?.from ?? "/";

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username.trim(), password);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: COLORS.bg,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
        fontFamily: "'Segoe UI', system-ui, sans-serif",
      }}
    >
      <Card style={{ width: "100%", maxWidth: 400 }} padding={32}>
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <img
            src={pamLogo}
            alt="PAM Money Changer"
            style={{ height: 64, objectFit: "contain", marginBottom: 10 }}
          />
          <h1 style={{ fontSize: 20, fontWeight: 900, color: COLORS.navy, margin: 0 }}>
            Rate Board System
          </h1>
          <p style={{ color: COLORS.muted, fontSize: 13, margin: "6px 0 0" }}>
            Masuk untuk mengelola rate dan display
          </p>
        </div>

        <ErrorBanner error={error} onDismiss={() => setError(null)} />

        <form onSubmit={handleSubmit}>
          <Field label="USERNAME">
            <input
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              autoFocus
              required
              style={inputStyle}
            />
          </Field>

          <Field label="PASSWORD">
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
              style={inputStyle}
            />
          </Field>

          <Button type="submit" disabled={busy} style={{ width: "100%", marginTop: 6 }}>
            {busy ? "Memproses..." : "Masuk"}
          </Button>
        </form>

        <p
          style={{
            textAlign: "center",
            color: COLORS.faint,
            fontSize: 11.5,
            marginTop: 22,
            marginBottom: 0,
          }}
        >
          {APP_COMPANY}
        </p>
      </Card>
    </div>
  );
}
