// ─── Activity ─────────────────────────────────────────────────────────────────
//
// Publish, edit and rollback history, plus scheduled publications that have
// not fired yet so a pending schedule is never a surprise.

import { useCallback, useState } from "react";

import { Badge, Button, Card, ErrorBanner, PageHeader, Spinner, SuccessBanner, Table } from "../../components/common/ui.jsx";
import { COLORS } from "../../components/common/theme.js";
import { useAuth } from "../../hooks/useAuth.js";
import { useRemoteData } from "../../hooks/useRemoteData.js";
import { auditApi, publicationApi } from "../../services/apiClient.js";
import { formatDateTime, relativeTime } from "../../utils/datetime.js";

const PAGE_SIZE = 25;

const ACTION_LABELS = {
  "auth.login": "Login",
  "auth.logout": "Logout",
  "auth.password_changed": "Ganti password",
  "user.created": "Buat pengguna",
  "user.updated": "Ubah pengguna",
  "branch.created": "Buat cabang",
  "branch.updated": "Ubah cabang",
  "branch.deleted": "Hapus cabang",
  "version.created": "Buat versi rate",
  "version.duplicated": "Salin versi",
  "version.archived": "Arsipkan versi",
  "version.restored": "Pulihkan versi",
  "version.deleted": "Hapus versi",
  "publication.created": "Tayangkan",
  "publication.scheduled": "Jadwalkan tayang",
  "publication.schedule_fired": "Jadwal berjalan",
  "publication.cancelled": "Batalkan jadwal",
  "publication.rollback": "Rollback",
  "display.paired": "Display terpasang",
  "display.pairing_approved": "Setujui pairing",
  "display.updated": "Ubah display",
  "display.refresh_requested": "Minta refresh",
  "display.revoked": "Cabut display",
  "display.deleted": "Hapus display",
};

export default function ActivityPage() {
  const { isAdmin } = useAuth();

  const [page, setPage] = useState(1);
  const [notice, setNotice] = useState(null);

  const fetchActivity = useCallback(async (signal) => {
    const [entries, publications] = await Promise.all([
      auditApi.list({ page, page_size: PAGE_SIZE }, { signal }),
      publicationApi.list({ state: "scheduled", page_size: 50 }, { signal }),
    ]);
    return { entries, scheduled: publications.items };
  }, [page]);
  const { data, loading, error, setError, refresh: load } = useRemoteData(
    fetchActivity, { initialData: { entries: { items: [], total: 0 }, scheduled: [] } }
  );
  const { entries, scheduled } = data;

  const cancelSchedule = async (publication) => {
    if (!window.confirm(`Batalkan jadwal tayang versi ${publication.version_label}?`)) return;
    try {
      await publicationApi.cancel(publication.id);
      setNotice("Jadwal dibatalkan.");
      load();
    } catch (err) {
      setError(err);
    }
  };

  const totalPages = Math.max(1, Math.ceil(entries.total / PAGE_SIZE));

  return (
    <div>
      <PageHeader
        title="Aktivitas"
        subtitle="Riwayat publish, edit, rollback dan perubahan konfigurasi"
        actions={
          <Button variant="secondary" size="sm" onClick={load}>
            ↻ Muat Ulang
          </Button>
        }
      />

      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      <SuccessBanner message={notice} onDismiss={() => setNotice(null)} />

      {scheduled.length > 0 && (
        <Card style={{ marginBottom: 20 }}>
          <h2 style={{ fontSize: 15, fontWeight: 900, color: COLORS.navy, marginTop: 0 }}>
            Jadwal Menunggu
          </h2>
          <Table
            columns={["Versi", "Tayang pada", "Target", "Dibuat oleh", "Aksi"]}
            rows={scheduled}
            renderRow={(publication) => (
              <tr key={publication.id} style={{ borderBottom: "1px solid #F0F4F8" }}>
                <td style={cellStyle}>
                  <strong style={{ color: COLORS.navy }}>{publication.version_label}</strong>
                </td>
                <td style={cellStyle}>
                  {formatDateTime(publication.scheduled_at)}
                  <div style={{ fontSize: 11, color: COLORS.faint }}>
                    {relativeTime(publication.scheduled_at)}
                  </div>
                </td>
                <td style={cellStyle}>
                  {publication.scope === "branch"
                    ? "satu cabang"
                    : `${publication.targets.length || "—"} display`}
                </td>
                <td style={cellStyle}>{publication.created_by_name || "—"}</td>
                <td style={cellStyle}>
                  {isAdmin && (
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => cancelSchedule(publication)}
                    >
                      Batalkan
                    </Button>
                  )}
                </td>
              </tr>
            )}
          />
        </Card>
      )}

      <Card padding={18}>
        {loading ? (
          <Spinner />
        ) : (
          <Table
            columns={["Waktu", "Aksi", "Oleh", "Objek", "Detail"]}
            rows={entries.items}
            emptyMessage="Belum ada aktivitas tercatat."
            renderRow={(entry) => (
              <tr key={entry.id} style={{ borderBottom: "1px solid #F0F4F8" }}>
                <td style={cellStyle}>
                  {formatDateTime(entry.created_at)}
                  <div style={{ fontSize: 11, color: COLORS.faint }}>
                    {relativeTime(entry.created_at)}
                  </div>
                </td>
                <td style={cellStyle}>
                  <Badge tone={entry.action.startsWith("publication") ? "info" : "neutral"}>
                    {ACTION_LABELS[entry.action] || entry.action}
                  </Badge>
                </td>
                <td style={cellStyle}>{entry.actor_label}</td>
                <td style={cellStyle}>
                  {entry.target_type ? `${entry.target_type} #${entry.target_id}` : "—"}
                </td>
                <td style={{ ...cellStyle, maxWidth: 280 }}>
                  <code
                    style={{
                      fontSize: 11,
                      color: COLORS.muted,
                      wordBreak: "break-word",
                      display: "block",
                    }}
                  >
                    {summarise(entry.details)}
                  </code>
                </td>
              </tr>
            )}
          />
        )}
      </Card>

      {totalPages > 1 && (
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            gap: 12,
            marginTop: 20,
          }}
        >
          <Button
            size="sm"
            variant="subtle"
            disabled={page <= 1}
            onClick={() => setPage((value) => value - 1)}
          >
            ← Sebelumnya
          </Button>
          <span style={{ fontSize: 13, color: COLORS.muted }}>
            Halaman {page} dari {totalPages}
          </span>
          <Button
            size="sm"
            variant="subtle"
            disabled={page >= totalPages}
            onClick={() => setPage((value) => value + 1)}
          >
            Berikutnya →
          </Button>
        </div>
      )}
    </div>
  );
}

function summarise(details) {
  if (!details || Object.keys(details).length === 0) return "—";
  return Object.entries(details)
    .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(",") : value}`)
    .join(" · ");
}

const cellStyle = { padding: "11px 12px", fontSize: 13, verticalAlign: "top" };
