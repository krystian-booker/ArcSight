interface CameraStatusBadgeProps {
  status: 'connected' | 'disconnected' | 'checking' | 'error'
}

const statusStyles: Record<CameraStatusBadgeProps['status'], string> = {
  connected: 'bg-green-500/20 text-green-400 border border-green-500/60',
  disconnected: 'bg-red-500/20 text-red-400 border border-red-500/60',
  checking: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/60',
  error: 'bg-gray-500/20 text-gray-300 border border-gray-500/40',
}

const statusLabels: Record<CameraStatusBadgeProps['status'], string> = {
  connected: 'Connected',
  disconnected: 'Disconnected',
  checking: 'Checking...',
  error: 'Error',
}

export function CameraStatusBadge({ status }: CameraStatusBadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${statusStyles[status]}`}>
      {statusLabels[status]}
    </span>
  )
}
