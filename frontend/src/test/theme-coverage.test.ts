import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * The stylesheet is read from disk rather than imported: Vitest runs with CSS
 * processing disabled, so a `?raw` import of a stylesheet comes back empty.
 */
function readStylesheet(): string {
  const candidates = [
    resolve(process.cwd(), 'src/index.css'),
    resolve(process.cwd(), 'index.css'),
    resolve(process.cwd(), '../src/index.css'),
  ];
  const found = candidates.find((candidate) => existsSync(candidate));
  if (!found) throw new Error(`index.css not found in: ${candidates.join(', ')}`);
  return readFileSync(found, 'utf-8');
}

const css = readStylesheet();

/**
 * Dark mode is enforced structurally rather than checked by eye.
 *
 * Every colour in JourneyMesh must come from a semantic token that is defined
 * twice in index.css - once for light, once under `.dark`. A component that
 * reaches for a raw Tailwind palette colour would look correct in one theme
 * and wrong in the other, so this test fails the build if one appears.
 */
const sources = import.meta.glob('../{components,pages}/**/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;



// Raw palette families that would only be right in one theme. JourneyMesh's
// own semantic tokens (`neutral-fg`, `positive-bg`, ...) are excluded by the
// lookahead, since only the numeric Tailwind ramps are the problem.
const UTILITY = '(?:bg|text|border|ring|divide|from|via|to|outline|placeholder|shadow)';
const RAW_COLOUR = new RegExp(
  `${UTILITY}-(?:slate|gray|zinc|stone|emerald|green|amber|yellow|rose|red|sky|blue|indigo|neutral)` +
    '(?:-\\d{2,3})?\\b(?!-(?:fg|bg|line))|' +
    `${UTILITY}-(?:white|black)\\b`,
  'g',
);

describe('theme coverage', () => {
  it('finds the component sources', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(20);
  });

  it('no component hard-codes a light-only colour', () => {
    const offenders: string[] = [];

    for (const [path, source] of Object.entries(sources)) {
      const matches = source.match(RAW_COLOUR) ?? [];
      if (matches.length > 0) {
        offenders.push(`${path}: ${[...new Set(matches)].join(', ')}`);
      }
    }

    expect(offenders, `use semantic tokens instead:\n${offenders.join('\n')}`).toEqual([]);
  });

  it('defines every semantic token in both themes', () => {
    const light = css.slice(css.indexOf(':root'), css.indexOf('.dark {'));
    const dark = css.slice(css.indexOf('.dark {'));

    const tokens = [...light.matchAll(/--(jm-[\w-]+):/g)].map((match) => match[1]);
    expect(tokens.length).toBeGreaterThan(20);

    const missing = tokens.filter((token) => !dark.includes(`--${token}:`));
    expect(missing, `tokens with no dark value: ${missing.join(', ')}`).toEqual([]);
  });

  it('sets color-scheme in both themes so native controls follow', () => {
    expect(css).toMatch(/:root[\s\S]*?color-scheme:\s*light/);
    expect(css).toMatch(/\.dark\s*\{[\s\S]*?color-scheme:\s*dark/);
  });

  it('does not paint dark mode as inverted light mode', () => {
    // The dark ground must be a deep slate, not pure black.
    const dark = css.slice(css.indexOf('.dark {'));
    const canvas = dark.match(/--jm-canvas:\s*([\d\s]+);/)?.[1]?.trim();
    expect(canvas).toBeDefined();

    const [r, g, b] = (canvas as string).split(/\s+/).map(Number);
    expect(r + g + b).toBeGreaterThan(0); // not #000000
    expect(Math.max(r, g, b)).toBeLessThan(60); // still genuinely dark
    expect(b).toBeGreaterThan(r); // blue-slate, carrying the brand temperature
  });
});
