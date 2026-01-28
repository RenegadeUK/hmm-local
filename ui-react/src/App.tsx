import { Routes, Route } from 'react-router-dom'
import { Suspense, lazy } from 'react'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import Miners from './pages/Miners'

const Health = lazy(() => import('./pages/Health').then((module) => ({ default: module.Health })))
const MinerHealth = lazy(() => import('./pages/MinerHealth'))
const Analytics = lazy(() => import('./pages/Analytics').then((module) => ({ default: module.Analytics })))
const Leaderboard = lazy(() => import('./pages/Leaderboard').then((module) => ({ default: module.Leaderboard })))
const CoinHunter = lazy(() => import('./pages/CoinHunter'))
const MinerDetail = lazy(() => import('./pages/MinerDetail'))
const MinerEdit = lazy(() => import('./pages/MinerEdit'))
const AddMiner = lazy(() => import('./pages/AddMiner'))
const Pools = lazy(() => import('./pages/Pools'))
const AgileStrategy = lazy(() => import('./pages/AgileStrategy'))
const EnergyOptimization = lazy(() => import('./pages/EnergyOptimization'))
const AutomationRules = lazy(() => import('./pages/AutomationRules'))

function App() {
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
          <Route path="/health" element={<Health />} />
          <Route path="/health/:minerId" element={<MinerHealth />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/coin-hunter" element={<CoinHunter />} />
          <Route path="/miners" element={<Miners />} />
          <Route path="/miners/add" element={<AddMiner />} />
          <Route path="/miners/:minerId" element={<MinerDetail />} />
          <Route path="/miners/:minerId/edit" element={<MinerEdit />} />
          <Route path="/pools" element={<Pools />} />
          <Route path="/settings/agile-solo-strategy" element={<AgileStrategy />} />
          <Route path="/settings/optimization" element={<EnergyOptimization />} />
          <Route path="/automation" element={<AutomationRules />} />
        </Routes>
      </Suspense>
    </Layout>
  )
}

export default App
