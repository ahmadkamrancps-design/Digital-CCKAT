import { useState } from "react";
import { Link, Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { AdminShell } from "./AdminShell";

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
        <Link className="secondary-button" to="/preview/admin">
          View administration design preview
        </Link>
      </main>
    ) : (
      <Navigate to="/admin/login" replace />
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
    <AdminShell
      name={profile.user.display_name}
      actions={
        <button
          disabled={pending}
          onClick={() => {
            void logout();
          }}
        >
          {pending ? "Signing out…" : "Sign out"}
        </button>
      }
    >
      {error && (
        <p className="admin-alert" role="alert">
          {error}
        </p>
      )}
      <Outlet />
    </AdminShell>
  );
}
