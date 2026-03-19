import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App.jsx";
import "./styles/AvatarWidget.css";

class TeamPopWidget extends HTMLElement {
  connectedCallback() {
    const shadow = this.attachShadow({ mode: "open" });

    const container = document.createElement("div");
    container.id = "team-pop-root";
    container.style.fontSize = "16px";

    // ✅ FIX 1: Inject Google Fonts via <link> — @import doesn't work in Shadow DOM
    const fontLink = document.createElement("link");
    fontLink.rel = "stylesheet";
    fontLink.href =
      "https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Space+Grotesk:wght@300;400;500;600;700&display=swap";
    shadow.appendChild(fontLink);

    // Inject CSS
    const style = document.createElement("style");

    const injectCSS = () => {
      let cssContent = window.__TEAM_POP_CSS__ || "";

      if (!cssContent) {
        // CSS not ready yet, try again next microtask
        console.warn("[TeamPop] CSS not ready, retrying...");
        setTimeout(injectCSS, 50);
        return;
      }

      // Fix double-encoding
      if (cssContent.startsWith('"') && cssContent.endsWith('"')) {
        try {
          cssContent = JSON.parse(cssContent);
        } catch (e) {
          cssContent = cssContent
            .slice(1, -1)
            .replace(/\\n/g, "\n")
            .replace(/\\"/g, '"')
            .replace(/\\\\/g, "\\");
        }
      }

      // Strip @import — doesn't work in Shadow DOM
      cssContent = cssContent.replace(/@import[^;]+;/g, "");

      console.log("[TeamPop] Injecting CSS, length:", cssContent.length);
      style.textContent = cssContent;
    };

    shadow.appendChild(style);

    shadow.appendChild(container);

    ReactDOM.createRoot(container).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    );
    injectCSS();
  }
}

if (!customElements.get("team-pop-agent")) {
  customElements.define("team-pop-agent", TeamPopWidget);
}
