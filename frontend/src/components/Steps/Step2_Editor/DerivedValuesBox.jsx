import { useEffect } from "react";

export function DerivedValuesBox({ usdValue, onUsdTChange, onUsdKChange, usdTValue, usdKValue }) {
  const usd = Number(usdValue || 0);
  const defaultUsdT = usd ? usd - 200 : "";
  const defaultUsdK = usd ? 14000 : "";

  // Update to default values when USD changes
  useEffect(() => {
    if (usd > 0 && !usdTValue) {
      onUsdTChange("USDT", defaultUsdT);
    }
    if (usd > 0 && !usdKValue) {
      onUsdKChange("USDK", defaultUsdK);
    }
  }, [usd, defaultUsdT, defaultUsdK, usdTValue, usdKValue, onUsdTChange, onUsdKChange]);

  return (
    <div
      style={{
        background: "linear-gradient(135deg, #E3F2FD, #EDE7F6)",
        borderRadius: 12,
        padding: "12px 14px",
        marginBottom: 16,
        border: "1px solid #BBDEFB",
        "@media (min-width: 640px)": { padding: "14px 16px", marginBottom: 20 }
      }}
    >
      <div style={{ fontWeight: 800, color: "#0D47A1", fontSize: 12, marginBottom: 8, "@media (min-width: 640px)": { fontSize: 13 } }}>
        📐 Auto-Derived Values (from USD) - Editable
      </div>
      <div style={{ display: "flex", gap: 12, "@media (min-width: 640px)": { gap: 16 } }}>
        {[
          ["USDT", usdTValue || defaultUsdT, onUsdTChange],
          ["USDK", usdKValue || defaultUsdK, onUsdKChange],
        ].map(([label, val, onChange]) => (
          <div
            key={label}
            style={{
              background: "#fff",
              borderRadius: 8,
              padding: "8px 12px",
              flex: 1,
              textAlign: "center",
              border: "1px solid #BBDEFB",
              "@media (min-width: 640px)": { padding: "8px 16px" }
            }}
          >
            <div style={{ fontSize: 11, color: "#607D8B", fontWeight: 600, "@media (min-width: 640px)": { fontSize: 12 } }}>{label}</div>
            <input
              type="number"
              value={val}
              onChange={(e) => onChange(label, e.target.value ? Number(e.target.value) : "")}
              placeholder="0"
              style={{
                width: "100%",
                textAlign: "center",
                border: "1px solid #BBDEFB",
                borderRadius: 6,
                padding: "8px 6px",
                fontSize: 13,
                fontWeight: 900,
                color: "#1565C0",
                background: "#F0F7FF",
                outline: "none",
                boxSizing: "border-box",
                minHeight: "40px",
                cursor: "text"
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
