import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import {
  BookOpen,
  CalendarDays,
  ClipboardList,
  History,
  LayoutDashboard,
  ShieldCheck,
  Users,
} from "lucide-react";
import CCKLogo from "../../components/CCKLogo";
import "./admin.css";

export const adminNavigation = [
  { path: "", label: "Overview", icon: LayoutDashboard },
  { path: "candidates", label: "Candidates", icon: Users },
  { path: "exams", label: "Exams & builder", icon: CalendarDays },
  { path: "questions", label: "Question bank", icon: ClipboardList },
  { path: "subjects", label: "Subjects", icon: BookOpen },
  { path: "actions", label: "Staff actions", icon: History },
] as const;

interface Props {
  name: string;
  preview?: boolean;
  actions: ReactNode;
  children: ReactNode;
}

export function AdminShell({
  name,
  preview = false,
  actions,
  children,
}: Props) {
  const { pathname } = useLocation();
  const base = preview ? "/preview/admin" : "/admin";
  const current =
    adminNavigation.find(
      (item) => item.path && pathname.startsWith(`${base}/${item.path}`),
    )?.label || "Overview";
  return (
    <div className="admin-layout">
      <a className="skip-link" href="#admin-main">
        Skip to main content
      </a>
      <aside className="admin-sidebar" aria-label="Administrator workspace">
        <div className="sidebar-brand">
          <CCKLogo size={54} />
          <div>
            <strong>Cadet College</strong>
            <span>Kohat</span>
          </div>
        </div>
        <div className="admin-workspace-label">
          <ShieldCheck size={15} aria-hidden="true" /> Administration
        </div>
        <nav aria-label="Administration">
          {adminNavigation.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={path ? `${base}/${path}` : base}
              end={!path}
            >
              <Icon size={19} aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="admin-sidebar-bottom">
          <Link to="/dashboard">
            {preview ? "← Candidate preview" : "← Portal home"}
          </Link>
          <p>
            CCK Digital Entry Test
            <br />
            <span>From darkness unto light</span>
          </p>
        </div>
      </aside>
      <div className="admin-content">
        <header className="admin-header">
          <div className="admin-breadcrumb">
            <Link to={base}>Administration</Link>
            <span aria-hidden="true">/</span>
            <span>{current}</span>
          </div>
          <div className="admin-account">
            <span className="admin-avatar" aria-hidden="true">
              {name.trim().charAt(0).toUpperCase()}
            </span>
            <div>
              <strong>
                <bdi>{name}</bdi>
              </strong>
              <span>
                {preview ? "Design preview · View only" : "Administrator"}
              </span>
            </div>
          </div>
          {actions}
        </header>
        {preview && (
          <p className="admin-preview-message" id="admin-preview-message">
            <ShieldCheck size={17} aria-hidden="true" />
            <span>
              Administration design preview · Sample data · Nothing is saved.
            </span>
          </p>
        )}
        <main id="admin-main" tabIndex={-1}>
          {children}
        </main>
        <footer className="admin-page-footer">
          Cadet College Kohat <span>Digital Entry Test · Administration</span>
        </footer>
      </div>
    </div>
  );
}
