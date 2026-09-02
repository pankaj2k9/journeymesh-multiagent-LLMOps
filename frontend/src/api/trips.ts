import type {
  HealthResponse,
  PlanRequestBody,
  PlanResult,
  TripDetailResponse,
  TripListResponse,
} from '../types';
import { request } from './client';

export function planTrip(body: PlanRequestBody, signal?: AbortSignal): Promise<PlanResult> {
  return request<PlanResult>('/trips/plan', { method: 'POST', body, signal });
}

export function listTrips(
  params: { limit?: number; offset?: number; status?: string } = {},
): Promise<TripListResponse> {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set('limit', String(params.limit));
  if (params.offset !== undefined) search.set('offset', String(params.offset));
  if (params.status) search.set('status', params.status);
  const query = search.toString();
  return request<TripListResponse>(`/trips${query ? `?${query}` : ''}`);
}

export function getTrip(tripId: string): Promise<TripDetailResponse> {
  return request<TripDetailResponse>(`/trips/${encodeURIComponent(tripId)}`);
}

export function deleteTrip(tripId: string): Promise<{ trip_id: string; deleted: boolean }> {
  return request(`/trips/${encodeURIComponent(tripId)}`, { method: 'DELETE' });
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}
