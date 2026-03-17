const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

// ─── Mock Data ────────────────────────────────────────────────────────────────
const mockStatus = {
  overall: 'healthy',
  adapters: {
    forextrader: {
      adapter: 'forextrader',
      status: 'healthy',
      last_check: new Date().toISOString(),
      components_checked: 12,
      issues_found: 0,
      details: {
        components: [
          { name: 'ml-trainer', type: 'kubernetes', status: 'healthy', last_seen: new Date().toISOString() },
          { name: 'api-gateway', type: 'kubernetes', status: 'healthy', last_seen: new Date().toISOString() },
          { name: 'timescaledb', type: 'database', status: 'healthy', last_seen: new Date().toISOString() },
          { name: 'redpanda', type: 'messaging', status: 'healthy', last_seen: new Date().toISOString() },
        ],
      },
    },
    aws_pipeline: {
      adapter: 'aws_pipeline',
      status: 'degraded',
      last_check: new Date(Date.now() - 300000).toISOString(),
      components_checked: 8,
      issues_found: 1,
      details: {
        components: [
          { name: 's3-ingestion', type: 'aws', status: 'healthy', last_seen: new Date().toISOString() },
          { name: 'lambda-processor', type: 'aws', status: 'degraded', last_seen: new Date().toISOString() },
          { name: 'rds-postgres', type: 'database', status: 'healthy', last_seen: new Date().toISOString() },
        ],
      },
    },
  },
  timestamp: new Date().toISOString(),
};

const mockIncidents = {
  total: 2,
  incidents: [
    {
      id: 'inc-001',
      severity: 'P2',
      component: 'lambda-processor',
      message: 'Lambda function execution latency above threshold (p99: 4200ms)',
      adapter: 'aws_pipeline',
      started_at: new Date(Date.now() - 1800000).toISOString(),
      resolved_at: null,
      status: 'active',
      ai_analysis: 'The Lambda function is experiencing elevated latency likely due to cold starts combined with increased payload sizes. Recommend reviewing memory allocation and considering provisioned concurrency for critical functions.',
    },
    {
      id: 'inc-002',
      severity: 'P3',
      component: 'ml-trainer',
      message: 'GPU utilization dropped to 45% during scheduled training window',
      adapter: 'forextrader',
      started_at: new Date(Date.now() - 7200000).toISOString(),
      resolved_at: new Date(Date.now() - 5400000).toISOString(),
      status: 'resolved',
      ai_analysis: 'GPU utilization dip was caused by a data preprocessing bottleneck. Training resumed normally after the preprocessing queue cleared.',
    },
  ],
};

const mockAdapters = {
  adapter_count: 2,
  adapters: [
    {
      name: 'forextrader',
      application: 'ForexTrader ML Platform',
      class: 'ForexTraderAdapter',
      is_running: true,
      check_count: 47,
      components: [
        { name: 'ml-trainer', type: 'kubernetes', status: 'healthy', last_seen: new Date().toISOString() },
        { name: 'api-gateway', type: 'kubernetes', status: 'healthy', last_seen: new Date().toISOString() },
        { name: 'timescaledb', type: 'database', status: 'healthy', last_seen: new Date().toISOString() },
        { name: 'redpanda', type: 'messaging', status: 'healthy', last_seen: new Date().toISOString() },
        { name: 'qdrant', type: 'vector-db', status: 'healthy', last_seen: new Date().toISOString() },
        { name: 'oanda-feed', type: 'external', status: 'healthy', last_seen: new Date().toISOString() },
      ],
    },
    {
      name: 'aws_pipeline',
      application: 'AWS Data Pipeline',
      class: 'AWSPipelineAdapter',
      is_running: true,
      check_count: 23,
      components: [
        { name: 's3-ingestion', type: 'aws', status: 'healthy', last_seen: new Date().toISOString() },
        { name: 'lambda-processor', type: 'aws', status: 'degraded', last_seen: new Date().toISOString() },
        { name: 'rds-postgres', type: 'database', status: 'healthy', last_seen: new Date().toISOString() },
        { name: 'cloudwatch-metrics', type: 'monitoring', status: 'healthy', last_seen: new Date().toISOString() },
      ],
    },
  ],
  registered_types: ['forextrader', 'aws_pipeline'],
};

const mockHealth = {
  status: 'ok',
  version: '2.0.0',
  timestamp: new Date().toISOString(),
  uptime_seconds: 16320,
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function fetchWithFallback<T>(url: string, fallback: T, options?: RequestInit): Promise<T> {
  try {
    const res = await fetch(url, { ...options, signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as T;
  } catch {
    console.warn(`[Nightwatch] API unavailable, using mock data for: ${url}`);
    return fallback;
  }
}

async function fetchTextWithFallback(url: string, fallback: string): Promise<string> {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.text();
  } catch {
    return fallback;
  }
}

// ─── API Client ───────────────────────────────────────────────────────────────

export const nightwatchApi = {
  getHealth: () =>
    fetchWithFallback(`${API_BASE}/health`, mockHealth),

  getStatus: () =>
    fetchWithFallback(`${API_BASE}/status`, mockStatus),

  getIncidents: (params?: { limit?: number; active_only?: boolean; adapter?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.active_only) searchParams.set('active_only', 'true');
    if (params?.adapter) searchParams.set('adapter', params.adapter);
    const query = searchParams.toString();
    return fetchWithFallback(
      `${API_BASE}/incidents${query ? `?${query}` : ''}`,
      mockIncidents
    );
  },

  triggerCheck: (adapter?: string) =>
    fetchWithFallback(
      `${API_BASE}/check`,
      { triggered: true, adapter: adapter || 'all', message: 'Check cycle started (mock)' },
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ adapter }),
      }
    ),

  getAdapters: () =>
    fetchWithFallback(`${API_BASE}/adapters`, mockAdapters),

  getMetrics: () =>
    fetchTextWithFallback(
      `${API_BASE}/metrics`,
      '# Nightwatch Metrics (mock)\nnightwatch_check_total{adapter="forextrader"} 47\nnightwatch_check_total{adapter="aws_pipeline"} 23\n'
    ),

  getSchedule: () =>
    fetchWithFallback(`${API_BASE}/schedule`, {
      tasks: [
        { name: 'monitor_forextrader', interval_seconds: 300, last_run: new Date().toISOString(), status: 'running' },
        { name: 'monitor_aws_pipeline', interval_seconds: 300, last_run: new Date().toISOString(), status: 'running' },
      ],
    }),

  generateReport: (incident_id: string, adapter?: string) =>
    fetchWithFallback(
      `${API_BASE}/report`,
      {
        incident_id,
        report: `## Incident Report: ${incident_id}\n\n**Generated:** ${new Date().toLocaleString()}\n\n### Summary\nMock report generated — connect the backend to get real AI analysis.\n\n### Root Cause\nPending investigation.\n\n### Recommendations\n1. Review service logs\n2. Check infrastructure metrics\n3. Monitor for recurrence`,
      },
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ incident_id, adapter }),
      }
    ),
};
