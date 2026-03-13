/**
 * FIXED: AvatarWidget with Maximum Z-Index
 * 
 * This version fixes the issue where widget falls behind client popups/shadow DOM
 * 
 * Changes made:
 * 1. Maximum z-index (2147483647)
 * 2. Portal rendering (bypasses parent z-index)
 * 3. Isolation stacking context
 * 4. Proper pointer-events handling
 */

import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

// CRITICAL: Global styles injected to ensure widget is always on top
const GLOBAL_WIDGET_STYLES = `
  /* Ensure widget root is always accessible */
  #avatar-widget-root {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    z-index: 2147483647 !important;  /* Maximum possible z-index */
    pointer-events: none !important;  /* Allow clicks through empty space */
    isolation: isolate !important;     /* Create stacking context */
  }

  /* Allow interactions with widget content */
  #avatar-widget-root > * {
    pointer-events: auto !important;
  }

  /* Widget container with maximum z-index */
  .avatar-widget-container {
    position: fixed !important;
    z-index: 2147483647 !important;
    isolation: isolate !important;
  }

  /* Override any conflicting z-index from parent */
  .avatar-widget-container,
  .avatar-widget-container * {
    position: relative;
  }

  /* Ensure modals/overlays from widget are above everything */
  .avatar-widget-modal,
  .avatar-widget-overlay {
    z-index: 2147483647 !important;
    position: fixed !important;
  }

  /* Fix for shadow DOM conflicts */
  :host(.avatar-widget-host) {
    all: initial;
    z-index: 2147483647 !important;
  }
`;

// Inject global styles once
if (typeof document !== 'undefined') {
  const styleId = 'avatar-widget-global-styles';
  if (!document.getElementById(styleId)) {
    const styleEl = document.createElement('style');
    styleEl.id = styleId;
    styleEl.textContent = GLOBAL_WIDGET_STYLES;
    document.head.appendChild(styleEl);
  }
}

export default function AvatarWidget({ storeId, searchApiUrl, ...props }) {
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    // Ensure widget root exists
    let widgetRoot = document.getElementById('avatar-widget-root');
    if (!widgetRoot) {
      widgetRoot = document.createElement('div');
      widgetRoot.id = 'avatar-widget-root';
      document.body.appendChild(widgetRoot);
    }
    
    setIsReady(true);

    return () => {
      // Cleanup on unmount
      if (widgetRoot && widgetRoot.childNodes.length === 0) {
        widgetRoot.remove();
      }
    };
  }, []);

  if (!isReady) {
    return null;
  }

  const widgetContent = (
    <div 
      className="avatar-widget-container"
      style={{
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        zIndex: 2147483647,
        isolation: 'isolate',
      }}
    >
      {/* Your existing widget content goes here */}
      <YourExistingWidgetComponent 
        storeId={storeId} 
        searchApiUrl={searchApiUrl} 
        {...props} 
      />
    </div>
  );

  // Render widget using portal to bypass parent z-index issues
  return createPortal(
    widgetContent,
    document.getElementById('avatar-widget-root')
  );
}

/**
 * Usage Example:
 * 
 * // In your app or static page:
 * import AvatarWidget from './components/AvatarWidget';
 * 
 * function App() {
 *   return (
 *     <div>
 *       {/* Your app content *\/}
 *       
 *       {/* Widget will always be on top *\/}
 *       <AvatarWidget 
 *         storeId="your-store-id"
 *         searchApiUrl="http://localhost:8006"
 *       />
 *     </div>
 *   );
 * }
 * 
 * // Or inject via script tag in static HTML:
 * <script>
 *   window.AVATAR_WIDGET_CONFIG = {
 *     storeId: 'your-store-id',
 *     searchApiUrl: 'http://localhost:8006'
 *   };
 * </script>
 * <script src="widget.js"></script>
 */

/**
 * Additional fix for existing AvatarWidget.jsx:
 * 
 * If you want to apply this fix to your existing widget without rewriting,
 * wrap your root component like this:
 */

export function withMaxZIndex(WidgetComponent) {
  return function WidgetWithMaxZIndex(props) {
    const [isReady, setIsReady] = useState(false);

    useEffect(() => {
      let widgetRoot = document.getElementById('avatar-widget-root');
      if (!widgetRoot) {
        widgetRoot = document.createElement('div');
        widgetRoot.id = 'avatar-widget-root';
        document.body.appendChild(widgetRoot);
      }
      setIsReady(true);

      return () => {
        if (widgetRoot && widgetRoot.childNodes.length === 0) {
          widgetRoot.remove();
        }
      };
    }, []);

    if (!isReady) return null;

    return createPortal(
      <div 
        className="avatar-widget-container"
        style={{
          position: 'fixed',
          bottom: '20px',
          right: '20px',
          zIndex: 2147483647,
          isolation: 'isolate',
        }}
      >
        <WidgetComponent {...props} />
      </div>,
      document.getElementById('avatar-widget-root')
    );
  };
}

/**
 * Then wrap your existing widget:
 * 
 * // In your widget file:
 * import { withMaxZIndex } from './WidgetZIndexFix';
 * 
 * function AvatarWidget(props) {
 *   // Your existing widget code
 * }
 * 
 * export default withMaxZIndex(AvatarWidget);
 */
