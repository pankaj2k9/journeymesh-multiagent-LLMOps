import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { API_BASE_URL, API_PREFIX } from '../api/client';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { ThemeSelector } from '../components/common/ThemeSelector';
import { LanguageSelector } from '../components/language/LanguageSelector';
import { useHealth } from '../hooks/useTrips';
import { getSessionId, resetSessionId } from '../utils/session';

export function SettingsPage() {
  const { t } = useTranslation();
  const [sessionId, setSessionId] = useState(getSessionId());
  const { data: health } = useHealth();

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold text-ink sm:text-2xl">{t('settings.title')}</h1>

      <Card className="p-5">
        <h2 className="text-base font-semibold text-ink">{t('settings.languageTitle')}</h2>
        <p className="mt-1 text-sm text-muted">{t('settings.languageBody')}</p>
        <div className="mt-3">
          <LanguageSelector variant="buttons" />
        </div>
      </Card>

      <Card className="p-5">
        <h2 className="text-base font-semibold text-ink">{t('theme.label')}</h2>
        <p className="mt-1 text-sm text-muted">{t('theme.description')}</p>
        <div className="mt-3">
          <ThemeSelector />
        </div>
      </Card>

      <Card className="p-5">
        <h2 className="text-base font-semibold text-ink">{t('settings.sessionTitle')}</h2>
        <p className="mt-1 text-sm text-muted">{t('settings.sessionBody')}</p>
        <p className="mt-3 break-all rounded-xl bg-elevated px-3 py-2 font-mono text-xs text-muted">
          {t('settings.sessionId')}: {sessionId}
        </p>
        <div className="mt-3">
          <Button variant="secondary" onClick={() => setSessionId(resetSessionId())}>
            {t('settings.clearSession')}
          </Button>
        </div>
      </Card>

      <Card className="p-5">
        <h2 className="text-base font-semibold text-ink">{t('settings.apiTitle')}</h2>
        <p className="mt-1 text-sm text-muted">{t('settings.apiBody')}</p>
        <p className="mt-2 break-all rounded-xl bg-elevated px-3 py-2 font-mono text-xs text-muted">
          {(API_BASE_URL || window.location.origin) + API_PREFIX}
        </p>
        {health ? (
          <p className="mt-2 text-xs text-muted">
            {health.app} {health.version} · {health.environment} · {health.database} · {health.llm}
          </p>
        ) : null}
      </Card>
    </div>
  );
}

export default SettingsPage;
