// ─── Dashboard ────────────────────────────────────────────────────────────────

import { useCallback } from "react";
import { Link } from "react-router-dom";

import { Badge, Button, Card, ErrorBanner, PageHeader, Spinner, StatTile } from "../../components/common/ui.jsx";
import { COLORS } from "../../components/common/theme.js";
import { dashboardApi, displayApi } from "../../services/apiClient.js";
import { formatDateTime, relativeTime } from "../../utils/datetime.js";
import { useRemoteData } from "../../hooks/useRemoteData.js";

const REFRESH_MS = 60000;

export default function DashboardPage() {
  const fetchDashboard = useCallback(async (signal) => {
    const [stats, displays] = await Promise.all([
      dashboardApi.get({ signal }), displayApi.list(undefined, { signal }),
    ]);
    return { stats, displays };
  }, []);
  const { data, error, setError, loading, refreshing, refresh: load } = useRemoteData(
    fetchDashboard, { initialData: { stats: null, displays: [] }, refreshMs: REFRESH_MS }
  );
  const { stats, displays } = data;

  if (loading) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Ringkasan display, rate aktif dan perubahan terakhir"
        actions={
          <Button variant="secondary" size="sm" onClick={load} disabled={refreshing}>
            ↻ Muat Ulang
          </Button>
        }
      />

      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
          gap: 14,
          marginBottom: 22,
        }}
      >
        <StatTile
          label="Display Online"
          value={stats?.displays_online ?? 0}
          tone="success"
          hint={`dari ${stats?.displays_total ?? 0} display`}
        />
        <StatTile
          label="Display Offline"
          value={stats?.displays_offline ?? 0}
          tone={stats?.displays_offline ? "warning" : "neutral"}
        />
        <StatTile
          label="Belum Sinkron"
          value={stats?.displays_stale ?? 0}
          tone={stats?.displays_stale ? "danger" : "neutral"}
          hint="versi tayang berbeda dari yang diminta"
        />
        <StatTile
          label="Versi Siap"
          value={stats?.versions_ready ?? 0}
          tone="info"
          hint={`dari ${stats?.versions_total ?? 0} versi`}
        />
        <StatTile
          label="Job Berjalan"
          value={stats?.pending_jobs ?? 0}
          tone={stats?.pending_jobs ? "warning" : "neutral"}
        />
        <StatTile
          label="Jadwal Menunggu"
          value={stats?.scheduled_publications ?? 0}
          tone="info"
        />
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
          gap: 16,
        }}
      >
        <Card>
          <h2 style={sectionTitle}>Perubahan Terakhir</h2>
          {stats?.last_publish_at ? (
            <div style={{ fontSize: 14, color: COLORS.text, lineHeight: 1.8 }}>
              <div>
                Rate aktif:{" "}
                <strong style={{ color: COLORS.navy }}>
                  {stats.live_version_label || "belum ada"}
                </strong>
              </div>
              <div>
                Ditayangkan: <strong>{formatDateTime(stats.last_publish_at)}</strong>{" "}
                <span style={{ color: COLORS.faint }}>
                  ({relativeTime(stats.last_publish_at)})
                </span>
              </div>
              <div>
                Oleh: <strong>{stats.last_publish_by || "—"}</strong>
              </div>
            </div>
          ) : (
            <p style={{ color: COLORS.muted, fontSize: 14 }}>
              Belum ada rate yang ditayangkan. Buat rate board lalu pilih
              “Tampilkan ke Display”.
            </p>
          )}

          {stats?.failed_jobs > 0 && (
            <div
              style={{
                marginTop: 14,
                background: COLORS.redBg,
                border: "1px solid #FFCDD2",
                borderRadius: 9,
                padding: "9px 12px",
                fontSize: 13,
                color: COLORS.red,
              }}
            >
              {stats.failed_jobs} job gagal. Cek riwayat rate untuk versi yang perlu dibuat ulang.
            </div>
          )}
        </Card>

        <Card>
          <h2 style={sectionTitle}>Status Display</h2>
          {displays.length === 0 ? (
            <p style={{ color: COLORS.muted, fontSize: 14 }}>
              Belum ada display terdaftar.{" "}
              <Link to="/displays" style={{ color: COLORS.blue }}>
                Pasangkan TV
              </Link>
              .
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {displays.map((display) => (
                <div
                  key={display.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 10,
                    padding: "9px 12px",
                    background: COLORS.paler,
                    borderRadius: 9,
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 800, color: COLORS.navy, fontSize: 13.5 }}>
                      {display.name}
                    </div>
                    <div style={{ fontSize: 11.5, color: COLORS.faint }}>
                      {display.branch_name || "tanpa cabang"} ·{" "}
                      {display.reported_version_label
                        ? `menayangkan ${display.reported_version_label}`
                        : "belum menayangkan"}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                    {display.is_stale && <Badge tone="warning">belum sinkron</Badge>}
                    <Badge tone={display.connection === "online" ? "success" : "danger"}>
                      {display.connection === "online"
                        ? "online"
                        : display.connection === "never_seen"
                          ? "belum pernah"
                          : "offline"}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

const sectionTitle = {
  fontSize: 15,
  fontWeight: 900,
  color: COLORS.navy,
  marginTop: 0,
  marginBottom: 14,
};
