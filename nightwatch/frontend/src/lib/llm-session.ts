import type { LlmProvider, LlmSettingsInput } from '@/lib/api';

const SESSION_KEY = 'nightwatch.llm.provider';
const PROVIDERS = new Set<LlmProvider>(['ollama', 'openai', 'anthropic', 'deepseek']);

export function readLlmSession(): LlmSettingsInput | undefined {
  if (typeof window === 'undefined') return undefined;
  const encoded = window.sessionStorage.getItem(SESSION_KEY);
  if (!encoded) return undefined;
  try {
    const value = JSON.parse(encoded) as Partial<LlmSettingsInput>;
    if (!value.provider || !PROVIDERS.has(value.provider) || !value.model?.trim()) return undefined;
    return {
      provider: value.provider,
      model: value.model,
      base_url: value.base_url ?? '',
      ...(value.api_key ? { api_key: value.api_key } : {}),
    };
  } catch {
    return undefined;
  }
}

export function saveLlmSession(settings: LlmSettingsInput): void {
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(settings));
}

export function clearLlmSession(): void {
  window.sessionStorage.removeItem(SESSION_KEY);
}
