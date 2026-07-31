import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { viteSingleFile } from 'vite-plugin-singlefile';
import { fileURLToPath, URL } from 'node:url';

// 独立预览构建：产出自包含 HTML（JS+CSS 内联），用于 file:// 双击打开，无需服务器。
export default defineConfig({
  base: './',
  plugins: [react(), viteSingleFile()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: 'dist-standalone',
    emptyOutDir: true,
    chunkSizeWarningLimit: 8000,
    cssCodeSplit: false,
    assetsInlineLimit: 0, // 纹理走 ./assets 相对路径（file:// 下 Image 可直接加载）
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
      },
    },
  },
});
