import { NavLink } from 'react-router-dom'
import type { PropsWithChildren } from 'react'

const navItems = [
  { to: '/', label: 'Dashboard' },
  { to: '/cameras', label: 'Cameras' },
  { to: '/settings', label: 'Settings' },
]

export default function Layout({ children }: PropsWithChildren) {
  return (
    <div className="flex min-h-screen bg-gray-900 text-white">
      <aside className="w-64 bg-gray-800 flex-shrink-0 sticky top-0 h-screen hidden md:block">
        <div className="p-6">
          <h1 className="text-2xl font-bold">Vision App</h1>
        </div>
        <nav>
          <ul>
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    `block p-4 transition-colors ${
                      isActive ? 'bg-gray-700 text-white' : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>

      <div className="flex-1 w-full">
        <header className="bg-gray-800 p-4 shadow md:hidden">
          <h1 className="text-xl font-bold">Vision App</h1>
          <nav className="mt-4 flex gap-2">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    isActive ? 'bg-indigo-600 text-white' : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </header>

        <main className="p-6 md:p-10 overflow-y-auto min-h-screen">{children}</main>
      </div>
    </div>
  )
}
