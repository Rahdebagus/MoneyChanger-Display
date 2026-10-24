// ─── Publish Dialog ───────────────────────────────────────────────────────────
//
// Choosing targets and (optionally) a schedule. Publishing is a deliberate,
// separate step from saving, so this dialog is the only place a saved version
// reaches a TV.

import { useEffect, useMemo, useState } from "react";

import { Badge, Button, ErrorBanner, Field, Spinner } from "../../components/common/ui.jsx";
import { COLORS, inputStyle } from "../../components/common/theme.js";
import { useAuth } from "../../hooks/useAuth.js";
import { displayApi, publicationApi } from "../../services/apiClient.js";

/** A stable key so a double-click or a retry cannot publish twice. */
function newIdempotencyKey() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `pub-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** datetime-local gives wall-clock text; the API wants an absolute instant. */
function toIsoOrNull(localValue) {
  if (!localValue) return null;
  const parsed = new Date(localValue);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

export default function PublishDialog({ version, onClose, onPublished }) {
  const { branches, isAdmin } = useAuth();

  const [displays, setDisplays] = useState([]);
  const [selected, setSelected] = useState([]);
  const [mode, setMode] = useState("displays");
  const [branchId, setBranchId] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [idempotencyKey] = useState(newIdempotencyKey);

  useEffect(() => {
    let cancelled = false;
    displayApi
      .list()
      .then((rows) => {
        if (cancelled) return;
        setDisplays(rows);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const eligible = useMemo(
    () => displays.filter((d) => d.is_active && !d.revoked_at && d.is_paired),
    [displays]
  );

  const toggle = (id) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((value) => value !== id) : [...prev, id]
    );
  };

  const handlePublish = async () => {
    setError(null);
    setBusy(true);
    try {
      const payload = {
        version_id: version.id,
        idempotency_key: idempotencyKey,
        scheduled_at: toIsoOrNull(scheduledAt),
        valid_until: toIsoOrNull(validUntil),
      };

      if (mode === "branch") {
        if (!branchId) throw new Error("Pilih cabang terlebih dahulu.");
        payload.branch_id = Number(branchId);
      } else {
        if (selected.length === 0) throw new Error("Pilih minimal satu display.");
        payload.display_ids = selected;
      }

      const result = await publicationApi.create(payload);
      onPublished?.(result);
      onClose();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  if (!isAdmin) {
    return (
      <Backdrop onClose={onClose}>
        <h2 style={headingStyle}>Tampilkan ke Display</h2>
        <p style={{ color: COLORS.muted, fontSize: 14 }}>
          Hanya admin yang dapat menayangkan rate ke display. Versi ini sudah tersimpan
          dan dapat ditayangkan oleh admin dari halaman Riwayat Rate.
        </p>
        <div style={{ textAlign: "right", marginTop: 20 }}>
          <Button variant="subtle" onClick={onClose}>
            Tutup
          </Button>
        </div>
      </Backdrop>
    );
  }

  return (
    <Backdrop onClose={onClose}>
      <h2 style={headingStyle}>Tampilkan ke Display</h2>
      <p style={{ color: COLORS.muted, fontSize: 13, marginTop: 0 }}>
        Versi <strong>v{version.version}</strong> akan dikirim ke perangkat yang dipilih.
      </p>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <Button
          size="sm"
          variant={mode === "displays" ? "primary" : "subtle"}
          onClick={() => setMode("displays")}
        >
          Pilih Display
        </Button>
        <Button
          size="sm"
          variant={mode === "branch" ? "primary" : "subtle"}
          onClick={() => setMode("branch")}
        >
          Satu Cabang
        </Button>
      </div>

      {loading ? (
        <Spinner label="Memuat display..." />
      ) : mode === "branch" ? (
        <>
          <Field
            label="CABANG"
            hint="Display yang dipasangkan setelah ini tidak ikut otomatis; tayangkan ulang bila perlu."
          >
            <select
              value={branchId}
              onChange={(event) => setBranchId(event.target.value)}
              style={inputStyle}
            >
              <option value="">— pilih cabang —</option>
              {branches.map((branch) => (
                <option key={branch.id} value={branch.id}>
                  {branch.name}
                </option>
              ))}
            </select>
          </Field>
        </>
      ) : eligible.length === 0 ? (
        <p style={{ color: COLORS.muted, fontSize: 13.5 }}>
          Belum ada display terpasang. Buka halaman Display untuk memasangkan TV.
        </p>
      ) : (
        <div
          style={{
            maxHeight: 220,
            overflowY: "auto",
            border: "1px solid #E3F2FD",
            borderRadius: 10,
            marginBottom: 16,
          }}
        >
          {eligible.map((display) => (
            <label
              key={display.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "10px 12px",
                borderBottom: "1px solid #F0F4F8",
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={selected.includes(display.id)}
                onChange={() => toggle(display.id)}
              />
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ fontWeight: 700, color: COLORS.navy, fontSize: 13.5 }}>
                  {display.name}
                </span>
                <span style={{ color: COLORS.faint, fontSize: 11.5, marginLeft: 8 }}>
                  {display.branch_name || "tanpa cabang"}
                </span>
              </span>
              <Badge tone={display.connection === "online" ? "success" : "warning"}>
                {display.connection === "online" ? "online" : "offline"}
              </Badge>
            </label>
          ))}
        </div>
      )}

      <details style={{ marginBottom: 14 }}>
        <summary
          style={{
            cursor: "pointer",
            fontSize: 12.5,
            fontWeight: 800,
            color: COLORS.blue,
            marginBottom: 10,
          }}
        >
          Jadwal & masa berlaku (opsional)
        </summary>
        <div style={{ paddingTop: 12 }}>
          <Field
            label="TAYANG MULAI"
            hint="Kosongkan untuk tayang sekarang. Waktu mengikuti jam perangkat ini."
          >
            <input
              type="datetime-local"
              value={scheduledAt}
              onChange={(event) => setScheduledAt(event.target.value)}
              style={inputStyle}
            />
          </Field>
          <Field
            label="BERLAKU SAMPAI"
            hint="Kosongkan berarti tetap tampil sampai diganti versi lain."
          >
            <input
              type="datetime-local"
              value={validUntil}
              onChange={(event) => setValidUntil(event.target.value)}
              style={inputStyle}
            />
          </Field>
        </div>
      </details>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
        <Button variant="subtle" onClick={onClose} disabled={busy}>
          Batal
        </Button>
        <Button onClick={handlePublish} disabled={busy || loading}>
          {busy ? "Mengirim..." : scheduledAt ? "Jadwalkan" : "Tayangkan Sekarang"}
        </Button>
      </div>
    </Backdrop>
  );
}

const headingStyle = {
  fontSize: 18,
  fontWeight: 900,
  color: COLORS.navy,
  marginTop: 0,
  marginBottom: 6,
};

function Backdrop({ children, onClose }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(13,71,161,0.28)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 18,
        zIndex: 1000,
      }}
    >
      <div
        onClick={(event) => event.stopPropagation()}
        style={{
          background: "#fff",
          borderRadius: 16,
          padding: 26,
          width: "100%",
          maxWidth: 480,
          maxHeight: "90vh",
          overflowY: "auto",
          boxShadow: "0 18px 50px rgba(13,71,161,0.3)",
        }}
      >
        {children}
      </div>
    </div>
  );
}
