import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import './index.css'

// Global error handler to catch and log Chart.js errors
window.addEventListener('error', (event) => {
  if (event.message.includes('toFixed')) {
    console.error('[GLOBAL ERROR] toFixed error caught:', {
      message: event.message,
      filename: event.filename,
      lineno: event.lineno,
      colno: event.colno,
      stack: event.error?.stack
    })
  }
})

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30000, // 30 seconds
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/static/service-worker.js')
      .then((registration) => {
        console.info('[PWA] Service worker registered', registration.scope)
      })
      .catch((error) => {
        console.error('[PWA] Service worker registration failed', error)
      })
  })
}
