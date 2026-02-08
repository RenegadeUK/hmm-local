import { Routes, Route } from 'react-router-dom'
import { Suspense, lazy } from 'react'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import Miners from './pages/Miners'
import { useRealtimeUpdates } from './hooks/useRealtimeUpdates'

const Health = lazy(() => import('./pages/Health').then((module) => ({ default: module.Health })))
const MinerHealth = lazy(() => import('./pages/MinerHealth'))
const Analytics = lazy(() => import('./pages/Analytics').then((module) => ({ default: module.Analytics })))
const Costs = lazy(() => import('./pages/Costs').then((module) => ({ default: module.Costs })))
const Leaderboard = lazy(() => import('./pages/Leaderboard').then((module) => ({ default: module.Leaderboard })))
const CoinHunter = lazy(() => import('./pages/CoinHunter'))
const MinerDetail = lazy(() => import('./pages/MinerDetail'))
const MinerEdit = lazy(() => import('./pages/MinerEdit'))
const AddMiner = lazy(() => import('./pages/AddMiner'))
const Pools = lazy(() => import('./pages/Pools'))
const AgileStrategy = lazy(() => import('./pages/AgileStrategy'))
const EnergyOptimization = lazy(() => import('./pages/EnergyOptimization'))
const EnergyPricing = lazy(() => import('./pages/EnergyPricing'))
const AutomationRules = lazy(() => import('./pages/AutomationRules'))
const PoolStrategies = lazy(() => import('./pages/PoolStrategies'))
const AgilePredict = lazy(() => import('./pages/AgilePredict'))
const HomeAssistant = lazy(() => import('./pages/HomeAssistant'))
const SmartThings = lazy(() => import('./pages/SmartThings'))
const SettingsPools = lazy(() => import('./pages/settings/PoolIntegrations'))
const SettingsCloud = lazy(() => import('./pages/settings/CloudSettings'))
const SettingsDiscovery = lazy(() => import('./pages/settings/NetworkDiscovery'))
const SettingsTuning = lazy(() => import('./pages/settings/TuningProfiles'))
const SettingsNotifications = lazy(() => import('./pages/settings/Notifications'))
const SettingsLogs = lazy(() => import('./pages/settings/SystemLogs'))
const SettingsAudit = lazy(() => import('./pages/settings/AuditLogs'))
const SettingsAI = lazy(() => import('./pages/settings/AISettings'))
const SettingsDatabase = lazy(() => import('./pages/DatabaseSettings'))
const SettingsRestart = lazy(() => import('./pages/settings/RestartContainer'))
const DriverUpdates = lazy(() => import('./pages/DriverUpdates'))
const FileManager = lazy(() => import('./pages/FileManager'))
const PlatformUpdates = lazy(() => import('./pages/PlatformUpdates'))
const Operations = lazy(() => import('./pages/Operations'))

function App() {
  useRealtimeUpdates()

  return (
    <Layout>
      <Suspense
        fallback={
          <div className="w-full py-10 text-center text-sm text-muted-foreground">Loading view…</div>
        }
      >
        <Routes>
          <Route index element={<Dashboard />} />
          <Route path="/" element={<Dashboard />} />
          <Route path="/dashboard/overview" element={<Dashboard />} />
          <Route path="/dashboard/operations" element={<Operations />} />
          <Route path="/health" element={<Health />} />
          <Route path="/health/:minerId" element={<MinerHealth />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/insights/costs" element={<Costs />} />
          <Route path="/insights/agile-predict" element={<AgilePredict />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/coin-hunter" element={<CoinHunter />} />
          <Route path="/miners" element={<Miners />} />
          <Route path="/miners/add" element={<AddMiner />} />
          <Route path="/miners/:minerId" element={<MinerDetail />} />
          <Route path="/miners/:minerId/edit" element={<MinerEdit />} />
          <Route path="/pools" element={<Pools />} />
          <Route path="/pools/strategies" element={<PoolStrategies />} />
          <Route path="/settings" element={<SettingsCloud />} />
          <Route path="/settings/pools" element={<SettingsPools />} />
          <Route path="/settings/cloud" element={<SettingsCloud />} />
          <Route path="/settings/database" element={<SettingsDatabase />} />
          <Route path="/settings/discovery" element={<SettingsDiscovery />} />
          <Route path="/settings/tuning" element={<SettingsTuning />} />
          <Route path="/settings/notifications" element={<SettingsNotifications />} />
          <Route path="/settings/logs" element={<SettingsLogs />} />
          <Route path="/settings/audit" element={<SettingsAudit />} />
          <Route path="/settings/openai" element={<SettingsAI />} />
          <Route path="/settings/agile-solo-strategy" element={<AgileStrategy />} />
          <Route path="/settings/energy" element={<EnergyPricing />} />
          <Route path="/settings/optimization" element={<EnergyOptimization />} />
          <Route path="/settings/integrations/homeassistant" element={<HomeAssistant />} />
          <Route path="/settings/integrations/smartthings" element={<SmartThings />} />
          <Route path="/settings/drivers" element={<DriverUpdates />} />
          <Route path="/settings/files" element={<FileManager />} />
          <Route path="/settings/platform" element={<PlatformUpdates />} />
          <Route path="/settings/restart" element={<SettingsRestart />} />
          <Route path="/automation" element={<AutomationRules />} />
        </Routes>
      </Suspense>
    </Layout>
  )
}

export default App
