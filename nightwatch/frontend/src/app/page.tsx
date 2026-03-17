'use client';

import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Cpu,
  RefreshCw,
  XCircle,
  Minus,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useHealth, useStatus, useIncidents } from '@/hooks/useNightwatch';
import { cn } from '@/lib/utils';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function statusColor(status: string) {
  switch (status?.toLowerCase()) {
    case 'healthy': return 'text-green-400';
    case 'degraded': return 'text-yellow-400';
    case 'unhealthy': return 'text-red-400';
    default: return 'text-slate-400';
  }
}

function statusBg(status: string) {
  switch (status?.toLowerCase()) {
    case 'healthy': return 'bg-green-500/10 text-green-400 border-green-500/20';
    case 'degraded': return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
    case 'unhealthy': return 'bg-red-500/10 text-red-400 border-red-500/20';
    default: return 'bg-slate-500/10 text-slate-400 border-slate-500/20';
  }
}

function severityBg(sev: string) {
  switch (sev) {
    case 'P1': return 'bg-red-500/10 text-red-400 border-red-500/20';
    case 'P2': return 'bg-orange-500/10 text-orange-400 border-orange-500/20';
    case 'P3': return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
    default: return 'bg-slate-500/10 text-slate-400 border-slate-500/20';
  }
}

function formatUptime(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'healthy') return <CheckCircle2 className="w-4 h-4 text-green-400" />;
  if (status === 'degraded') return <Minus className="w-4 h-4 text-yellow-400" />;
  return <XCircle className="w-4 h-4 text-red-400" />;
}

// ─── Stat Card ────────────────────────────────────────────────────────────────

