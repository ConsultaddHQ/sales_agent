import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './Widget.tsx'
import './index.css'

declare global {
  interface Window {
    __SHOP_ASSISTANT_CSS__?: string;
    __HYPERFLEX_WIDGET_STORE_ID__?: string;
    __HYPERFLEX_WIDGET_POSITION__?: "bottom-left" | "bottom-right";
    __HYPERFLEX_WIDGET_AGENT_ID__?: string;
    __HYPERFLEX_WIDGET_API_KEY__?: string;
    __HYPERFLEX_WIDGET_INITIALIZED__?: boolean;
  }
}

class ShopWidget extends HTMLElement {
  connectedCallback() {
    const shadow = this.attachShadow({ mode: 'open' });
    const container = document.createElement('div');
    container.id = 'shop-widget-root';

    // Inject CSS
    const style = document.createElement('style');
    let cssContent = window.__SHOP_ASSISTANT_CSS__ || '';
    if (typeof cssContent === 'string' && cssContent.startsWith('"')) {
      cssContent = JSON.parse(cssContent);
    }
    style.textContent = cssContent;
    shadow.appendChild(style);

    // Parse query params from script src
    const script = document.currentScript as HTMLScriptElement;
    const url = new URL(script.src);
    const params = url.searchParams;

    window.__HYPERFLEX_WIDGET_STORE_ID__ = params.get('store_id') || 'demo-store';
    const pos = params.get('position') || 'bottom-right';
    window.__HYPERFLEX_WIDGET_POSITION__ = (pos === 'bottom-left' || pos === 'bottom-right') ? pos : 'bottom-right';
    window.__HYPERFLEX_WIDGET_AGENT_ID__ = params.get('agent_id') || '';
    window.__HYPERFLEX_WIDGET_API_KEY__ = params.get('api_key') || '';

    shadow.appendChild(container);
    ReactDOM.createRoot(container).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>
    );
  }
}

customElements.define('shop-widget', ShopWidget);

if (!window.__HYPERFLEX_WIDGET_INITIALIZED__) {
  window.__HYPERFLEX_WIDGET_INITIALIZED__ = true;
  const widget = document.createElement('shop-widget');
  document.body.appendChild(widget);
}