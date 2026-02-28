(function () {
  if (window.__HYPERFLEX_WIDGET_INITIALIZED__) return;
  window.__HYPERFLEX_WIDGET_INITIALIZED__ = true;

  function getCurrentScript() {
    if (document.currentScript) return document.currentScript;
    const scripts = document.getElementsByTagName('script');
    for (let i = scripts.length - 1; i >= 0; i -= 1) {
      const s = scripts[i];
      if (s.src && s.src.indexOf('widget.js') !== -1) return s;
    }
    return null;
  }

  const scriptEl = getCurrentScript();
  if (!scriptEl || !scriptEl.src) {
    console.error('[Hyperflex Widget] Could not locate widget.js script tag.');
    return;
  }

  const scriptUrl = new URL(scriptEl.src);
  const params = scriptUrl.searchParams;

  const storeId = params.get('store_id') || '';
  const position =
    params.get('position') === 'bottom-left' ? 'bottom-left' : 'bottom-right';

  // Create a host element and attach a shadow root to isolate styles/markup
  const host = document.createElement('div');
  host.style.all = 'initial';
  host.style.position = 'fixed';
  host.style.inset = '0';
  host.style.zIndex = '2147483647';
  host.style.pointerEvents = 'none';
  document.body.appendChild(host);

  const shadowRoot = host.attachShadow
    ? host.attachShadow({ mode: 'open' })
    : host;

  const root = document.createElement('div');
  root.id = 'hyperflex-widget-root';
  root.style.pointerEvents = 'auto';
  shadowRoot.appendChild(root);

  // Expose config and root element to the React bundle
  window.__HYPERFLEX_WIDGET_ROOT__ = root;
  window.__HYPERFLEX_WIDGET_STORE_ID__ = storeId;
  window.__HYPERFLEX_WIDGET_POSITION__ = position;

  // Load ElevenLabs SDK once
  (function loadElevenLabsSdk() {
    if (document.querySelector('script[data-elevenlabs-sdk="true"]')) return;
    const sdkScript = document.createElement('script');
    sdkScript.src = 'https://unpkg.com/@elevenlabs/convai-widget-embed';
    sdkScript.async = true;
    sdkScript.setAttribute('data-elevenlabs-sdk', 'true');
    document.head.appendChild(sdkScript);
  })();

  // Load the React widget bundle once
  (function loadReactBundle() {
    if (document.querySelector('script[data-hyperflex-widget-bundle="true"]'))
      return;

    const bundleScript = document.createElement('script');
    bundleScript.async = true;
    bundleScript.setAttribute('data-hyperflex-widget-bundle', 'true');

    // Assume the built React bundle sits next to widget.js as widget-bundle.js
    const bundlePath = scriptUrl.pathname.replace(
      /[^/]+$/,
      'widget-bundle.js'
    );
    bundleScript.src = scriptUrl.origin + bundlePath + scriptUrl.search;

    document.head.appendChild(bundleScript);
  })();
})();