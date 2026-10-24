// ─── Currency Input Component ─────────────────────────────────────────────────

import { CURRENCY_LABELS } from "../../../constants/currencies.js";

export function CurrencyInput({ code, value, onChange }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "8px 12px",
        borderRadius: 10,
        background: value ? "#F0F7FF" : "#FAFAFA",
        border: `1px solid ${value ? "#BBDEFB" : "#ECEFF1"}`,
        transition: "all 0.2s",
        gap: 8,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 800, color: "#0D47A1", fontSize: 14, "@media (min-width: 640px)": { fontSize: 15 } }}>
          {code}
        </div>
        <div style={{ fontSize: 10, color: "#90A4AE" }}>
          {CURRENCY_LABELS[code]}
        </div>
      </div>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(code, e.target.value)}
        placeholder="0"
        style={{
          width: 80,
          textAlign: "right",
          border: "1px solid #BBDEFB",
          borderRadius: 8,
          padding: "6px 8px",
          fontSize: 14,
          fontWeight: 700,
          color: "#0D47A1",
          background: "#fff",
          outline: "none",
          flexShrink: 0,
          "@media (min-width: 640px)": { width: 100, padding: "6px 10px", fontSize: 15 }
        }}
      />
    </div>
  );
}
