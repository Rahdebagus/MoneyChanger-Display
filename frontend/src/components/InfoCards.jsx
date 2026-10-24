// ─── Info Cards Component ─────────────────────────────────────────────────────

export function InfoCards() {
  const cards = [
    {
      icon: "🔍",
      title: "Auto OCR",
      desc: "PaddleOCR extracts currency codes and rates from any board image",
    },
    {
      icon: "✏️",
      title: "Manual Edit",
      desc: "Review and correct extracted rates before generating the design",
    },
    {
      icon: "🖼️",
      title: "PAM Branded",
      desc: "Export a pixel-perfect PAM-branded rate board ready for display",
    },
  ];

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr",
        gap: 16,
        marginTop: 24,
        "@media (min-width: 640px)": {
          gridTemplateColumns: "repeat(3, 1fr)",
        }
      }}
    >
      {cards.map((card) => (
        <div
          key={card.title}
          style={{
            background: "#fff",
            borderRadius: 14,
            padding: "20px 16px",
            border: "1px solid #E3F2FD",
            boxShadow: "0 2px 10px rgba(21,101,192,0.06)",
          }}
        >
          <div style={{ fontSize: 28, marginBottom: 10 }}>{card.icon}</div>
          <div
            style={{
              fontWeight: 800,
              color: "#0D47A1",
              fontSize: 15,
              marginBottom: 6,
            }}
          >
            {card.title}
          </div>
          <div style={{ fontSize: 13, color: "#78909C", lineHeight: 1.5 }}>
            {card.desc}
          </div>
        </div>
      ))}
    </div>
  );
}
