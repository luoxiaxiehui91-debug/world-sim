import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

// 开阳 Wave 1：纯静态站点。base 使用相对路径，便于 NAS 容器 serve dist/ 时任意子路径挂载。
export default defineConfig({
  base: './',
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    chunkSizeWarningLimit: 4000,
    rollupOptions: {
      output: {
        manualChunks: {
          three: ['three'],
          echarts: ['echarts'],
          react: ['react', 'react-dom'],
          geo: ['d3-geo', 'topojson-client'],
        },
      },
    },
  },
  server: {
    host: true,
    port: 5173,
  },
});
