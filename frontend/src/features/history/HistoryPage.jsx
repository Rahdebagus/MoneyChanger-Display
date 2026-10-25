// ─── Rate History ─────────────────────────────────────────────────────────────
//
// Thumbnails here are a separate, small asset. The full-resolution board is
// never downscaled to make this list fast.

import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Badge, Button, Card, ErrorBanner, EmptyState, PageHeader, Spinner, SuccessBanner } from "../../components/common/ui.jsx";
import { COLORS, inputStyle } from "../../components/common/theme.js";
import PublishDialog from "../displays/PublishDialog.jsx";
import { useAuth } from "../../hooks/useAuth.js";
import { useAuthedMedia } from "../../hooks/useAuthedMedia.js";
import { useRemoteData } from "../../hooks/useRemoteData.js";
import { downloadMedia, versionApi } from "../../services/apiClient.js";
import { formatDateTime, relativeTime } from "../../utils/datetime.js";

const PAGE_SIZE = 12;

const STATUS_TONE = {
  ready: "success",
  generating: "warning",
  draft: "neutral",
  failed: "danger",
  archived: "neutral",
};

function Thumbnail({ version }) {
  const { url } = useAuthedMedia(version.thumbnail_url || version.png_url);

  return (
    <div
      style={{
        width: "100%",
        aspectRatio: "16 / 9",
        background: COLORS.paler,
        borderRadius: 10,
        overflow: "hidden",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        border: "1px solid #E3F2FD",
      }}
    >
      {url ? (
        <img
          src={url}
          alt={`Pratinjau versi ${version.version}`}
          style={{ width: "100%", height: "100%", objectFit: "contain" }}
          loading="lazy"
        />
      ) : (
        <span style={{ color: COLORS.faint, fontSize: 12 }}>
          {version.status === "failed" ? "gagal dibuat" : "tanpa pratinjau"}
        </span>
      )}
    </div>
  );
}

