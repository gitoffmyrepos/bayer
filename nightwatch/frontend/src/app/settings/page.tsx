'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useAdapters, useSchedule } from '@/hooks/useNightwatch';
import { Brain, Bell, Clock, Puzzle, AlertCircle } from 'lucide-react';

function SettingRow({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex items-start justify-between py-3">
      <div>
        <p className="text-sm text-slate-300">{label}</p>
        {sub && <p className="text-xs text-slate-600 mt-0.5">{sub}</p>}
      </div>
      <span className="text-sm text-slate-400 font-mono bg-slate-800 px-2 py-1 rounded text-right max-w-xs">
        {value}
      </span>
    </div>
  );
}

export default function SettingsPage() {
  const { data: adapters } = useAdapters();
  const { data: schedule } = useSchedule();

  const tasks = schedule?.tasks ?? [];
  const checkInterval = tasks[0]?.interval_seconds
    ? `${tasks[0].interval_seconds}s (${Math.floor(tasks[0].interval_seconds / 60)}m)`
    : '300s (5m)';

  return (
    <div className="p-6 lg:pt-6 pt-16 space-y-6 max-w-3xl">
      <div>
        <h1 className="text-xl font-bold text-slate-100">Settings</h1>
        <p className="text-sm text-slate-500">Platform configuration (read from nightwatch.yaml)</p>
      </div>

      {/* LLM Config */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2 text-slate-300">
            <Brain className="w-4 h-4 text-indigo-400" />
            LLM Provider
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="divide-y divide-slate-800">
            <SettingRow
              label="Provider"
              value="anthropic"
              sub="Configured via LLM_PROVIDER env var"
            />
            <SettingRow
              label="Model"
              value="claude-3-5-sonnet-20241022"
              sub="Default Anthropic model"
            />
            <SettingRow
              label="API Key"
              value="$ANTHROPIC_API_KEY"
              sub="Set via environment variable"
            />
          </div>
          <div className="mt-3 p-3 bg-indigo-950/30 border border-indigo-500/20 rounded-lg text-xs text-indigo-300">
            Supports: Claude (Anthropic) · GPT-4 (OpenAI) · DeepSeek · Ollama (local)
          </div>
        </CardContent>
      </Card>

      {/* Check Schedule */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2 text-slate-300">
            <Clock className="w-4 h-4 text-indigo-400" />
            Check Schedule
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="divide-y divide-slate-800">
            <SettingRow
              label="Check Interval"
              value={checkInterval}
              sub="How often Nightwatch runs automated checks"
            />
            <div className="py-3">
              <p className="text-sm text-slate-300 mb-3">Scheduled Tasks</p>
              <div className="space-y-2">
                {tasks.length > 0 ? tasks.map((task: { name: string; status: string; last_run?: string }) => (
                  <div key={task.name} className="flex items-center justify-between p-2 bg-slate-800/40 rounded-lg">
                    <span className="text-xs text-slate-400 font-mono">{task.name}</span>
                    <Badge variant="outline" className={`text-xs ${task.status === 'running' ? 'bg-green-500/10 text-green-400 border-green-500/20' : 'bg-slate-500/10 text-slate-400 border-slate-500/20'}`}>
                      {task.status}
                    </Badge>
                  </div>
                )) : (
                  <p className="text-xs text-slate-600">No tasks scheduled</p>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Alert Channels */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2 text-slate-300">
            <Bell className="w-4 h-4 text-indigo-400" />
            Alert Channels
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="divide-y divide-slate-800">
            {[
              { name: 'Slack', key: 'SLACK_WEBHOOK_URL', configured: false },
              { name: 'Discord', key: 'DISCORD_WEBHOOK_URL', configured: false },
              { name: 'PagerDuty', key: 'PAGERDUTY_ROUTING_KEY', configured: false },
              { name: 'Email (SMTP)', key: 'SMTP_HOST', configured: false },
            ].map(ch => (
              <div key={ch.name} className="flex items-center justify-between py-3">
                <div>
                  <p className="text-sm text-slate-300">{ch.name}</p>
                  <p className="text-xs text-slate-600">{ch.key}</p>
                </div>
                <Badge
                  variant="outline"
                  className={ch.configured
                    ? 'text-xs bg-green-500/10 text-green-400 border-green-500/20'
                    : 'text-xs bg-slate-500/10 text-slate-500 border-slate-700'
                  }
                >
                  {ch.configured ? 'configured' : 'not configured'}
                </Badge>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-start gap-2 p-3 bg-yellow-500/5 border border-yellow-500/20 rounded-lg text-xs text-yellow-400">
            <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            Configure alert channels via environment variables or nightwatch.yaml
          </div>
        </CardContent>
      </Card>

      {/* Adapters */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2 text-slate-300">
            <Puzzle className="w-4 h-4 text-indigo-400" />
            Adapters
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {(adapters?.adapters ?? []).map((adapter: { name: string; application: string; class: string; is_running: boolean }) => (
              <div key={adapter.name} className="flex items-center justify-between p-3 bg-slate-800/40 rounded-lg border border-slate-800">
                <div>
                  <p className="text-sm text-slate-200 font-medium">{adapter.name}</p>
                  <p className="text-xs text-slate-500">{adapter.application} · {adapter.class}</p>
                </div>
                <div className="flex items-center gap-3">
                  <Label htmlFor={`sw-${adapter.name}`} className="text-xs text-slate-500">Enabled</Label>
                  <Switch
                    id={`sw-${adapter.name}`}
                    checked={adapter.is_running}
                    disabled
                    className="data-[state=checked]:bg-indigo-600"
                  />
                </div>
              </div>
            ))}
            {(adapters?.adapters?.length ?? 0) === 0 && (
              <p className="text-xs text-slate-600 text-center py-4">No adapters configured</p>
            )}
          </div>
          <p className="mt-3 text-xs text-slate-600">
            Adapter toggles are visual only. To enable/disable adapters, edit <code className="text-slate-500">config/nightwatch.yaml</code>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