function StatCard({
  title,
  value,
  icon: Icon,
  color,
  loading,
}: {
  title: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
  loading?: boolean;
}) {
  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-slate-500 font-medium uppercase tracking-wider mb-1">{title}</p>
            {loading ? (
              <Skeleton className="h-7 w-20 bg-slate-800" />
            ) : (
              <p className={cn('text-2xl font-bold', color)}>{value}</p>
            )}
          </div>
          <div className={cn('p-2 rounded-lg bg-slate-800/60')}>
            <Icon className={cn('w-5 h-5', color)} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Adapter Card ─────────────────────────────────────────────────────────────

function AdapterCard({ name, data }: { name: string; data: Record<string, unknown> }) {
  const status = (data?.status ?? 'unknown') as string;
  const lastCheck = data?.last_check as string | undefined;
  const components = ((data as Record<string, unknown>)?.details as Record<string, unknown>)?.components as Array<Record<string, unknown>> | undefined;

  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold text-slate-100">{name}</CardTitle>
          <Badge variant="outline" className={cn('text-xs', statusBg(status))}>
            <StatusIcon status={status} />
            <span className="ml-1.5">{status.toUpperCase()}</span>
          </Badge>
        </div>
        {lastCheck && (
          <p className="text-xs text-slate-500">
            Last check: {formatDistanceToNow(new Date(lastCheck), { addSuffix: true })}
          </p>
        )}
      </CardHeader>
      <CardContent className="pt-0">
        {components?.length ? (
          <div className="space-y-1.5">
            {components.slice(0, 5).map((c, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2 text-slate-400">
                  <StatusIcon status={c.status as string} />
                  <span>{c.name as string}</span>
                  <span className="text-slate-600">({c.type as string})</span>
                </div>
                <span className={statusColor(c.status as string)}>
                  {(c.status as string).toUpperCase()}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-600">No component data</p>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Incident Row ─────────────────────────────────────────────────────────────

type Incident = {
  id: string;
  severity: string;
  component: string;
  message: string;
  adapter: string;
  started_at: string;
  status: string;
  ai_analysis?: string;
  resolved_at?: string | null;
};

function IncidentRow({
  incident,
  onClick,
}: {
  incident: Incident;
  onClick: () => void;
}) {
  return (
    <tr
      className="border-b border-slate-800 hover:bg-slate-800/40 cursor-pointer transition-colors"
      onClick={onClick}
    >
      <td className="px-4 py-3">
        <Badge variant="outline" className={cn('text-xs font-bold', severityBg(incident.severity))}>
          {incident.severity}
        </Badge>
      </td>
      <td className="px-4 py-3 text-sm text-slate-300">{incident.component}</td>
      <td className="px-4 py-3 text-sm text-slate-400 max-w-xs truncate">{incident.message}</td>
      <td className="px-4 py-3 text-xs text-slate-500">
        {formatDistanceToNow(new Date(incident.started_at), { addSuffix: true })}
      </td>
      <td className="px-4 py-3">
        <Badge
          variant="outline"
          className={cn(
            'text-xs',
            incident.status === 'active'
              ? 'bg-red-500/10 text-red-400 border-red-500/20'
              : 'bg-green-500/10 text-green-400 border-green-500/20'
          )}
        >
          {incident.status}
        </Badge>
      </td>
    </tr>
  );
}

// ─── Dashboard Page ───────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { data: health, isLoading: healthLoading } = useHealth();
  const { data: status, isLoading: statusLoading } = useStatus();
  const { data: incidents, isLoading: incidentsLoading } = useIncidents({ limit: 10 });

  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);

  const adapters = status?.adapters ?? {};
  const adapterCount = Object.keys(adapters).length;
  const activeIncidents = incidents?.incidents?.filter((i: Incident) => i.status === 'active') ?? [];

  return (
    <div className="p-6 lg:pt-6 pt-16 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100">Dashboard</h1>
          <p className="text-sm text-slate-500">Real-time monitoring overview</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          Auto-refreshing
        </div>
      </div>

      {/* Row 1 — Status Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Overall Health"
          value={status?.overall?.toUpperCase() ?? 'UNKNOWN'}
          icon={Activity}
          color={statusColor(status?.overall ?? '')}
          loading={statusLoading}
        />
        <StatCard
          title="Active Incidents"
          value={activeIncidents.length}
          icon={AlertTriangle}
          color={activeIncidents.length > 0 ? 'text-red-400' : 'text-green-400'}
          loading={incidentsLoading}
        />
        <StatCard
          title="Adapters"
          value={adapterCount}
          icon={Cpu}
          color="text-indigo-400"
          loading={statusLoading}
        />
        <StatCard
          title="Uptime"
          value={health?.uptime_seconds ? formatUptime(health.uptime_seconds) : '—'}
          icon={Clock}
          color="text-slate-300"
          loading={healthLoading}
        />
      </div>

      {/* Row 2 — Adapter Panels */}
      <div>
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
          Adapter Status
        </h2>
        {statusLoading ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {[0, 1].map((i) => (
              <Card key={i} className="bg-slate-900 border-slate-800">
                <CardContent className="p-5">
                  <Skeleton className="h-5 w-32 bg-slate-800 mb-3" />
                  <Skeleton className="h-3 w-full bg-slate-800 mb-2" />
                  <Skeleton className="h-3 w-4/5 bg-slate-800" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : adapterCount === 0 ? (
          <Card className="bg-slate-900 border-slate-800">
            <CardContent className="p-8 text-center text-slate-500 text-sm">
              No adapters configured. Add adapters to <code className="text-slate-400">config/nightwatch.yaml</code>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {Object.entries(adapters).map(([name, data]) => (
              <AdapterCard key={name} name={name} data={data as Record<string, unknown>} />
            ))}
          </div>
        )}
      </div>

      {/* Row 3 — Recent Incidents */}
      <div>
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
          Recent Incidents
        </h2>
        <Card className="bg-slate-900 border-slate-800">
          {incidentsLoading ? (
            <CardContent className="p-4 space-y-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-10 w-full bg-slate-800" />
              ))}
            </CardContent>
          ) : incidents?.incidents?.length === 0 ? (
            <CardContent className="p-8 text-center text-slate-500 text-sm">
              <CheckCircle2 className="w-8 h-8 text-green-500/40 mx-auto mb-2" />
              No incidents — all systems healthy
            </CardContent>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-800">
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Severity</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Component</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Message</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Time</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(incidents?.incidents ?? []).slice(0, 8).map((inc: Incident) => (
                    <IncidentRow
                      key={inc.id}
                      incident={inc}
                      onClick={() => setSelectedIncident(inc)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* Row 4 — Activity Feed */}
      <div>
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
          Activity Feed
        </h2>
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-4 space-y-2">
            {Object.entries(adapters as Record<string, Record<string, unknown>>).flatMap(([name, data]) => {
              const comps = ((data?.details as Record<string, unknown>)?.components as Array<Record<string, unknown>>) ?? [];
              return comps.map((c, i) => ({
                key: `${name}-${i}`,
                time: new Date(c.last_seen as string || Date.now()),
                adapter: name,
                component: c.name as string,
                status: c.status as string,
              }));
            }).sort((a, b) => b.time.getTime() - a.time.getTime()).slice(0, 10).map((item) => (
              <div key={item.key} className="flex items-center gap-3 text-xs py-1">
                <StatusIcon status={item.status} />
                <span className="text-slate-500 w-20 flex-shrink-0">
                  {formatDistanceToNow(item.time, { addSuffix: true })}
                </span>
                <span className="text-slate-400 font-medium">[{item.adapter}]</span>
                <span className="text-slate-300">{item.component}</span>
                <span className={cn('ml-auto font-semibold', statusColor(item.status))}>
                  {item.status.toUpperCase()}
                </span>
              </div>
            ))}
            {Object.keys(adapters).length === 0 && (
              <p className="text-xs text-slate-600 text-center py-4">No activity yet</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Incident Detail Dialog */}
      <Dialog open={!!selectedIncident} onOpenChange={() => setSelectedIncident(null)}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100 max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selectedIncident && (
                <Badge variant="outline" className={cn('text-xs font-bold', severityBg(selectedIncident.severity))}>
                  {selectedIncident.severity}
                </Badge>
              )}
              Incident Detail
            </DialogTitle>
          </DialogHeader>
          {selectedIncident && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-slate-500 text-xs mb-1">Component</p>
                  <p className="text-slate-200 font-medium">{selectedIncident.component}</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs mb-1">Adapter</p>
                  <p className="text-slate-200 font-medium">{selectedIncident.adapter}</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs mb-1">Started</p>
                  <p className="text-slate-200">{new Date(selectedIncident.started_at).toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs mb-1">Status</p>
                  <Badge variant="outline" className={cn('text-xs', selectedIncident.status === 'active' ? 'bg-red-500/10 text-red-400 border-red-500/20' : 'bg-green-500/10 text-green-400 border-green-500/20')}>
                    {selectedIncident.status}
                  </Badge>
                </div>
              </div>
              <div>
                <p className="text-slate-500 text-xs mb-1">Message</p>
                <p className="text-slate-200 text-sm bg-slate-800 rounded-lg p-3">{selectedIncident.message}</p>
              </div>
              {selectedIncident.ai_analysis && (
                <div>
                  <p className="text-slate-500 text-xs mb-1 flex items-center gap-1">
                    <span>⚡</span> AI Analysis
                  </p>
                  <p className="text-slate-300 text-sm bg-indigo-950/40 border border-indigo-500/20 rounded-lg p-3 leading-relaxed">
                    {selectedIncident.ai_analysis}
                  </p>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
