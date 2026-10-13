import {
  CircleHelp,
  ClipboardList,
  Gauge,
  MonitorCheck,
  UserRound,
} from "lucide-react";

import CCKLogo from "./CCKLogo";
import { NavLink } from 'react-router-dom';

const items = [
  { icon: Gauge, label: "Dashboard", to: '/dashboard' },
  { icon: ClipboardList, label: "My Exam", to: '/exam' },
  { icon: CircleHelp, label: "Instructions", to: '/instructions' },
  { icon: MonitorCheck, label: "System Check", to: '/system-check' },
  { icon: UserRound, label: "Profile", to: '/profile' },
  { icon: CircleHelp, label: "Help & Support", to: '/help' },
];

export default function CandidateSidebar() {
  return (
    <aside className="candidate-sidebar" aria-label="Candidate navigation">
      <div className="sidebar-brand">
        <CCKLogo size={65} />

        <div>
          <strong>Cadet College</strong>
          <span>Kohat</span>
        </div>
      </div>

      <nav aria-label="Candidate pages">
        {items.map(({ icon: Icon, label, to }) => (
          <NavLink
            key={label}
            to={to}
            className={({ isActive }) => isActive ? 'sidebar-active' : ''}
          >
            <Icon size={18} aria-hidden="true" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        © 2026 CCK
        <br />
        Online Entry Test
      </div>
    </aside>
  );
}
