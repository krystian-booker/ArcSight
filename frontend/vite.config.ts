import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: '../app/static/react_build',
    emptyOutDir: true,
    // Optimize for Raspberry Pi - smaller chunks
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'query-vendor': ['@tanstack/react-query'],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy API calls to Flask backend during development
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/cameras': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/calibration': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/settings': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/monitoring': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/video_feed': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/processed_video_feed': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8080',
        ws: true,
      },
    },
  },
})
