'use client';

import { AlertCircle, Bell, Brain, Clock, Puzzle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useAdapters, useSchedule } from '@/hooks/useNightwatch';
import type { NightwatchAdapter, NightwatchScheduledTask } from '@/lib/api';

function UnavailableConfig({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-zinc-800 bg-black/30 p-3 text-sm text-zinc-500">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-zinc-600" />
      <p>{children}</p>
    </div>
  );
}

export default function SettingsPage() {
  const adaptersQuery = useAdapters();
  const scheduleQuery = useSchedule();
  const tasks = scheduleQuery.data?.tasks ?? [];
  const adapters = adaptersQuery.data?.adapters ?? [];

  return (
    <div className="max-w-3xl space-y-6 p-6 pt-16 lg:pt-6">
      <div>
        <h1 className="text-xl font-bold text-zinc-100">Settings</h1>
        <p className="text-sm text-zinc-500">Read-only runtime state exposed by the Nightwatch API.</p>
      </div>

      <Card className="border-zinc-800 bg-zinc-950">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm text-zinc-300">
            <Brain className="h-4 w-4 text-cyan-400" />
            LLM configuration
          </CardTitle>
        </CardHeader>
        <CardContent>
          <UnavailableConfig>
            Provider, model, endpoint, and credential state are unavailable because the current API does not
            expose configuration metadata. Inspect the deployment configuration on the server.
          </UnavailableConfig>
        </CardContent>
      </Card>

      <Card className="border-zinc-800 bg-zinc-950">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm text-zinc-300">
            <Clock className="h-4 w-4 text-cyan-400" />
            Check schedule
          </CardTitle>
        </CardHeader>
        <CardContent>
          {scheduleQuery.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-14 bg-zinc-900" />
              <Skeleton className="h-14 bg-zinc-900" />
            </div>
          ) : scheduleQuery.isError ? (
            <UnavailableConfig>Schedule unavailable: {scheduleQuery.error.message}</UnavailableConfig>
          ) : tasks.length === 0 ? (
            <p className="py-4 text-center text-sm text-zinc-600">No scheduled tasks reported.</p>
          ) : (
            <div className="space-y-2">
              {tasks.map((task: NightwatchScheduledTask) => (
                <div key={task.name} className="rounded-lg border border-zinc-800 bg-black/30 p-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-mono text-sm text-zinc-300">{task.name}</p>
                      <p className="mt-1 text-xs text-zinc-600">
                        Every {task.interval_seconds}s · {task.run_count} runs · {task.error_count} errors
                      </p>
                    </div>
                    <Badge
                      variant="outline"
                      className={task.is_running
                        ? 'border-green-500/20 bg-green-500/10 text-green-400'
                        : 'border-zinc-700 bg-zinc-900 text-zinc-500'}
                    >
                      {task.is_running ? 'running' : 'stopped'}
                    </Badge>
                  </div>
                  <p className="mt-2 text-xs text-zinc-600">
                    Last run: {task.last_run ? new Date(task.last_run).toLocaleString() : 'not yet run'}
                  </p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-zinc-800 bg-zinc-950">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm text-zinc-300">
            <Bell className="h-4 w-4 text-cyan-400" />
            Alert channels
          </CardTitle>
        </CardHeader>
        <CardContent>
          <UnavailableConfig>
            Alert channel names and readiness are unavailable because the current API does not expose alert
            configuration. No channel state is inferred from frontend defaults.
          </UnavailableConfig>
        </CardContent>
      </Card>

      <Card className="border-zinc-800 bg-zinc-950">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm text-zinc-300">
            <Puzzle className="h-4 w-4 text-cyan-400" />
            Adapters
          </CardTitle>
        </CardHeader>
        <CardContent>
          {adaptersQuery.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-16 bg-zinc-900" />
              <Skeleton className="h-16 bg-zinc-900" />
            </div>
          ) : adaptersQuery.isError ? (
            <UnavailableConfig>Adapter state unavailable: {adaptersQuery.error.message}</UnavailableConfig>
          ) : adapters.length === 0 ? (
            <p className="py-4 text-center text-sm text-zinc-600">No adapters reported.</p>
          ) : (
            <div className="space-y-3">
              {adapters.map((adapter: NightwatchAdapter) => (
                <div
                  key={adapter.name}
                  className="flex items-center justify-between gap-4 rounded-lg border border-zinc-800 bg-black/30 p-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-zinc-200">{adapter.name}</p>
                    <p className="truncate text-xs text-zinc-500">
                      {adapter.application} · {adapter.class} · {adapter.components.length} components
                    </p>
                  </div>
                  <Badge
                    variant="outline"
                    className={adapter.is_running
                      ? 'border-green-500/20 bg-green-500/10 text-green-400'
                      : 'border-zinc-700 bg-zinc-900 text-zinc-500'}
                  >
                    {adapter.is_running ? 'running' : 'stopped'}
                  </Badge>
                </div>
              ))}
            </div>
          )}
          <p className="mt-3 text-xs text-zinc-600">
            This page is read-only. Change adapter configuration on the Nightwatch server and restart it.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
