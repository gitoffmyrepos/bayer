'use client';

import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { ChevronDown, ChevronRight, CheckCircle2, XCircle, Minus, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useAdapters } from '@/hooks/useNightwatch';
import { cn } from '@/lib/utils';

type Component = {
  name: string;
  type: string;
  status: string;
  last_seen?: string;
};

type AdapterData = {
  name: string;
  application: string;
  class: string;
  is_running: boolean;
  check_count: number;
  components: Component[];
};

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

function StatusIcon({ status }: { status: string }) {
  if (status === 'healthy') return <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />;
  if (status === 'degraded') return <Minus className="w-3.5 h-3.5 text-yellow-400" />;
  return <XCircle className="w-3.5 h-3.5 text-red-400" />;
}

function AdapterCard({ adapter }: { adapter: AdapterData }) {
  const [expanded, setExpanded] = useState(true);

  const healthyCount = adapter.components.filter(c => c.status === 'healthy').length;
  const degradedCount = adapter.components.filter(c => c.status === 'degraded').length;
  const unhealthyCount = adapter.components.filter(c => c.status === 'unhealthy').length;

  const overallStatus =
    unhealthyCount > 0 ? 'unhealthy' :
    degradedCount > 0 ? 'degraded' : 'healthy';

  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardHeader
        className="cursor-pointer hover:bg-slate-800/30 rounded-t-lg transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 text-slate-400">
              {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </div>
            <div>
              <CardTitle className="text-base text-slate-100">{adapter.name}</CardTitle>
              <p className="text-xs text-slate-500 mt-0.5">{adapter.application}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs bg-slate-800 text-slate-400 border-slate-700">
              {adapter.class}
            </Badge>
            <Badge variant="outline" className={cn('text-xs', statusBg(overallStatus))}>
              {overallStatus.toUpperCase()}
            </Badge>
            <Badge variant="outline" className={cn('text-xs', adapter.is_running ? 'bg-green-500/10 text-green-400 border-green-500/20' : 'bg-slate-500/10 text-slate-400 border-slate-500/20')}>
              {adapter.is_running ? 'RUNNING' : 'STOPPED'}
            </Badge>
          </div>
        </div>

        <div className="flex items-center gap-4 mt-2 ml-7">
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <RefreshCw className="w-3 h-3" />
            <span>{adapter.check_count} checks</span>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <span className="text-green-400">{healthyCount} healthy</span>
            {degradedCount > 0 && <span className="text-yellow-400">{degradedCount} degraded</span>}
            {unhealthyCount > 0 && <span className="text-red-400">{unhealthyCount} unhealthy</span>}
          </div>
        </div>
      </CardHeader>

      {expanded && (
        <CardContent className="pt-0 pb-4">
          <div className="border-t border-slate-800 pt-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">
              Components ({adapter.components.length})
            </p>
            <div className="space-y-2">
              {adapter.components.map((comp, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between p-3 bg-slate-800/40 rounded-lg border border-slate-800"
                >
                  <div className="flex items-center gap-2.5">
                    <StatusIcon status={comp.status} />
                    <div>
                      <p className="text-sm text-slate-200 font-medium">{comp.name}</p>
                      <p className="text-xs text-slate-500">{comp.type}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <Badge variant="outline" className={cn('text-xs mb-1', statusBg(comp.status))}>
                      {comp.status.toUpperCase()}
                    </Badge>
                    {comp.last_seen && (
                      <p className="text-xs text-slate-600 mt-0.5">
                        {formatDistanceToNow(new Date(comp.last_seen), { addSuffix: true })}
                      </p>
                    )}
                  </div>
                </div>
              ))}
              {adapter.components.length === 0 && (
                <p className="text-xs text-slate-600 text-center py-4">No components registered</p>
              )}
            </div>
          </div>
        </CardContent>
      )}
    </Card>
  );
}

export default function AdaptersPage() {
  const { data, isLoading } = useAdapters();

  const adapters: AdapterData[] = data?.adapters ?? [];

  return (
    <div className="p-6 lg:pt-6 pt-16 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100">Adapters</h1>
          <p className="text-sm text-slate-500">
            {data?.adapter_count ?? 0} adapters configured •{' '}
            {data?.registered_types?.join(', ') ?? 'none'}
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[0, 1].map(i => (
            <Card key={i} className="bg-slate-900 border-slate-800">
              <CardContent className="p-5">
                <Skeleton className="h-6 w-48 bg-slate-800 mb-3" />
                <Skeleton className="h-4 w-32 bg-slate-800 mb-4" />
                <Skeleton className="h-20 w-full bg-slate-800" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : adapters.length === 0 ? (
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-10 text-center text-slate-500 text-sm">
            No adapters configured. Add adapters to <code className="text-slate-400">config/nightwatch.yaml</code>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {adapters.map((adapter) => (
            <AdapterCard key={adapter.name} adapter={adapter} />
          ))}
        </div>
      )}
    </div>
  );
}
