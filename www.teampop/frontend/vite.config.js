import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import cssInjectedByJsPlugin from 'vite-plugin-css-injected-by-js'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    cssInjectedByJsPlugin({
      injectCode: (cssCode) => {
        return `window.__TEAM_POP_CSS__ = ${JSON.stringify(cssCode)};`
      }
    })
  ],
  build: {
    lib: {
      entry: 'src/main.jsx',
      name: 'TeamPopWidget',
      fileName: () => 'widget.js',
      formats: ['iife'],
    },
  },
  define: {
    'process.env': {}
  }
})