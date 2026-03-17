'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import {
  LayoutDashboard,
  AlertTriangle,
  Puzzle,
  Zap,
  Settings,
  BookOpen,
  Menu,
  X,
  Eye,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { useHealth } from '@/hooks/useNightwatch';

const navItems = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/incidents', label: 'Incidents', icon: AlertTriangle },
  { href: '/adapters', label: 'Adapters', icon: Puzzle },
  { href: '/check', label: 'Live Check', icon: Zap },
  { href: '/settings', label: 'Settings', icon: Settings },
  { href: '/docs', label: 'Docs', icon: BookOpen },
];

function HealthDot({ status }: { status?: string }) {
  const color =
    status === 'healthy' || status === 'ok'
      ? 'bg-green-400'
      : status === 'degraded'
      ? 'bg-yellow-400'
      : status === 'unhealthy'
      ? 'bg-red-400'
      : 'bg-slate-500';
  return (
    <span
      className={cn(
        'inline-block w-2.5 h-2.5 rounded-full animate-pulse',
        color
      )}
    />
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
          ? 'bg-slate-800 text-slate-100 shadow-sm'
          : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/60'
      )}
    >
      <Icon className="w-4 h-4 flex-shrink-0" />
      {label}
    </Link>
  );
}

function SidebarContent({ onClose }: { onClose?: () => void }) {
  const { data: health } = useHealth();

  return (
    <div className="flex flex-col h-full bg-slate-900 border-r border-slate-800">
      {/* Header */}
      <div className="px-4 py-5 border-b border-slate-800">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center">
            <Eye className="w-4 h-4 text-indigo-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-slate-100 tracking-tight">⚡ Nightwatch</span>
              <HealthDot status={health?.status === 'ok' ? 'healthy' : health?.status} />
            </div>
            <p className="text-xs text-slate-500">v{health?.version ?? '2.0.0'}</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink key={item.href} {...item} onClick={onClose} />
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-slate-800">
        <p className="text-xs text-slate-600">
          Cloud-agnostic AI monitoring
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
      <div className="lg:hidden fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-4 py-3 bg-slate-900 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Eye className="w-5 h-5 text-indigo-400" />
          <span className="font-bold text-slate-100">⚡ Nightwatch</span>
        </div>
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetTrigger>
            <Button variant="ghost" size="icon" className="text-slate-400">
              {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="p-0 w-56 bg-slate-900 border-slate-800">
            <SidebarContent onClose={() => setMobileOpen(false)} />
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
