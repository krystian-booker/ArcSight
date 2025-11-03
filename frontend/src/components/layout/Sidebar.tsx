/**
 * Navigation sidebar component
 */

import { NavLink } from 'react-router-dom';
import {
  HomeIcon,
  CameraIcon,
  Cog6ToothIcon,
  ChartBarIcon,
  ViewfinderCircleIcon
} from '@heroicons/react/24/outline';
import BrandMark from './BrandMark';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

const navigation = [
  { name: 'Dashboard', href: '/', icon: HomeIcon },
  { name: 'Cameras', href: '/cameras', icon: CameraIcon },
  { name: 'Calibration', href: '/calibration', icon: ViewfinderCircleIcon },
  { name: 'Monitoring', href: '/monitoring', icon: ChartBarIcon },
  { name: 'Settings', href: '/settings', icon: Cog6ToothIcon },
];

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
  return (
    <>
      {/* Desktop sidebar */}
      <aside
        className={`
          fixed left-0 top-0 z-40 h-screen
          transform transition-transform duration-arc ease-arc-out
          border-r border-arc-border
          handheld:w-sidebar-mobile w-sidebar
          ${isOpen ? 'translate-x-0' : '-translate-x-full handheld:-translate-x-full'}
        `}
        style={{
          background: 'linear-gradient(180deg, rgba(23, 23, 23, 0.9), rgba(23, 23, 23, 0.92) 45%, rgba(12, 12, 12, 0.96))'
        }}
      >
        {/* Logo */}
        <div className="flex h-topbar items-center justify-between border-b border-arc-border px-lg">
          <div className="flex items-center gap-sm">
            <BrandMark />
            <span className="text-xl font-bold text-arc-text">ArcSight</span>
          </div>

          {/* Close button (mobile only) */}
          <button
            onClick={onClose}
            className="handheld:block hidden rounded p-2 text-arc-muted hover:bg-arc-surface-alt hover:text-arc-text"
          >
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex flex-col gap-2xs p-md">
          {navigation.map((item) => (
            <NavLink
              key={item.name}
              to={item.href}
              onClick={() => {
                // Close sidebar on mobile after navigation
                if (window.innerWidth <= 1080) {
                  onClose();
                }
              }}
              className={({ isActive }) =>
                `
                  flex items-center gap-md rounded-arc-md px-md py-sm
                  relative nav-link-glow
                  transition-colors duration-arc ease-arc-out
                  uppercase text-[0.85rem] tracking-arc
                  ${
                    isActive
                      ? 'bg-arc-teal/10 text-arc-text active'
                      : 'text-arc-muted hover:text-arc-text'
                  }
                `
              }
            >
              <div className="grid h-9 w-9 place-items-center rounded-arc-sm bg-arc-primary/12 text-arc-primary">
                <item.icon className="h-5 w-5" />
              </div>
              <span className="font-medium">{item.name}</span>
            </NavLink>
          ))}
        </nav>

        {/* Footer info */}
        <div className="absolute bottom-0 left-0 right-0 border-t border-arc-border p-md">
          <div className="text-xs text-arc-subtle">
            <div className="font-medium text-arc-muted">ArcSight v1.0.0</div>
            <div>Industrial Computer Vision</div>
          </div>
        </div>
      </aside>
    </>
  );
}
