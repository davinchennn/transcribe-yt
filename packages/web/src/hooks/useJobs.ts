import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as api from '../api/client';
import type { CreateJobOptions, NavigationView } from '../api/client';

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
    refetchInterval: refetchInterval ?? ((query) => {
      const status = query.state.data?.analysis?.status;
      return status === 'pending' || status === 'processing' ? 2000 : false;
    }),
  });
}

export function useNavigation(id: string, view: NavigationView) {
  return useQuery({
    queryKey: ['navigation', id, view],
    queryFn: () => api.getNavigation(id, view),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'pending' || status === 'processing' ? 2000 : false;
    },
  });
}

export function useCreateNavigation(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (view: NavigationView) => api.createNavigation(id, view),
    onSuccess: async (data, view) => {
      await queryClient.cancelQueries({ queryKey: ['navigation', id, view], exact: true });
      queryClient.setQueryData(['navigation', id, view], data);
      queryClient.invalidateQueries({ queryKey: ['job', id] });
    },
  });
}

export function useUpdateNavigationSummaries(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (view: NavigationView) => api.updateNavigationSummaries(id, view),
    onSuccess: async (data, view) => {
      await queryClient.cancelQueries({ queryKey: ['navigation', id, view], exact: true });
      queryClient.setQueryData(['navigation', id, view], data);
      queryClient.invalidateQueries({ queryKey: ['job', id] });
    },
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
