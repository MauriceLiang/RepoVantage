import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

const root = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  root,
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('../src', import.meta.url)) },
    dedupe: ['vue'],
  },
  server: {
    host: '127.0.0.1',
    port: 5180,
    proxy: {
      '/api/browser': { target: 'http://127.0.0.1:8501', changeOrigin: true },
    },
  },
  build: {
    outDir: `${root}dist`,
    emptyOutDir: true,
    rollupOptions: {
      input: {
        app: fileURLToPath(new URL('./index.html', import.meta.url)),
        components: fileURLToPath(new URL('./components.html', import.meta.url)),
      },
    },
  },
})
