'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { BookOpen, Terminal, Puzzle, Eye, Zap } from 'lucide-react';

function Endpoint({
  method,
  path,
  description,
}: {
  method: string;
  path: string;
  description: string;
}) {
  const color =
    method === 'GET' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
    method === 'POST' ? 'bg-green-500/10 text-green-400 border-green-500/20' :
    'bg-slate-500/10 text-slate-400 border-slate-500/20';

  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-slate-800 last:border-0">
      <Badge variant="outline" className={`text-xs font-mono shrink-0 ${color}`}>{method}</Badge>
      <div>
        <code className="text-sm text-slate-200 font-mono">{path}</code>
        <p className="text-xs text-slate-500 mt-0.5">{description}</p>
      </div>
    </div>
  );
}

export default function DocsPage() {
  return (
    <div className="p-6 lg:pt-6 pt-16 space-y-6 max-w-3xl">
      <div>
        <h1 className="text-xl font-bold text-slate-100">Documentation</h1>
        <p className="text-sm text-slate-500">Nightwatch platform reference</p>
      </div>

      {/* About */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2 text-slate-300">
            <Eye className="w-4 h-4 text-indigo-400" />
            About Nightwatch
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-slate-400 space-y-2">
          <p>
            Nightwatch is a <strong className="text-slate-200">cloud-agnostic AI monitoring platform</strong> that
            monitors any application with any LLM, running anywhere.
          </p>
          <p>
            It uses pluggable <em className="text-slate-300">adapters</em> to connect to different platforms
            (Kubernetes, AWS, databases, etc.) and an LLM backend for intelligent root cause analysis.
          </p>
        </CardContent>
      </Card>

      {/* API Reference */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2 text-slate-300">
            <Terminal className="w-4 h-4 text-indigo-400" />
            API Reference
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-xs text-slate-500 mb-4 flex items-center gap-2">
            Base URL:
            <code className="text-slate-300 bg-slate-800 px-2 py-0.5 rounded">http://localhost:8080</code>
          </div>
          <Endpoint method="GET" path="/health" description="System health and uptime" />
          <Endpoint method="GET" path="/status" description="Status of all monitored adapters and components" />
          <Endpoint method="GET" path="/incidents" description="List incidents (supports limit, active_only, adapter filters)" />
          <Endpoint method="POST" path="/check" description="Trigger an immediate check cycle (body: {adapter?: string})" />
          <Endpoint method="GET" path="/adapters" description="List all configured adapters and their component inventory" />
          <Endpoint method="GET" path="/metrics" description="Prometheus-format metrics" />
          <Endpoint method="GET" path="/schedule" description="Scheduler task status" />
          <Endpoint method="POST" path="/report" description="Generate AI incident report (body: {incident_id, adapter?})" />
        </CardContent>
      </Card>

      {/* Adapters */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2 text-slate-300">
            <Puzzle className="w-4 h-4 text-indigo-400" />
            Writing Adapters
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-slate-400 space-y-3">
          <p>Adapters live in <code className="text-slate-300">src/adapters/&lt;name&gt;/adapter.py</code></p>
          <div className="bg-slate-800 rounded-lg p-3 font-mono text-xs text-slate-300 overflow-x-auto">
            {`class MyAdapter(NightwatchAdapter):
    def initialize(self) -> None: ...
    def get_component_inventory(self) -> List[Component]: ...
    async def collect_metrics(self) -> MetricSet: ...
    def cleanup(self) -> None: ...`}
          </div>
          <p className="text-xs">
            Register in <code className="text-slate-300">src/api/main.py</code> ADAPTER_REGISTRY,
            then add to <code className="text-slate-300">config/nightwatch.yaml</code>.
          </p>
        </CardContent>
      </Card>

      {/* Quick Start */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2 text-slate-300">
            <Zap className="w-4 h-4 text-indigo-400" />
            Quick Start
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3 text-sm">
            {[
              ['1. Start the backend', 'cd nightwatch && python -m src.api.main'],
              ['2. Start the frontend', 'cd nightwatch/frontend && npm run dev'],
              ['3. Open dashboard', 'http://localhost:3000'],
              ['4. Or use Docker', 'docker compose up'],
            ].map(([label, cmd]) => (
              <div key={label}>
                <p className="text-xs text-slate-500 mb-1">{label}</p>
                <div className="bg-slate-800 rounded px-3 py-2 font-mono text-xs text-slate-200">{cmd}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
