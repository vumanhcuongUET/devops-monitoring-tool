import { lazy, Suspense, useEffect, useState } from 'react'
import type { ComponentType } from 'react'
import { Routes, Route } from 'react-router-dom'
import { ErrorBoundary } from './components/common/ErrorBoundary'
import { AppShell } from './components/layout/AppShell'
import { LoadingSkeleton } from './components/common/LoadingSkeleton'
import { useAlertNotifications } from './hooks/useWebSocket'
import { getAuthStatus } from './api/client'

// Code split pages with lazy loading
// Pages export named symbols (except Skills/Governance) — wrap for React.lazy
const named = (p: Promise<Record<string, unknown>>, key: string) =>
  p.then((m) => ({ default: m[key] as ComponentType }))

const OverviewPage = lazy(() => named(import('./pages/OverviewPage'), 'OverviewPage'))
const LogsPage = lazy(() => named(import('./pages/LogsPage'), 'LogsPage'))
const ApmPage = lazy(() => named(import('./pages/ApmPage'), 'ApmPage'))
const InfrastructurePage = lazy(() => named(import('./pages/InfrastructurePage'), 'InfrastructurePage'))
const KubernetesPage = lazy(() => named(import('./pages/KubernetesPage'), 'KubernetesPage'))
const AlertsPage = lazy(() => named(import('./pages/AlertsPage'), 'AlertsPage'))
const SloPage = lazy(() => named(import('./pages/SloPage'), 'SloPage'))
const ActionsPage = lazy(() => named(import('./pages/ActionsPage'), 'ActionsPage'))  // Phase 2
const SkillsPage = lazy(() => import('./pages/SkillsPage'))  // Phase 3
const GovernanceDashboard = lazy(() => import('./pages/GovernanceDashboard'))  // Phase 3
const LoginPage = lazy(() => import('./pages/LoginPage'))

// Loading fallback for lazy-loaded components
function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[400px]">
      <LoadingSkeleton />
    </div>
  )
}

function App() {
  useAlertNotifications()

  // Phase 13: gate the whole app behind login; a token-expired event from the
  // api client drops back to the login screen.
  const [authed, setAuthed] = useState(() => getAuthStatus().isAuthenticated)
  useEffect(() => {
    const onAuthRequired = () => setAuthed(false)
    window.addEventListener('auth-required', onAuthRequired)
    return () => window.removeEventListener('auth-required', onAuthRequired)
  }, [])

  if (!authed) {
    return (
      <ErrorBoundary>
        <LoginPage onLogin={() => setAuthed(true)} />
      </ErrorBoundary>
    )
  }

  return (
    <ErrorBoundary>
      <AppShell>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/logs" element={<LogsPage />} />
            <Route path="/apm" element={<ApmPage />} />
            <Route path="/infrastructure" element={<InfrastructurePage />} />
            <Route path="/kubernetes" element={<KubernetesPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/slo" element={<SloPage />} />
            <Route path="/actions" element={<ActionsPage />} />  {/* Phase 2 */}
            <Route path="/skills" element={<SkillsPage />} />  {/* Phase 3 */}
            <Route path="/governance" element={<GovernanceDashboard />} />  {/* Phase 3 */}
          </Routes>
        </Suspense>
      </AppShell>
    </ErrorBoundary>
  )
}

export default App
