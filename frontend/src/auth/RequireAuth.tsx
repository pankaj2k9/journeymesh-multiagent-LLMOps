import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useLocation } from 'react-router-dom';

import { Spinner } from '../components/common/Spinner';
import type { Role } from '../types';
import { useAuth } from './useAuth';

export const USER_LOGIN_PATH = '/user/login';
export const ADMIN_LOGIN_PATH = '/admin/login';

const ROLE_RANK: Record<Role, number> = { USER: 0, SUPPORT: 1, ADMIN: 2 };

interface RequireAuthProps {
  children: ReactNode;
  /** Minimum role, ranked the way the backend ranks it. */
  role?: Role;
  loginPath?: string;
}

/**
 * Keeps a signed-out visitor off an account page and sends them to sign in,
 * remembering where they were going.
 *
 * This is navigation, not security: every endpoint behind these pages checks
 * the token and the role on the server.
 */
export function RequireAuth({ children, role, loginPath = USER_LOGIN_PATH }: RequireAuthProps) {
  const { t } = useTranslation();
  const { signedIn, restoring, user } = useAuth();
  const location = useLocation();

  if (restoring) {
    return <Spinner label={t('common.loading')} className="py-16" />;
  }

  const next = `${location.pathname}${location.search}`;
  if (!signedIn || !user) {
    return <Navigate to={`${loginPath}?next=${encodeURIComponent(next)}`} replace />;
  }

  if (role && (ROLE_RANK[user.role] ?? -1) < ROLE_RANK[role]) {
    return <Navigate to={`${loginPath}?next=${encodeURIComponent(next)}&denied=1`} replace />;
  }

  return <>{children}</>;
}

/** A `next` value is only followed when it is a path on this site. */
export function safeNext(value: string | null, fallback: string): string {
  if (!value || !value.startsWith('/') || value.startsWith('//')) return fallback;
  return value;
}
