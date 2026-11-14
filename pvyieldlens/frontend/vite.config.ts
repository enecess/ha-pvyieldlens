import { fileURLToPath } from 'node:url';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  base: './',
  server: { fs: { allow: [fileURLToPath(new URL('../..', import.meta.url))] } },
  plugins: [vue(), tailwindcss()],
  build: {
    outDir: '../src/pvyieldlens/static/dist',
    emptyOutDir: true,
  },
  test: {
    include: ['../../tests/frontend/**/*.test.ts'],
    environment: 'jsdom',
  },
  resolve: {
    alias: { vue: fileURLToPath(new URL('./node_modules/vue/dist/vue.runtime.esm-bundler.js', import.meta.url)) },
  },
});
