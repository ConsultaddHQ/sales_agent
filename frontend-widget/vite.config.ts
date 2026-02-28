import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import cssInjectedByJsPlugin from 'vite-plugin-css-injected-by-js'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    cssInjectedByJsPlugin({
      injectCode: (cssCode) => {
        return `window.__SHOP_ASSISTANT_CSS__ = ${JSON.stringify(cssCode)};`
      }
    })
  ],
  build: {
    lib: {
      entry: 'src/main.tsx',
      name: 'ShopAssistantWidget',
      fileName: () => 'widget.js',
      formats: ['iife'],
    },
  },
  define: {
    'process.env': {}
  }
})