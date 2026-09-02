import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { approveTrip, regenerateTrip, requestChanges } from '../api/reviews';
import { deleteTrip, getHealth, getTrip, listTrips, planTrip } from '../api/trips';
import type { LanguageCode, PlanRequestBody } from '../types';

export const tripKeys = {
  all: ['trips'] as const,
  list: (params: Record<string, unknown>) => ['trips', 'list', params] as const,
  detail: (tripId: string) => ['trips', 'detail', tripId] as const,
  health: ['health'] as const,
};

export function useTripList(params: { limit?: number; offset?: number } = {}) {
  return useQuery({
    queryKey: tripKeys.list(params),
    queryFn: () => listTrips(params),
    staleTime: 15_000,
  });
}

export function useTrip(tripId: string | undefined) {
  return useQuery({
    queryKey: tripKeys.detail(tripId ?? 'unknown'),
    queryFn: () => getTrip(tripId as string),
    enabled: Boolean(tripId),
    staleTime: 5_000,
  });
}

export function useHealth() {
  return useQuery({ queryKey: tripKeys.health, queryFn: getHealth, staleTime: 60_000 });
}

export function usePlanTrip() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PlanRequestBody) => planTrip(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: tripKeys.all });
    },
  });
}

export function useApproveTrip(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { language: LanguageCode; note?: string }) =>
      approveTrip(tripId, vars.language, vars.note),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: tripKeys.detail(tripId) });
      void queryClient.invalidateQueries({ queryKey: tripKeys.all });
    },
  });
}

export function useRequestChanges(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { changes: string; language: LanguageCode }) =>
      requestChanges(tripId, vars.changes, vars.language),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: tripKeys.detail(tripId) });
      void queryClient.invalidateQueries({ queryKey: tripKeys.all });
    },
  });
}

export function useRegenerateTrip(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => regenerateTrip(tripId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: tripKeys.detail(tripId) });
    },
  });
}

export function useDeleteTrip() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tripId: string) => deleteTrip(tripId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: tripKeys.all });
    },
  });
}
