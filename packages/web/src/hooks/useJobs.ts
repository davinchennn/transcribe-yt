import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as api from '../api/client';
import type { CreateAnalysisOptions, CreateJobOptions, SavedAnalysis } from '../api/client';

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
    refetchInterval: refetchInterval ?? ((query) => query.state.data?.analyses.some((analysis) => analysis.status === 'pending' || analysis.status === 'processing') ? 2000 : false),
  });
}

export function useAnalyses(jobId: string, initialData?: SavedAnalysis[]) {
  return useQuery({
    queryKey: ['analyses', jobId],
    queryFn: () => api.listAnalyses(jobId),
    initialData,
    refetchInterval: (query) => query.state.data?.some((analysis) => analysis.status === 'pending' || analysis.status === 'processing') ? 2000 : false,
  });
}

export function useCreateAnalysis(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ options, sourceId }: { options: CreateAnalysisOptions; sourceId?: string }) => sourceId
      ? api.regenerateAnalysis(jobId, sourceId, options) : api.createAnalysis(jobId, options),
    onSuccess: async (analysis) => {
      await queryClient.cancelQueries({ queryKey: ['analyses', jobId], exact: true });
      queryClient.setQueryData<SavedAnalysis[]>(['analyses', jobId], (previous = []) => [analysis, ...previous.filter((item) => item.id !== analysis.id)]);
      queryClient.invalidateQueries({ queryKey: ['analyses', jobId] });
      queryClient.invalidateQueries({ queryKey: ['job', jobId] });
    },
  });
}

export function useDeleteAnalysis(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (analysisId: string) => api.deleteAnalysis(jobId, analysisId),
    onSuccess: async (_result, analysisId) => {
      await queryClient.cancelQueries({ queryKey: ['analyses', jobId], exact: true });
      queryClient.setQueryData<SavedAnalysis[]>(['analyses', jobId], (previous = []) => previous.filter((item) => item.id !== analysisId));
      queryClient.invalidateQueries({ queryKey: ['analyses', jobId] });
      queryClient.invalidateQueries({ queryKey: ['job', jobId] });
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
