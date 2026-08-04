'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { AlertCircle, Bell, Brain, CheckCircle2, Clock, KeyRound, Loader2, Puzzle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  useAdapters,
  useLlmSettings,
  useSchedule,
  useTestLlmSettings,
} from '@/hooks/useNightwatch';
import type { LlmProvider, LlmSettings, LlmSettingsInput, NightwatchAdapter, NightwatchScheduledTask } from '@/lib/api';
import { clearLlmSession, readLlmSession, saveLlmSession } from '@/lib/llm-session';

function UnavailableConfig({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-zinc-800 bg-black/30 p-3 text-sm text-zinc-500">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-zinc-600" />
      <p>{children}</p>
    </div>
  );
}

function LlmSettingsForm({ deployment }: { deployment: LlmSettings }) {
  const queryClient = useQueryClient();
  const testMutation = useTestLlmSettings();
  const initial = readLlmSession();
  const [provider, setProvider] = useState<LlmProvider>(initial?.provider ?? deployment.provider);
  const [model, setModel] = useState(initial?.model ?? deployment.model);
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? deployment.base_url);
  const [apiKey, setApiKey] = useState(initial?.api_key ?? '');
  const [savedForSession, setSavedForSession] = useState(Boolean(initial));

  const payload: LlmSettingsInput = {
    provider,
    model: model.trim(),
    base_url: baseUrl.trim(),
    ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
  };
  const cloudProvider = provider !== 'ollama';
  const invalid = !payload.model
    || (provider === 'ollama' && !payload.base_url)
    || (cloudProvider && !apiKey.trim());

  function save() {
    saveLlmSession(payload);
    queryClient.setQueryData(['llm-session'], payload);
    setSavedForSession(true);
  }

  function useDeploymentDefault() {
    clearLlmSession();
    queryClient.setQueryData(['llm-session'], null);
    setSavedForSession(false);
    setProvider(deployment.provider);
    setModel(deployment.model);
    setBaseUrl(deployment.base_url);
    setApiKey('');
    testMutation.reset();
  }

  return (
    <Card className="border-zinc-800 bg-zinc-950">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-zinc-300">
          <Brain className="h-4 w-4 text-cyan-400" />
          LLM configuration
        </CardTitle>
      </CardHeader>
      <CardContent>
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1.5 text-xs text-zinc-500">
                <span>Provider</span>
                <select
                  value={provider}
                  onChange={(event) => {
                    const nextProvider = event.target.value as LlmProvider;
                    setProvider(nextProvider);
                    setBaseUrl(
                      nextProvider === 'ollama' && deployment.provider === 'ollama'
                        ? deployment.base_url
                        : '',
                    );
                    testMutation.reset();
                    setSavedForSession(false);
                  }}
                  className="h-10 w-full rounded-md border border-zinc-700 bg-black px-3 text-sm text-zinc-200"
                >
                  <option value="ollama">Ollama</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="deepseek">DeepSeek</option>
                </select>
              </label>
              <label className="space-y-1.5 text-xs text-zinc-500">
                <span>Model</span>
                <input
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  placeholder="Enter the exact provider model ID"
                  className="h-10 w-full rounded-md border border-zinc-700 bg-black px-3 text-sm text-zinc-200 placeholder:text-zinc-700"
                />
              </label>
            </div>

            <label className="block space-y-1.5 text-xs text-zinc-500">
              <span>{provider === 'ollama' ? 'Ollama endpoint' : 'Provider endpoint'}</span>
              <input
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                disabled={cloudProvider}
                placeholder={provider === 'ollama' ? 'Configured by the Nightwatch deployment' : 'Official provider endpoint'}
                className="h-10 w-full rounded-md border border-zinc-700 bg-black px-3 font-mono text-sm text-zinc-200 placeholder:text-zinc-700 disabled:cursor-not-allowed disabled:text-zinc-600"
              />
            </label>

            {cloudProvider && (
              <label className="block space-y-1.5 text-xs text-zinc-500">
                <span className="flex items-center gap-1.5">
                  <KeyRound className="h-3.5 w-3.5" />
                  API key
                </span>
                <input
                  type="password"
                  autoComplete="new-password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder={`Enter your ${provider} API key`}
                  className="h-10 w-full rounded-md border border-zinc-700 bg-black px-3 font-mono text-sm text-zinc-200 placeholder:text-zinc-700"
                />
                <span className="block text-zinc-700">
                  The key stays in this browser tab and is sent only with your test or report request. Nightwatch
                  does not persist it on the server or return it in an API response.
                </span>
              </label>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={invalid || testMutation.isPending}
                onClick={() => testMutation.mutate(payload)}
                className="border-zinc-700 bg-black text-zinc-300 hover:bg-zinc-900"
              >
                {testMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Test connection
              </Button>
              <Button
                type="button"
                disabled={invalid}
                onClick={save}
                className="bg-cyan-500 text-black hover:bg-cyan-400"
              >
                Use for this tab
              </Button>
              {savedForSession && (
                <Badge variant="outline" className="border-green-500/20 bg-green-500/10 text-green-400">
                  <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
                  {provider} selected
                </Badge>
              )}
              {savedForSession && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={useDeploymentDefault}
                  className="text-zinc-500 hover:text-zinc-200"
                >
                  Use deployment default
                </Button>
              )}
            </div>

            {testMutation.isSuccess && (
              <p className="text-sm text-green-400">Connection verified for {testMutation.data.model}.</p>
            )}
            {testMutation.isError && (
              <p className="text-sm text-red-400">Connection failed: {testMutation.error.message}</p>
            )}
            <p className="text-xs text-zinc-700">
              Closing the browser tab clears user-supplied credentials. The deployment-configured provider remains
              available to all sessions.
            </p>
          </div>
      </CardContent>
    </Card>
  );
}

function LlmSettingsCard() {
  const settingsQuery = useLlmSettings();
  if (settingsQuery.isLoading) {
    return <Skeleton className="h-64 bg-zinc-900" />;
  }
  if (settingsQuery.isError || !settingsQuery.data) {
    return (
      <Card className="border-zinc-800 bg-zinc-950">
        <CardContent className="p-5">
          <UnavailableConfig>
            LLM configuration unavailable: {settingsQuery.error?.message ?? 'API returned no configuration'}
          </UnavailableConfig>
        </CardContent>
      </Card>
    );
  }
  return <LlmSettingsForm deployment={settingsQuery.data} />;
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

      <LlmSettingsCard />

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
