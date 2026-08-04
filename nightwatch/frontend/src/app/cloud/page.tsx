'use client';

import {
  AlertTriangle,
  CheckCircle2,
  Cloud,
  Cpu,
  Layers3,
  Server,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useAdapters, useStatus } from '@/hooks/useNightwatch';
import { cn } from '@/lib/utils';

type InventoryComponent = {
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
  components?: InventoryComponent[];
};

type CloudResource = InventoryComponent & { adapter: Adapter };

const CLOUD_MARKERS = [
  'aws',
  'eks',
  'ec2',
  'ecs',
  'lambda',
  's3',
  'glue',
  'dynamodb',
  'step_function',
  'sftp',
];

function isCloudResource(component: InventoryComponent) {
  const searchable = [
    component.type,
    component.category,
    component.metadata?.provider,
    component.metadata?.service,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  return CLOUD_MARKERS.some((marker) => searchable.includes(marker));
}

function componentStatus(component: InventoryComponent) {
  const raw = String(component.status ?? component.metadata?.status ?? 'unknown').toLowerCase();
  if (['ok', 'active', 'running', 'available', 'healthy'].includes(raw)) return 'healthy';
  if (['fail', 'failed', 'unhealthy', 'stopped', 'inactive'].includes(raw)) return 'unhealthy';
  if (['warn', 'warning', 'degraded', 'pending'].includes(raw)) return 'degraded';
  return raw;
}

function serviceName(type: string) {
  const normalized = type.toLowerCase();
  if (normalized.includes('eks')) return 'EKS';
  if (normalized.includes('ec2')) return 'EC2';
  if (normalized.includes('ecs')) return 'ECS';
  if (normalized.includes('lambda')) return 'Lambda';
  if (normalized.includes('s3')) return 'S3';
  if (normalized.includes('glue')) return 'Glue';
  if (normalized.includes('dynamodb')) return 'DynamoDB';
  if (normalized.includes('step')) return 'Step Functions';
  return type.replaceAll('_', ' ');
}

function serviceIcon(type: string) {
  const normalized = type.toLowerCase();
  if (normalized.includes('ec2')) return Server;
  if (normalized.includes('ecs') || normalized.includes('eks')) return Layers3;
  if (normalized.includes('lambda')) return Cpu;
  return Cloud;
}

function statusStyle(status: string) {
  if (status === 'healthy') return 'border-green-500/20 bg-green-500/10 text-green-400';
  if (status === 'unhealthy') return 'border-red-500/20 bg-red-500/10 text-red-400';
  if (status === 'degraded') return 'border-yellow-500/20 bg-yellow-500/10 text-yellow-400';
  return 'border-zinc-700 bg-zinc-900 text-zinc-400';
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function metadataEntries(component: InventoryComponent) {
  return Object.entries(component.metadata ?? {})
    .filter(([key]) => !['status', 'last_seen'].includes(key))
    .slice(0, 6);
}

export default function CloudEstatePage() {
  const adaptersQuery = useAdapters();
  const statusQuery = useStatus();
  const adapters = (adaptersQuery.data?.adapters ?? []) as Adapter[];
  const resources: CloudResource[] = adapters.flatMap((adapter) =>
    (adapter.components ?? [])
      .filter(isCloudResource)
      .map((component) => ({ ...component, adapter }))
  );

  const counts = resources.reduce<Record<string, number>>((result, resource) => {
    const service = serviceName(resource.type);
    result[service] = (result[service] ?? 0) + 1;
    return result;
  }, {});

  return (
    <div className="space-y-6 p-6 pt-16 lg:pt-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-400">Observe</p>
          <h1 className="mt-1 text-2xl font-bold text-white">Cloud Estate</h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-500">
            Live read-only inventory reported by connected AWS monitoring adapters.
          </p>
        </div>
        <Badge variant="outline" className="border-cyan-500/20 bg-cyan-500/10 text-cyan-300">
          <Cloud className="mr-1.5 h-3.5 w-3.5" />
          {resources.length} resources observed
        </Badge>
      </div>

      {statusQuery.isError && (
        <div className="flex items-start gap-2 rounded-lg border border-yellow-900/40 bg-yellow-950/10 p-3 text-xs text-yellow-300">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Aggregate adapter status is unavailable. Resource states below use component evidence only.
        </div>
      )}

      {adaptersQuery.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <Skeleton key={item} className="h-24 bg-zinc-900" />
          ))}
        </div>
      ) : adaptersQuery.isError ? (
        <Card className="border-red-900/50 bg-red-950/20">
          <CardContent className="flex gap-3 p-5">
            <AlertTriangle className="mt-0.5 h-5 w-5 text-red-400" />
            <div>
              <p className="font-medium text-red-300">Cloud inventory unavailable</p>
              <p className="mt-1 text-sm text-zinc-500">
                Nightwatch could not load live adapter data: {adaptersQuery.error.message}
              </p>
            </div>
          </CardContent>
        </Card>
      ) : resources.length === 0 ? (
        <Card className="border-zinc-800 bg-zinc-950">
          <CardContent className="p-10 text-center">
            <Cloud className="mx-auto h-8 w-8 text-zinc-700" />
            <p className="mt-3 font-medium text-zinc-300">No cloud resources reported</p>
            <p className="mt-1 text-sm text-zinc-600">
              Connect and start an AWS infrastructure adapter to populate this estate.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Object.entries(counts).map(([service, count]) => (
              <Card key={service} className="border-zinc-800 bg-zinc-950">
                <CardContent className="p-4">
                  <p className="text-xs uppercase tracking-wider text-zinc-600">{service}</p>
                  <p className="mt-1 text-2xl font-bold text-white">{count}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            {resources.map((resource) => {
              const status = componentStatus(resource);
              const Icon = serviceIcon(resource.type);
              const metadata = metadataEntries(resource);

              return (
                <Card
                  key={`${resource.adapter.name}-${resource.type}-${resource.name}`}
                  className="border-zinc-800 bg-zinc-950"
                >
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-start gap-3">
                        <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/10 p-2">
                          <Icon className="h-4 w-4 text-cyan-300" />
                        </div>
                        <div className="min-w-0">
                          <CardTitle className="truncate text-base text-white">{resource.name}</CardTitle>
                          <p className="mt-1 text-xs text-zinc-500">
                            {serviceName(resource.type)} · {resource.adapter.application ?? resource.adapter.name}
                          </p>
                        </div>
                      </div>
                      <Badge variant="outline" className={cn('capitalize', statusStyle(status))}>
                        {status === 'healthy' && <CheckCircle2 className="mr-1 h-3 w-3" />}
                        {status}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {resource.description && (
                      <p className="text-sm text-zinc-400">{resource.description}</p>
                    )}
                    {metadata.length > 0 && (
                      <dl className="grid grid-cols-2 gap-x-5 gap-y-2 border-t border-zinc-800 pt-3 text-xs">
                        {metadata.map(([key, value]) => (
                          <div key={key} className="min-w-0">
                            <dt className="truncate text-zinc-600">{key.replaceAll('_', ' ')}</dt>
                            <dd className="mt-0.5 truncate font-mono text-zinc-300" title={displayValue(value)}>
                              {displayValue(value)}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
