/**
 * Toast notification component
 */

import { useEffect } from 'react';
import {
  CheckCircleIcon,
  XCircleIcon,
  InformationCircleIcon,
  ExclamationTriangleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface ToastMessage {
  id: string;
  type: ToastType;
  message: string;
  duration?: number;
}

interface ToastProps extends ToastMessage {
  onClose: (id: string) => void;
}

const icons = {
  success: CheckCircleIcon,
  error: XCircleIcon,
  info: InformationCircleIcon,
  warning: ExclamationTriangleIcon,
};

const styles = {
  success: 'bg-arc-success bg-opacity-20 border-arc-success text-arc-success',
  error: 'bg-arc-danger bg-opacity-20 border-arc-danger text-arc-danger',
  info: 'bg-arc-teal bg-opacity-20 border-arc-teal text-arc-teal',
  warning: 'bg-arc-warning bg-opacity-20 border-arc-warning text-arc-warning',
};

export default function Toast({ id, type, message, duration = 5000, onClose }: ToastProps) {
  const Icon = icons[type];

  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        onClose(id);
      }, duration);

      return () => clearTimeout(timer);
    }
  }, [id, duration, onClose]);

  return (
    <div
      className={`
        flex items-start gap-sm rounded-arc-md border p-md
        shadow-arc-soft
        animate-in slide-in-from-right-full
        ${styles[type]}
      `}
    >
      <Icon className="h-5 w-5 flex-shrink-0 mt-0.5" />
      <p className="flex-1 text-sm text-arc-text">{message}</p>
      <button
        onClick={() => onClose(id)}
        className="flex-shrink-0 rounded p-1 hover:bg-black hover:bg-opacity-10 transition-colors"
        aria-label="Close notification"
      >
        <XMarkIcon className="h-4 w-4" />
      </button>
    </div>
  );
}
