import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// `/admin` is both an API prefix and a client route, so a blanket proxy sends
// the browser's navigation to FastAPI and gets a 404 back. Let document
// requests fall through to the SPA and proxy only the XHR/fetch traffic.
const api = (target = 'http://127.0.0.1:8000') => ({
  target,
  changeOrigin: true,
  bypass(req) {
    if (req.headers.accept?.includes('text/html')) return '/index.html'
  },
})

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/auth': api(),
      '/items': api(),
      '/matches': api(),
      '/claims': api(),
      '/admin': api(),
      '/health': api(),
      // Images are <img src> requests, not navigations — always proxy them.
      '/uploads': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
