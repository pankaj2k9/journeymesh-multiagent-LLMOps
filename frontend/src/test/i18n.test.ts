import { describe, expect, it } from 'vitest';

import i18n, { persistLanguage, storedLanguage } from '../i18n/config';
import bn from '../locales/bn/common.json';
import en from '../locales/en/common.json';
import hi from '../locales/hi/common.json';

function flatten(value: unknown, prefix = ''): string[] {
  if (typeof value !== 'object' || value === null) return [prefix];
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    flatten(child, prefix ? `${prefix}.${key}` : key),
  );
}

describe('internationalisation', () => {
  it('ships the same keys in every language', () => {
    const english = flatten(en).sort();
    expect(flatten(bn).sort()).toEqual(english);
    expect(flatten(hi).sort()).toEqual(english);
  });

  it('defaults to English', () => {
    expect(storedLanguage()).toBe('en');
  });

  it('remembers the chosen language in localStorage', () => {
    persistLanguage('bn');
    expect(storedLanguage()).toBe('bn');
    persistLanguage('en');
  });

  it('translates the tagline in each supported language', async () => {
    await i18n.changeLanguage('en');
    expect(i18n.t('app.tagline')).toBe('Every journey, intelligently connected.');

    await i18n.changeLanguage('bn');
    expect(i18n.t('app.tagline')).toMatch(/[ঀ-৿]/);

    await i18n.changeLanguage('hi');
    expect(i18n.t('app.tagline')).toMatch(/[ऀ-ॿ]/);

    await i18n.changeLanguage('en');
  });

  it('never leaves a user-facing string untranslated', async () => {
    await i18n.changeLanguage('hi');
    expect(i18n.t('review.approve')).not.toBe('Approve');
    await i18n.changeLanguage('en');
  });
});
