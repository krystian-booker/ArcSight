/**
 * Main application layout with sidebar and topbar
 */

import { useState } from 'react';
import type { ReactNode } from 'react';
import Sidebar from './Sidebar';
import Topbar from './Topbar';

interface AppLayoutProps {
  children: ReactNode;
}

export default function AppLayout({ children }: AppLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const toggleSidebar = () => {
    setSidebarOpen(!sidebarOpen);
  };

  return (
    <div
      className="flex h-screen w-screen overflow-hidden"
      style={{
        background: 'linear-gradient(135deg, rgba(0, 194, 168, 0.06), transparent 60%), #141414'
      }}
    >
      {/* Sidebar */}
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* Main content area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Topbar */}
        <Topbar onMenuClick={toggleSidebar} />

        {/* Page content */}
        <main
          className="flex-1 overflow-auto"
          style={{
            background: 'linear-gradient(135deg, rgba(20, 20, 20, 0.94), rgba(20, 20, 20, 0.98))'
          }}
        >
          <div className="h-full w-full">{children}</div>
        </main>
      </div>

      {/* Overlay for mobile when sidebar is open */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black bg-opacity-50 handheld:block hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
    </div>
  );
}
