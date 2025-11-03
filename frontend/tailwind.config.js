/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        arc: {
          primary: '#d42e12',
          bg: '#141414',
          surface: '#1c1c1c',
          'surface-alt': '#232323',
          panel: '#2e2e2e',
          accent: '#bfc4ca',
          teal: '#00c2a8',
          text: '#f4f5f6',
          muted: '#9ca2a6',
          subtle: '#5c6166',
          success: '#2bc48a',
          warning: '#f0b429',
          danger: '#ff5a4f',
          border: '#2c2c2c',
          'border-strong': '#3a3a3a',
          outline: 'rgba(0, 194, 168, 0.45)',
        },
      },
      lineHeight: {
        'arc': '1.6',
      },
      letterSpacing: {
        'arc-tight': '0.01em',
        'arc': '0.08em',
        'arc-wide': '0.12em',
        'arc-wider': '0.14em',
      },
      fontSize: {
        'heading-1': 'clamp(2rem, 2.8vw, 2.6rem)',
        'heading-2': 'clamp(1.5rem, 2.2vw, 2rem)',
        'heading-3': 'clamp(1.25rem, 1.8vw, 1.6rem)',
      },
      fontFamily: {
        sans: ['"Inter"', '"Segoe UI"', '"Helvetica Neue"', 'Arial', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', '"SFMono-Regular"', 'Menlo', 'monospace'],
      },
      borderRadius: {
        'arc-sm': '6px',
        'arc-md': '10px',
        'arc-lg': '16px',
      },
      boxShadow: {
        'arc-soft': '0 12px 30px rgba(0, 0, 0, 0.28)',
        'arc-sharp': '0 0 0 1px rgba(0, 194, 168, 0.2), 0 14px 42px rgba(0, 0, 0, 0.56)',
      },
      transitionDuration: {
        'arc-fast': '120ms',
        arc: '180ms',
        'arc-slow': '280ms',
      },
      transitionTimingFunction: {
        'arc-out': 'cubic-bezier(0.2, 0.8, 0.3, 1)',
        'arc-in': 'cubic-bezier(0.6, 0.04, 0.98, 0.335)',
      },
      spacing: {
        '3xs': '2px',
        '2xs': '4px',
        xs: '8px',
        sm: '12px',
        md: '16px',
        lg: '24px',
        xl: '32px',
        '2xl': '48px',
        '3xl': '64px',
        'sidebar': '280px',
        'sidebar-mobile': 'min(82vw, 320px)',
        'topbar': '64px',
      },
      maxWidth: {
        'arc': '1440px',
      },
      screens: {
        'handheld': {'max': '1080px'},
      },
    },
  },
  plugins: [],
}
