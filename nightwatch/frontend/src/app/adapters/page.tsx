'use client';

import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import {
  ChevronDown, ChevronRight, CheckCircle2, XCircle, Minus,
  RefreshCw, Database, Server, Cpu, Activity, BarChart2,
  GitBranch, Shield, Monitor, Layers, AlertTriangle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useAdapters } from '@/hooks/useNightwatch';
import { cn } from '@/lib/utils';

type Component = {
  name: string;
  type: string;
  status?: string;
  last_seen?: string;
  category?: string;
  description?: string;
  metadata?: { status?: string; last_seen?: string; [key: string]: unknown };
};

type AdapterData = {
  name: string;
  application: string;
  class: string;
  is_running: boolean;
  check_count: number;
  components: Component[];
};

function compStatus(c: Component): string {
  return c.status ?? c.metadata?.status ?? 'unknown';
}
function compLastSeen(c: Component): string | undefined {
  return c.last_seen ?? (c.metadata?.last_seen as string | undefined);
}

function statusColor(s: string) {
  switch (s?.toLowerCase()) {
    case 'healthy':     return 'text-green-400';
    case 'degraded':    return 'text-yellow-400';
    case 'unhealthy':   return 'text-red-400';
    case 'scaled_down': return 'text-zinc-500';
    default:            return 'text-zinc-400';
  }
}

function statusBg(s: string) {
  switch (s?.toLowerCase()) {
    case 'healthy':     return 'bg-green-500/10 text-green-400 border-green-500/20';
    case 'degraded':    return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
    case 'unhealthy':   return 'bg-red-500/10 text-red-400 border-red-500/20';
    case 'scaled_down': return 'bg-zinc-800/60 text-zinc-500 border-zinc-700';
    default:            return 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20';
  }
}

function StatusIcon({ status, size = 'sm' }: { status: string; size?: 'sm' | 'xs' }) {
  const cls = size === 'xs' ? 'w-3 h-3' : 'w-3.5 h-3.5';
  if (status === 'healthy')     return <CheckCircle2 className={cn(cls, 'text-green-400')} />;
  if (status === 'degraded')    return <Minus className={cn(cls, 'text-yellow-400')} />;
  if (status === 'scaled_down') return <Minus className={cn(cls, 'text-zinc-500')} />;
  if (status === 'unhealthy')   return <XCircle className={cn(cls, 'text-red-400')} />;
  return <AlertTriangle className={cn(cls, 'text-zinc-500')} />;
}

const CATEGORY_META: Record<string, { icon: React.ElementType; order: number }> = {
  'Trading Execution':    { icon: Activity,   order: 1 },
  'ML / AI':              { icon: Cpu,        order: 2 },
  'ETL Pipeline':         { icon: Layers,     order: 3 },
  'Analytics':            { icon: BarChart2,  order: 4 },
  'Data Layer':           { icon: Database,   order: 5 },
  'Platform Services':    { icon: Shield,     order: 6 },
  'Frontend & Tools':     { icon: Monitor,    order: 7 },
  'Ops & Infrastructure': { icon: GitBranch,  order: 8 },
  'Cluster':              { icon: Server,     order: 9 },
  'API':                  { icon: Activity,   order: 10 },
  'OANDA':                { icon: Activity,   order: 11 },
  'Jenkins CI':           { icon: GitBranch,  order: 12 },
  'Kubernetes':           { icon: Server,     order: 99 },
};

function getCategoryMeta(cat: string) {
  return CATEGORY_META[cat] ?? { icon: Server, order: 50 };
}

function categoryRisk(comps: Component[]): number {
  if (comps.some(c => compStatus(c) === 'unhealthy')) return 0;
  if (comps.some(c => compStatus(c) === 'degraded'))  return 1;
  return 2;
}

