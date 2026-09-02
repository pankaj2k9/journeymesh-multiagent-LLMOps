import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import bn from '../locales/bn/common.json';
import en from '../locales/en/common.json';
import hi from '../locales/hi/common.json';
import {
  DEFAULT_LANGUAGE,
  LANGUAGES,
  LANGUAGE_STORAGE_KEY,
  LEGACY_LANGUAGE_STORAGE_KEY,
} from '../utils/constants';
import type { LanguageCode } from '../types';

export const resources = {
  en: { common: en },
  bn: { common: bn },
  hi: { common: hi },
} as const;

export function storedLanguage(): LanguageCode {
  if (typeof window === 'undefined') return DEFAULT_LANGUAGE;
  try {
    const saved = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (saved && (LANGUAGES as string[]).includes(saved)) {
      return saved as LanguageCode;
    }

    // Migrate the pre-standardisation key once, so a returning visitor keeps
    // the language they chose.
    const legacy = window.localStorage.getItem(LEGACY_LANGUAGE_STORAGE_KEY);
    if (legacy && (LANGUAGES as string[]).includes(legacy)) {
      window.localStorage.setItem(LANGUAGE_STORAGE_KEY, legacy);
      window.localStorage.removeItem(LEGACY_LANGUAGE_STORAGE_KEY);
      return legacy as LanguageCode;
    }
  } catch {
    /* storage unavailable - fall through to the default */
  }
  return DEFAULT_LANGUAGE;
}

export function persistLanguage(language: LanguageCode): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    /* storage unavailable - the choice simply is not remembered */
  }
}

export function applyDocumentLanguage(language: LanguageCode): void {
  if (typeof document === 'undefined') return;
  document.documentElement.lang = language;
  document.documentElement.dir = 'ltr';
}

const initial = storedLanguage();

void i18n.use(initReactI18next).init({
  resources,
  lng: initial,
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: LANGUAGES,
  defaultNS: 'common',
  ns: ['common'],
  interpolation: { escapeValue: false },
  returnNull: false,
});

applyDocumentLanguage(initial);

export default i18n;
