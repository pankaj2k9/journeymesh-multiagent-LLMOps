/**
 * JourneyMesh Tailwind configuration.
 *
 * Colours are semantic, not literal: components say `bg-surface` and
 * `text-muted`, never `bg-white dark:bg-slate-900`. Each token resolves to a
 * CSS custom property defined twice in `src/index.css` - once for light, once
 * under `.dark` - so a component is written once and themed centrally.
 *
 * `<alpha-value>` keeps Tailwind's opacity modifiers working (`bg-surface/60`).
 */

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // ---- Surfaces -------------------------------------------------------
        canvas: 'rgb(var(--jm-canvas) / <alpha-value>)',
        surface: 'rgb(var(--jm-surface) / <alpha-value>)',
        elevated: 'rgb(var(--jm-elevated) / <alpha-value>)',
        line: 'rgb(var(--jm-line) / <alpha-value>)',
        'line-strong': 'rgb(var(--jm-line-strong) / <alpha-value>)',

        // ---- Text -----------------------------------------------------------
        ink: 'rgb(var(--jm-ink) / <alpha-value>)',
        muted: 'rgb(var(--jm-muted) / <alpha-value>)',
        faint: 'rgb(var(--jm-faint) / <alpha-value>)',

        // ---- Brand ----------------------------------------------------------
        accent: {
          DEFAULT: 'rgb(var(--jm-accent) / <alpha-value>)',
          strong: 'rgb(var(--jm-accent-strong) / <alpha-value>)',
          soft: 'rgb(var(--jm-accent-soft) / <alpha-value>)',
          contrast: 'rgb(var(--jm-accent-contrast) / <alpha-value>)',
        },

        // ---- Status ---------------------------------------------------------
        positive: {
          fg: 'rgb(var(--jm-positive-fg) / <alpha-value>)',
          bg: 'rgb(var(--jm-positive-bg) / <alpha-value>)',
          line: 'rgb(var(--jm-positive-line) / <alpha-value>)',
        },
        caution: {
          fg: 'rgb(var(--jm-caution-fg) / <alpha-value>)',
          bg: 'rgb(var(--jm-caution-bg) / <alpha-value>)',
          line: 'rgb(var(--jm-caution-line) / <alpha-value>)',
        },
        negative: {
          fg: 'rgb(var(--jm-negative-fg) / <alpha-value>)',
          bg: 'rgb(var(--jm-negative-bg) / <alpha-value>)',
          line: 'rgb(var(--jm-negative-line) / <alpha-value>)',
        },
        info: {
          fg: 'rgb(var(--jm-info-fg) / <alpha-value>)',
          bg: 'rgb(var(--jm-info-bg) / <alpha-value>)',
          line: 'rgb(var(--jm-info-line) / <alpha-value>)',
        },
        neutral: {
          fg: 'rgb(var(--jm-neutral-fg) / <alpha-value>)',
          bg: 'rgb(var(--jm-neutral-bg) / <alpha-value>)',
          line: 'rgb(var(--jm-neutral-line) / <alpha-value>)',
        },
        brand: {
          fg: 'rgb(var(--jm-brand-fg) / <alpha-value>)',
          bg: 'rgb(var(--jm-brand-bg) / <alpha-value>)',
          line: 'rgb(var(--jm-brand-line) / <alpha-value>)',
        },

        // The fixed brand ramp, for the few places that need a literal shade
        // (the logo mark, the favicon colour) rather than a themed token.
        mesh: {
          50: '#eef6ff',
          100: '#d9ebff',
          200: '#bcdcff',
          300: '#8ec6ff',
          400: '#59a6ff',
          500: '#3182f6',
          600: '#1c63dc',
          700: '#184eb2',
          800: '#19438e',
          900: '#17365d',
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          'Noto Sans Bengali',
          'Noto Sans Devanagari',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'sans-serif',
        ],
      },
      boxShadow: {
        card: 'var(--jm-shadow-card)',
        raised: 'var(--jm-shadow-raised)',
      },
      keyframes: {
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.6s infinite',
      },
    },
  },
  plugins: [],
};
