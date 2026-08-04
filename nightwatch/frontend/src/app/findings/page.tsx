'use client';

import { AlertTriangle, CheckCircle2, ListChecks } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useIncidents } from '@/hooks/useNightwatch';

function severityStyle(severity: string) {
  if (severity === 'critical') return 'border-red-500/30 bg-red-500/10 text-red-300';
  if (severity === 'high') return 'border-orange-500/30 bg-orange-500/10 text-orange-300';
  return 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300';
}

export default function FindingsPage() {
  const query = useIncidents({ limit: 100, active_only: true });
  const findings = query.data?.incidents ?? [];

  return (
    <div className="space-y-6 p-6 pt-16 lg:pt-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-purple-400">Observe</p>
        <h1 className="mt-1 text-2xl font-bold text-white">Findings</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Active findings derived from collected checks; no client-side records are inserted.
        </p>
      </div>

      {query.isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((item) => <Skeleton key={item} className="h-28 bg-zinc-900" />)}
        </div>
      ) : query.isError ? (
        <Card className="border-red-900/50 bg-red-950/20">
          <CardContent className="flex gap-3 p-5 text-red-300">
            <AlertTriangle className="h-5 w-5 shrink-0" />
            <p>Findings are unavailable: {query.error.message}</p>
          </CardContent>
        </Card>
      ) : findings.length === 0 ? (
        <Card className="border-zinc-800 bg-zinc-950">
          <CardContent className="p-10 text-center">
            <CheckCircle2 className="mx-auto h-8 w-8 text-green-500" />
            <p className="mt-3 font-medium text-zinc-200">No active findings reported</p>
            <p className="mt-1 text-sm text-zinc-500">Run Live Check to collect current evidence.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {findings.map((finding) => (
            <Card key={finding.id} className="border-zinc-800 bg-zinc-950">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-start justify-between gap-3 text-base text-white">
                  <span className="flex items-center gap-2">
                    <ListChecks className="h-4 w-4 text-purple-300" />
                    {finding.component}
                  </span>
                  <Badge variant="outline" className={severityStyle(finding.severity)}>
                    {finding.severity}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-zinc-300">{finding.message}</p>
                <div className="mt-3 flex justify-between text-xs text-zinc-600">
                  <span>{finding.adapter}</span>
                  <span className="font-mono">{finding.id}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
