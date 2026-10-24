// ─── Application Shell ────────────────────────────────────────────────────────
//
// Header, navigation and footer for every signed-in page. Navigation entries
// are filtered by role, but that is only a convenience: the server enforces
// the same rules on every request, so hiding a link is never what keeps a
// staff account out of the admin pages.

import { NavLink, Outlet, useNavigate } from "react-router-dom";

import pamLogo from "../../assets/pam_logo.png";
import { Footer } from "./Footer.jsx";
import { COLORS } from "../common/theme.js";
import { useAuth } from "../../hooks/useAuth.js";

const NAV_ITEMS = [
  { to: "/", label: "Generator", end: true },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/history", label: "Riwayat Rate" },
  { to: "/displays", label: "Display" },
  { to: "/activity", label: "Aktivitas" },
  { to: "/branches", label: "Cabang", adminOnly: true },
  { to: "/users", label: "Pengguna", adminOnly: true },
];

export default function AppLayout() {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();

  const items = NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: COLORS.bg,
        fontFamily: "'Segoe UI', system-ui, sans-serif",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <header
        style={{
          background: "#fff",
          borderBottom: "1px solid #E3F2FD",
          padding: "10px 16px",
          position: "sticky",
          top: 0,
          zIndex: 100,
          boxShadow: "0 2px 12px rgba(21,101,192,0.08)",
        }}
      >
        <div
          style={{
            maxWidth: 1180,
            margin: "0 auto",
            display: "flex",
            alignItems: "center",
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          <img
            src={pamLogo}
            alt="PAM Money Changer"
            style={{ height: 46, maxWidth: 110, objectFit: "contain" }}
          />

          <nav
            style={{
              display: "flex",
              gap: 4,
              flexWrap: "wrap",
              flex: "1 1 auto",
            }}
          >
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                style={({ isActive }) => ({
                  padding: "7px 13px",
                  borderRadius: 9,
                  fontSize: 13.5,
                  fontWeight: isActive ? 800 : 600,
                  textDecoration: "none",
                  color: isActive ? "#fff" : COLORS.muted,
                  background: isActive ? COLORS.blue : "transparent",
                  whiteSpace: "nowrap",
                })}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ textAlign: "right", lineHeight: 1.3 }}>
              <div style={{ fontSize: 12.5, fontWeight: 800, color: COLORS.navy }}>
                {user?.full_name || user?.username}
              </div>
              <div style={{ fontSize: 10.5, color: COLORS.faint, textTransform: "uppercase" }}>
                {user?.role}
                {user?.branches?.length
                  ? ` · ${user.branches.map((b) => b.name).join(", ")}`
                  : ""}
              </div>
            </div>
            <button
              onClick={handleLogout}
              style={{
                padding: "7px 12px",
                borderRadius: 9,
                border: `1px solid ${COLORS.border}`,
                background: "#fff",
                color: COLORS.muted,
                fontWeight: 700,
                fontSize: 12.5,
                cursor: "pointer",
              }}
            >
              Keluar
            </button>
          </div>
        </div>
      </header>

      <main
        style={{
          maxWidth: 1180,
          margin: "0 auto",
          padding: "28px 16px 40px",
          width: "100%",
          boxSizing: "border-box",
          flex: "1 0 auto",
        }}
      >
        <Outlet />
      </main>

      <Footer />
    </div>
  );
}
