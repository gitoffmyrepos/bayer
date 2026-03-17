'use client';

import { useState } from 'react';
import { Zap, CheckCircle2, XCircle, Minus, Loader2, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import { useAdapters, useTriggerCheck } from '@/hooks/useNightwatch';
import { cn } from '@/lib/utils';

function statusBg(status: string) {
  switch (status?.toLowerCase()) {
    case 'healthy': return 'bg-green-500/10 text-green-400 border-green-500/20';
    case 'degraded': return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
    case 'unhealthy': return 'bg-red-500/10 text-red-400 border-red-500/20';
    default: return 'bg-slate-500/10 text-slate-400 border-slate-500/20';
  }
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'healthy') return <CheckCircle2 className="w-4 h-4 text-green-400" />;
  if (status === 'degraded') return <Minus className="w-4 h-4 text-yellow-400" />;
  return <XCircle className="w-4 h-4 text-red-400" />;
}

type CheckResult = {
  triggered: boolean;
  adapter: string;
  message: string;
};

export default function LiveCheckPage() {
  const [selectedAdapter, setSelectedAdapter] = useState<string>('all');
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<CheckResult | null>(null);
  const [checkHistory, setCheckHistory] = useState<Array<{ time: Date; result: CheckResult }>>([]);

  const { data: adapters } = useAdapters();
  const { mutate: triggerCheck, isPending } = useTriggerCheck();

  const adapterNames: string[] = adapters?.adapters?.map((a: { name: string }) => a.name) ?? [];

  function runCheck() {
    setResult(null);
    setProgress(0);

    // Simulate progress
    const interval = setInterval(() => {
      setProgress(p => {
        if (p >= 90) { clearInterval(interval); return p; }
        return p + Math.random() * 15;
      });
    }, 200);

    triggerCheck(
      selectedAdapter === 'all' ? undefined : selectedAdapter,
      {
        onSuccess: (data: CheckResult) => {
          clearInterval(interval);
          setProgress(100);
          setResult(data);
          setCheckHistory(h => [{ time: new Date(), result: data }, ...h].slice(0, 10));
        },
        onError: () => {
          clearInterval(interval);
          setProgress(0);
        },
      }
    );
  }

  const currentAdapterData = adapters?.adapters?.find(
    (a: { name: string }) => a.name === (result?.adapter === 'all' ? adapterNames[0] : result?.adapter)
  );

  return (
    <div className="p-6 lg:pt-6 pt-16 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-100">Live Check</h1>
        <p className="text-sm text-slate-500">Trigger an immediate monitoring check on any adapter</p>
      </div>

      {/* Controls */}
      <Card className="bg-slate-900 border-slate-800">
        <CardContent className="p-6">
          <div className="flex flex-wrap items-center gap-4">
            <div>
              <p className="text-xs text-slate-500 mb-2 uppercase tracking-wider">Target Adapter</p>
              <Select value={selectedAdapter} onValueChange={(v) => setSelectedAdapter(v ?? 'all')}>
                <SelectTrigger className="w-[200px] bg-slate-800 border-slate-700 text-slate-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-slate-900 border-slate-700">
                  <SelectItem value="all">All Adapters</SelectItem>
                  {adapterNames.map((name) => (
                    <SelectItem key={name} value={name}>{name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex-1" />

            <Button
              onClick={runCheck}
              disabled={isPending}
              size="lg"
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-8 gap-2"
            >
              {isPending ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Running Check…
                </>
              ) : (
                <>
                  <Zap className="w-5 h-5" />
                  Run Check Now
                </>
              )}
            </Button>
          </div>

          {isPending && (
            <div className="mt-4 space-y-2">
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>Checking components…</span>
                <span>{Math.round(progress)}%</span>
              </div>
              <Progress value={progress} className="h-2 bg-slate-800" />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Result */}
      {result && (
        <div className="space-y-4">
          <Card className="bg-slate-900 border-slate-800 border-green-500/20">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2 text-green-400">
                <CheckCircle2 className="w-4 h-4" />
                Check Complete
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-slate-500 text-xs mb-1">Target</p>
                  <p className="text-slate-200 font-medium">{result.adapter}</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs mb-1">Triggered</p>
                  <p className="text-slate-200">{result.triggered ? 'Yes' : 'No'}</p>
                </div>
              </div>
              <div className="mt-3">
                <p className="text-slate-500 text-xs mb-1">Message</p>
                <p className="text-slate-300 text-sm bg-slate-800 rounded-lg p-3">{result.message}</p>
              </div>
            </CardContent>
          </Card>

          {/* Component results from adapter data */}
          {adapters?.adapters && (
            <div>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">Component Results</p>
              <div className="space-y-2">
                {adapters.adapters
                  .filter((a: { name: string }) => result.adapter === 'all' || a.name === result.adapter)
                  .flatMap((a: { name: string; components: Array<{ name: string; type: string; status: string; last_seen?: string }> }) =>
                    a.components.map((c: { name: string; type: string; status: string; last_seen?: string }) => ({ ...c, adapter: a.name }))
                  )
                  .map((comp: { name: string; type: string; status: string; last_seen?: string; adapter: string }, i: number) => (
                    <Card key={i} className="bg-slate-900 border-slate-800">
                      <CardContent className="p-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2.5">
                            <StatusIcon status={comp.status} />
                            <div>
                              <p className="text-sm text-slate-200 font-medium">{comp.name}</p>
                              <p className="text-xs text-slate-500">{comp.adapter} · {comp.type}</p>
                            </div>
                          </div>
                          <Badge variant="outline" className={cn('text-xs', statusBg(comp.status))}>
                            {comp.status.toUpperCase()}
                          </Badge>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Check History */}
      {checkHistory.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Check History
          </h2>
          <Card className="bg-slate-900 border-slate-800">
            <CardContent className="p-0">
              {checkHistory.map((item, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between px-4 py-3 border-b border-slate-800 last:border-0 text-sm"
                >
                  <div className="flex items-center gap-2.5">
                    <RefreshCw className="w-3.5 h-3.5 text-slate-500" />
                    <span className="text-slate-400">{item.result.adapter}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-slate-600">
                      {item.time.toLocaleTimeString()}
                    </span>
                    <Badge variant="outline" className="text-xs bg-green-500/10 text-green-400 border-green-500/20">
                      triggered
                    </Badge>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}

      {!result && !isPending && (
        <div className="text-center py-12 text-slate-600 text-sm">
          <Zap className="w-10 h-10 mx-auto mb-3 opacity-30" />
          Select an adapter and click Run Check to trigger an immediate check
        </div>
      )}
    </div>
  );
}
