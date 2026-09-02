import { describe, expect, it } from 'vitest';

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

const css = Object.values(
  import.meta.glob('../index.css', { query: '?raw', import: 'default', eager: true }) as Record<
    string,
    string
  >,
)[0];

// Raw palette families that would only be right in one theme.
const RAW_COLOUR = new RegExp(
  '(?:bg|text|border|ring|divide|from|via|to|outline|placeholder|shadow)-' +
    '(?:slate|gray|zinc|neutral|stone|white|black|emerald|green|amber|yellow|rose|red|sky|blue|indigo)' +
    '(?:-\\d{2,3})?\\b',
  'g',
);

// `neutral-fg|bg|line` are JourneyMesh status tokens, not the Tailwind ramp.
const TOKEN_EXCEPTIONS = /-(?:neutral)-(?:fg|bg|line)\b/;

describe('theme coverage', () => {
  it('finds the component sources', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(20);
  });

  it('no component hard-codes a light-only colour', () => {
    const offenders: string[] = [];

    for (const [path, source] of Object.entries(sources)) {
      const matches = source.match(RAW_COLOUR) ?? [];
      const real = matches.filter((match) => !TOKEN_EXCEPTIONS.test(match));
      if (real.length > 0) {
        offenders.push(`${path}: ${[...new Set(real)].join(', ')}`);
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
