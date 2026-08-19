import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import { ErrorBoundary } from './components/common/ErrorBoundary'
import { AppShell } from './components/layout/AppShell'
import { LoadingSkeleton } from './components/common/LoadingSkeleton'
import { useAlertNotifications } from './hooks/useAlertNotifications'

// Code split pages with lazy loading
const OverviewPage = lazy(() => import('./pages/OverviewPage'))
const LogsPage = lazy(() => import('./pages/LogsPage'))
const ApmPage = lazy(() => import('./pages/ApmPage'))
const InfrastructurePage = lazy(() => import('./pages/InfrastructurePage'))
const KubernetesPage = lazy(() => import('./pages/KubernetesPage'))
const AlertsPage = lazy(() => import('./pages/AlertsPage'))
const SloPage = lazy(() => import('./pages/SloPage'))
const ActionsPage = lazy(() => import('./pages/ActionsPage'))  // Phase 2

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
          </Routes>
        </Suspense>
      </AppShell>
    </ErrorBoundary>
  )
}

export default App
