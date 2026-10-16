import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, HOME_FOR_ROLE, useAuth } from "./auth.jsx";
import Navbar from "./components/Navbar";
import { Spinner } from "./components/Spinner";
import { ToastProvider } from "./components/Toast";
import AdminPanel from "./pages/AdminPanel";
import Login from "./pages/Login";
import Register from "./pages/Register";
import SecurityDashboard from "./pages/SecurityDashboard";
import StudentDashboard from "./pages/StudentDashboard";
import { theme } from "./theme";

/** Gate a route on being signed in, and optionally on holding one of `roles`. */
function Protected({ roles, children }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center bg-ground text-ink">
        <Spinner size={20} />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) {
    return <Navigate to={HOME_FOR_ROLE[user.role] ?? "/student"} replace />;
  }

  return (
    <div className={theme.layout.shell}>
      <Navbar />
      <main className={theme.layout.main}>
        <div className={theme.layout.content}>{children}</div>
      </main>
    </div>
  );
}

function LandingRedirect() {
  const { user, loading } = useAuth();
  if (loading) return null;
  return <Navigate to={user ? (HOME_FOR_ROLE[user.role] ?? "/student") : "/login"} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />

            {/* Every section is its own URL, so the sidebar navigates, the back
                button works, and a section can be linked to directly. The bare
                path renders the first section. Admins can view every workspace;
                staff routes stay closed to students. */}
            {[
              ["/student", ["student", "security", "admin"], <StudentDashboard />],
              ["/security", ["security", "admin"], <SecurityDashboard />],
              ["/admin", ["admin"], <AdminPanel />],
            ].flatMap(([path, roles, element]) =>
              [path, `${path}/:section`].map((p) => (
                <Route key={p} path={p} element={<Protected roles={roles}>{element}</Protected>} />
              )),
            )}

            <Route path="*" element={<LandingRedirect />} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
