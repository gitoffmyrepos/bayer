'use client';

import {
  AlertTriangle,
  Boxes,
  CheckCircle2,
  CircleHelp,
  ServerCog,
  ShieldCheck,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useAdapters, useStatus } from '@/hooks/useNightwatch';
import { cn } from '@/lib/utils';

type KubernetesComponent = {
  name: string;
  type: string;
  category?: string;
  description?: string;
  status?: string;
  last_seen?: string | null;
  metadata?: Record<string, unknown>;
};

type Adapter = {
  name: string;
  application?: string;
  is_running?: boolean;
  components?: KubernetesComponent[];
};

type Workload = KubernetesComponent & { adapter: Adapter };

function isKubernetesComponent(component: KubernetesComponent) {
  const value = [component.type, component.category, component.metadata?.provider]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  return value.includes('k8s') || value.includes('kubernetes') || value.includes('eks');
}

function normalizeStatus(component: KubernetesComponent) {
  const raw = String(component.status ?? component.metadata?.status ?? 'unknown').toLowerCase();
  if (['ok', 'active', 'running', 'available', 'healthy', 'ready'].includes(raw)) return 'healthy';
  if (['warn', 'warning', 'degraded', 'pending', 'partial'].includes(raw)) return 'degraded';
  if (['fail', 'failed', 'unhealthy', 'stopped', 'notready'].includes(raw)) return 'unhealthy';
  if (raw === 'scaled_down') return 'scaled down';
  return raw;
}

function statusStyle(status: string) {
  if (status === 'healthy') return 'border-green-500/20 bg-green-500/10 text-green-400';
  if (status === 'unhealthy') return 'border-red-500/20 bg-red-500/10 text-red-400';
  if (status === 'degraded') return 'border-yellow-500/20 bg-yellow-500/10 text-yellow-400';
  return 'border-zinc-700 bg-zinc-900 text-zinc-400';
}

