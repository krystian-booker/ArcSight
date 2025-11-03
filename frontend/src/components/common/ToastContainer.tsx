/**
 * Toast container component - displays all active toasts
 */

import Toast from './Toast';
import type { ToastMessage } from './Toast';

interface ToastContainerProps {
  toasts: ToastMessage[];
  onClose: (id: string) => void;
}

export default function ToastContainer({ toasts, onClose }: ToastContainerProps) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-lg right-lg z-50 flex flex-col gap-sm w-full max-w-sm pointer-events-none">
      <div className="flex flex-col gap-sm pointer-events-auto">
        {toasts.map((toast) => (
          <Toast key={toast.id} {...toast} onClose={onClose} />
        ))}
      </div>
    </div>
  );
}
