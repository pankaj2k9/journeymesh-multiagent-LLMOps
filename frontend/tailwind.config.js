/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
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
          900: '#1a3b73',
        },
        journey: {
          sand: '#f7f5f0',
          ink: '#12212f',
          slate: '#5b6b7c',
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
        card: '0 1px 2px rgba(18, 33, 47, 0.06), 0 8px 24px -12px rgba(18, 33, 47, 0.25)',
      },
    },
  },
  plugins: [],
};
