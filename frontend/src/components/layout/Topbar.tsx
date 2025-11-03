/**
 * Top navigation bar component
 */

import { Bars3Icon } from '@heroicons/react/24/outline';

interface TopbarProps {
  onMenuClick: () => void;
}

export default function Topbar({ onMenuClick }: TopbarProps) {
  return (
    <header className="flex h-topbar items-center justify-between border-b border-arc-border bg-arc-surface px-lg">
      {/* Left side - Menu button */}
      <div className="flex items-center gap-md">
        <button
          onClick={onMenuClick}
          className="rounded-arc-sm p-2 text-arc-muted transition-colors hover:bg-arc-surface-alt hover:text-arc-text"
          aria-label="Toggle menu"
        >
          <Bars3Icon className="h-6 w-6" />
        </button>
      </div>

      {/* Right side - Status indicators */}
      <div className="flex items-center gap-md">
        {/* Connection status */}
        <div className="inline-flex items-center gap-sm uppercase tracking-arc-wide text-xs text-arc-muted">
          <div className="h-1.5 w-1.5 rounded-full bg-arc-teal glow-dot" />
          <span className="text-arc-teal">Connected</span>
        </div>
      </div>
    </header>
  );
}
