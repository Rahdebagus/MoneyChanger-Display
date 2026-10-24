// ─── Shared UI Primitives ─────────────────────────────────────────────────────
//
// Small building blocks reused across the admin pages. They reproduce the
// palette and shapes the generator page already uses (navy #0D47A1, blue
// #1565C0 / #1E88E5, soft blue-tinted shadows, rounded cards) so the new
// screens read as the same application rather than a bolted-on admin panel.

import { BADGE_TONES, COLORS } from "./theme.js";

export function Card({ children, style, padding = 24 }) {
  return (
    <div
      style={{
        background: "#fff",
        borderRadius: 16,
        padding,
        border: "1px solid #E3F2FD",
        boxShadow: "0 4px 20px rgba(21,101,192,0.08)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 12,
        alignItems: "flex-start",
        justifyContent: "space-between",
        marginBottom: 24,
      }}
    >
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 900, color: COLORS.navy, margin: 0 }}>
          {title}
        </h1>
        {subtitle && (
          <p style={{ color: COLORS.muted, fontSize: 14, margin: "6px 0 0" }}>{subtitle}</p>
        )}
      </div>
      {actions && <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>{actions}</div>}
    </div>
  );
}

const BUTTON_VARIANTS = {
  primary: {
    background: "linear-gradient(135deg, #0D47A1, #1E88E5)",
    color: "#fff",
    border: "none",
    boxShadow: "0 4px 14px rgba(13,71,161,0.25)",
  },
  secondary: {
    background: "#fff",
    color: COLORS.blue,
    border: `1.5px solid ${COLORS.lightBlue}`,
  },
  subtle: {
    background: "#fff",
    color: COLORS.muted,
    border: `1px solid ${COLORS.border}`,
  },
  danger: {
    background: "#fff",
    color: COLORS.red,
    border: "1.5px solid #FFCDD2",
  },
  success: {
    background: "linear-gradient(135deg, #1B5E20, #2E7D32)",
    color: "#fff",
    border: "none",
    boxShadow: "0 4px 14px rgba(27,94,32,0.25)",
  },
};

export function Button({
  children,
  variant = "primary",
  size = "md",
  disabled = false,
  style,
  ...rest
}) {
  const sizing =
    size === "sm"
      ? { padding: "7px 12px", fontSize: 12.5 }
      : { padding: "10px 18px", fontSize: 14 };

  return (
    <button
      disabled={disabled}
      style={{
        ...BUTTON_VARIANTS[variant],
        ...sizing,
        borderRadius: 10,
        fontWeight: 800,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.55 : 1,
        transition: "transform 0.15s, opacity 0.15s",
        whiteSpace: "nowrap",
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Badge({ children, tone = "neutral", style }) {
  const palette = BADGE_TONES[tone] ?? BADGE_TONES.neutral;
  return (
    <span
      style={{
        display: "inline-block",
        background: palette.bg,
        color: palette.fg,
        borderRadius: 50,
        padding: "3px 10px",
        fontSize: 11.5,
        fontWeight: 800,
        letterSpacing: 0.2,
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {children}
    </span>
  );
}

export function Field({ label, hint, children }) {
  return (
    <label style={{ display: "block", marginBottom: 14 }}>
      <span
        style={{
          display: "block",
          fontSize: 11,
          fontWeight: 800,
          color: COLORS.muted,
          letterSpacing: 0.5,
          marginBottom: 5,
        }}
      >
        {label}
      </span>
      {children}
      {hint && (
        <span style={{ display: "block", fontSize: 11, color: COLORS.faint, marginTop: 4 }}>
          {hint}
        </span>
      )}
    </label>
  );
}

export function ErrorBanner({ error, onDismiss }) {
  if (!error) return null;
  const message = typeof error === "string" ? error : error.displayMessage || error.message;

  return (
    <div
      role="alert"
      style={{
        background: COLORS.redBg,
        border: "1px solid #FFCDD2",
        color: COLORS.red,
        borderRadius: 10,
        padding: "11px 15px",
        fontSize: 13.5,
        marginBottom: 16,
        display: "flex",
        justifyContent: "space-between",
        gap: 12,
        alignItems: "flex-start",
      }}
    >
      <span>⚠️ {message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          style={{
            background: "none",
            border: "none",
            color: COLORS.red,
            cursor: "pointer",
            fontWeight: 800,
            fontSize: 15,
            lineHeight: 1,
          }}
          aria-label="Tutup"
        >
          ×
        </button>
      )}
    </div>
  );
}

export function SuccessBanner({ message, onDismiss }) {
  if (!message) return null;
  return (
    <div
      style={{
        background: COLORS.greenBg,
        border: "1px solid #A5D6A7",
        color: COLORS.green,
        borderRadius: 10,
        padding: "11px 15px",
        fontSize: 13.5,
        marginBottom: 16,
        display: "flex",
        justifyContent: "space-between",
        gap: 12,
      }}
    >
      <span>✓ {message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          style={{
            background: "none",
            border: "none",
            color: COLORS.green,
            cursor: "pointer",
            fontWeight: 800,
            fontSize: 15,
            lineHeight: 1,
          }}
          aria-label="Tutup"
        >
          ×
        </button>
      )}
    </div>
  );
}

export function Spinner({ label = "Memuat..." }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 10,
        padding: "36px 12px",
        color: COLORS.muted,
        fontSize: 14,
      }}
    >
      <span className="pam-spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

export function EmptyState({ icon = "📭", title, description, action }) {
  return (
    <div style={{ textAlign: "center", padding: "44px 20px", color: COLORS.muted }}>
      <div style={{ fontSize: 38, marginBottom: 12 }}>{icon}</div>
      <div style={{ fontWeight: 800, color: COLORS.navy, fontSize: 16, marginBottom: 6 }}>
        {title}
      </div>
      {description && (
        <div style={{ fontSize: 13.5, maxWidth: 420, margin: "0 auto 16px" }}>{description}</div>
      )}
      {action}
    </div>
  );
}

export function Table({ columns, rows, renderRow, emptyMessage = "Belum ada data." }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5 }}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column}
                style={{
                  textAlign: "left",
                  padding: "10px 12px",
                  borderBottom: "2px solid #E3F2FD",
                  color: COLORS.faint,
                  fontSize: 11,
                  fontWeight: 800,
                  letterSpacing: 0.6,
                  textTransform: "uppercase",
                  whiteSpace: "nowrap",
                }}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                style={{ padding: "28px 12px", textAlign: "center", color: COLORS.faint }}
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map(renderRow)
          )}
        </tbody>
      </table>
    </div>
  );
}

export function StatTile({ label, value, tone = "info", hint }) {
  const palette = BADGE_TONES[tone] ?? BADGE_TONES.info;
  return (
    <Card padding={18} style={{ minWidth: 0 }}>
      <div
        style={{
          fontSize: 11,
          fontWeight: 800,
          color: COLORS.faint,
          letterSpacing: 0.6,
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: 30, fontWeight: 900, color: palette.fg, lineHeight: 1.25 }}>
        {value}
      </div>
      {hint && <div style={{ fontSize: 12, color: COLORS.muted }}>{hint}</div>}
    </Card>
  );
}
