import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RequireAuth, safeNext } from '../auth/RequireAuth';
import type { AuthState } from '../auth/AuthProvider';

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('../auth/useAuth', () => ({ useAuth }));

function auth(overrides: Partial<AuthState> = {}): AuthState {
  return {
    user: null,
    signedIn: false,
    restoring: false,
    claimedTrips: 0,
    signIn: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn(),
    ...overrides,
  };
}

function user(role: 'USER' | 'ADMIN') {
  return {
    id: 'u1',
    email: 'someone@example.com',
    display_name: null,
    role,
    status: 'active' as const,
    preferred_language: 'en' as const,
    preferred_currency: 'INR',
    last_login_at: null,
    created_at: null,
  };
}

function Where() {
  const location = useLocation();
  return <p>at {`${location.pathname}${location.search}`}</p>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <p>dashboard content</p>
            </RequireAuth>
          }
        />
        <Route
          path="/admin"
          element={
            <RequireAuth role="ADMIN" loginPath="/admin/login">
              <p>admin content</p>
            </RequireAuth>
          }
        />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('RequireAuth', () => {
  beforeEach(() => useAuth.mockReset());

  it('sends a signed-out visitor to the traveller sign in, remembering the page', () => {
    useAuth.mockReturnValue(auth());
    renderAt('/dashboard');
    expect(screen.getByText('at /user/login?next=%2Fdashboard')).toBeInTheDocument();
  });

  it('lets a signed-in traveller through', () => {
    useAuth.mockReturnValue(auth({ signedIn: true, user: user('USER') }));
    renderAt('/dashboard');
    expect(screen.getByText('dashboard content')).toBeInTheDocument();
  });

  it('turns a traveller away from the admin panel', () => {
    useAuth.mockReturnValue(auth({ signedIn: true, user: user('USER') }));
    renderAt('/admin');
    expect(screen.getByText('at /admin/login?next=%2Fadmin&denied=1')).toBeInTheDocument();
  });

  it('lets an administrator into the admin panel', () => {
    useAuth.mockReturnValue(auth({ signedIn: true, user: user('ADMIN') }));
    renderAt('/admin');
    expect(screen.getByText('admin content')).toBeInTheDocument();
  });
});

describe('safeNext', () => {
  it('follows only same-site paths', () => {
    expect(safeNext('/trip/abc', '/dashboard')).toBe('/trip/abc');
    expect(safeNext('//evil.example', '/dashboard')).toBe('/dashboard');
    expect(safeNext('https://evil.example', '/dashboard')).toBe('/dashboard');
    expect(safeNext(null, '/dashboard')).toBe('/dashboard');
  });
});
