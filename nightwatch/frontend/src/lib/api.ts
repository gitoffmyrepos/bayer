// In production, kgateway routes /api/* to the backend and strips /api.
// Local development can override this with NEXT_PUBLIC_API_URL=http://localhost:8080.
const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

export type NightwatchComponent = {
  name: string;
  type: string;
  status?: string;
  category?: string;
  description?: string;
  last_seen?: string;
  metadata?: Record<string, unknown>;
};

export type NightwatchAdapter = {
  name: string;
  application: string;
  class: string;
  is_running: boolean;
  check_count: number;
  components: NightwatchComponent[];
};

export type NightwatchIncident = {
  id: string;
  severity: string;
  component: string;
  message: string;
  adapter: string;
  started_at: string;
  resolved_at?: string | null;
  status: string;
  ai_analysis?: string;
  ai_diagnosis_status?: 'disabled' | 'pending' | 'complete' | 'unavailable';
  ai_diagnosis_provider?: string;
  ai_diagnosis_model?: string;
  ai_diagnosis_updated_at?: string | null;
  diagnosis?: {
    root_cause?: string;
    severity?: string;
    recommendation?: string;
    confidence?: number;
    auto_fix_possible?: boolean;
    auto_fix_command?: string | null;
  };
};

type HealthResponse = {
  status: string;
  version: string;
  timestamp: string;
  uptime_seconds: number;
};

type StatusResponse = {
  overall: string;
  timestamp: string;
  adapters: Record<string, Record<string, unknown>>;
};

type IncidentsResponse = { total: number; incidents: NightwatchIncident[] };
type AdaptersResponse = {
  adapter_count: number;
  adapters: NightwatchAdapter[];
  registered_types?: string[];
};
export type NightwatchScheduledTask = {
  name: string;
  interval_seconds: number;
  last_run?: string | null;
  run_count: number;
  error_count: number;
  is_running: boolean;
  [key: string]: unknown;
};
type ScheduleResponse = {
  tasks: NightwatchScheduledTask[];
};
type MetricsResponse = {
  timestamp: string;
  metrics: Record<string, Record<string, unknown>>;
};
export type TriggerResponse = { triggered: boolean; adapter: string; message: string };
type ReportResponse = { incident_id: string; report: string };
export type LlmProvider = 'ollama' | 'openai' | 'anthropic' | 'deepseek';
export type LlmSettings = {
  provider: LlmProvider;
  model: string;
  base_url: string;
  api_key_configured: boolean;
  configured: boolean;
  configured_providers: Record<LlmProvider, boolean>;
  persistence_enabled: boolean;
};
export type LlmSettingsInput = {
  provider: LlmProvider;
  model: string;
  base_url: string;
  api_key?: string;
  clear_api_key?: boolean;
};
type LlmTestResponse = { ok: boolean; provider: LlmProvider; model: string };

export class NightwatchApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly url?: string,
  ) {
    super(message);
    this.name = 'NightwatchApiError';
  }
}

async function request<T>(
  path: string,
  options?: RequestInit,
  timeoutMilliseconds = 10000,
): Promise<T> {
  const url = `${API_BASE}${path}`;
  let response: Response;

  try {
    response = await fetch(url, {
      ...options,
      signal: AbortSignal.timeout(timeoutMilliseconds),
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : 'network request failed';
    throw new NightwatchApiError(`Nightwatch API unavailable: ${detail}`, undefined, url);
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail || detail;
    } catch {
      // The status code remains the authoritative failure when no JSON body exists.
    }
    throw new NightwatchApiError(detail, response.status, url);
  }

  return (await response.json()) as T;
}

export const nightwatchApi = {
  getHealth: () => request<HealthResponse>('/health'),

  getStatus: () => request<StatusResponse>('/status'),

  getIncidents: (params?: { limit?: number; active_only?: boolean; adapter?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.active_only) searchParams.set('active_only', 'true');
    if (params?.adapter) searchParams.set('adapter', params.adapter);
    const query = searchParams.toString();
    return request<IncidentsResponse>(`/incidents${query ? `?${query}` : ''}`);
  },

  triggerCheck: (adapter?: string) => {
    const query = adapter ? `?adapter=${encodeURIComponent(adapter)}` : '';
    return request<TriggerResponse>(`/check${query}`, { method: 'POST' });
  },

  getAdapters: () => request<AdaptersResponse>('/adapters'),

  getMetrics: () => request<MetricsResponse>('/metrics'),

  getSchedule: () => request<ScheduleResponse>('/schedule'),

  getLlmSettings: () => request<LlmSettings>('/llm/settings'),

  testLlmSettings: (settings: LlmSettingsInput) =>
    request<LlmTestResponse>('/llm/settings/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    }, 120000),

  generateReport: (incident_id: string, adapter?: string, llm?: LlmSettingsInput) =>
    request<ReportResponse>(
      '/report',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ incident_id, adapter, ...(llm ? { llm } : {}) }),
      },
      120000,
    ),
};
