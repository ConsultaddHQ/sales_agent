import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import App from './App.jsx'


class TeamPopWidget extends HTMLElement {
  connectedCallback() {
    // 1. Attach Shadow DOM
    const shadow = this.attachShadow({ mode: 'open' })

    // 2. Create Container
    const container = document.createElement('div')
    container.id = 'team-pop-root'
    container.style.fontSize = '16px' // Protect REM units

    // 3. Inject CSS
    const style = document.createElement('style')
    let cssContent = window.__TEAM_POP_CSS__ || ''
    
    // Formatting Fix: Remove potential double-encoding from build process
    if (cssContent.startsWith('"') && cssContent.endsWith('"')) {
        try {
            cssContent = JSON.parse(cssContent);
        } catch (e) {
            console.error('[TeamPopWidget] Error parsing CSS string', e);
            cssContent = cssContent.slice(1, -1).replace(/\\"/g, '"');
        }
    }
    
    style.textContent = cssContent
    shadow.appendChild(style)

    // 4. Mount React App
    shadow.appendChild(container)
    
    ReactDOM.createRoot(container).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    )
  }
}

// Check if element is already defined to avoid errors during HMR or re-loads
if (!customElements.get('team-pop-agent')) {
  customElements.define('team-pop-agent', TeamPopWidget)
}