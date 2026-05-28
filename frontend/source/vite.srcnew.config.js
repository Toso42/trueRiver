import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  root: './',
  plugins: [react()],
  build: {
    outDir: 'build',
    emptyOutDir: true,
    sourcemap: true,
    minify: false, // Disable minification for debugging
    rollupOptions: {
      input: {
        index: 'index.html',
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 6002,
    open: false,
    cors: true,
  },
});
