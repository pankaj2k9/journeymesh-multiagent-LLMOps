import type {
  ExpenseBody,
  LedgerResponse,
  SelectionListResponse,
  TripBudget,
} from '../types';
import { request } from './client';

export function getBudget(tripId: string): Promise<TripBudget> {
  return request<TripBudget>(`/trips/${encodeURIComponent(tripId)}/budget`);
}

export function getLedger(tripId: string): Promise<LedgerResponse> {
  return request<LedgerResponse>(`/trips/${encodeURIComponent(tripId)}/budget/ledger`);
}

export function setBudget(
  tripId: string,
  body: { total_budget?: string | null; emergency_reserve?: string | null },
): Promise<TripBudget> {
  return request<TripBudget>(`/trips/${encodeURIComponent(tripId)}/budget`, {
    method: 'PUT',
    body,
  });
}

export function addExpense(tripId: string, body: ExpenseBody): Promise<LedgerResponse> {
  return request<LedgerResponse>(`/trips/${encodeURIComponent(tripId)}/budget/expenses`, {
    method: 'POST',
    body,
  });
}

/**
 * Removing an expense appends a reversal rather than deleting a row, so the
 * history keeps showing what was removed and when.
 */
export function reverseExpense(tripId: string, itemId: string): Promise<LedgerResponse> {
  return request<LedgerResponse>(
    `/trips/${encodeURIComponent(tripId)}/budget/expenses/${encodeURIComponent(itemId)}`,
    { method: 'DELETE' },
  );
}

export function getSelections(tripId: string): Promise<SelectionListResponse> {
  return request<SelectionListResponse>(`/trips/${encodeURIComponent(tripId)}/selections`);
}
