# Team Pop Frontend

**Status:** alpha prototype

The frontend for the Team Pop Voice Agent. Built with **React 19** and **Vite**, this application provides the embeddable `AvatarWidget`—a cinematic, voice-first UI component that connects directly to the LiveKit Cloud.

_(Note: The onboarding flow now lives in the `/dashboard` application)._

## ✨ Features

- **Avatar Widget**: A cinematic, voice-first UI component.
  - **LiveKit Integration**: Uses `@livekit/components-react` to establish a low-latency WebRTC room directly with the backend Python Worker.
  - **Orb Mode**: A glowing, animated orb that reacts to "Listening", "Thinking", and "Speaking" states piped in real-time from the agent.
  - **Chat Mode**: A simplifed, glassmorphism-styled chat window that opens on interaction, displaying product cards via Data Channels.
  - **Voice-First**: "Tap-to-Interrupt" logic, auto-open on speech, and real-time state visualization.
- **Dynamic UI Control**:
  - The UI (e.g., active product focus) reacts natively to transcriptions and specific keywords uttered by the AI fashion expert.

## 🚀 Setup & Run

### Prerequisites

- Node.js 18+
- Backend running on port 8080 (to serve local LiveKit tokens).

### Installation

```bash
cd frontend
npm install
```

### Development

```bash
npm run dev
```

Access the app at `http://localhost:5173`.

### Production Build

```bash
# Optional: To build the embeddable widget.js script bundle
npm run build
npm run preview
```

## 🏗️ Project Structure

```
src/
├── components/
│   ├── AvatarWidget.jsx   # The core LiveKit voice assistant widget
│   └── ShoppingCard.jsx   # E-commerce product display passed via data channels
├── pages/
│   └── Home.jsx           # Demo environment to embed the widget
├── styles/
│   └── index.css          # Setup for Glassmorphism, Animations, Layout
└── App.jsx                # Fetches Token -> Renders AvatarWidget
```

## 🔌 API Integration

The frontend primarily communicates over WebRTC (`wss://`) using LiveKit.

For the initial handshake, it fetches a JWT from the FastAPI backend:

- `GET http://localhost:8080/get-livekit-token`: Receives the token and LiveKit URL to initialize the room.

## 🎨 Styling

We use raw CSS with CSS variables for theming (see `index.css`) alongside Tailwind classes.

- **Font**: "Space Grotesk" for a modern, tech-forward look.
- **Glassmorphism**: Heavy use of `backdrop-filter: blur()` and transparent backgrounds.
- **Animations**: CSS keyframes for the Orb's "breathing" and "speaking" waves.
