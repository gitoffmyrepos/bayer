'use client';

import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  CheckCircle2,
  CircleHelp,
  Eye,
  Network,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useAdapters, useStatus } from '@/hooks/useNightwatch';
import { cn } from '@/lib/utils';

type TopologyComponent = {
  name: string;
  type: string;
  category?: string;
  description?: string;
  status?: string;
  metadata?: Record<string, unknown>;
};

type Adapter = {
  name: string;
  application?: string;
  is_running?: boolean;
  components?: TopologyComponent[];
};

type AdapterStatus = { status?: string; last_check?: string; issues_found?: number };

function normalizeStatus(value: unknown) {
  const status = String(value ?? 'unknown').toLowerCase();
  if (['ok', 'active', 'running', 'available', 'healthy', 'ready'].includes(status)) return 'healthy';
  if (['warn', 'warning', 'degraded', 'pending', 'partial'].includes(status)) return 'degraded';
  if (['fail', 'failed', 'unhealthy', 'stopped', 'inactive'].includes(status)) return 'unhealthy';
  return status;
}

function componentStatus(component: TopologyComponent) {
  return normalizeStatus(component.status ?? component.metadata?.status);
}

function nodeStyle(status: string) {
  if (status === 'healthy') return 'border-green-500/25 bg-green-500/5';
  if (status === 'unhealthy') return 'border-red-500/30 bg-red-500/5';
  if (status === 'degraded') return 'border-yellow-500/30 bg-yellow-500/5';
  return 'border-zinc-800 bg-zinc-900/50';
}

function dotStyle(status: string) {
  if (status === 'healthy') return 'bg-green-400';
  if (status === 'unhealthy') return 'bg-red-400';
  if (status === 'degraded') return 'bg-yellow-400';
  return 'bg-zinc-600';
}

export default function TopologyPage() {
  const adaptersQuery = useAdapters();
  const statusQuery = useStatus();
  const adapters = (adaptersQuery.data?.adapters ?? []) as Adapter[];
  const adapterStatuses = (statusQuery.data?.adapters ?? {}) as Record<string, AdapterStatus>;
  const relationCount = adapters.reduce(
    (count, adapter) => count + 1 + (adapter.components?.length ?? 0),
    0
  );
  return (
    <div className="space-y-6 p-6 pt-16 lg:pt-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-400">Investigate</p>
          <h1 className="mt-1 text-2xl font-bold text-white">Topology</h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-500">
            Live observation paths from Nightwatch through each adapter to its reported resources.
          </p>
        </div>
        <Badge variant="outline" className="border-emerald-500/20 bg-emerald-500/10 text-emerald-300">
          <Network className="mr-1.5 h-3.5 w-3.5" />
          {relationCount} relationships
        </Badge>
      </div>

      {statusQuery.isError && (
        <div className="flex items-start gap-2 rounded-lg border border-yellow-900/40 bg-yellow-950/10 p-3 text-xs text-yellow-300">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Adapter health is unavailable. Component nodes retain their own reported states or remain unknown.
        </div>
      )}

      {adaptersQuery.isLoading ? (
        <div className="space-y-4">
          {[0, 1].map((item) => <Skeleton key={item} className="h-56 bg-zinc-900" />)}
        </div>
      ) : adaptersQuery.isError ? (
        <Card className="border-red-900/50 bg-red-950/20">
          <CardContent className="flex gap-3 p-5">
            <AlertTriangle className="mt-0.5 h-5 w-5 text-red-400" />
            <div>
              <p className="font-medium text-red-300">Topology unavailable</p>
              <p className="mt-1 text-sm text-zinc-500">
                Nightwatch could not load live relationships: {adaptersQuery.error.message}
              </p>
            </div>
          </CardContent>
        </Card>
      ) : adapters.length === 0 ? (
        <Card className="border-zinc-800 bg-zinc-950">
          <CardContent className="p-10 text-center">
            <Network className="mx-auto h-8 w-8 text-zinc-700" />
            <p className="mt-3 font-medium text-zinc-300">No topology reported</p>
            <p className="mt-1 text-sm text-zinc-600">
              Connected adapters and their live component inventory appear here.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-5">
          {adapters.map((adapter) => {
            const reportedAdapterStatus = adapterStatuses[adapter.name]?.status;
            const adapterStatus = reportedAdapterStatus
              ? normalizeStatus(reportedAdapterStatus)
              : adapter.is_running
                ? 'running'
                : 'unknown';
            const components = adapter.components ?? [];

            return (
              <Card key={adapter.name} className="overflow-hidden border-zinc-800 bg-zinc-950">
                <CardHeader className="border-b border-zinc-900 pb-4">
                  <div className="flex items-center justify-between gap-3">
                    <CardTitle className="text-sm font-semibold text-white">
                      {adapter.application ?? adapter.name}
                    </CardTitle>
                    <p className="text-xs text-zinc-600">{components.length} resource nodes</p>
                  </div>
                </CardHeader>
                <CardContent className="p-5">
                  <div className="grid items-center gap-4 lg:grid-cols-[180px_28px_220px_28px_minmax(0,1fr)]">
                    <div className="rounded-lg border border-red-500/25 bg-red-500/5 p-4">
                      <div className="flex items-center gap-2">
                        <Eye className="h-4 w-4 text-red-400" />
                        <p className="font-medium text-zinc-200">Nightwatch</p>
                      </div>
                      <p className="mt-2 text-xs text-zinc-600">Read-only observer</p>
                    </div>

                    <div className="hidden items-center justify-center text-zinc-700 lg:flex">
                      <ArrowRight className="h-5 w-5" />
                    </div>

                    <div className={cn('rounded-lg border p-4', nodeStyle(adapterStatus))}>
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex min-w-0 items-center gap-2">
                          <Boxes className="h-4 w-4 shrink-0 text-cyan-400" />
                          <p className="truncate font-medium text-zinc-200">{adapter.name}</p>
                        </div>
                        <span className={cn('h-2 w-2 shrink-0 rounded-full', dotStyle(adapterStatus))} />
                      </div>
                      <p className="mt-2 text-xs capitalize text-zinc-600">{adapterStatus} connection</p>
                    </div>

                    <div className="hidden items-center justify-center text-zinc-700 lg:flex">
                      <ArrowRight className="h-5 w-5" />
                    </div>

                    {components.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-zinc-800 p-5 text-sm text-zinc-600">
                        This adapter reported no component relationships.
                      </div>
                    ) : (
                      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                        {components.map((component) => {
                          const status = componentStatus(component);
                          return (
                            <div
                              key={`${component.type}-${component.name}`}
                              className={cn('min-w-0 rounded-lg border p-3', nodeStyle(status))}
                            >
                              <div className="flex items-center gap-2">
                                {status === 'healthy' ? (
                                  <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-green-400" />
                                ) : (
                                  <CircleHelp className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
                                )}
                                <p className="truncate text-sm font-medium text-zinc-300" title={component.name}>
                                  {component.name}
                                </p>
                              </div>
                              <p className="mt-1 truncate text-xs text-zinc-600">
                                {component.category ?? component.type.replaceAll('_', ' ')}
                              </p>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
