import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { Health } from './pages/Health'
import MinerHealth from './pages/MinerHealth'
import { Analytics } from './pages/Analytics'
import { Leaderboard } from './pages/Leaderboard'
import CoinHunter from './pages/CoinHunter'
import Miners from './pages/Miners'

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
      </Routes>
    </Layout>
  )
}

export default App
