// ─── Step Badge Component ─────────────────────────────────────────────────────

export function StepBadge({ n, label, active, done }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        opacity: active || done ? 1 : 0.4,
      }}
    >
      <div
        style={{
          width: 28,
          height: 28,
          borderRadius: "50%",
          background: done ? "#1565C0" : active ? "#1E88E5" : "#E3F2FD",
          color: done || active ? "#fff" : "#90A4AE",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontWeight: 800,
          fontSize: 13,
          border: active ? "2px solid #1E88E5" : "2px solid transparent",
          boxShadow: active ? "0 0 0 3px rgba(30,136,229,0.2)" : "none",
          transition: "all 0.3s",
        }}
      >
        {done ? "✓" : n}
      </div>
      <span
        style={{
          fontSize: 13,
          color: active ? "#1565C0" : done ? "#1565C0" : "#90A4AE",
          fontWeight: done || active ? 700 : 400,
        }}
      >
        {label}
      </span>
    </div>
  );
}
