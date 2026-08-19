# Dashboard Screenshots & Mockups

This directory contains visual documentation of the DevOps AI Agentics 2026 dashboard.

## Current Screenshots

### Overview Page (NOC Dashboard)
- **File**: `overview-page.png`
- **Description**: Main NOC-style dashboard showing:
  - System health status across all projects
  - Active alerts with severity indicators
  - Quick stats (total alerts, incidents, SLO health)
  - Real-time WebSocket updates indicator

### Triage Card Detail
- **File**: `triage-card-detail.png`
- **Description**: AI-generated incident analysis showing:
  - Summary and severity assessment
  - Findings with confidence scores
  - Prioritized recommendations with commands
  - Context sources analyzed

### Actions Page
- **File**: `actions-page.png`
- **Description**: Human-in-the-loop action management:
  - Action list with filters (project, status, risk level)
  - Approve/Reject/Execute buttons
  - Risk level indicators (SAFE, LOW, MEDIUM, HIGH, CRITICAL)
  - Execution status and results

## SVG Mockups (Fallback)

When actual screenshots are not available, use the SVG mockups in `mockups/`:

- `overview-mockup.svg` - Overview page wireframe
- `actions-mockup.svg` - Actions page wireframe
- `triage-card-mockup.svg` - Triage card wireframe

## How to Capture Screenshots

### 1. Start the Application

```bash
# Using Docker Compose
docker compose up -d

# Or manually (development)
# Terminal 1 - Backend
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 - Frontend
cd frontend
npm run dev
```

### 2. Access the Dashboard

Open browser to: `http://localhost:3000`

### 3. Capture Screenshots

**Option A: Browser DevTools**
1. Open DevTools (F12)
2. Press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
3. Type "screenshot" and select:
   - "Capture full size screenshot" for entire page
   - "Capture node screenshot" for specific element

**Option B: Command Line**
```bash
# Using chromium-cli (if installed)
chromium-cli --headless --screenshot=overview-page.png http://localhost:3000/overview

# Using Puppeteer
npx puppeteer-cli screenshot http://localhost:3000/overview --output overview-page.png
```

### 4. Naming Convention

```
{page-name}-{state}-{timestamp}.png

Examples:
- overview-page-normal-20260818.png
- actions-page-pending-20260818.png
- triage-card-critical-20260818.png
```

### 5. Optimize for Documentation

```bash
# Optimize PNG size
optipng -o7 *.png

# Or convert to WebP for smaller files
cwebp -q 80 overview-page.png -o overview-page.webp
```

## Adding Images to Markdown

```markdown
### Overview Page

![Overview Dashboard](images/overview-page.png)

*Figure 1: NOC-style overview dashboard with real-time alerts*
```

## Placeholder Images

When screenshots are not available, use placeholder blocks:

```markdown
<div align="center">

```svg
<svg width="800" height="400" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#f8fafc"/>
  <text x="50%" y="50%" text-anchor="middle" fill="#64748b" font-size="16">
    Screenshot placeholder - Overview Dashboard
  </text>
</svg>
```

*Figure 1: Overview Dashboard (screenshot pending)*

</div>
```
