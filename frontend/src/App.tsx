import { Routes, Route } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { OverviewPage } from './pages/OverviewPage'
import { LogsPage } from './pages/LogsPage'
import { ApmPage } from './pages/ApmPage'
import { InfrastructurePage } from './pages/InfrastructurePage'
import { KubernetesPage } from './pages/KubernetesPage'
import { AlertsPage } from './pages/AlertsPage'
import { SloPage } from './pages/SloPage'
import { ActionsPage } from './pages/ActionsPage'  // Phase 2
import { useAlertNotifications } from './hooks/useAlertNotifications'

function App() {
  useAlertNotifications()

  return (
    <AppShell>
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
    </AppShell>
  )
}

export default App
