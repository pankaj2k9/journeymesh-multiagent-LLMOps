import type { ApproveResponse, ChangeResponse, LanguageCode } from '../types';
import { request } from './client';

export function approveTrip(
  tripId: string,
  responseLanguage: LanguageCode,
  reviewerNote?: string,
): Promise<ApproveResponse> {
  return request<ApproveResponse>(`/trips/${encodeURIComponent(tripId)}/approve`, {
    method: 'POST',
    body: { response_language: responseLanguage, reviewer_note: reviewerNote },
  });
}

export function requestChanges(
  tripId: string,
  requestedChanges: string,
  responseLanguage: LanguageCode,
): Promise<ChangeResponse> {
  return request<ChangeResponse>(`/trips/${encodeURIComponent(tripId)}/request-changes`, {
    method: 'POST',
    body: { requested_changes: requestedChanges, response_language: responseLanguage },
  });
}

export function regenerateTrip(tripId: string): Promise<ChangeResponse> {
  return request<ChangeResponse>(`/trips/${encodeURIComponent(tripId)}/regenerate`, {
    method: 'POST',
  });
}
