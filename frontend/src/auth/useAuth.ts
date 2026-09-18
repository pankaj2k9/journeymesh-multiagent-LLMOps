import { useContext } from 'react';

import { AuthContext, type AuthState } from './AuthProvider';

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error('useAuth must be used inside an AuthProvider');
  }
  return value;
}
