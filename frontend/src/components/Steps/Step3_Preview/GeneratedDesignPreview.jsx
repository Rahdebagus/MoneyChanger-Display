// ─── Generated Design Preview Component ───────────────────────────────────────
//
// Step 3 of the generator. The board shown here is the PNG the save endpoint wrote
// for this saved version - the same file a TV will display - so what is
// previewed and what is published can never differ.

import { useState } from "react";

import { Badge, ErrorBanner, SuccessBanner } from "../../common/ui.jsx";
import { COLORS } from "../../common/theme.js";
import { useAuthedMedia } from "../../../hooks/useAuthedMedia.js";
import { downloadMedia } from "../../../services/apiClient.js";
import PublishDialog from "../../../features/displays/PublishDialog.jsx";

export function GeneratedDesignPreview({ version, onReset }) {
  const { url: previewUrl, loading: previewLoading, error: previewError } =
    useAuthedMedia(version?.png_url);

  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [showPublish, setShowPublish] = useState(false);

  const downloadPng = async () => {
    if (!version?.png_url) return;
    try {
      await downloadMedia(version.png_url, `pam_rate_board_v${version.version}.png`);
    } catch (err) {
      setError(err);
    }
  };

  return (
    <div>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 12,
          alignItems: "flex-start",
          marginBottom: 20,
          "@media (min-width: 640px)": {
            flexDirection: "row",
            justifyContent: "space-between",
            alignItems: "center",
          },
        }}
      >
        <div>
          <h2
            style={{
              fontSize: 18,
              fontWeight: 800,
              color: "#0D47A1",
              marginBottom: 4,
              "@media (min-width: 640px)": { fontSize: 20 },
            }}
          >
            ✅ Rate Board Tersimpan
          </h2>
          <p style={{ fontSize: 13, color: "#607D8B", margin: 0 }}>
            Versi v{version?.version} tersimpan sebagai riwayat. Menyimpan tidak
            mengubah tampilan TV — gunakan “Tampilkan ke Display” untuk menayangkan.
          </p>
        </div>
        <Badge tone="success" style={{ fontSize: 13, padding: "6px 14px" }}>
          ✓ v{version?.version} siap
        </Badge>
      </div>

      <ErrorBanner error={error || previewError} onDismiss={() => setError(null)} />
      <SuccessBanner message={notice} onDismiss={() => setNotice(null)} />

      <div
        className="animate-board-reveal"
        style={{
          borderRadius: 14,
          overflow: "hidden",
          boxShadow: "0 8px 32px rgba(21,101,192,0.18)",
          border: "2px solid #BBDEFB",
          marginBottom: 16,
          background: "#fff",
          minHeight: 160,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {previewLoading ? (
          <span style={{ color: COLORS.muted, fontSize: 14, padding: 40 }}>
            Memuat pratinjau...
          </span>
        ) : previewUrl ? (
          <img
            src={previewUrl}
            alt={`Rate board versi ${version?.version}`}
            style={{ width: "100%", display: "block", maxHeight: "70vh", objectFit: "contain" }}
          />
        ) : (
          <span style={{ color: COLORS.muted, fontSize: 14, padding: 40 }}>
            Pratinjau tidak tersedia.
          </span>
        )}
      </div>

      <div className="button-group" style={{ flexDirection: "row", flexWrap: "wrap" }}>
        <button
          onClick={downloadPng}
          style={{
            background: "linear-gradient(135deg, #0D47A1, #1E88E5)",
            color: "#fff",
            border: "none",
            fontWeight: 900,
            cursor: "pointer",
            boxShadow: "0 6px 20px rgba(13,71,161,0.3)",
          }}
        >
          ⬇️ Download PNG
        </button>
        <button
          onClick={() => setShowPublish(true)}
          style={{
            background: "#fff",
            color: "#1565C0",
            border: "2px solid #1E88E5",
            fontWeight: 900,
            cursor: "pointer",
          }}
        >
          📺 Tampilkan ke Display
        </button>
        <button
          onClick={onReset}
          style={{
            background: "#fff",
            color: "#607D8B",
            border: "1px solid #CFD8DC",
            fontWeight: 700,
            cursor: "pointer",
          }}
        >
          🔄 Rate Board Baru
        </button>
      </div>

      {showPublish && (
        <PublishDialog
          version={version}
          onClose={() => setShowPublish(false)}
          onPublished={() => setNotice("Rate board dikirim ke display yang dipilih.")}
        />
      )}
    </div>
  );
}
