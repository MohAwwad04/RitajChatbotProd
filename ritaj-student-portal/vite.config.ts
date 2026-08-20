import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev (`npm run dev`) the page is served by Vite, but the chat backend runs
// separately (uvicorn on :8000). Proxy the API calls there so streaming works
// the same as in the FastAPI-served production build.
//
// `/v2/chat/stream` is the route src/api/chat.ts actually calls; the proxy still
// listed only the older `/chat/stream`, so every dev conversation hit Vite's own
// 404 instead of the backend. `/capabilities` is what the home view renders.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/v2/chat': 'http://localhost:8000',
      '/chat/stream': 'http://localhost:8000',
      '/capabilities': 'http://localhost:8000',
      '/ready': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/privacy': 'http://localhost:8000',
    },
  },
})
