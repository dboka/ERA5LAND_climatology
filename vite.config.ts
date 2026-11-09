import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const repository = process.env.GITHUB_REPOSITORY?.split('/').pop() || 'PROJECT_EUROPE';
const pagesBase = process.env.PAGES_BASE || (repository.endsWith('.github.io') ? '/' : `/${repository}/`);

export default defineConfig({
  plugins: [react()],
  base: process.env.GITHUB_PAGES === '1' ? pagesBase : '/',
  server: { proxy: { '/api': 'http://127.0.0.1:8013' } },
});
