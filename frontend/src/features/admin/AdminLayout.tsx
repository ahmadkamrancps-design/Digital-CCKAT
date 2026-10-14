import { useState } from "react";
import { Navigate, NavLink, Outlet } from "react-router-dom";
import {
  BookOpen,
  CalendarDays,
  ClipboardList,
  History,
  Users,
} from "lucide-react";
import CCKLogo from "../../components/CCKLogo";
import { useAuth } from "../auth/AuthProvider";
import "./admin.css";

export function AdminLayout() {
  const { profile, isPreview, signOut } = useAuth();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  if (!profile)
    return isPreview ? (
      <main id="main" className="card session-state">
        <h1>Administrator sign-in required</h1>
        <p>
          Admin tools require an approved administrator account. Disable
          candidate preview to sign in.
        </p>
      </main>
    ) : (
      <Navigate to="/" replace />
    );
  if (profile.user.role !== "ADMIN")
    return <Navigate to="/dashboard" replace />;
  const logout = async () => {
    setPending(true);
    setError("");
    try {
      await signOut();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to sign out.");
    } finally {
      setPending(false);
    }
  };
  return (
    <div className="admin-layout">
      <a className="skip-link" href="#admin-main">
        Skip to main content
      </a>
      <aside className="admin-sidebar">
        <div className="sidebar-brand">
          <CCKLogo size={60} />
          <div>
            <strong>Cadet College</strong>
            <span>Kohat · Administration</span>
          </div>
        </div>
        <nav aria-label="Administration">
          {[
            { to: "/admin/candidates", label: "Candidates", icon: Users },
            {
              to: "/admin/exams",
              label: "Exams & builder",
              icon: CalendarDays,
            },
            { to: "/admin/subjects", label: "Subjects", icon: BookOpen },
            {
              to: "/admin/questions",
              label: "Question bank",
              icon: ClipboardList,
            },
            { to: "/admin/actions", label: "Staff actions", icon: History },
          ].map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to}>
              <Icon size={18} aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>
        <p className="sidebar-footer">
          CCK Digital Entry Test
          <br />
          Administrator workspace
        </p>
      </aside>
      <div className="admin-content">
        <header className="admin-header">
          <span>Administration</span>
          <bdi>{profile.user.display_name}</bdi>
          <button
            disabled={pending}
            onClick={() => {
              void logout();
            }}
          >
            {pending ? "Signing out…" : "Sign out"}
          </button>
        </header>
        {error && (
          <p className="admin-alert" role="alert">
            {error}
          </p>
        )}
        <main id="admin-main" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
