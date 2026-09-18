import type { AuthResponse, LoginBody, RegisterBody, User } from '../types';
import { getSessionId } from '../utils/session';
import { request } from './client';

/**
 * Registration and sign-in both carry the browser session id, so the journeys
 * planned anonymously before signing up are adopted by the new account rather
 * than stranded. The server only ever moves trips that belong to nobody.
 */
export function register(body: RegisterBody): Promise<AuthResponse> {
  return request<AuthResponse>('/auth/register', {
    method: 'POST',
    body: { session_id: getSessionId(), ...body },
    anonymous: true,
  });
}

export function login(body: LoginBody): Promise<AuthResponse> {
  return request<AuthResponse>('/auth/login', {
    method: 'POST',
    body: { session_id: getSessionId(), ...body },
    anonymous: true,
  });
}

export function refresh(token: string): Promise<AuthResponse> {
  return request<AuthResponse>('/auth/refresh', {
    method: 'POST',
    body: { refresh_token: token },
    anonymous: true,
  });
}

export function me(): Promise<User> {
  return request<User>('/auth/me');
}

export function signOutEverywhere(): Promise<void> {
  return request<void>('/auth/sign-out-everywhere', { method: 'POST' });
}
