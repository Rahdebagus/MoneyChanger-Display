// ─── Users (admin only) ───────────────────────────────────────────────────────

import { useCallback, useState } from "react";

import { Badge, Button, Card, ErrorBanner, Field, PageHeader, Spinner, SuccessBanner, Table } from "../../components/common/ui.jsx";
import { COLORS, inputStyle } from "../../components/common/theme.js";
import { branchApi, userApi } from "../../services/apiClient.js";
import { formatDateTime } from "../../utils/datetime.js";
import { useRemoteData } from "../../hooks/useRemoteData.js";

const EMPTY_FORM = {
  username: "",
  password: "",
  full_name: "",
  role: "staff",
  branch_ids: [],
};

export default function UsersPage() {
  const [notice, setNotice] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null);

  const fetchUsers = useCallback(async (signal) => {
    const [users, branches] = await Promise.all([userApi.list({ signal }), branchApi.list({ signal })]);
    return { users, branches };
  }, []);
  const { data, loading, error, setError, refresh: load } = useRemoteData(
    fetchUsers, { initialData: { users: [], branches: [] } }
  );
  const { users, branches } = data;

  const toggleBranch = (id) => {
    setForm((prev) => ({
      ...prev,
      branch_ids: prev.branch_ids.includes(id)
        ? prev.branch_ids.filter((value) => value !== id)
        : [...prev.branch_ids, id],
    }));
  };

  const handleCreate = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await userApi.create({
        ...form,
        username: form.username.trim().toLowerCase(),
        full_name: form.full_name.trim() || null,
      });
      setNotice(`Akun "${form.username.trim()}" dibuat.`);
      setForm(EMPTY_FORM);
      load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const update = async (user, payload, message) => {
    setError(null);
    try {
      await userApi.update(user.id, payload);
      setNotice(message);
      setEditing(null);
      load();
    } catch (err) {
      setError(err);
    }
  };

  return (
    <div>
      <PageHeader
        title="Pengguna"
        subtitle="Akun admin dan staf. Tidak ada pendaftaran mandiri."
      />

      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      <SuccessBanner message={notice} onDismiss={() => setNotice(null)} />

      <Card style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 15, fontWeight: 900, color: COLORS.navy, marginTop: 0 }}>
          Tambah Pengguna
        </h2>
        <form onSubmit={handleCreate}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
              gap: 12,
            }}
          >
            <Field label="USERNAME">
              <input
                value={form.username}
                onChange={(event) => setForm({ ...form, username: event.target.value })}
                required
                minLength={3}
                style={inputStyle}
              />
            </Field>
            <Field label="NAMA LENGKAP">
              <input
                value={form.full_name}
                onChange={(event) => setForm({ ...form, full_name: event.target.value })}
                style={inputStyle}
              />
            </Field>
            <Field label="PASSWORD" hint="Minimal 8 karakter.">
              <input
                type="password"
                value={form.password}
                onChange={(event) => setForm({ ...form, password: event.target.value })}
                required
                minLength={8}
                autoComplete="new-password"
                style={inputStyle}
              />
            </Field>
            <Field label="ROLE">
              <select
                value={form.role}
                onChange={(event) => setForm({ ...form, role: event.target.value })}
                style={inputStyle}
              >
                <option value="staff">Staf</option>
                <option value="admin">Admin</option>
              </select>
            </Field>
          </div>

          {form.role === "staff" && (
            <Field
              label="CABANG YANG DITUGASKAN"
              hint="Staf hanya dapat melihat rate dan display pada cabang ini."
            >
              <div style={{ display: "flex", gap: 14, flexWrap: "wrap", paddingTop: 4 }}>
                {branches.length === 0 && (
                  <span style={{ fontSize: 13, color: COLORS.faint }}>
                    Belum ada cabang. Buat cabang terlebih dahulu.
                  </span>
                )}
                {branches.map((branch) => (
                  <label
                    key={branch.id}
                    style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}
                  >
                    <input
                      type="checkbox"
                      checked={form.branch_ids.includes(branch.id)}
                      onChange={() => toggleBranch(branch.id)}
                    />
                    {branch.name}
                  </label>
                ))}
              </div>
            </Field>
          )}

          <Button type="submit" disabled={busy}>
            {busy ? "Menyimpan..." : "Tambah Pengguna"}
          </Button>
        </form>
      </Card>

      <Card padding={18}>
        {loading ? (
          <Spinner />
        ) : (
          <Table
            columns={["Pengguna", "Role", "Cabang", "Login Terakhir", "Aksi"]}
            rows={users}
            emptyMessage="Belum ada pengguna."
            renderRow={(user) => (
              <tr key={user.id} style={{ borderBottom: "1px solid #F0F4F8" }}>
                <td style={cellStyle}>
                  <strong style={{ color: COLORS.navy }}>{user.username}</strong>
                  <div style={{ fontSize: 11.5, color: COLORS.faint }}>
                    {user.full_name || "—"}
                  </div>
                </td>
                <td style={cellStyle}>
                  <Badge tone={user.role === "admin" ? "info" : "neutral"}>{user.role}</Badge>
                </td>
                <td style={cellStyle}>
                  {user.branches.length
                    ? user.branches.map((branch) => branch.name).join(", ")
                    : user.role === "admin"
                      ? "semua"
                      : "—"}
                </td>
                <td style={cellStyle}>
                  {user.last_login_at ? formatDateTime(user.last_login_at) : "belum pernah"}
                </td>
                <td style={cellStyle}>
                  <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
                    <Button
                      size="sm"
                      variant="subtle"
                      onClick={() =>
                        update(
                          user,
                          { is_active: !user.is_active },
                          `Akun "${user.username}" diperbarui.`
                        )
                      }
                    >
                      {user.is_active ? "Nonaktifkan" : "Aktifkan"}
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => setEditing(user)}>
                      Reset Password
                    </Button>
                  </div>
                </td>
              </tr>
            )}
          />
        )}
      </Card>

      {editing && (
        <PasswordDialog
          user={editing}
          onClose={() => setEditing(null)}
          onSave={(password) =>
            update(
              editing,
              { password },
              `Password "${editing.username}" diubah. Sesi lama otomatis berakhir.`
            )
          }
        />
      )}
    </div>
  );
}

function PasswordDialog({ user, onClose, onSave }) {
  const [password, setPassword] = useState("");

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
          maxWidth: 380,
          boxShadow: "0 18px 50px rgba(13,71,161,0.3)",
        }}
      >
        <h2 style={{ fontSize: 17, fontWeight: 900, color: COLORS.navy, marginTop: 0 }}>
          Reset Password
        </h2>
        <p style={{ fontSize: 13, color: COLORS.muted, marginTop: 0 }}>
          Password baru untuk <strong>{user.username}</strong>. Semua sesi aktif akun ini
          akan langsung berakhir.
        </p>

        <Field label="PASSWORD BARU" hint="Minimal 8 karakter.">
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={8}
            autoComplete="new-password"
            style={inputStyle}
          />
        </Field>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <Button variant="subtle" onClick={onClose}>
            Batal
          </Button>
          <Button disabled={password.length < 8} onClick={() => onSave(password)}>
            Simpan
          </Button>
        </div>
      </div>
    </div>
  );
}

const cellStyle = { padding: "12px", fontSize: 13.5, verticalAlign: "middle" };
