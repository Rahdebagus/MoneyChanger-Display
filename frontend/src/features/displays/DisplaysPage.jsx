// ─── Displays ─────────────────────────────────────────────────────────────────
//
// Pairing, status, and per-display actions. Desired and reported versions are
// shown separately on purpose: "we asked for v7" and "the TV confirmed v7"
// are different facts, and collapsing them would hide a stuck display.

import { useCallback, useState } from "react";

import { Badge, Button, Card, EmptyState, ErrorBanner, Field, PageHeader, Spinner, SuccessBanner, Table } from "../../components/common/ui.jsx";
import { COLORS, inputStyle } from "../../components/common/theme.js";
import { useAuth } from "../../hooks/useAuth.js";
import { useRemoteData } from "../../hooks/useRemoteData.js";
import { displayApi } from "../../services/apiClient.js";
import { formatDateTime, relativeTime } from "../../utils/datetime.js";

const REFRESH_MS = 60000;

function connectionBadge(display) {
  if (display.revoked_at) return <Badge tone="danger">dicabut</Badge>;
  if (!display.is_paired) return <Badge tone="warning">menunggu pairing</Badge>;
  if (display.connection === "online") return <Badge tone="success">online</Badge>;
  if (display.connection === "never_seen") return <Badge tone="neutral">belum pernah</Badge>;
  return <Badge tone="danger">offline</Badge>;
}

