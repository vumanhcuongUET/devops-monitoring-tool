---
name: run-app
description: Launch and drive the DevOps monitoring tool app - backend and frontend services
---

# Run DevOps Monitoring Tool

Launch the monitoring platform application for development and testing.

## Usage

Run `/run-app` or `/run-app <service>` to start:

- `backend` - Start FastAPI backend server
- `frontend` - Start React frontend dev server
- `all` or no argument - Start both services

## Backend (FastAPI)

The backend runs on port 8000 by default:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Health check:** `http://localhost:8000/api/v1/overview`

**API docs:** `http://localhost:8000/docs` (Swagger UI)

## Frontend (React + Vite)

The frontend runs on port 3000 with API proxy to backend:

```bash
cd frontend
npm install
npm run dev
```

**Dev server:** `http://localhost:3000`

**Note:** Vite proxies `/api/*` and `/ws` to backend at localhost:8000

## Environment Setup

Ensure `.env` file exists in the root directory:

```bash
cp .env.example .env
# Edit .env with your endpoints
```

Required for backend:
- `ELASTICSEARCH_URL`, `ELASTICSEARCH_USERNAME`, `ELASTICSEARCH_PASSWORD`
- `PROMETHEUS_URL`
- `ANTHROPIC_API_KEY` (for Triage Cards)
- `KUBECONFIG_PATH` (optional, for local development)

## Troubleshooting

**Backend won't start:**
- Check if port 8000 is already in use: `lsof -i :8000`
- Verify Python dependencies: `pip install -r requirements.txt`
- Check environment variables in `.env`

**Frontend won't start:**
- Check if port 3000 is already in use: `lsof -i :3000`
- Verify Node modules: `npm install`
- Ensure backend is running for API proxy

## Docker Alternative

To run everything with Docker Compose:

```bash
docker compose up
```
