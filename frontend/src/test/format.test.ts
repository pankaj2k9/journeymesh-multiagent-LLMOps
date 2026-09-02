import { describe, expect, it } from 'vitest';

import { formatMoney, formatPercent, formatTemperature, scoreTone, sourceTone } from '../utils/format';

describe('formatting helpers', () => {
  it('formats money with the requested currency', () => {
    expect(formatMoney(1200, 'USD', 'en')).toContain('1,200');
    expect(formatMoney(null, 'USD', 'en')).toBe('—');
  });

  it('formats temperature and percentages', () => {
    expect(formatTemperature(31.4)).toBe('31°C');
    expect(formatPercent(62.6)).toBe('63%');
    expect(formatTemperature(undefined)).toBe('—');
  });

  it('maps a data source to a visual tone', () => {
    expect(sourceTone('LIVE')).toBe('positive');
    expect(sourceTone('ESTIMATE')).toBe('caution');
    expect(sourceTone('UNAVAILABLE')).toBe('muted');
  });

  it('maps an evaluation score to a tone', () => {
    expect(scoreTone(0.95)).toBe('positive');
    expect(scoreTone(0.65)).toBe('caution');
    expect(scoreTone(0.2)).toBe('negative');
  });
});
