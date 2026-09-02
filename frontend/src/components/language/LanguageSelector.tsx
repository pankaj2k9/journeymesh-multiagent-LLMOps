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
        className={`inline-flex rounded-xl bg-slate-100 p-1 ${className}`.trim()}
      >
        {languages.map((code) => (
          <button
            key={code}
            type="button"
            onClick={() => setLanguage(code)}
            aria-pressed={language === code}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              language === code
                ? 'bg-white text-mesh-700 shadow-sm'
                : 'text-journey-slate hover:text-journey-ink'
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
        className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-journey-ink focus:border-mesh-500 focus:outline-none focus:ring-2 focus:ring-mesh-200"
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
