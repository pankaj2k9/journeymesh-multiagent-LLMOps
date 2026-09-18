import { describe, expect, it } from 'vitest';

import { barPercent, formatMoneyExact, formatMoneyString, isNegative, parseMoney } from '../utils/money';

describe('reading the money the API sends', () => {
  it('parses an exact decimal string', () => {
    expect(parseMoney('1836.35')).toBe(1836.35);
    expect(parseMoney('0')).toBe(0);
    expect(parseMoney('-300.00')).toBe(-300);
  });

  it('returns null rather than NaN for anything unreadable', () => {
    // A budget page must render an em dash, never "NaN".
    for (const value of [null, undefined, '', 'not-money', 'Infinity']) {
      expect(parseMoney(value as string)).toBeNull();
    }
  });

  it('formats an amount in the active language', () => {
    expect(formatMoneyString('2125.00', 'USD', 'en')).toMatch(/2,125/);
    expect(formatMoneyString(null, 'USD', 'en')).toBe('—');
  });

  it('keeps cents where a cent matters', () => {
    expect(formatMoneyExact('64.50', 'USD', 'en')).toMatch(/64\.50/);
    expect(formatMoneyExact('-80.00', 'USD', 'en')).toMatch(/80\.00/);
    expect(formatMoneyExact(null, 'USD', 'en')).toBe('—');
  });

  it('knows when a remaining balance has gone negative', () => {
    expect(isNegative('-0.01')).toBe(true);
    expect(isNegative('0')).toBe(false);
    expect(isNegative(null)).toBe(false);
  });

  it('clamps a progress bar so an overspend cannot break the layout', () => {
    expect(barPercent(140)).toBe(100);
    expect(barPercent(-20)).toBe(0);
    expect(barPercent(46.9)).toBe(46.9);
    expect(barPercent(null)).toBe(0);
  });
});
