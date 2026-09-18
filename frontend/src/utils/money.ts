/**
 * Reading the money the API sends.
 *
 * Amounts arrive as exact decimal strings (see `MoneyString`). These helpers
 * are the only place that turns one into a number, and they do it for display
 * only - the backend owns every total, and nothing in the interface should be
 * adding amounts together in the first place.
 *
 * `parseMoney` returns `null` rather than `NaN` for anything unreadable, so a
 * missing amount renders as an em dash instead of "NaN" on a budget page.
 */

import type { MoneyString } from '../types';
import { formatMoney } from './format';

export function parseMoney(value: MoneyString | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Format an API amount for display, in the active language. */
export function formatMoneyString(
  value: MoneyString | null | undefined,
  currency: string | null | undefined,
  language = 'en',
): string {
  return formatMoney(parseMoney(value), currency, language);
}

/**
 * Format with cents. Used where a cent actually matters - a ledger line, a
 * final total - while cards elsewhere round to whole units for scannability.
 */
export function formatMoneyExact(
  value: MoneyString | null | undefined,
  currency: string | null | undefined,
  language = 'en',
): string {
  const amount = parseMoney(value);
  if (amount === null) return '—';
  try {
    return new Intl.NumberFormat(language === 'en' ? 'en-GB' : language, {
      style: 'currency',
      currency: currency || 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${currency ?? ''} ${amount.toFixed(2)}`.trim();
  }
}

/** True when an amount is present and below zero - i.e. over budget. */
export function isNegative(value: MoneyString | null | undefined): boolean {
  const parsed = parseMoney(value);
  return parsed !== null && parsed < 0;
}

/**
 * A 0-100 percentage for a progress bar, clamped.
 *
 * Clamped because a budget can genuinely be 140% spent, and a bar that renders
 * wider than its track breaks the layout rather than communicating the
 * overspend. The number itself is still shown next to the bar.
 */
export function barPercent(value: number | null | undefined): number {
  if (value === null || value === undefined || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(100, value));
}
