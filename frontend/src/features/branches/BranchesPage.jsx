// ─── Branches (admin only) ────────────────────────────────────────────────────

import { useCallback, useState } from "react";

import { Badge, Button, Card, ErrorBanner, Field, PageHeader, Spinner, SuccessBanner, Table } from "../../components/common/ui.jsx";
import { COLORS, inputStyle } from "../../components/common/theme.js";
import { branchApi } from "../../services/apiClient.js";
import { useAuth } from "../../hooks/useAuth.js";
import { useRemoteData } from "../../hooks/useRemoteData.js";

const COMMON_TIMEZONES = [
  "Asia/Makassar",
  "Asia/Jakarta",
  "Asia/Jayapura",
  "UTC",
];

export default function BranchesPage() {
  const { reloadBranches } = useAuth();

  const [notice, setNotice] = useState(null);

  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState("Asia/Makassar");
  const [busy, setBusy] = useState(false);

  const fetchBranches = useCallback((signal) => branchApi.list({ signal }), []);
  const { data: branches, loading, error, setError, refresh: load } = useRemoteData(
    fetchBranches, { initialData: [] }
  );

  const handleCreate = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await branchApi.create({ name: name.trim(), timezone });
      setNotice(`Cabang "${name.trim()}" dibuat.`);
      setName("");
      load();
      reloadBranches();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (branch) => {
    try {
      await branchApi.update(branch.id, { is_active: !branch.is_active });
      setNotice(`Cabang "${branch.name}" diperbarui.`);
      load();
    } catch (err) {
      setError(err);
    }
  };

  const remove = async (branch) => {
    if (!window.confirm(`Hapus cabang "${branch.name}"?`)) return;
    try {
      await branchApi.remove(branch.id);
      setNotice(`Cabang "${branch.name}" dihapus.`);
      load();
      reloadBranches();
    } catch (err) {
      setError(err);
    }
  };

  return (
    <div>
      <PageHeader
        title="Cabang"
        subtitle="Cabang menentukan akses staf dan pengelompokan display"
      />

      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      <SuccessBanner message={notice} onDismiss={() => setNotice(null)} />

      <Card style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 15, fontWeight: 900, color: COLORS.navy, marginTop: 0 }}>
          Tambah Cabang
        </h2>
        <form
          onSubmit={handleCreate}
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
            gap: 12,
            alignItems: "end",
          }}
        >
          <Field label="NAMA CABANG">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Kuta"
              required
              style={inputStyle}
            />
          </Field>
          <Field label="ZONA WAKTU" hint="Dipakai untuk menampilkan dan menjadwalkan.">
            <select
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
              style={inputStyle}
            >
              {COMMON_TIMEZONES.map((zone) => (
                <option key={zone} value={zone}>
                  {zone}
                </option>
              ))}
            </select>
          </Field>
          <div style={{ marginBottom: 14 }}>
            <Button type="submit" disabled={busy} style={{ width: "100%" }}>
              {busy ? "Menyimpan..." : "Tambah"}
            </Button>
          </div>
        </form>
      </Card>

      <Card padding={18}>
        {loading ? (
          <Spinner />
        ) : (
          <Table
            columns={["Cabang", "Zona Waktu", "Status", "Aksi"]}
            rows={branches}
            emptyMessage="Belum ada cabang."
            renderRow={(branch) => (
              <tr key={branch.id} style={{ borderBottom: "1px solid #F0F4F8" }}>
                <td style={cellStyle}>
                  <strong style={{ color: COLORS.navy }}>{branch.name}</strong>
                </td>
                <td style={cellStyle}>{branch.timezone}</td>
                <td style={cellStyle}>
                  <Badge tone={branch.is_active ? "success" : "neutral"}>
                    {branch.is_active ? "aktif" : "nonaktif"}
                  </Badge>
                </td>
                <td style={cellStyle}>
                  <div style={{ display: "flex", gap: 7 }}>
                    <Button size="sm" variant="subtle" onClick={() => toggleActive(branch)}>
                      {branch.is_active ? "Nonaktifkan" : "Aktifkan"}
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => remove(branch)}>
                      Hapus
                    </Button>
                  </div>
                </td>
              </tr>
            )}
          />
        )}
      </Card>
    </div>
  );
}

const cellStyle = { padding: "12px", fontSize: 13.5, verticalAlign: "middle" };
