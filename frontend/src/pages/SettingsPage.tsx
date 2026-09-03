import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { ThemeSelector } from '../components/common/ThemeSelector';
import { LanguageSelector } from '../components/language/LanguageSelector';
import { tripKeys } from '../hooks/useTrips';
import { resetSessionId } from '../utils/session';

export function SettingsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [cleared, setCleared] = useState(false);

  const handleReset = () => {
    resetSessionId();
    void queryClient.invalidateQueries({ queryKey: tripKeys.all });
    setCleared(true);
  };

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
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button variant="secondary" onClick={handleReset}>
            {t('settings.clearSession')}
          </Button>
          {cleared ? (
            <span role="status" className="text-sm text-muted">
              {t('settings.sessionCleared')}
            </span>
          ) : null}
        </div>
      </Card>
    </div>
  );
}

export default SettingsPage;