function workloadKind(type: string) {
  return type
    .replace(/^k8s_/, '')
    .replace(/^kubernetes_/, '')
    .replaceAll('_', ' ');
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export default function KubernetesPage() {
  const adaptersQuery = useAdapters();
  const statusQuery = useStatus();
  const adapters = (adaptersQuery.data?.adapters ?? []) as Adapter[];
  const workloads: Workload[] = adapters.flatMap((adapter) =>
    (adapter.components ?? [])
      .filter(isKubernetesComponent)
      .map((component) => ({ ...component, adapter }))
  );

  const statusCounts = workloads.reduce(
    (counts, workload) => {
      const status = normalizeStatus(workload);
      if (status === 'healthy') counts.healthy += 1;
      else if (status === 'unhealthy') counts.unhealthy += 1;
      else if (status === 'degraded') counts.degraded += 1;
      else counts.unknown += 1;
      return counts;
    },
    { healthy: 0, degraded: 0, unhealthy: 0, unknown: 0 }
  );

  return (
    <div className="space-y-6 p-6 pt-16 lg:pt-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-purple-400">Observe</p>
          <h1 className="mt-1 text-2xl font-bold text-white">Kubernetes</h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-500">
            Cluster and workload state from Nightwatch&apos;s read-only Kubernetes and EKS connections.
          </p>
        </div>
        <Badge variant="outline" className="border-purple-500/20 bg-purple-500/10 text-purple-300">
          <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
          Observe mode
        </Badge>
      </div>

      {statusQuery.isError && (
        <div className="flex items-start gap-2 rounded-lg border border-yellow-900/40 bg-yellow-950/10 p-3 text-xs text-yellow-300">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Aggregate adapter status is unavailable. Workload states below use component evidence only.
        </div>
      )}

      {adaptersQuery.isLoading ? (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((item) => <Skeleton key={item} className="h-24 bg-zinc-900" />)}
          </div>
          <Skeleton className="h-72 bg-zinc-900" />
        </div>
      ) : adaptersQuery.isError ? (
        <Card className="border-red-900/50 bg-red-950/20">
          <CardContent className="flex gap-3 p-5">
            <AlertTriangle className="mt-0.5 h-5 w-5 text-red-400" />
            <div>
              <p className="font-medium text-red-300">Kubernetes inventory unavailable</p>
              <p className="mt-1 text-sm text-zinc-500">
                Nightwatch could not load live cluster data: {adaptersQuery.error.message}
              </p>
            </div>
          </CardContent>
        </Card>
      ) : workloads.length === 0 ? (
        <Card className="border-zinc-800 bg-zinc-950">
          <CardContent className="p-10 text-center">
            <Boxes className="mx-auto h-8 w-8 text-zinc-700" />
            <p className="mt-3 font-medium text-zinc-300">No Kubernetes resources reported</p>
            <p className="mt-1 text-sm text-zinc-600">
              Connect a Kubernetes or EKS adapter and verify its read-only access.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { label: 'Healthy', value: statusCounts.healthy, color: 'text-green-400' },
              { label: 'Degraded', value: statusCounts.degraded, color: 'text-yellow-400' },
              { label: 'Unhealthy', value: statusCounts.unhealthy, color: 'text-red-400' },
              { label: 'Unknown', value: statusCounts.unknown, color: 'text-zinc-400' },
            ].map((item) => (
              <Card key={item.label} className="border-zinc-800 bg-zinc-950">
                <CardContent className="p-4">
                  <p className="text-xs uppercase tracking-wider text-zinc-600">{item.label}</p>
                  <p className={cn('mt-1 text-2xl font-bold', item.color)}>{item.value}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          <Card className="border-zinc-800 bg-zinc-950">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base text-white">
                <ServerCog className="h-4 w-4 text-purple-300" />
                Observed clusters and workloads
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px]">
                  <thead>
                    <tr className="border-y border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-600">
                      <th className="px-5 py-3 font-medium">Resource</th>
                      <th className="px-5 py-3 font-medium">Kind</th>
                      <th className="px-5 py-3 font-medium">Namespace / Cluster</th>
                      <th className="px-5 py-3 font-medium">Adapter</th>
                      <th className="px-5 py-3 font-medium">Readiness</th>
                      <th className="px-5 py-3 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workloads.map((workload) => {
                      const status = normalizeStatus(workload);
                      const metadata = workload.metadata ?? {};
                      const scope =
                        metadata.namespace ?? metadata.cluster ?? metadata.cluster_name ?? metadata.name;
                      const ready =
                        metadata.ready !== undefined && metadata.desired !== undefined
                          ? `${displayValue(metadata.ready)} / ${displayValue(metadata.desired)}`
                          : metadata.version ?? workload.description;

                      return (
                        <tr
                          key={`${workload.adapter.name}-${workload.type}-${workload.name}`}
                          className="border-b border-zinc-900 hover:bg-zinc-900/30"
                        >
                          <td className="px-5 py-4">
                            <div className="flex items-center gap-2">
                              {status === 'healthy' ? (
                                <CheckCircle2 className="h-4 w-4 text-green-400" />
                              ) : (
                                <CircleHelp className="h-4 w-4 text-zinc-500" />
                              )}
                              <span className="font-medium text-zinc-200">{workload.name}</span>
                            </div>
                          </td>
                          <td className="px-5 py-4 text-sm capitalize text-zinc-400">
                            {workloadKind(workload.type)}
                          </td>
                          <td className="px-5 py-4 font-mono text-xs text-zinc-400">
                            {displayValue(scope)}
                          </td>
                          <td className="px-5 py-4 text-sm text-zinc-500">
                            {workload.adapter.application ?? workload.adapter.name}
                          </td>
                          <td className="px-5 py-4 text-sm text-zinc-400">
                            {displayValue(ready)}
                          </td>
                          <td className="px-5 py-4">
                            <Badge variant="outline" className={cn('capitalize', statusStyle(status))}>
                              {status}
                            </Badge>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
