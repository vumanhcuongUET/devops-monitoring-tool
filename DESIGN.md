# DESIGN.md — DevOps Monitor frontend

Derived from the shipped frontend (`frontend/src`). This is the reference for any future UI work; deviations need a reason, not a vibe.

## Mode

**Operate.** The visitor completes ops tasks (monitor, triage, approve, execute). Scanability, consistency, and honest state outrank expression. Brand lives in precise details (health colors, monospace commands), not decoration.

## Visual world

Dark-only control plane. Indigo accent on near-black blue surfaces. There is deliberately **one** world: every page consumes the same tokens; light-theme pages are regression, not variety.

## Tokens (`src/index.css`, Tailwind 4 `@theme`)

| Token | Value | Use |
|---|---|---|
| `--color-bg-primary` | `#0f1117` | App/body background |
| `--color-bg-secondary` | `#1a1d2e` | Sidebar, header, table heads, inset rows |
| `--color-bg-card` | `#1e2235` | Cards, panels, toasts, inputs |
| `--color-border` | `#2e3148` | Every border, no exceptions |
| `--color-text` / `--color-text-primary` | `#e2e8f0` | Primary text (~12:1 on bg-card) |
| `--color-text-secondary` | `#94a3b8` | Labels, metadata, subtitles (~6.5:1 on bg-card) |
| `--color-healthy` | `#22c55e` | Healthy/firing-resolved/allowed states |
| `--color-degraded` | `#eab308` | Warning states |
| `--color-down` | `#ef4444` | Firing/error/danger states |
| `--color-unknown` | `#64748b` | Unknown/absent status — never transparent |
| `--color-accent` | `#6366f1` | Brand, active nav, primary buttons, focus rings |

Referencing a token that isn't defined here is a bug — undefined CSS variables silently render nothing.

## Rules

1. **Colors**: semantic tokens for all state and surface color. Raw Tailwind palette is allowed only in the "solid text on 10% tint" chip idiom (below), never for surfaces or body text. Never white text on `--color-healthy`/`--color-down` (fails AA).
2. **Severity chips**: `text-<color>-500 bg-<color>-500/10` (+ optional `border-<color>-500/30`). Shared by ActionCard, risk badges, status badges.
3. **Monospace is mandatory** for shell commands, suggested commands, parameters JSON, stdout/stderr, and is preferred for timestamps/log lines: `font-mono text-xs` on `bg-[var(--color-bg-primary)]` with `border border-[var(--color-border)]`, text-primary. Commands are the product's most dangerous content — they render at full contrast, never as faint gray.
4. **Cards**: `rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5` (or `p-4`). Section panels: header row with `border-b border-[var(--color-border)] px-5 py-4`.
5. **Page header pattern**: `h2.text-lg.font-semibold` + `p.text-sm.text-[var(--color-text-secondary)]` subtitle. No `text-3xl` heroes inside the app shell.
6. **Destructive actions are two-step**: arm ("Delete" → "Confirm"/"Cancel") or a confirmation dialog naming the target (`role="dialog"` + `aria-label`). Executing AI-generated commands additionally requires a dry run first for `high`/`critical` risk.
7. **Identity is real**: audit fields (`approved_by`, `executed_by`) come from the session username (`tokenManager.getUsername()`), falling back to `'unknown'` — never a hardcoded placeholder name.
8. **Every async surface has three states**: `LoadingSkeleton` while loading, `ErrorState` with Retry on failure, and a real empty state. "No data" must not stand in for an error.
9. **Alerts/status toasts**: dark card background (`--color-bg-card`), text-primary, 1px severity-colored border. Emojis may punctuate, color never carries meaning alone.
10. **Accessibility floor**: interactive elements are real `<button>`/`<a>` (an `onClick` div is a bug); toggles use `role="switch"` + `aria-checked`; icon-only buttons get `aria-label`; inputs get `aria-label` or a `<label>`; touch targets ≥ 40px (≥44px on phone-first controls).
11. **Responsive**: content-first on mobile — the sidebar is a drawer (`fixed` + `-translate-x-full`, `md:static`), a hamburger lives in the header, `p-4 md:p-6` page padding, grids stack `grid-cols-1 md:grid-cols-*`. Tables scroll horizontally inside `overflow-x-auto`.
12. **Data freshness is shown truthfully**: Live/Polling indicator in the header; WS-first with polling fallback stays the data-layer pattern.

## Typography

System font stack (Inter is declared but intentionally not loaded; do not add webfonts without removing the fallback). Scale: `text-lg` page titles, `text-sm` body/UI, `text-xs` metadata/chips, `text-4xl` reserved for dashboard metric numbers.

## Motion

Transition colors/shadows only (`transition-colors`, `transition-shadow`, sidebar `transition-transform`). Spinners: the Tailwind `animate-spin` arc on `border-b-2 border-[var(--color-accent)]` for inline waits; `LoadingSkeleton` for page loads. No `prefers-reduced-motion` violations today — keep animations subtle if any are added.
