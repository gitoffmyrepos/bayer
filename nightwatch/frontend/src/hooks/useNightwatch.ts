'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { nightwatchApi, type LlmSettingsInput } from '@/lib/api';
import { readLlmSession } from '@/lib/llm-session';

export const useHealth = () =>
  useQuery({
    queryKey: ['health'],
    queryFn: nightwatchApi.getHealth,
    refetchInterval: 30000,
  });

export const useStatus = () =>
  useQuery({
    queryKey: ['status'],
    queryFn: nightwatchApi.getStatus,
    refetchInterval: 30000,
  });

export const useIncidents = (params?: {
  limit?: number;
  active_only?: boolean;
  adapter?: string;
}) =>
  useQuery({
    queryKey: ['incidents', params],
    queryFn: () => nightwatchApi.getIncidents(params),
    // Background Ollama diagnosis enriches an already-recorded incident.
    // Poll frequently enough for an open issue sheet to update in place.
    refetchInterval: 15000,
  });

export const useAdapters = () =>
  useQuery({
    queryKey: ['adapters'],
    queryFn: nightwatchApi.getAdapters,
    refetchInterval: 60000,
  });

export const useSchedule = () =>
  useQuery({
    queryKey: ['schedule'],
    queryFn: nightwatchApi.getSchedule,
    refetchInterval: 30000,
  });

export const useLlmSettings = () =>
  useQuery({
    queryKey: ['llm-settings'],
    queryFn: nightwatchApi.getLlmSettings,
  });

export const useSessionLlm = () =>
  useQuery({
    queryKey: ['llm-session'],
    queryFn: async () => readLlmSession() ?? null,
    staleTime: Number.POSITIVE_INFINITY,
  });

export const useTestLlmSettings = () =>
  useMutation({ mutationFn: (settings: LlmSettingsInput) => nightwatchApi.testLlmSettings(settings) });

export const useTriggerCheck = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: nightwatchApi.triggerCheck,
    onSuccess: () => {
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['status'] });
        queryClient.invalidateQueries({ queryKey: ['incidents'] });
      }, 3000);
    },
  });
};

export const useGenerateReport = () =>
  useMutation({
    mutationFn: ({ incident_id, adapter, llm }: { incident_id: string; adapter?: string; llm?: LlmSettingsInput }) =>
      nightwatchApi.generateReport(incident_id, adapter, llm),
  });