function CategoryGroup({ category, components }: { category: string; components: Component[] }) {
  const [expanded, setExpanded] = useState(true);
  const meta = getCategoryMeta(category);
  const Icon = meta.icon;

  const healthy    = components.filter(c => compStatus(c) === 'healthy').length;
  const degraded   = components.filter(c => compStatus(c) === 'degraded').length;
  const unhealthy  = components.filter(c => compStatus(c) === 'unhealthy').length;
  const scaledDown = components.filter(c => compStatus(c) === 'scaled_down').length;
  const unknown    = components.filter(c =>
    !['healthy','degraded','unhealthy','scaled_down'].includes(compStatus(c))).length;

  const groupStatus =
    unhealthy > 0 ? 'unhealthy' :
    degraded  > 0 ? 'degraded'  : 'healthy';

  const sorted = [...components].sort((a, b) => {
    const order: Record<string, number> = { unhealthy: 0, degraded: 1, unknown: 2, healthy: 3, scaled_down: 4 };
    return (order[compStatus(a)] ?? 2) - (order[compStatus(b)] ?? 2);
  });

  return (
    <Card className="bg-zinc-950 border-zinc-800">
      <CardHeader
        className="cursor-pointer hover:bg-zinc-900/30 rounded-t-lg transition-colors py-4"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {expanded
              ? <ChevronDown className="w-4 h-4 text-zinc-500" />
              : <ChevronRight className="w-4 h-4 text-zinc-500" />}
            <div className="p-1.5 rounded-md bg-zinc-900">
              <Icon className="w-4 h-4 text-zinc-400" />
            </div>
            <div>
              <CardTitle className="text-sm font-semibold text-white">{category}</CardTitle>
              <p className="text-xs text-zinc-500 mt-0.5">{components.length} components</p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            {unhealthy > 0 && (
              <span className="text-xs font-bold text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded">
                {unhealthy} unhealthy
              </span>
            )}
            {degraded > 0 && (
              <span className="text-xs font-bold text-yellow-400 bg-yellow-500/10 border border-yellow-500/20 px-2 py-0.5 rounded">
                {degraded} degraded
              </span>
            )}
            {healthy > 0 && (
              <span className="text-xs text-green-400 bg-green-500/10 border border-green-500/20 px-2 py-0.5 rounded">
                {healthy} healthy
              </span>
            )}
            {scaledDown > 0 && (
              <span className="text-xs text-zinc-500 bg-zinc-800 border border-zinc-700 px-2 py-0.5 rounded">
                {scaledDown} off
              </span>
            )}
            {unknown > 0 && (
              <span className="text-xs text-zinc-500 bg-zinc-800 border border-zinc-700 px-2 py-0.5 rounded">
                {unknown} unknown
              </span>
            )}
            <Badge variant="outline" className={cn('text-xs ml-1', statusBg(groupStatus))}>
              <StatusIcon status={groupStatus} size="xs" />
              <span className="ml-1">{groupStatus.toUpperCase()}</span>
            </Badge>
          </div>
        </div>
      </CardHeader>

      {expanded && (
        <CardContent className="pt-0 pb-4">
          <div className="border-t border-zinc-800 pt-3">
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
              {sorted.map((comp, i) => {
                const st = compStatus(comp);
                const ls = compLastSeen(comp);
                return (
                  <div
                    key={i}
                    className={cn(
                      'flex items-center justify-between p-2.5 rounded-lg border',
                      st === 'unhealthy'   ? 'bg-red-950/20 border-red-900/40' :
                      st === 'degraded'    ? 'bg-yellow-950/20 border-yellow-900/40' :
                      st === 'scaled_down' ? 'bg-zinc-900/20 border-zinc-800/40' :
                      'bg-zinc-900/30 border-zinc-800/60'
                    )}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <StatusIcon status={st} size="xs" />
                      <div className="min-w-0">
                        <p className="text-xs text-zinc-200 font-medium truncate">{comp.name}</p>
                        <p className="text-xs text-zinc-600 truncate">{comp.description || comp.type}</p>
                      </div>
                    </div>
                    <div className="flex-shrink-0 text-right ml-2">
                      <span className={cn('text-xs font-semibold', statusColor(st))}>
                        {st === 'scaled_down' ? 'OFF' : st.toUpperCase()}
                      </span>
                      {ls && (
                        <p className="text-xs text-zinc-700 mt-0.5">
                          {formatDistanceToNow(new Date(ls), { addSuffix: true })}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </CardContent>
      )}
    </Card>
  );
}

function AdapterCard({ adapter }: { adapter: AdapterData }) {
  const grouped: Record<string, Component[]> = {};
  for (const comp of adapter.components) {
    const cat = comp.category ?? 'Kubernetes';
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(comp);
  }

  const sortedCategories = Object.entries(grouped).sort(([catA, compsA], [catB, compsB]) => {
    const riskDiff = categoryRisk(compsA) - categoryRisk(compsB);
    if (riskDiff !== 0) return riskDiff;
    return getCategoryMeta(catA).order - getCategoryMeta(catB).order;
  });

  const totalHealthy   = adapter.components.filter(c => compStatus(c) === 'healthy').length;
  const totalDegraded  = adapter.components.filter(c => compStatus(c) === 'degraded').length;
  const totalUnhealthy = adapter.components.filter(c => compStatus(c) === 'unhealthy').length;
  const totalScaled    = adapter.components.filter(c => compStatus(c) === 'scaled_down').length;

  const overallStatus =
    totalUnhealthy > 0 ? 'unhealthy' :
    totalDegraded  > 0 ? 'degraded'  : 'healthy';

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between px-1">
        <div>
          <h2 className="text-base font-bold text-white">{adapter.name}</h2>
          <p className="text-xs text-zinc-500">{adapter.application} · {adapter.check_count} checks · {adapter.components.length} components</p>
        </div>
        <div className="flex items-center gap-2 text-xs flex-wrap justify-end">
          <span className="text-green-400">{totalHealthy} healthy</span>
          {totalDegraded  > 0 && <span className="text-yellow-400">{totalDegraded} degraded</span>}
          {totalUnhealthy > 0 && <span className="text-red-400">{totalUnhealthy} unhealthy</span>}
          {totalScaled    > 0 && <span className="text-zinc-500">{totalScaled} off</span>}
          <Badge variant="outline" className={cn('text-xs', statusBg(overallStatus))}>
            {overallStatus.toUpperCase()}
          </Badge>
          <Badge variant="outline" className={cn('text-xs', adapter.is_running
            ? 'bg-green-500/10 text-green-400 border-green-500/20'
            : 'bg-zinc-800 text-zinc-500 border-zinc-700')}>
            {adapter.is_running ? 'RUNNING' : 'STOPPED'}
          </Badge>
        </div>
      </div>

      {sortedCategories.map(([category, comps]) => (
        <CategoryGroup key={category} category={category} components={comps} />
      ))}
    </div>
  );
}

export default function AdaptersPage() {
  const { data, isLoading } = useAdapters();
  const adapters: AdapterData[] = data?.adapters ?? [];
  const totalComponents = adapters.reduce((sum, a) => sum + a.components.length, 0);

  return (
    <div className="p-6 lg:pt-6 pt-16 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Adapters</h1>
          <p className="text-sm text-zinc-500">
            {data?.adapter_count ?? 0} adapters · {totalComponents} components monitored
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          Auto-refreshing
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[0, 1, 2].map(i => (
            <Card key={i} className="bg-zinc-950 border-zinc-800">
              <CardContent className="p-5">
                <Skeleton className="h-6 w-48 bg-zinc-800 mb-3" />
                <Skeleton className="h-4 w-32 bg-zinc-800 mb-4" />
                <Skeleton className="h-20 w-full bg-zinc-800" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : adapters.length === 0 ? (
        <Card className="bg-zinc-950 border-zinc-800">
          <CardContent className="p-10 text-center text-zinc-500 text-sm">
            No adapters configured. Add adapters to{' '}
            <code className="text-zinc-400">config/nightwatch.yaml</code>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-10">
          {adapters.map((adapter) => (
            <AdapterCard key={adapter.name} adapter={adapter} />
          ))}
        </div>
      )}
    </div>
  );
}
