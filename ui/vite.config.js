import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: Vite serves the UI on :5173 and proxies /api to FastAPI on :8000.
// Prod: `npm run build` -> ui/dist, which api.py serves itself.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
