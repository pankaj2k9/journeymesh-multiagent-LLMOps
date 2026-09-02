import type { DataSource, LanguageCode } from '../types';

const LOCALE_BY_LANGUAGE: Record<LanguageCode, string> = {
  en: 'en-GB',
  bn: 'bn-BD',
  hi: 'hi-IN',
};

export function localeFor(language: string): string {
  return LOCALE_BY_LANGUAGE[language as LanguageCode] ?? 'en-GB';
}

export function formatMoney(
  amount: number | null | undefined,
  currency: string | null | undefined,
  language = 'en',
): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return '—';
  try {
    return new Intl.NumberFormat(localeFor(language), {
      style: 'currency',
      currency: currency || 'USD',
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${currency ?? ''} ${Math.round(amount)}`.trim();
  }
}

export function formatNumber(value: number | null | undefined, language = 'en'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat(localeFor(language)).format(value);
}

export function formatDate(value: string | null | undefined, language = 'en'): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(localeFor(language), {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(date);
}

export function formatDateTime(value: string | null | undefined, language = 'en'): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(localeFor(language), {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function formatTemperature(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${Math.round(value)}°C`;
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${Math.round(value)}%`;
}

export function sourceTone(source: DataSource): 'positive' | 'neutral' | 'caution' | 'muted' {
  switch (source) {
    case 'LIVE':
      return 'positive';
    case 'SEARCH_DERIVED':
      return 'neutral';
    case 'ESTIMATE':
      return 'caution';
    default:
      return 'muted';
  }
}

export function scoreTone(score: number): 'positive' | 'caution' | 'negative' {
  if (score >= 0.8) return 'positive';
  if (score >= 0.6) return 'caution';
  return 'negative';
}

export function titleCase(value: string): string {
  return value
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(' ');
}

export function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}
