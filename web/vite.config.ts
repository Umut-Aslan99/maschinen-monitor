/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  // No data: URIs – the Content-Security-Policy only allows files from this origin.
  build: { assetsInlineLimit: 0 },
  server: { proxy: { '/api': { target: 'http://localhost:8000', ws: true } } },
  test: { environment: 'jsdom', globals: true },
});
