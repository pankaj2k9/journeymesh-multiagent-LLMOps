import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { login as loginRequest, me, register as registerRequest } from '../api/auth';
import { ApiError } from '../api/client';
import type { AuthResponse, LoginBody, RegisterBody, User } from '../types';
import { accessToken, clearTokens, storeTokens, subscribe } from './tokens';

export interface AuthState {
  user: User | null;
  signedIn: boolean;
  /** True only while the stored token is being checked on first load. */
  restoring: boolean;
  claimedTrips: number;
  signIn: (body: LoginBody) => Promise<AuthResponse>;
  signUp: (body: RegisterBody) => Promise<AuthResponse>;
  signOut: () => void;
}

export const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [restoring, setRestoring] = useState<boolean>(() => accessToken() !== null);
  const [claimedTrips, setClaimedTrips] = useState(0);

  // Signing in or out changes what almost every query returns, so the cache is
  // dropped rather than left to go stale behind a new identity.
  const resetCache = useCallback(() => {
    void queryClient.invalidateQueries();
  }, [queryClient]);

  const applySession = useCallback(
    (response: AuthResponse) => {
      storeTokens(response.access_token, response.refresh_token);
      setUser(response.user);
      setClaimedTrips(response.claimed_trips);
      resetCache();
      return response;
    },
    [resetCache],
  );

  const signOut = useCallback(() => {
    clearTokens();
    setUser(null);
    setClaimedTrips(0);
    resetCache();
  }, [resetCache]);

  // On first load, a stored token is only worth trusting if the server still
  // accepts it: it may have expired, or `token_version` may have moved on.
  useEffect(() => {
    let cancelled = false;
    if (accessToken() === null) {
      setRestoring(false);
      return () => {
        cancelled = true;
      };
    }

    me()
      .then((value) => {
        if (!cancelled) setUser(value);
      })
      .catch((error: unknown) => {
        // A rejected token is cleared rather than retried; anything else is a
        // network problem and the token stays for the next attempt.
        if (error instanceof ApiError && (error.isUnauthorised || error.isForbidden)) {
          clearTokens();
          if (!cancelled) setUser(null);
        }
      })
      .finally(() => {
        if (!cancelled) setRestoring(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Another tab signing out signs this one out too.
  useEffect(
    () =>
      subscribe(() => {
        if (accessToken() === null) {
          setUser(null);
          resetCache();
        }
      }),
    [resetCache],
  );

  const value = useMemo<AuthState>(
    () => ({
      user,
      signedIn: user !== null,
      restoring,
      claimedTrips,
      signIn: (body) => loginRequest(body).then(applySession),
      signUp: (body) => registerRequest(body).then(applySession),
      signOut,
    }),
    [user, restoring, claimedTrips, applySession, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
