

import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import App from './App.jsx'

class TeamPopWidget extends HTMLElement {
  connectedCallback() {
    const shadow = this.attachShadow({ mode: 'open' })

    // Google Fonts via link — @import doesn't work in Shadow DOM
    const fontLink = document.createElement('link')
    fontLink.rel = 'stylesheet'
    fontLink.href = 'https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Space+Grotesk:wght@300;400;500;600;700&display=swap'
    shadow.appendChild(fontLink)

    const style = document.createElement('style')
    shadow.appendChild(style)

    const container = document.createElement('div')
    container.id = 'team-pop-root'
    shadow.appendChild(container)

    ReactDOM.createRoot(container).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    )

    // Inject CSS after React mounts
    requestAnimationFrame(() => {
      let css = window.__TEAM_POP_CSS__ || ''

      if (css[0] === '"') {
        try {
          css = JSON.parse(css)
        } catch(e) {
          css = css.slice(1, css.lastIndexOf('"'))
            .replace(/\\n/g, '\n')
            .replace(/\\t/g, '\t')
            .replace(/\\"/g, '"')
            .replace(/\\\\/g, '\\')
        }
      }

      css = css.replace(/@import[^;]+;/g, '')
      style.textContent = css
    })
  }
}

if (!customElements.get('team-pop-agent')) {
  customElements.define('team-pop-agent', TeamPopWidget)
}