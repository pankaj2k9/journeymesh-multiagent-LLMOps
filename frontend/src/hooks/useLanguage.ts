import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { applyDocumentLanguage, persistLanguage } from '../i18n/config';
import type { LanguageCode } from '../types';
import { DEFAULT_LANGUAGE, LANGUAGES } from '../utils/constants';

export interface UseLanguage {
  language: LanguageCode;
  languages: LanguageCode[];
  setLanguage: (language: LanguageCode) => void;
}

/**
 * Reads and writes the active language, keeping localStorage and the
 * document's `lang` attribute in step with i18next.
 */
export function useLanguage(): UseLanguage {
  const { i18n } = useTranslation();
  const current = (LANGUAGES as string[]).includes(i18n.language)
    ? (i18n.language as LanguageCode)
    : DEFAULT_LANGUAGE;

  const setLanguage = useCallback(
    (language: LanguageCode) => {
      void i18n.changeLanguage(language);
      persistLanguage(language);
      applyDocumentLanguage(language);
    },
    [i18n],
  );

  return { language: current, languages: LANGUAGES, setLanguage };
}
