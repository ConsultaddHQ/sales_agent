# Team Pop Voice Agent

A voice-first AI assistant built with **React 19**, **LiveKit WebRTC**, and **FastAPI**. This system allows users to "train" an assistant on any website URL, which is then indexed by **Elasticsearch** and made accessible via a cinematic "Avatar Widget" that supports real-time, ultra-low latency multimodal voice interaction.

## 🚀 High-Level Architecture

The system consists of three main components arranged in a monorepo pattern:

1.  **Dashboard (`/dashboard`)**: A React application built with Vite and TailwindCSS for the user onboarding experience. It handles the 3-step timeline UI where users enter a URL, monitor the backend crawler's progress, and receive their embeddable snippet.
2.  **Frontend Widget (`/frontend`)**: The core WebRTC React application. This is the embeddable, floating "Avatar Widget" (Orb) that establishes a real-time LiveKit connection to the agent for voice recording, playback, and chat UI.
3.  **Backend (`/backend`)**: A FastAPI server running the core AI orchestrated logic.
    - **Crawler Service**: Orchestrates web crawling using a Firecrawl/Elastic pipeline to index website content (Sitemaps, HTML).
    - **LiveKit Agent Worker**: Runs a persistent Python WebRTC worker (`livekit.agents`) connecting user audio to Google's Gemini Multimodal Live API.
    - **Integrations**:
      - **LiveKit** (WebRTC Transport & Token Vending)
      - **Elasticsearch** (Vector Store + Hybrid Search Context)
      - **Google Gemini 2.5 Flash** (Native Audio/Multimodal generation)

## 🛠️ Tech Stack

- **Dashboard**: React 19, Vite, Tailwind CSS, Lucide Icons.
- **Frontend Widget**: React 19, Vite, LiveKit React Components (`@livekit/components-react`), CSS Modules (Glassmorphism).
- **Backend**: Python 3.10+, FastAPI, LiveKit Agents API, Async Elasticsearch.

## ⚡ Quick Start

### 1. Backend Setup

The backend requires LiveKit and Gemini API keys. Create a `.env` file in `backend/` (see `backend/README_backend.MD`).

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# Run Server on port 8080 to sync with frontends
uvicorn app.main:app --port 8080 --reload
```

_Runs on `http://localhost:8080`_

### 2. Frontend Widget Setup

```bash
cd frontend
npm install
npm run dev
```

_Runs on `http://localhost:5173`_

### 3. Dashboard Setup

```bash
cd dashboard
npm install
npm run dev
```

_Runs on `http://localhost:5174` (or next available port)_

## 🌊 User Flow

1.  **Onboarding**: User visits the dashboard (`localhost:5174`), enters `https://example.com`.
2.  **Crawling**: Backend instructs the crawler to index the site. Dashboard polls for status on port `8080`.
3.  **Deployment**: Dashboard provides a `<script>` snippet for the user to embed `widget.js`.
4.  **Interaction**: User clicks the Orb on a deployed site.
    - The widget fetches a LiveKit Token from `http://localhost:8080/get-livekit-token`.
    - A WebRTC room is established.
    - The Python Agent Worker listens to user speech and streams it to Gemini.
    - Gemini streams native audio back to the user via LiveKit with sub-second latency.

## 📂 Repository Structure

- `frontend/`: The embeddable Avatar Widget.
- `dashboard/`: The onboarding SaaS application.
- `backend/`: FastAPI application and LiveKit WebRTC Worker.

## 📄 License

MIT.
