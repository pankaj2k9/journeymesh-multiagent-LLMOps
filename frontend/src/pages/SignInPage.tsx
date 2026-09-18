import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { ApiError } from '../api/client';
import { useAuth } from '../auth/useAuth';
import { Button } from '../components/common/Button';
import { Callout } from '../components/common/Callout';
import { Card } from '../components/common/Card';
import { useLanguage } from '../hooks/useLanguage';

type Mode = 'signIn' | 'signUp';

const MIN_PASSWORD_LENGTH = 10;

export function SignInPage() {
  const { t } = useTranslation();
  const { language } = useLanguage();
  const navigate = useNavigate();
  const { signIn, signUp, signedIn, signOut, user } = useAuth();

  const [mode, setMode] = useState<Mode>('signIn');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [claimed, setClaimed] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const fieldClass =
    'w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink ' +
    'focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30';

  if (signedIn) {
    return (
      <Card className="mx-auto max-w-md space-y-4 p-6">
        <h1 className="text-lg font-semibold text-ink">{t('auth.alreadySignedIn')}</h1>
        <p className="text-sm text-muted">{user?.email}</p>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => navigate('/dashboard')}>{t('nav.dashboard')}</Button>
          <Button variant="secondary" onClick={signOut}>
            {t('auth.signOut')}
          </Button>
        </div>
      </Card>
    );
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);

    if (mode === 'signUp' && password.length < MIN_PASSWORD_LENGTH) {
      setError(t('auth.errors.passwordTooShort', { count: MIN_PASSWORD_LENGTH }));
      return;
    }

    setBusy(true);
    try {
      const response =
        mode === 'signIn'
          ? await signIn({ email, password })
          : await signUp({
              email,
              password,
              display_name: displayName || undefined,
              preferred_language: language,
            });

      // Signing up from an anonymous session adopts the journeys planned in
      // this browser, which is worth confirming rather than doing silently.
      if (response.claimed_trips > 0) {
        setClaimed(response.claimed_trips);
        window.setTimeout(() => navigate('/dashboard'), 1200);
      } else {
        navigate('/dashboard');
      }
    } catch (caught) {
      if (caught instanceof ApiError) {
        // The server answers identically for an unknown address and a wrong
        // password, and so does this message - repeating that distinction here
        // would undo the protection.
        setError(caught.message || t('auth.errors.generic'));
      } else {
        setError(t('auth.errors.generic'));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-md space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-ink sm:text-2xl">
          {mode === 'signIn' ? t('auth.signIn') : t('auth.createAccount')}
        </h1>
        <p className="mt-1 text-sm text-muted">{t('auth.subtitle')}</p>
      </header>

      {claimed !== null ? (
        <Callout tone="success" title={t('auth.claimedTitle')}>
          {t('auth.claimedBody', { count: claimed })}
        </Callout>
      ) : null}

      <Card className="p-5 sm:p-6">
        <form onSubmit={submit} className="space-y-3">
          {mode === 'signUp' ? (
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-muted">
                {t('auth.displayName')} ({t('common.optional')})
              </span>
              <input
                className={fieldClass}
                value={displayName}
                maxLength={120}
                autoComplete="name"
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </label>
          ) : null}

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">{t('auth.email')}</span>
            <input
              className={fieldClass}
              type="email"
              required
              value={email}
              autoComplete="email"
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">
              {t('auth.password')}
            </span>
            <input
              className={fieldClass}
              type="password"
              required
              value={password}
              autoComplete={mode === 'signIn' ? 'current-password' : 'new-password'}
              onChange={(event) => setPassword(event.target.value)}
            />
            {mode === 'signUp' ? (
              <span className="mt-1 block text-xs text-muted">
                {t('auth.passwordHint', { count: MIN_PASSWORD_LENGTH })}
              </span>
            ) : null}
          </label>

          {error ? (
            <Callout tone="danger" title={t('errors.title')}>
              {error}
            </Callout>
          ) : null}

          <Button type="submit" loading={busy} className="w-full">
            {mode === 'signIn' ? t('auth.signIn') : t('auth.createAccount')}
          </Button>
        </form>
      </Card>

      <p className="text-center text-sm text-muted">
        {mode === 'signIn' ? t('auth.noAccount') : t('auth.haveAccount')}{' '}
        <button
          type="button"
          className="font-medium text-accent underline-offset-2 hover:underline"
          onClick={() => {
            setMode(mode === 'signIn' ? 'signUp' : 'signIn');
            setError(null);
          }}
        >
          {mode === 'signIn' ? t('auth.createAccount') : t('auth.signIn')}
        </button>
      </p>

      <p className="text-center text-xs text-muted">{t('auth.anonymousNote')}</p>
    </div>
  );
}

export default SignInPage;