export default function HistoryPage() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();

  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [notice, setNotice] = useState(null);
  const [publishTarget, setPublishTarget] = useState(null);

  const fetchHistory = useCallback((signal) => versionApi.list({
    page,
    page_size: PAGE_SIZE,
    status: status || undefined,
    include_archived: includeArchived ? "true" : undefined,
  }, { signal }), [page, status, includeArchived]);
  const { data, error, setError, loading, refreshing, refresh: load } = useRemoteData(
    fetchHistory, { initialData: { items: [], total: 0 } }
  );

  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));

  const openAsNewVersion = (version) => {
    navigate("/", { state: { openVersionId: version.id } });
  };

  const archive = async (version) => {
    try {
      await versionApi.archive(version.id);
      setNotice(`Versi v${version.version} diarsipkan.`);
      load();
    } catch (err) {
      setError(err);
    }
  };

  const restore = async (version) => {
    try {
      await versionApi.restore(version.id);
      setNotice(`Versi v${version.version} dikembalikan dari arsip.`);
      load();
    } catch (err) {
      setError(err);
    }
  };

  const remove = async (version) => {
    if (!window.confirm(`Hapus permanen versi v${version.version} beserta file yang tidak dipakai? Tindakan ini tidak dapat dibatalkan.`)) return;
    setBusyId(version.id);
    setError(null);
    try {
      const result = await versionApi.remove(version.id);
      setNotice(result.message);
      if (data.items.length === 1 && page > 1) setPage(page - 1);
      else load();
    } catch (err) {
      setError(err);
    } finally {
      setBusyId(null);
    }
  };

  const download = async (version, kind) => {
    setBusyId(version.id);
    try {
      await downloadMedia(version[`${kind}_url`], `pam_rate_board_v${version.version}.${kind}`);
    } catch (err) {
      setError(err);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Riwayat Rate"
        subtitle="Semua versi yang pernah dibuat, lengkap dengan pembuat dan waktunya"
        actions={
          <Button variant="secondary" size="sm" onClick={load} disabled={refreshing}>
            ↻ Muat Ulang
          </Button>
        }
      />

      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      <SuccessBanner message={notice} onDismiss={() => setNotice(null)} />

      <Card padding={16} style={{ marginBottom: 18 }}>
        <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
            style={{ ...inputStyle, width: "auto", minWidth: 170 }}
          >
            <option value="">Semua status</option>
            <option value="ready">Siap tayang</option>
            <option value="generating">Sedang dibuat</option>
            <option value="failed">Gagal</option>
            <option value="archived">Diarsipkan</option>
          </select>

          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 7,
              fontSize: 13,
              color: COLORS.muted,
            }}
          >
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(event) => {
                setIncludeArchived(event.target.checked);
                setPage(1);
              }}
            />
            Tampilkan arsip
          </label>

          <span style={{ marginLeft: "auto", fontSize: 12.5, color: COLORS.faint }}>
            {data.total} versi
          </span>
        </div>
      </Card>

      {loading ? (
        <Spinner />
      ) : data.items.length === 0 ? (
        <Card>
          <EmptyState
            icon="🗂️"
            title="Belum ada riwayat"
            description="Versi akan muncul di sini setiap kali Anda menekan Generate & Save pada halaman Generator."
            action={<Button onClick={() => navigate("/")}>Buat Rate Board</Button>}
          />
        </Card>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: 16,
          }}
        >
          {data.items.map((version) => (
            <Card key={version.id} padding={14}>
              <Thumbnail version={version} />

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 8,
                  margin: "12px 0 6px",
                }}
              >
                <strong style={{ color: COLORS.navy, fontSize: 15 }}>
                  v{version.version}
                </strong>
                <div style={{ display: "flex", gap: 6 }}>
                  {version.is_live && <Badge tone="success">tayang</Badge>}
                  <Badge tone={STATUS_TONE[version.status] || "neutral"}>
                    {version.status}
                  </Badge>
                </div>
              </div>

              <div style={{ fontSize: 12, color: COLORS.muted, lineHeight: 1.7 }}>
                <div>{version.board_title}</div>
                <div>
                  {version.created_by_name || "—"} · {relativeTime(version.created_at)}
                </div>
                <div style={{ color: COLORS.faint }}>
                  {formatDateTime(version.created_at)}
                  {version.branch_name ? ` · ${version.branch_name}` : ""}
                </div>
                {version.source_version_id && (
                  <div style={{ color: COLORS.faint }}>
                    dari versi #{version.source_version_id}
                  </div>
                )}
                {version.status === "failed" && version.error_message && (
                  <div style={{ color: COLORS.red }}>Gagal dibuat — coba generate ulang.</div>
                )}
              </div>

              <div
                style={{
                  display: "flex",
                  gap: 7,
                  flexWrap: "wrap",
                  marginTop: 12,
                  paddingTop: 12,
                  borderTop: "1px solid #F0F4F8",
                }}
              >
                <Button size="sm" variant="secondary" onClick={() => openAsNewVersion(version)}>
                  Buka sebagai versi baru
                </Button>

                {version.png_url && (
                  <Button
                    size="sm"
                    variant="subtle"
                    disabled={busyId === version.id}
                    onClick={() => download(version, "png")}
                  >
                    PNG
                  </Button>
                )}

                {isAdmin && version.status === "ready" && (
                  <Button size="sm" onClick={() => setPublishTarget(version)}>
                    Tampilkan
                  </Button>
                )}

                {isAdmin && version.status === "archived" && (
                  <Button size="sm" variant="subtle" onClick={() => restore(version)}>
                    Pulihkan
                  </Button>
                )}

                {isAdmin && version.status === "ready" && !version.is_live && (
                  <Button size="sm" variant="danger" onClick={() => archive(version)}>
                    Arsipkan
                  </Button>
                )}
                {isAdmin && "delete_blocked_reason" in version && (
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={busyId === version.id || Boolean(version.delete_blocked_reason) || version.is_live}
                    title={version.delete_blocked_reason || (version.is_live ? "Versi masih dipakai display." : "Hapus versi dan file yang tidak dipakai")}
                    onClick={() => remove(version)}
                  >
                    {busyId === version.id ? "Memproses…" : "Hapus"}
                  </Button>
                )}
              </div>
              {isAdmin && version.delete_blocked_reason && (
                <p style={{ marginBottom: 0, color: COLORS.faint, fontSize: 12 }}>
                  {version.delete_blocked_reason}
                </p>
              )}
            </Card>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            gap: 12,
            marginTop: 22,
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

      {publishTarget && (
        <PublishDialog
          version={publishTarget}
          onClose={() => setPublishTarget(null)}
          onPublished={() => {
            setNotice("Rate board dikirim ke display yang dipilih.");
            load();
          }}
        />
      )}
    </div>
  );
}
