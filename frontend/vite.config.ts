import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      // optional proxies if you run frontend + backend together
    },
  },
  preview: { port: 4173, host: true },
})
