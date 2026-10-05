import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as api from '../api/client';
import type { CreateJobOptions } from '../api/client';

export function useJobs() {
  return useQuery({
    queryKey: ['jobs'],
    queryFn: () => api.listJobs(),
    refetchInterval: 2000, // Poll every 2 seconds for status updates
  });
}

export function useJob(id: string | null, refetchInterval?: number | false) {
  return useQuery({
    queryKey: ['job', id],
    queryFn: () => (id ? api.getJob(id) : null),
    enabled: !!id,
    refetchInterval: refetchInterval,
  });
}

export function useCreateJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (options: CreateJobOptions) => api.createJob(options),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useRetryJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.retryJob(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useDeleteJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.deleteJob(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useAnalyzeJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.analyzeJob(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ['job', id] });
    },
  });
}
