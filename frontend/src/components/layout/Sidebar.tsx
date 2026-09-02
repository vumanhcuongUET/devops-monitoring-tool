import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FileText,
  Activity,
  Server,
  Box,
  Bell,
  Target,
  CheckCircle,
  ShieldCheck,
  Wrench,
} from 'lucide-react';

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/logs', label: 'Logs', icon: FileText },
  { to: '/apm', label: 'APM', icon: Activity },
  { to: '/slo', label: 'SLO', icon: Target },
  { to: '/infrastructure', label: 'Infrastructure', icon: Server },
  { to: '/kubernetes', label: 'Kubernetes', icon: Box },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/actions', label: 'Actions', icon: CheckCircle },  // Phase 2
];

const governanceItems = [
  { to: '/governance', label: 'Governance', icon: ShieldCheck },
  { to: '/skills', label: 'Skills', icon: Wrench },
];

interface SidebarProps {
  /** Mobile drawer state; ignored from md up where the sidebar is static. */
  open?: boolean;
  onClose?: () => void;
}

function NavLinkList({ items, onNavigate }: { items: typeof navItems; onNavigate?: () => void }) {
  return (
    <>
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          onClick={onNavigate}
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
    </>
  );
}

export function Sidebar({ open, onClose }: SidebarProps) {
  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 flex w-56 flex-col border-r border-[var(--color-border)] bg-[var(--color-bg-secondary)] transition-transform duration-200 md:static md:translate-x-0 ${
        open ? 'translate-x-0' : '-translate-x-full'
      }`}
      aria-label="Primary navigation"
    >
      <div className="flex h-14 items-center px-4 text-lg font-semibold text-[var(--color-accent)]">
        DevOps Monitor
      </div>
      <nav className="flex-1 space-y-1 px-2 py-4">
        <NavLinkList items={navItems} onNavigate={onClose} />
        <div className="pt-4 mt-4 border-t border-[var(--color-border)]">
          <div className="px-3 pb-2 text-xs font-medium uppercase tracking-wide text-[var(--color-text-secondary)]">
            Governance
          </div>
          <NavLinkList items={governanceItems} onNavigate={onClose} />
        </div>
      </nav>
    </aside>
  );
}
