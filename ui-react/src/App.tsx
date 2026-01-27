import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { Health } from './pages/Health'
import MinerHealth from './pages/MinerHealth'
import { Analytics } from './pages/Analytics'

function App() {
  return (
    <Layout>
      <Routes>
        <Route index element={<Dashboard />} />
        <Route path="/" element={<Dashboard />} />
        <Route path="/health" element={<Health />} />
        <Route path="/health/:minerId" element={<MinerHealth />} />
        <Route path="/analytics" element={<Analytics />} />
      </Routes>
    </Layout>
  )
}

export default App
