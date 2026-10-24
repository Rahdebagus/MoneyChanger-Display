// ─── Design Tokens ────────────────────────────────────────────────────────────
//
// Kept in a plain module rather than alongside the components so that the
// component file only exports components, which is what React Fast Refresh
// needs to hot-reload reliably.
//
// The palette reproduces what the generator page already used, so the admin
// screens read as the same application.

export const COLORS = {
  navy: "#0D47A1",
  blue: "#1565C0",
  lightBlue: "#1E88E5",
  pale: "#E3F2FD",
  paler: "#F0F7FF",
  bg: "#F0F4F8",
  text: "#37474F",
  muted: "#607D8B",
  faint: "#90A4AE",
  border: "#CFD8DC",
  green: "#2E7D32",
  greenBg: "#E8F5E9",
  amber: "#EF6C00",
  amberBg: "#FFF3E0",
  red: "#C62828",
  redBg: "#FFEBEE",
};

export const BADGE_TONES = {
  neutral: { bg: "#ECEFF1", fg: COLORS.muted },
  info: { bg: COLORS.pale, fg: COLORS.blue },
  success: { bg: COLORS.greenBg, fg: COLORS.green },
  warning: { bg: COLORS.amberBg, fg: COLORS.amber },
  danger: { bg: COLORS.redBg, fg: COLORS.red },
};

export const inputStyle = {
  width: "100%",
  padding: "9px 12px",
  border: "1.5px solid #BBDEFB",
  borderRadius: 9,
  fontSize: 14,
  color: COLORS.navy,
  background: "#fff",
  outline: "none",
  boxSizing: "border-box",
  fontFamily: "inherit",
};
