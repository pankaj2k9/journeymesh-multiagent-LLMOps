import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  addExpense,
  getBudget,
  getLedger,
  getSelections,
  reverseExpense,
  setBudget,
} from '../api/budget';
import type { ExpenseBody } from '../types';
import { dashboardKeys } from './useDashboard';

export const budgetKeys = {
  budget: (tripId: string) => ['budget', tripId] as const,
  ledger: (tripId: string) => ['budget', tripId, 'ledger'] as const,
  selections: (tripId: string) => ['selections', tripId] as const,
};

export function useBudget(tripId: string | undefined) {
  return useQuery({
    queryKey: budgetKeys.budget(tripId ?? 'unknown'),
    queryFn: () => getBudget(tripId as string),
    enabled: Boolean(tripId),
    staleTime: 5_000,
  });
}

export function useLedger(tripId: string | undefined) {
  return useQuery({
    queryKey: budgetKeys.ledger(tripId ?? 'unknown'),
    queryFn: () => getLedger(tripId as string),
    enabled: Boolean(tripId),
    staleTime: 5_000,
  });
}

export function useSelections(tripId: string | undefined) {
  return useQuery({
    queryKey: budgetKeys.selections(tripId ?? 'unknown'),
    queryFn: () => getSelections(tripId as string),
    enabled: Boolean(tripId),
    staleTime: 5_000,
  });
}

/**
 * Anything that moves money invalidates the budget, the ledger and the
 * dashboard together - the dashboard card shows the same remaining balance, and
 * leaving it stale is how two screens start disagreeing about one number.
 */
function useMoneyMutation<TVars, TData>(
  tripId: string,
  mutationFn: (vars: TVars) => Promise<TData>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: budgetKeys.budget(tripId) });
      void queryClient.invalidateQueries({ queryKey: budgetKeys.ledger(tripId) });
      void queryClient.invalidateQueries({ queryKey: budgetKeys.selections(tripId) });
      void queryClient.invalidateQueries({ queryKey: dashboardKeys.root });
    },
  });
}

export function useAddExpense(tripId: string) {
  return useMoneyMutation(tripId, (body: ExpenseBody) => addExpense(tripId, body));
}

export function useReverseExpense(tripId: string) {
  return useMoneyMutation(tripId, (itemId: string) => reverseExpense(tripId, itemId));
}

export function useSetBudget(tripId: string) {
  return useMoneyMutation(
    tripId,
    (body: { total_budget?: string | null; emergency_reserve?: string | null }) =>
      setBudget(tripId, body),
  );
}
