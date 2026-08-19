---
name: build-frontend
description: Build frontend React application for production
---

# Build Frontend

Build the frontend React application for production deployment.

## Usage

Run `/build-frontend` to create a production build.

## Building

```bash
cd frontend

# Build for production
npm run build

# Build with analysis
npm run build -- --mode analyze
```

## Build Process

The build process:
1. Runs TypeScript type check (`tsc -b`)
2. Runs ESLint to check code quality
3. Bundles with Vite for production
4. Outputs to `frontend/dist/`

## Output

Built files are in `frontend/dist/`:
- `index.html` - Entry HTML
- `assets/` - JavaScript and CSS bundles
- `assets/*.map` - Source maps (for debugging)

## Build Configuration

- Build config: `frontend/vite.config.ts`
- Environment variables: `frontend/.env.production`
- Base path: Configured for `/` (root)

## Docker Build

For Docker production build:

```bash
# Build Docker image
docker build -t devops-monitoring-frontend -f frontend/Dockerfile .

# Or use docker compose
docker compose build frontend
```

## Troubleshooting

**Build fails on type errors:**
- Check TypeScript errors with `tsc -b`
- Fix type issues in source files

**Build fails on lint errors:**
- Run `npm run lint` to see issues
- Fix with `eslint . --fix` if possible

**Production build vs dev:**
- Dev: `npm run dev` (port 3000, hot reload)
- Prod: `npm run build` then serve dist/

## Preview Production Build

```bash
npm run preview
# Serves dist/ at http://localhost:4173
```