export default function DisplaysPage() {
  const { isAdmin, branches } = useAuth();

  const [notice, setNotice] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [branchId, setBranchId] = useState("");
  const [pairing, setPairing] = useState(false);

  const fetchDisplays = useCallback((signal) => displayApi.list(undefined, { signal }), []);
  const { data: displays, loading, error, setError, refreshing, refresh: load } = useRemoteData(
    fetchDisplays, { initialData: [], refreshMs: REFRESH_MS }
  );

  const handlePair = async (event) => {
    event.preventDefault();
    setError(null);
    setPairing(true);
    try {
      await displayApi.approvePairing({
        code: code.trim().toUpperCase(),
        name: name.trim(),
        branch_id: branchId ? Number(branchId) : null,
      });
      setNotice(
        `Display "${name.trim()}" didaftarkan. TV akan mengambil kredensialnya sendiri dalam beberapa detik.`
      );
      setCode("");
      setName("");
      load();
    } catch (err) {
      setError(err);
    } finally {
      setPairing(false);
    }
  };

  const act = async (id, action, successMessage) => {
    setBusyId(id);
    setError(null);
    try {
      await action();
      setNotice(successMessage);
      load();
    } catch (err) {
      setError(err);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Display"
        subtitle="Pasangkan TV, pantau status, dan kendalikan apa yang tayang"
        actions={
          <Button variant="secondary" size="sm" onClick={load} disabled={refreshing}>
            ↻ Muat Ulang
          </Button>
        }
      />

      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      <SuccessBanner message={notice} onDismiss={() => setNotice(null)} />

      {isAdmin && (
        <Card style={{ marginBottom: 20 }}>
          <h2 style={sectionTitle}>Pasangkan Display Baru</h2>
          <p style={{ fontSize: 13, color: COLORS.muted, marginTop: 0 }}>
            Buka <code>/display</code> pada TV, lalu masukkan kode yang muncul di layar.
          </p>
          <form
            onSubmit={handlePair}
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
              gap: 12,
              alignItems: "end",
            }}
          >
            <Field label="KODE PAIRING">
              <input
                value={code}
                onChange={(event) => setCode(event.target.value.toUpperCase())}
                placeholder="ABC123"
                maxLength={8}
                required
                style={{ ...inputStyle, letterSpacing: 3, fontWeight: 800 }}
              />
            </Field>
            <Field label="NAMA DISPLAY">
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="TV Lobby"
                required
                style={inputStyle}
              />
            </Field>
            <Field label="CABANG">
              <select
                value={branchId}
                onChange={(event) => setBranchId(event.target.value)}
                style={inputStyle}
              >
                <option value="">— tanpa cabang —</option>
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name}
                  </option>
                ))}
              </select>
            </Field>
            <div style={{ marginBottom: 14 }}>
              <Button type="submit" disabled={pairing} style={{ width: "100%" }}>
                {pairing ? "Memproses..." : "Pasangkan"}
              </Button>
            </div>
          </form>
        </Card>
      )}

      <Card padding={18}>
        {loading ? (
          <Spinner />
        ) : displays.length === 0 ? (
          <EmptyState
            icon="📺"
            title="Belum ada display"
            description="Buka /display pada perangkat TV untuk mendapatkan kode pairing."
          />
        ) : (
          <Table
            columns={[
              "Display",
              "Status",
              "Diminta",
              "Dilaporkan",
              "Terakhir terlihat",
              "Aksi",
            ]}
            rows={displays}
            renderRow={(display) => (
              <tr key={display.id} style={{ borderBottom: "1px solid #F0F4F8" }}>
                <td style={cellStyle}>
                  <div style={{ fontWeight: 800, color: COLORS.navy }}>{display.name}</div>
                  <div style={{ fontSize: 11.5, color: COLORS.faint }}>
                    {display.branch_name || "tanpa cabang"}
                  </div>
                </td>

                <td style={cellStyle}>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {connectionBadge(display)}
                    {display.is_stale && <Badge tone="warning">belum sinkron</Badge>}
                  </div>
                  {display.last_error && (
                    <div style={{ fontSize: 11, color: COLORS.red, marginTop: 4 }}>
                      {display.last_error}
                    </div>
                  )}
                </td>

                <td style={cellStyle}>
                  {display.desired_version_label || "—"}
                  <div style={{ fontSize: 11, color: COLORS.faint }}>
                    rev {display.desired_revision}
                    {display.target_state ? ` · ${display.target_state}` : ""}
                  </div>
                </td>

                <td style={cellStyle}>
                  {display.reported_version_label || "—"}
                  <div style={{ fontSize: 11, color: COLORS.faint }}>
                    rev {display.reported_revision}
                  </div>
                </td>

                <td style={cellStyle}>
                  {display.last_seen_at ? (
                    <>
                      {relativeTime(display.last_seen_at)}
                      <div style={{ fontSize: 11, color: COLORS.faint }}>
                        {formatDateTime(display.last_seen_at)}
                      </div>
                    </>
                  ) : (
                    "—"
                  )}
                </td>

                <td style={cellStyle}>
                  {isAdmin ? (
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <Button
                        size="sm"
                        variant="subtle"
                        disabled={busyId === display.id}
                        onClick={() =>
                          act(
                            display.id,
                            () => displayApi.refresh(display.id),
                            "Perintah refresh dikirim."
                          )
                        }
                      >
                        Refresh
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={busyId === display.id}
                        onClick={() =>
                          act(
                            display.id,
                            () =>
                              displayApi.rollback(
                                display.id,
                                `rollback-${display.id}-${Date.now()}`
                              ),
                            "Dikembalikan ke versi sebelumnya."
                          )
                        }
                      >
                        Rollback
                      </Button>
                      {!display.revoked_at && (
                        <Button
                          size="sm"
                          variant="danger"
                          disabled={busyId === display.id}
                          onClick={() => {
                            if (
                              !window.confirm(
                                `Cabut akses "${display.name}"?\n\n` +
                                  "Berlaku saat perangkat menghubungi server lagi. " +
                                  "TV yang sedang offline tetap menampilkan media terakhirnya sampai tersambung kembali."
                              )
                            ) {
                              return;
                            }
                            act(
                              display.id,
                              () => displayApi.revoke(display.id),
                              "Akses perangkat dicabut."
                            );
                          }}
                        >
                          Cabut
                        </Button>
                      )}
                    </div>
                  ) : (
                    <span style={{ color: COLORS.faint, fontSize: 12 }}>hanya admin</span>
                  )}
                </td>
              </tr>
            )}
          />
        )}
      </Card>
    </div>
  );
}

const sectionTitle = {
  fontSize: 15,
  fontWeight: 900,
  color: COLORS.navy,
  marginTop: 0,
  marginBottom: 8,
};

const cellStyle = { padding: "12px", verticalAlign: "top", fontSize: 13 };
