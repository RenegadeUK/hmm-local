import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Activity,
  BarChart3,
  Trophy,
  Coins,
  ChevronDown,
  Cpu,
  Waves,
  Settings,
  Target,
  Zap,
  Bot,
  Shuffle,
  Lightbulb,
  Home,
  Sparkles,
  Cloud,
  Radar,
  SlidersHorizontal,
  BellRing,
  ClipboardList,
  ShieldCheck,
  RefreshCw,
  Database,
  Gauge
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Logo } from './Logo'
import { PriceTicker } from './PriceTicker'

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const [openSection, setOpenSection] = useState<'dashboard' | 'manage' | 'settings' | 'insights' | 'leaderboards' | null>(null)

  useEffect(() => {
    if (location.pathname === '/' || location.pathname === '' || location.pathname.startsWith('/dashboard')) {
      setOpenSection('dashboard')
    }
  }, [location.pathname])

  const dashboardItems = [
    { path: '/', icon: LayoutDashboard, label: 'Overview' },
    { path: '/dashboard/operations', icon: Gauge, label: 'Operations' },
  ]
  
  const managementItems = [
    { path: '/miners', icon: Cpu, label: 'Miners' },
    { path: '/pools', icon: Waves, label: 'Pools' },
    { path: '/automation', icon: Bot, label: 'Automation Rules' },
    { path: '/pools/strategies', icon: Shuffle, label: 'Pool Strategies' },
    { path: '/settings/agile-solo-strategy', icon: Target, label: 'Agile Strategy' },
    { path: '/settings/optimization', icon: Zap, label: 'Energy Optimization' },
    { path: '/settings/energy', icon: Lightbulb, label: 'Energy Pricing' },
    { path: '/settings/integrations/homeassistant', icon: Home, label: 'Home Assistant' },
  ]

  const settingsItems = [
    { path: '/settings/cloud', icon: Cloud, label: 'Cloud Settings' },
    { path: '/settings/database', icon: Database, label: 'Database' },
    { path: '/settings/discovery', icon: Radar, label: 'Network Discovery' },
    { path: '/settings/tuning', icon: SlidersHorizontal, label: 'Tuning Profiles' },
    { path: '/settings/notifications', icon: BellRing, label: 'Notifications' },
    { path: '/settings/logs', icon: ClipboardList, label: 'System Logs' },
    { path: '/settings/audit', icon: ShieldCheck, label: 'Audit Logs' },
    { path: '/settings/openai', icon: Bot, label: 'AI Settings' },
    { path: '/settings/restart', icon: RefreshCw, label: 'Restart Container' },
  ]
  
  const insightsItems = [
    { path: '/health', icon: Activity, label: 'Health' },
    { path: '/analytics', icon: BarChart3, label: 'Analytics' },
    { path: '/insights/agile-predict', icon: Sparkles, label: 'Agile Predict' },
  ]
  
  const leaderboardItems = [
    { path: '/leaderboard', icon: Trophy, label: 'Hall of Pain' },
    { path: '/coin-hunter', icon: Coins, label: 'Coin Hunter' },
  ]

  const sectionStates = useMemo(
    () => ({
      dashboardOpen: openSection === 'dashboard',
      managementOpen: openSection === 'manage',
      settingsOpen: openSection === 'settings',
      insightsOpen: openSection === 'insights',
      leaderboardsOpen: openSection === 'leaderboards',
    }),
    [openSection]
  )

  const toggleSection = (section: 'dashboard' | 'manage' | 'settings' | 'insights' | 'leaderboards') => {
    setOpenSection((current) => (current === section ? null : section))
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Mobile Header */}
      <header className="lg:hidden sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur">
        <div className="flex h-14 items-center px-4 gap-2">
          <Logo className="h-8 w-8" />
          <span className="font-bold text-lg">HMM Local</span>
        </div>
      </header>

      {/* Desktop Sidebar */}
      <aside className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col border-r">
        <div className="flex flex-col gap-2 p-4">
          <div className="flex h-14 items-center border-b px-2 mb-4 gap-3">
            <Logo className="h-10 w-10" />
            <div className="flex flex-col">
              <span className="font-bold text-xl">HMM Local</span>
              <span className="text-xs text-muted-foreground">Home Miner Manager</span>
            </div>
          </div>
          <nav className="flex flex-col gap-1">
            {/* Dashboard Category */}
            <div className="mt-2">
              <button
                onClick={() => toggleSection('dashboard')}
                className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                <div className="flex items-center gap-3">
                  <LayoutDashboard className="h-5 w-5" />
                  <span>Dashboard</span>
                </div>
                <ChevronDown
                  className={`h-4 w-4 transition-transform ${
                    sectionStates.dashboardOpen ? 'rotate-180' : ''
                  }`}
                />
              </button>

              {sectionStates.dashboardOpen && (
                <div className="ml-4 mt-1 flex flex-col gap-1 border-l-2 border-border pl-4">
                  {dashboardItems.map(({ path, icon: Icon, label }) => {
                    const isActive = location.pathname === path
                    return (
                      <Link
                        key={path}
                        to={path}
                        className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                          isActive
                            ? 'bg-primary text-primary-foreground'
                            : 'hover:bg-accent hover:text-accent-foreground'
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                        {label}
                      </Link>
                    )}
                  )}
                </div>
              )}
            </div>

            {/* Manage Category */}
            <div className="mt-2">
              <button
                onClick={() => toggleSection('manage')}
                className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                <div className="flex items-center gap-3">
                  <LayoutDashboard className="h-5 w-5" />
                  <span>Manage</span>
                </div>
                <ChevronDown
                  className={`h-4 w-4 transition-transform ${
                    sectionStates.managementOpen ? 'rotate-180' : ''
                  }`}
                />
              </button>

              {sectionStates.managementOpen && (
                <div className="ml-4 mt-1 flex flex-col gap-1 border-l-2 border-border pl-4">
                  {managementItems.map(({ path, icon: Icon, label }) => {
                    const isActive = location.pathname === path
                    return (
                      <Link
                        key={path}
                        to={path}
                        className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                          isActive
                            ? 'bg-primary text-primary-foreground'
                            : 'hover:bg-accent hover:text-accent-foreground'
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                        {label}
                      </Link>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Insights Category */}
            <div className="mt-2">
              <button
                onClick={() => toggleSection('insights')}
                className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                <div className="flex items-center gap-3">
                  <Activity className="h-5 w-5" />
                  <span>Insights</span>
                </div>
                <ChevronDown
                  className={`h-4 w-4 transition-transform ${
                    sectionStates.insightsOpen ? 'rotate-180' : ''
                  }`}
                />
              </button>

              {sectionStates.insightsOpen && (
                <div className="ml-4 mt-1 flex flex-col gap-1 border-l-2 border-border pl-4">
                  {insightsItems.map(({ path, icon: Icon, label }) => {
                    const isActive = location.pathname === path
                    return (
                      <Link
                        key={path}
                        to={path}
                        className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                          isActive
                            ? 'bg-primary text-primary-foreground'
                            : 'hover:bg-accent hover:text-accent-foreground'
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                        {label}
                      </Link>
                    )
                  })}
                </div>
              )}
            </div>
            
            {/* Leaderboards Category */}
            <div className="mt-2">
              <button
                onClick={() => toggleSection('leaderboards')}
                className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                <div className="flex items-center gap-3">
                  <Trophy className="h-5 w-5" />
                  <span>Leaderboards</span>
                </div>
                <ChevronDown
                  className={`h-4 w-4 transition-transform ${
                    sectionStates.leaderboardsOpen ? 'rotate-180' : ''
                  }`}
                />
              </button>
              
              {sectionStates.leaderboardsOpen && (
                <div className="ml-4 mt-1 flex flex-col gap-1 border-l-2 border-border pl-4">
                  {leaderboardItems.map(({ path, icon: Icon, label }) => {
                    const isActive = location.pathname === path
                    return (
                      <Link
                        key={path}
                        to={path}
                        className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                          isActive
                            ? 'bg-primary text-primary-foreground'
                            : 'hover:bg-accent hover:text-accent-foreground'
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                        {label}
                      </Link>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Settings Category */}
            <div className="mt-2">
              <button
                onClick={() => toggleSection('settings')}
                className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                <div className="flex items-center gap-3">
                  <Settings className="h-5 w-5" />
                  <span>Settings</span>
                </div>
                <ChevronDown
                  className={`h-4 w-4 transition-transform ${
                    sectionStates.settingsOpen ? 'rotate-180' : ''
                  }`}
                />
              </button>

              {sectionStates.settingsOpen && (
                <div className="ml-4 mt-1 flex flex-col gap-1 border-l-2 border-border pl-4">
                  {settingsItems.map(({ path, icon: Icon, label }) => {
                    const isActive = location.pathname === path
                    return (
                      <Link
                        key={path}
                        to={path}
                        className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                          isActive
                            ? 'bg-primary text-primary-foreground'
                            : 'hover:bg-accent hover:text-accent-foreground'
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                        {label}
                      </Link>
                    )
                  })}
                </div>
              )}
            </div>
          </nav>
        </div>
      </aside>

      {/* Main Content */}
      <main className="lg:pl-64">
        <div className="container mx-auto p-4 md:p-6 lg:p-8 pb-80 lg:pb-8">
          {/* Price Ticker */}
          <div className="flex justify-end mb-4">
            <PriceTicker />
          </div>
          
          {children}
        </div>
      </main>

      {/* Mobile Bottom Nav */}
      <nav className="lg:hidden fixed bottom-0 z-50 w-full border-t bg-background/95 backdrop-blur">
        <div className="grid grid-cols-5 items-center gap-2 min-h-16 py-2">
          {dashboardItems.map(({ path, icon: Icon, label }) => {
            const isActive = location.pathname === path
            return (
              <Link
                key={path}
                to={path}
                className={`flex flex-col items-center gap-1 px-2 py-2 text-xs transition-colors ${
                  isActive
                    ? 'text-primary'
                    : 'text-muted-foreground'
                }`}
              >
                <Icon className="h-5 w-5" />
                <span className="truncate w-full text-center">{label}</span>
              </Link>
            )
          })}
          {managementItems.map(({ path, icon: Icon, label }) => {
            const isActive = location.pathname === path
            return (
              <Link
                key={path}
                to={path}
                className={`flex flex-col items-center gap-1 px-2 py-2 text-xs transition-colors ${
                  isActive
                    ? 'text-primary'
                    : 'text-muted-foreground'
                }`}
              >
                <Icon className="h-5 w-5" />
                <span className="truncate w-full text-center">{label}</span>
              </Link>
            )
          })}
          {insightsItems.map(({ path, icon: Icon, label }) => {
            const isActive = location.pathname === path
            return (
              <Link
                key={path}
                to={path}
                className={`flex flex-col items-center gap-1 px-2 py-2 text-xs transition-colors ${
                  isActive
                    ? 'text-primary'
                    : 'text-muted-foreground'
                }`}
              >
                <Icon className="h-5 w-5" />
                <span className="truncate w-full text-center">{label}</span>
              </Link>
            )
          })}
          {leaderboardItems.map(({ path, icon: Icon, label }) => {
            const isActive = location.pathname === path
            return (
              <Link
                key={path}
                to={path}
                className={`flex flex-col items-center gap-1 px-2 py-2 text-xs transition-colors ${
                  isActive
                    ? 'text-primary'
                    : 'text-muted-foreground'
                }`}
              >
                <Icon className="h-5 w-5" />
                <span className="truncate w-full text-center">{label}</span>
              </Link>
            )
          })}
          {settingsItems.map(({ path, icon: Icon, label }) => {
            const isActive = location.pathname === path
            return (
              <Link
                key={path}
                to={path}
                className={`flex flex-col items-center gap-1 px-2 py-2 text-xs transition-colors ${
                  isActive
                    ? 'text-primary'
                    : 'text-muted-foreground'
                }`}
              >
                <Icon className="h-5 w-5" />
                <span className="truncate w-full text-center">{label}</span>
              </Link>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
