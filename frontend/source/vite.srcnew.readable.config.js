import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  root: './',
  plugins: [react()],
  esbuild: {
    keepNames: true,
  },
  build: {
    outDir: 'build',
    emptyOutDir: true,
    sourcemap: true,
    minify: false,
    target: 'chrome74',
    modulePreload: false,
    cssCodeSplit: false,
    assetsInlineLimit: 0,
    rollupOptions: {
      input: {
        index: 'index.html',
      },
      treeshake: false,
      output: {
        format: 'es',
        compact: false,
        manualChunks: undefined,
        inlineDynamicImports: true,
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
        generatedCode: {
          preset: 'es2015',
          constBindings: true,
          objectShorthand: true,
        },
      },
    },
  },
});
