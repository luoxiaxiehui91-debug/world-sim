/** @type {import('tailwindcss').Config} */
// 视觉基线：玻璃拟态 + 青绿(accent)主色 + 扫描线点缀。
// 颜色令牌与 src/config/theme.ts 对齐（theme.ts 为 JS 侧单一事实来源）。
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        accent: {
          DEFAULT: '#5eead4',
          soft: '#22d3ee',
          deep: '#0d9488',
        },
        warn: '#fbbf24',
        danger: '#f87171',
        void: '#0a0e1a',
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      keyframes: {
        scan: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100%)' },
        },
        pulseSoft: {
          '0%,100%': { opacity: '0.55' },
          '50%': { opacity: '1' },
        },
        glowPulse: {
          '0%,100%': { filter: 'brightness(1)' },
          '50%': { filter: 'brightness(1.35)' },
        },
      },
      animation: {
        scan: 'scan 7s linear infinite',
        pulseSoft: 'pulseSoft 2.6s ease-in-out infinite',
        glowPulse: 'glowPulse 2.8s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
