import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const root = fileURLToPath(new URL('./ml-console', import.meta.url))
const proxy = {
  '/api/browser': {
    target: process.env.ML_API_TARGET ?? 'http://127.0.0.1:8501',
    changeOrigin: true,
  },
}

export default defineConfig({
  root,
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    proxy,
  },
  preview: {
    host: '127.0.0.1',
    port: 8502,
    strictPort: true,
    proxy,
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
