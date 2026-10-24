// ─── Routes ───────────────────────────────────────────────────────────────────
//
// The player route is lazy loaded and shares nothing with the admin bundle:
// a TV must not download the editor, the OCR upload UI or the admin tables
// just to show a PNG. The admin pages are lazy loaded for the same reason in
// the other direction.

import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import AppLayout from "./components/Layout/AppLayout.jsx";
import { Spinner } from "./components/common/ui.jsx";
import { COLORS } from "./components/common/theme.js";
import { AuthProvider } from "./context/AuthContext.jsx";
import { useAuth } from "./hooks/useAuth.js";
import LoginPage from "./features/auth/LoginPage.jsx";
import "./App.css";

const RateBoardPage = lazy(() => import("./pages/RateBoardPage.jsx"));
const DashboardPage = lazy(() => import("./features/dashboard/DashboardPage.jsx"));
const HistoryPage = lazy(() => import("./features/history/HistoryPage.jsx"));
const DisplaysPage = lazy(() => import("./features/displays/DisplaysPage.jsx"));
const BranchesPage = lazy(() => import("./features/branches/BranchesPage.jsx"));
const UsersPage = lazy(() => import("./features/users/UsersPage.jsx"));
const ActivityPage = lazy(() => import("./features/activity/ActivityPage.jsx"));
const PlayerPage = lazy(() => import("./features/player/PlayerPage.jsx"));

function FullPageLoader() {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: COLORS.bg,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Spinner />
    </div>
  );
}

function RequireAuth({ children }) {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) return <FullPageLoader />;
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}

function RequireAdmin({ children }) {
  const { isAdmin, loading } = useAuth();
  if (loading) return <FullPageLoader />;
  if (!isAdmin) return <Navigate to="/" replace />;
  return children;
}

function RedirectIfAuthenticated({ children }) {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return <FullPageLoader />;
  if (isAuthenticated) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Suspense fallback={<FullPageLoader />}>
          <Routes>
            {/* The TV player is intentionally outside the admin shell and
                outside RequireAuth: it authenticates as a device, not a user. */}
            <Route path="/display" element={<PlayerPage />} />

            <Route
              path="/login"
              element={
                <RedirectIfAuthenticated>
                  <LoginPage />
                </RedirectIfAuthenticated>
              }
            />

            <Route
              element={
                <RequireAuth>
                  <AppLayout />
                </RequireAuth>
              }
            >
              <Route index element={<RateBoardPage />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="history" element={<HistoryPage />} />
              <Route path="displays" element={<DisplaysPage />} />
              <Route path="activity" element={<ActivityPage />} />
              <Route
                path="branches"
                element={
                  <RequireAdmin>
                    <BranchesPage />
                  </RequireAdmin>
                }
              />
              <Route
                path="users"
                element={
                  <RequireAdmin>
                    <UsersPage />
                  </RequireAdmin>
                }
              />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  );
}
