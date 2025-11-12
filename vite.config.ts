import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/static/dist/', // Assets will be served from /static/dist/ in production
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 8080,
    host: '0.0.0.0', // Bind to all interfaces (IPv4 and IPv6)
    proxy: {
      // Proxy API calls and backend endpoints to Flask (running on port 5001 in development)
      // IMPORTANT: Only proxy paths with trailing content (e.g., /api/cameras, /settings/api/...)
      // Direct page routes (/monitoring, /settings, /cameras, /calibration) are NOT proxied
      // so they can be handled by Vite and React Router with proper HMR support
      '^/(api|cameras|calibration|settings|monitoring)/': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/video_feed': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/processed_video_feed': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: './app/static/dist',
    emptyOutDir: true,
    // Optimize chunk size for low-power devices
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          // Simplified chunking strategy to avoid dependency issues
          if (id.includes('node_modules')) {
            // Put ALL vendor code in one chunk to avoid loading order issues
            return 'vendor'
          }
          // Split large pages
          if (id.includes('/pages/Dashboard')) {
            return 'page-dashboard'
          }
          if (id.includes('/pages/Cameras')) {
            return 'page-cameras'
          }
          if (id.includes('/pages/Calibration')) {
            return 'page-calibration'
          }
          if (id.includes('/pages/Settings')) {
            return 'page-settings'
          }
          if (id.includes('/pages/Monitoring')) {
            return 'page-monitoring'
          }
        },
        // Optimize chunk naming for better caching
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
  },
})
