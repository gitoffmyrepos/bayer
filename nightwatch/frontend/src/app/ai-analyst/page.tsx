'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  AlertTriangle,
  BrainCircuit,
  FileSearch,
  Loader2,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { useGenerateReport, useIncidents, useLlmSettings, useSessionLlm } from '@/hooks/useNightwatch';
import { cn } from '@/lib/utils';

function severityStyle(severity: string) {
  const normalized = severity.toLowerCase();
  if (['critical', 'p1'].includes(normalized)) {
    return 'border-red-500/20 bg-red-500/10 text-red-400';
  }
  if (['high', 'p2'].includes(normalized)) {
    return 'border-orange-500/20 bg-orange-500/10 text-orange-400';
  }
  if (['medium', 'p3'].includes(normalized)) {
    return 'border-yellow-500/20 bg-yellow-500/10 text-yellow-400';
  }
  return 'border-zinc-700 bg-zinc-900 text-zinc-400';
}

export default function AiAnalystPage() {
  const [selectedId, setSelectedId] = useState('');
  const incidentsQuery = useIncidents({ limit: 100 });
  const llmSettingsQuery = useLlmSettings();
  const sessionLlmQuery = useSessionLlm();
  const reportMutation = useGenerateReport();
  const incidents = incidentsQuery.data?.incidents ?? [];
  const selected = incidents.find((incident) => incident.id === selectedId);
  const sessionLlm = sessionLlmQuery.data ?? undefined;
  const llmConfigured = Boolean(sessionLlm || llmSettingsQuery.data?.configured);

  function selectIncident(value: string | null) {
    setSelectedId(value ?? '');
    reportMutation.reset();
  }

  function generateReport() {
    if (!selected) return;
    reportMutation.mutate({ incident_id: selected.id, llm: sessionLlm });
  }

  return (
    <div className="space-y-6 p-6 pt-16 lg:pt-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-400">Investigate</p>
          <h1 className="mt-1 text-2xl font-bold text-white">AI Analyst</h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-500">
            Ask the configured Nightwatch LLM to explain a real incident using its collected evidence.
          </p>
        </div>
        <Badge variant="outline" className="border-cyan-500/20 bg-cyan-500/10 text-cyan-300">
          <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
          Analysis only · no remediation
        </Badge>
      </div>

      {incidentsQuery.isLoading ? (
        <div className="grid gap-5 xl:grid-cols-[360px_1fr]">
          <Skeleton className="h-80 bg-zinc-900" />
          <Skeleton className="h-80 bg-zinc-900" />
        </div>
      ) : incidentsQuery.isError ? (
        <Card className="border-red-900/50 bg-red-950/20">
          <CardContent className="flex gap-3 p-5">
            <AlertTriangle className="mt-0.5 h-5 w-5 text-red-400" />
            <div>
              <p className="font-medium text-red-300">Incident evidence unavailable</p>
              <p className="mt-1 text-sm text-zinc-500">
                Nightwatch could not load incidents: {incidentsQuery.error.message}
              </p>
            </div>
          </CardContent>
        </Card>
      ) : incidents.length === 0 ? (
        <Card className="border-zinc-800 bg-zinc-950">
          <CardContent className="p-10 text-center">
            <FileSearch className="mx-auto h-8 w-8 text-zinc-700" />
            <p className="mt-3 font-medium text-zinc-300">No incidents available for analysis</p>
            <p className="mt-1 text-sm text-zinc-600">
              The analyst only works from incidents emitted by live Nightwatch checks.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid items-start gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
          <Card className="border-zinc-800 bg-zinc-950">
            <CardHeader>
              <CardTitle className="text-base text-white">Investigation evidence</CardTitle>
              <p className="text-xs text-zinc-600">Select an incident recorded by Nightwatch.</p>
            </CardHeader>
            <CardContent className="space-y-4">
              <Select value={selectedId || null} onValueChange={selectIncident}>
                <SelectTrigger className="h-10 w-full border-zinc-700 bg-black text-zinc-300">
                  <SelectValue placeholder="Choose an incident" />
                </SelectTrigger>
                <SelectContent className="border-zinc-700 bg-zinc-950 text-zinc-200">
                  {incidents.map((incident) => (
                    <SelectItem key={incident.id} value={incident.id}>
                      {incident.severity} · {incident.component} · {incident.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {selected ? (
                <div className="space-y-4 rounded-lg border border-zinc-800 bg-black/50 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className={cn('text-xs', severityStyle(selected.severity))}>
                      {selected.severity}
                    </Badge>
                    <Badge variant="outline" className="border-zinc-700 text-zinc-400">
                      {selected.status}
                    </Badge>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-wider text-zinc-600">Component</p>
                    <p className="mt-1 text-sm font-medium text-zinc-200">{selected.component}</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-wider text-zinc-600">Finding</p>
                    <p className="mt-1 text-sm leading-relaxed text-zinc-400">{selected.message}</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <p className="text-zinc-600">Adapter</p>
                      <p className="mt-1 truncate text-zinc-400">{selected.adapter}</p>
                    </div>
                    <div>
                      <p className="text-zinc-600">Observed</p>
                      <p className="mt-1 text-zinc-400">
                        {new Date(selected.started_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-600">
                  No incident selected
                </div>
              )}

              <Button
                onClick={generateReport}
                disabled={!selected || reportMutation.isPending || !llmConfigured}
                className="h-10 w-full bg-cyan-500 text-black hover:bg-cyan-400"
              >
                {reportMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="mr-2 h-4 w-4" />
                )}
                Analyze with Nightwatch LLM
              </Button>
              {!llmConfigured && !llmSettingsQuery.isLoading && (
                <p className="text-center text-xs text-amber-400">
                  An LLM provider is required.{' '}
                  <Link href="/settings" className="underline underline-offset-2 hover:text-amber-300">
                    Add Ollama or an API key
                  </Link>
                  .
                </p>
              )}
            </CardContent>
          </Card>

          <Card className="min-h-[420px] border-zinc-800 bg-zinc-950">
            <CardHeader className="border-b border-zinc-900">
              <CardTitle className="flex items-center gap-2 text-base text-white">
                <BrainCircuit className="h-4 w-4 text-cyan-300" />
                Analyst report
              </CardTitle>
              <p className="text-xs text-zinc-600">
                {sessionLlm
                  ? `${sessionLlm.provider} · ${sessionLlm.model} · this browser tab`
                  : llmSettingsQuery.data?.configured
                    ? `${llmSettingsQuery.data.provider} · ${llmSettingsQuery.data.model} · deployment default`
                  : 'Configure Ollama, OpenAI, Anthropic, or DeepSeek in Settings.'}
              </p>
            </CardHeader>
            <CardContent className="p-5">
              {reportMutation.isPending ? (
                <div className="flex min-h-64 flex-col items-center justify-center text-center">
                  <Loader2 className="h-7 w-7 animate-spin text-cyan-400" />
                  <p className="mt-3 text-sm text-zinc-400">Analyzing incident evidence…</p>
                </div>
              ) : reportMutation.isError ? (
                <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-4">
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
                    <div>
                      <p className="font-medium text-red-300">LLM report unavailable</p>
                      <p className="mt-1 text-sm leading-relaxed text-zinc-500">
                        {reportMutation.error.message}
                      </p>
                      <p className="mt-2 text-xs text-zinc-600">
                        Retry shortly or{' '}
                        <Link href="/settings" className="text-cyan-400 underline underline-offset-2">
                          test or change the LLM provider
                        </Link>
                        .
                      </p>
                    </div>
                  </div>
                </div>
              ) : reportMutation.data?.report ? (
                <article className="whitespace-pre-wrap text-sm leading-7 text-zinc-300">
                  {reportMutation.data.report}
                </article>
              ) : selected?.ai_diagnosis_status === 'pending' ? (
                <div className="flex min-h-64 flex-col items-center justify-center text-center">
                  <Loader2 className="h-7 w-7 animate-spin text-cyan-400" />
                  <p className="mt-3 text-sm text-zinc-400">Background Ollama analysis in progress…</p>
                  <p className="mt-1 max-w-sm text-xs leading-relaxed text-zinc-600">
                    The issue is already visible. Nightwatch will attach the diagnosis when it completes.
                  </p>
                </div>
              ) : selected?.diagnosis?.root_cause ? (
                <div className="space-y-5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs font-semibold uppercase tracking-wider text-cyan-400">
                      Background issue overview
                    </p>
                    <p className="text-xs text-zinc-600">
                      {[selected.ai_diagnosis_provider, selected.ai_diagnosis_model].filter(Boolean).join(' · ')}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-zinc-600">Root cause</p>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-zinc-300">
                      {selected.diagnosis.root_cause}
                    </p>
                  </div>
                  {selected.diagnosis.recommendation && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-zinc-600">
                        Recommended investigation
                      </p>
                      <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-zinc-400">
                        {selected.diagnosis.recommendation}
                      </p>
                    </div>
                  )}
                  <p className="border-t border-zinc-900 pt-4 text-xs text-zinc-600">
                    Advisory only — remediation is disabled and no changes were executed.
                  </p>
                </div>
              ) : selected?.ai_analysis ? (
                <div>
                  <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-600">
                    Existing incident analysis
                  </p>
                  <p className="whitespace-pre-wrap text-sm leading-7 text-zinc-400">
                    {selected.ai_analysis}
                  </p>
                </div>
              ) : (
                <div className="flex min-h-64 flex-col items-center justify-center text-center">
                  <BrainCircuit className="h-8 w-8 text-zinc-800" />
                  <p className="mt-3 text-sm text-zinc-500">Select an incident and request analysis.</p>
                  <p className="mt-1 max-w-sm text-xs leading-relaxed text-zinc-700">
                    Nightwatch sends the selected incident to the configured backend LLM; this page does not
                    synthesize findings or reports locally.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
