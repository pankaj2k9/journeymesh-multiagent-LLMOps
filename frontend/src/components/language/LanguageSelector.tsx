import { useTranslation } from 'react-i18next';

import { useLanguage } from '../../hooks/useLanguage';
import type { LanguageCode } from '../../types';

interface LanguageSelectorProps {
  variant?: 'inline' | 'buttons';
  className?: string;
}

/**
 * Language choice for both the interface and the generated journey. The
 * selection is stored in localStorage and applied to the document's lang
 * attribute by `useLanguage`.
 */
export function LanguageSelector({ variant = 'inline', className = '' }: LanguageSelectorProps) {
  const { t } = useTranslation();
  const { language, languages, setLanguage } = useLanguage();

  if (variant === 'buttons') {
    return (
      <div
        role="group"
        aria-label={t('language.label')}
        className={`inline-flex rounded-xl bg-elevated p-1 ${className}`.trim()}
      >
        {languages.map((code) => (
          <button
            key={code}
            type="button"
            onClick={() => setLanguage(code)}
            aria-pressed={language === code}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              language === code
                ? 'bg-surface text-accent shadow-sm'
                : 'text-muted hover:text-ink'
            }`}
          >
            {t(`language.${code}`)}
          </button>
        ))}
      </div>
    );
  }

  return (
    <label className={`inline-flex items-center gap-2 text-sm ${className}`.trim()}>
      <span className="sr-only">{t('language.label')}</span>
      <select
        value={language}
        onChange={(event) => setLanguage(event.target.value as LanguageCode)}
        className="rounded-lg border border-line-strong bg-surface px-2.5 py-1.5 text-sm text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40"
        aria-label={t('language.label')}
      >
        {languages.map((code) => (
          <option key={code} value={code}>
            {t(`language.${code}`)}
          </option>
        ))}
      </select>
    </label>
  );
}
