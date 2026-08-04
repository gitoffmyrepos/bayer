'use client';

import { useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock3, Loader2, RefreshCw, Zap } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useAdapters, useTriggerCheck } from '@/hooks/useNightwatch';
import type { NightwatchAdapter, TriggerResponse } from '@/lib/api';

type AcceptedRequest = { acceptedAt: Date; response: TriggerResponse };

export default function LiveCheckPage() {
  const [selectedAdapter, setSelectedAdapter] = useState('all');
  const [result, setResult] = useState<TriggerResponse | null>(null);
  const [acceptedRequests, setAcceptedRequests] = useState<AcceptedRequest[]>([]);
  const adaptersQuery = useAdapters();
  const triggerMutation = useTriggerCheck();
  const adapterNames = (adaptersQuery.data?.adapters ?? []).map(
    (adapter: NightwatchAdapter) => adapter.name
  );

  function runCheck() {
    setResult(null);
    triggerMutation.reset();
    triggerMutation.mutate(selectedAdapter === 'all' ? undefined : selectedAdapter, {
      onSuccess: (response) => {
        setResult(response);
        setAcceptedRequests((requests) => [
          { acceptedAt: new Date(), response },
          ...requests,
        ].slice(0, 10));
      },
    });
  }

  return (
    <div className="space-y-6 p-6 pt-16 lg:pt-6">
      <div>
        <h1 className="text-xl font-bold text-white">Live Check</h1>
        <p className="text-sm text-zinc-500">
          Ask Nightwatch to start an asynchronous monitoring cycle for one adapter or all adapters.
        </p>
      </div>

      <Card className="border-zinc-800 bg-zinc-950">
        <CardContent className="p-6">
          {adaptersQuery.isError ? (
            <div className="flex items-start gap-3 rounded-lg border border-red-900/50 bg-red-950/20 p-4">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
              <div>
                <p className="text-sm font-medium text-red-300">Adapter list unavailable</p>
                <p className="mt-1 text-xs text-zinc-500">{adaptersQuery.error.message}</p>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap items-end gap-4">
              <div>
                <p className="mb-2 text-xs uppercase tracking-wider text-zinc-500">Target adapter</p>
                <Select value={selectedAdapter} onValueChange={(value) => setSelectedAdapter(value ?? 'all')}>
                  <SelectTrigger className="w-[220px] border-zinc-700 bg-zinc-900 text-zinc-200">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-zinc-700 bg-zinc-950">
                    <SelectItem value="all">All adapters</SelectItem>
                    {adapterNames.map((name) => (
                      <SelectItem key={name} value={name}>{name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex-1" />

              <Button
                onClick={runCheck}
                disabled={triggerMutation.isPending || adaptersQuery.isLoading}
                size="lg"
                className="gap-2 bg-red-600 px-8 font-semibold text-white hover:bg-red-700"
              >
                {triggerMutation.isPending ? (
                  <>
                    <Loader2 className="h-5 w-5 animate-spin" />
                    Submitting…
                  </>
                ) : (
                  <>
                    <Zap className="h-5 w-5" />
                    Start check
                  </>
                )}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {triggerMutation.isError && (
        <Card className="border-red-900/50 bg-red-950/20">
          <CardContent className="flex items-start gap-3 p-4">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
            <div>
              <p className="font-medium text-red-300">Check request rejected</p>
              <p className="mt-1 text-sm text-zinc-500">{triggerMutation.error.message}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {result && (
        <Card className="border-cyan-500/20 bg-zinc-950">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm text-cyan-300">
              <CheckCircle2 className="h-4 w-4" />
              Check request accepted
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pt-0">
            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <p className="text-xs text-zinc-600">Target</p>
                <p className="mt-1 font-medium text-zinc-200">{result.adapter}</p>
              </div>
              <div>
                <p className="text-xs text-zinc-600">API response</p>
                <p className="mt-1 text-zinc-300">{result.message}</p>
              </div>
            </div>
            <div className="flex items-start gap-2 rounded-lg border border-zinc-800 bg-black/40 p-3 text-xs text-zinc-500">
              <Clock3 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              The API accepted this request and runs collection in the background. This response does not prove
              that the check is complete; review Status and Incidents after the cycle finishes.
            </div>
          </CardContent>
        </Card>
      )}

      {acceptedRequests.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-500">
            Accepted requests this session
          </h2>
          <Card className="border-zinc-800 bg-zinc-950">
            <CardContent className="p-0">
              {acceptedRequests.map((item, index) => (
                <div
                  key={`${item.acceptedAt.toISOString()}-${index}`}
                  className="flex items-center justify-between border-b border-zinc-800 px-4 py-3 text-sm last:border-0"
                >
                  <div className="flex items-center gap-2.5">
                    <RefreshCw className="h-3.5 w-3.5 text-zinc-500" />
                    <span className="text-zinc-400">{item.response.adapter}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-zinc-600">{item.acceptedAt.toLocaleTimeString()}</span>
                    <Badge variant="outline" className="border-cyan-500/20 bg-cyan-500/10 text-xs text-cyan-300">
                      accepted
                    </Badge>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}

      {!result && !triggerMutation.isPending && !triggerMutation.isError && (
        <div className="py-12 text-center text-sm text-zinc-600">
          <Zap className="mx-auto mb-3 h-10 w-10 opacity-30" />
          Select a target and start a check request.
        </div>
      )}
    </div>
  );
}
