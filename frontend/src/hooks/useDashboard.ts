import { useQuery } from '@tanstack/react-query';

import { getDashboard } from '../api/dashboard';
import { useAuth } from '../auth/useAuth';

export const dashboardKeys = {
  root: ['dashboard'] as const,
  // Keyed by identity: signing in must not show the previous visitor's cached
  // dashboard for a frame before the new one arrives.
  forUser: (userId: string | null) => ['dashboard', userId ?? 'anonymous'] as const,
};

export function useDashboard() {
  const { user, restoring } = useAuth();
  return useQuery({
    queryKey: dashboardKeys.forUser(user?.id ?? null),
    queryFn: getDashboard,
    enabled: !restoring,
    staleTime: 15_000,
  });
}
