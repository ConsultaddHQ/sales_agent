# Team Pop Dashboard

SaaS user interface for configuring and launching the Team Pop voice
assistant. This React 19 + Vite + Tailwind CSS application allows a merchant
to enter their domain, watch the ingestion progress, and copy the snippet
needed to embed the Avatar Widget.

> **Status:** alpha – used in demos and internal tests.

## Features

- Guided three‑step onboarding timeline.
- Real‑time polling of backend ingestion status.
- Automatic generation of the `<script>` embed snippet.
- Light-weight, mobile‑friendly design.

## Prerequisites

- Node.js 18+
- Backend services running locally:
  - `onboarding-service` at `http://localhost:8005` (or adjust `VITE_BACKEND_URL`)
  - `search-service` is not required for dashboard.

### Environment variables

Create `.env` in this directory (copy from `.env.example` if you add one).
Key variables:

```env
VITE_BACKEND_URL=http://localhost:8005
```

### Setup

```bash
cd www.teampop/dashboard
npm install
```

### Development

```bash
npm run dev
```

Visit `http://localhost:5174` (Vite displays the port after start).

### API integration

- POST `{$VITE_BACKEND_URL}/onboard` – body `{ url: string }`.
- GET  `{$VITE_BACKEND_URL}/health` – used to validate the backend.
- The service will return a `job_id` that you poll via
  `GET /job/{job_id}` until completion.

_NOTE:_ endpoint paths correspond to the current `onboarding-service` API.
Adjust if you move services or change ports.

### Project structure

```
src/
└── [components, pages, App.jsx] same as before...
```

### Best practices

- Keep the backend URL configurable via environment.
- Do not commit build artifacts.
- Test on multiple screen sizes to ensure the widget snippet is clear.
