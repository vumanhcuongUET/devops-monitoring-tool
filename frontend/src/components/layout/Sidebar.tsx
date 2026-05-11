import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FileText,
  Activity,
  Server,
  Box,
  Bell,
  Target,
} from 'lucide-react';

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/logs', label: 'Logs', icon: FileText },
  { to: '/apm', label: 'APM', icon: Activity },
  { to: '/slo', label: 'SLO', icon: Target },
  { to: '/infrastructure', label: 'Infrastructure', icon: Server },
  { to: '/kubernetes', label: 'Kubernetes', icon: Box },
  { to: '/alerts', label: 'Alerts', icon: Bell },
];

export function Sidebar() {
  return (
    <aside className="flex w-56 flex-col border-r border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
      <div className="flex h-14 items-center px-4 text-lg font-semibold text-[var(--color-accent)]">
        DevOps Monitor
      </div>
      <nav className="flex-1 space-y-1 px-2 py-4">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                isActive
                  ? 'bg-[var(--color-accent)]/10 text-[var(--color-accent)]'
                  : 'text-[var(--color-text-secondary)] hover:bg-white/5 hover:text-[var(--color-text-primary)]'
              }`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
