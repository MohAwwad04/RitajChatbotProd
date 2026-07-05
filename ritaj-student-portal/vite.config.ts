import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev (`npm run dev`) the page is served by Vite, but the chat backend runs
// separately (uvicorn on :8000). Proxy the API calls there so streaming works
// the same as in the FastAPI-served production build (GET /chat).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/chat/stream': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
