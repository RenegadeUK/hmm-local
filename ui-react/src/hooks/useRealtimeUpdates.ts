import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'

const RECONNECT_BASE_DELAY_MS = 1000
const RECONNECT_MAX_DELAY_MS = 10000
const PING_INTERVAL_MS = 30000
const INVALIDATE_THROTTLE_MS = 2000

export function useRealtimeUpdates() {
  const queryClient = useQueryClient()
  const reconnectAttempt = useRef(0)
  const wsRef = useRef<WebSocket | null>(null)
  const pingTimerRef = useRef<number | null>(null)
  const invalidateTimerRef = useRef<number | null>(null)
  const pendingInvalidateRef = useRef(false)

  useEffect(() => {
    let isMounted = true

    const buildWebSocketUrl = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      return `${protocol}://${window.location.host}/ws/updates`
    }

    const scheduleInvalidate = () => {
      if (pendingInvalidateRef.current) return
      pendingInvalidateRef.current = true

      invalidateTimerRef.current = window.setTimeout(() => {
        pendingInvalidateRef.current = false
        queryClient.invalidateQueries({ queryKey: ['dashboard', 'all'] })
        queryClient.invalidateQueries({ queryKey: ['dashboard', 'ticker'] })
        queryClient.invalidateQueries({ queryKey: ['miners'] })
        queryClient.invalidateQueries({ queryKey: ['dashboard-all-asic'] })
      }, INVALIDATE_THROTTLE_MS)
    }

    const startPing = () => {
      if (pingTimerRef.current) window.clearInterval(pingTimerRef.current)
      pingTimerRef.current = window.setInterval(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send('ping')
        }
      }, PING_INTERVAL_MS)
    }

    const stopPing = () => {
      if (pingTimerRef.current) {
        window.clearInterval(pingTimerRef.current)
        pingTimerRef.current = null
      }
    }

    const connect = () => {
      if (!isMounted) return

      const ws = new WebSocket(buildWebSocketUrl())
      wsRef.current = ws

      ws.onopen = () => {
        reconnectAttempt.current = 0
        startPing()
      }

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data)
          if (payload?.type === 'telemetry_update' || payload?.type === 'miner_update') {
            scheduleInvalidate()
          }
        } catch {
          // Ignore non-JSON messages (e.g., pong)
        }
      }

      ws.onerror = () => {
        ws.close()
      }

      ws.onclose = () => {
        stopPing()
        if (!isMounted) return

        reconnectAttempt.current += 1
        const delay = Math.min(
          RECONNECT_BASE_DELAY_MS * 2 ** (reconnectAttempt.current - 1),
          RECONNECT_MAX_DELAY_MS
        )

        window.setTimeout(() => {
          if (isMounted) connect()
        }, delay)
      }
    }

    connect()

    return () => {
      isMounted = false
      stopPing()
      if (invalidateTimerRef.current) window.clearTimeout(invalidateTimerRef.current)
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close()
      }
    }
  }, [queryClient])
}
