'use client';

import { AlertTriangle, GitFork } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useAdapters } from '@/hooks/useNightwatch';

function isPipeline(type: string, category?: string) {
  const identity = `${type} ${category ?? ''}`.toLowerCase();
  return ['pipeline', 'step_function', 'glue', 'job', 'workflow'].some((value) =>
    identity.includes(value),
  );
}

export default function PipelinesPage() {
  const query = useAdapters();
  const pipelines = (query.data?.adapters ?? []).flatMap((adapter) =>
    (adapter.components ?? [])
      .filter((component) => isPipeline(component.type, component.category))
      .map((component) => ({ ...component, adapter: adapter.application || adapter.name })),
  );

  return (
    <div className="space-y-6 p-6 pt-16 lg:pt-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-purple-400">Observe</p>
        <h1 className="mt-1 text-2xl font-bold text-white">Pipelines</h1>
        <p className="mt-1 text-sm text-zinc-500">Pipeline resources reported by connected adapters.</p>
      </div>

      {query.isLoading ? (
        <Skeleton className="h-64 bg-zinc-900" />
      ) : query.isError ? (
        <Card className="border-red-900/50 bg-red-950/20">
          <CardContent className="flex gap-3 p-5 text-red-300">
            <AlertTriangle className="h-5 w-5 shrink-0" />
            <p>Pipeline inventory is unavailable: {query.error.message}</p>
          </CardContent>
        </Card>
      ) : pipelines.length === 0 ? (
        <Card className="border-zinc-800 bg-zinc-950">
          <CardContent className="p-10 text-center text-sm text-zinc-500">
            No connected adapter reported pipeline resources.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {pipelines.map((pipeline) => (
            <Card key={`${pipeline.adapter}-${pipeline.type}-${pipeline.name}`} className="border-zinc-800 bg-zinc-950">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base text-white">
                  <GitFork className="h-4 w-4 text-purple-300" />
                  {pipeline.name}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex items-center justify-between gap-3 text-sm">
                <span className="text-zinc-500">{pipeline.adapter}</span>
                <Badge variant="outline" className="border-zinc-700 text-zinc-300">
                  {String(pipeline.status ?? pipeline.metadata?.status ?? 'unknown')}
                </Badge>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
