# Team Pop Dashboard

The dashboard for the Team Pop Voice Agent. Built with **React 19**, **Vite**, and **Tailwind CSS**. This application serves as the SaaS frontend where users configure their target domain and orchestrate the background crawler.

## ✨ Features

- **Get Started Timeline**: A guided onboarding flow (Enter URL -> Crawling -> Snippet Generation).
- **Background Polling**: Visually tracks the status of the backend crawler using skeleton loaders and animated progress states.
- **Installation Snippet**: Automatically generates the `<script>` tag configuration for users to embed the widget in their own HTML sites.

## 🚀 Setup & Run

### Prerequisites

- Node.js 18+
- Backend running on port 8080 (serves the crawling endpoints).

### Installation

```bash
cd dashboard
npm install
```

### Development

```bash
npm run dev
```

Access the app at `http://localhost:5174` (or the port Vite assigns).

## 🏗️ Project Structure

```
src/
├── components/
│   ├── InstallSnippet.jsx   # Renders the copy-paste deployment code
│   └── ...
├── pages/
│   ├── Landing.jsx          # Initial marketing/URL entry page
│   └── Onboarding.jsx       # The multi-state polling and crawl progress UI
└── App.jsx                  # Main router config
```

## 🔌 API Integration

The dashboard communicates via REST to the FastAPI backend to trigger and monitor background tasks:

- `POST http://localhost:8080/api/onboard`: Sends `{ url, tenant_id }` to trigger the Elastic Crawler and returns a `job_id`.
- `GET http://localhost:8080/api/job/{job_id}`: Polls the background process until it returns a `status` of `'completed'` or `'failed'`.
