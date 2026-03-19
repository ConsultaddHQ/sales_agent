import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import cssInjectedByJsPlugin from 'vite-plugin-css-injected-by-js'

export default defineConfig({
  plugins: [
    react(),
    cssInjectedByJsPlugin({
      // Use topExecutionPriority to ensure CSS runs before everything
      topExecutionPriority: true,
      injectCode: (cssCode, options) => {
        const escaped = JSON.stringify(cssCode)
        return `try{window.__TEAM_POP_CSS__=${escaped};}catch(e){console.error('[TeamPop] CSS inject failed',e);}`
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
    rollupOptions: {
      output: {
        // Ensure CSS is not extracted as separate file
        assetFileNames: '[name][extname]',
      }
    }
  },
  define: {
    'process.env': {}
  }
})