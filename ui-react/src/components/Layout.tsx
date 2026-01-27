import { Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Activity, BarChart3 } from 'lucide-react'
import { Logo } from './Logo'
import { PriceTicker } from './PriceTicker'

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()

  const navItems = [
    { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/health', icon: Activity, label: 'Health' },
    { path: '/analytics', icon: BarChart3, label: 'Analytics' },
  ]

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
            {navItems.map(({ path, icon: Icon, label }) => {
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
                  <Icon className="h-5 w-5" />
                  {label}
                </Link>
              )
            })}
          </nav>
        </div>
      </aside>

      {/* Main Content */}
      <main className="lg:pl-64">
        <div className="container mx-auto p-4 md:p-6 lg:p-8">
          {/* Price Ticker */}
          <div className="flex justify-end mb-4">
            <PriceTicker />
          </div>
          
          {children}
        </div>
      </main>

      {/* Mobile Bottom Nav */}
      <nav className="lg:hidden fixed bottom-0 z-50 w-full border-t bg-background/95 backdrop-blur">
        <div className="flex justify-around items-center h-16">
          {navItems.map(({ path, icon: Icon, label }) => {
            const isActive = location.pathname === path
            return (
              <Link
                key={path}
                to={path}
                className={`flex flex-col items-center gap-1 px-3 py-2 text-xs transition-colors ${
                  isActive
                    ? 'text-primary'
                    : 'text-muted-foreground'
                }`}
              >
                <Icon className="h-5 w-5" />
                {label}
              </Link>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
