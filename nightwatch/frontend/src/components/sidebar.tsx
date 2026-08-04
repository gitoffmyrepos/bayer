'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import {
  LayoutDashboard,
  AlertTriangle,
  Boxes,
  ListChecks,
  BrainCircuit,
  Cloud,
  GitFork,
  Link2,
  Zap,
  Settings,
  BookOpen,
  Menu,
  Eye,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { useHealth } from '@/hooks/useNightwatch';

const navGroups = [
  {
    label: 'Observe',
    items: [
      { href: '/cloud', label: 'Cloud Estate', icon: Cloud },
      { href: '/kubernetes', label: 'Kubernetes', icon: Boxes },
      { href: '/pipelines', label: 'Pipelines', icon: GitFork },
    ],
  },
  {
    label: 'Investigate',
    items: [
      { href: '/check', label: 'Live Check', icon: Zap },
      { href: '/findings', label: 'Findings', icon: ListChecks },
      { href: '/topology', label: 'Topology', icon: GitFork },
      { href: '/incidents', label: 'Incidents', icon: AlertTriangle },
      { href: '/ai-analyst', label: 'AI Analyst', icon: BrainCircuit },
    ],
  },
  {
    label: 'Manage',
    items: [
      { href: '/adapters', label: 'Connections', icon: Link2 },
      { href: '/settings', label: 'Settings', icon: Settings },
      { href: '/docs', label: 'Documentation', icon: BookOpen },
    ],
  },
];

function HealthDot({ status, unavailable = false }: { status?: string; unavailable?: boolean }) {
  const label = unavailable
    ? 'Nightwatch API unavailable'
    : status === 'healthy' || status === 'ok'
      ? 'Nightwatch API healthy'
      : status === 'degraded'
        ? 'Nightwatch API degraded'
        : status === 'unhealthy'
          ? 'Nightwatch API unhealthy'
          : 'Nightwatch API status unknown';
  const color = unavailable
    ? 'bg-zinc-600'
    : status === 'healthy' || status === 'ok'
      ? 'bg-green-400'
      : status === 'degraded'
      ? 'bg-yellow-400'
      : status === 'unhealthy'
      ? 'bg-red-400'
      : 'bg-zinc-600';
  return (
    <span
      className={cn(
        'inline-block w-2.5 h-2.5 rounded-full animate-pulse',
        color
      )}
      role="status"
      title={label}
    >
      <span className="sr-only">{label}</span>
    </span>
  );
}

function NavLink({
  href,
  label,
  icon: Icon,
  onClick,
}: {
  href: string;
  label: string;
  icon: React.ElementType;
  onClick?: () => void;
}) {
  const pathname = usePathname();
  const isActive = pathname === href || (href !== '/' && pathname?.startsWith(href));

  return (
    <Link
      href={href}
      onClick={onClick}
      className={cn(
        'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all',
        isActive
          ? 'bg-red-600/15 text-white border-l-2 border-red-500'
          : 'text-zinc-400 hover:text-white hover:bg-zinc-900/60'
      )}
    >
      <Icon className="w-4 h-4 flex-shrink-0" />
      {label}
    </Link>
  );
}

function SidebarContent({ onClose }: { onClose?: () => void }) {
  const { data: health, isError: healthUnavailable } = useHealth();

  return (
    <div className="flex flex-col h-full bg-black border-r border-zinc-900">
      {/* Header */}
      <div className="px-4 py-5 border-b border-zinc-900">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-red-600/20 border border-red-600/30 flex items-center justify-center">
            <Eye className="w-4 h-4 text-red-500" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-white tracking-tight">⚡ Nightwatch</span>
              <HealthDot status={health?.status} unavailable={healthUnavailable} />
            </div>
            <p className="text-xs text-zinc-600">
              {health?.version ? `v${health.version}` : 'Version unavailable'}
            </p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-5 overflow-y-auto">
        <div className="space-y-1">
          <NavLink
            href="/"
            label="Command Center"
            icon={LayoutDashboard}
            onClick={onClose}
          />
        </div>

        {navGroups.map((group) => (
          <div key={group.label} className="space-y-1">
            <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-zinc-600">
              {group.label}
            </p>
            {group.items.map((item) => (
              <NavLink
                key={`${group.label}-${item.href}`}
                {...item}
                onClick={onClose}
              />
            ))}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-zinc-900">
        <p className="text-xs text-zinc-700">
          Read-only operations intelligence
        </p>
      </div>
    </div>
  );
}

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-56 flex-shrink-0">
        <SidebarContent />
      </aside>

      {/* Mobile: top bar + sheet */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-4 py-3 bg-black border-b border-zinc-900">
        <div className="flex items-center gap-2">
          <Eye className="w-5 h-5 text-red-500" />
          <span className="font-bold text-white">⚡ Nightwatch</span>
        </div>
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetTrigger
            render={
              <Button
                variant="ghost"
                size="icon"
                className="text-zinc-400"
                aria-label="Open navigation menu"
              />
            }
          >
            <Menu className="w-5 h-5" />
            <span className="sr-only">Open navigation menu</span>
          </SheetTrigger>
          <SheetContent side="left" className="p-0 w-56 bg-black border-zinc-900">
            <SidebarContent onClose={() => setMobileOpen(false)} />
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
