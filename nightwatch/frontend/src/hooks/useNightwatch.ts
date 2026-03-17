'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { nightwatchApi } from '@/lib/api';

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
    refetchInterval: 60000,
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
    mutationFn: ({ incident_id, adapter }: { incident_id: string; adapter?: string }) =>
      nightwatchApi.generateReport(incident_id, adapter),
  });
