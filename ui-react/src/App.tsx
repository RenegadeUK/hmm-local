import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { Health } from './pages/Health'
import MinerHealth from './pages/MinerHealth'
import { Analytics } from './pages/Analytics'
import { Leaderboard } from './pages/Leaderboard'
import CoinHunter from './pages/CoinHunter'
import Miners from './pages/Miners'
import MinerDetail from './pages/MinerDetail'
import MinerEdit from './pages/MinerEdit'
import Pools from './pages/Pools'

function App() {
  return (
    <Layout>
      <Routes>
        <Route index element={<Dashboard />} />
        <Route path="/" element={<Dashboard />} />
        <Route path="/health" element={<Health />} />
        <Route path="/health/:minerId" element={<MinerHealth />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/leaderboard" element={<Leaderboard />} />
        <Route path="/coin-hunter" element={<CoinHunter />} />
        <Route path="/miners" element={<Miners />} />
        <Route path="/miners/:minerId" element={<MinerDetail />} />
        <Route path="/miners/:minerId/edit" element={<MinerEdit />} />
        <Route path="/pools" element={<Pools />} />
      </Routes>
    </Layout>
  )
}

export default App
