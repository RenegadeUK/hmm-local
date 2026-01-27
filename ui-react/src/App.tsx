import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { Health } from './pages/Health'
import { Analytics } from './pages/Analytics'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/health" element={<Health />} />
        <Route path="/analytics" element={<Analytics />} />
      </Routes>
    </Layout>
  )
}

export default App
