/**
 * Callout component for info/warning/danger messages
 */

import type { ReactNode } from 'react';
import {
  InformationCircleIcon,
  ExclamationTriangleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';

type CalloutVariant = 'info' | 'warning' | 'danger' | 'success';

interface CalloutProps {
  children: ReactNode;
  variant?: CalloutVariant;
  title?: string;
  className?: string;
}

const variantStyles: Record<CalloutVariant, string> = {
  info: 'bg-arc-teal/8 border-arc-teal/30 text-arc-teal',
  warning: 'bg-arc-warning/8 border-arc-warning/30 text-arc-warning',
  danger: 'bg-arc-danger/8 border-arc-danger/30 text-arc-danger',
  success: 'bg-arc-success/8 border-arc-success/30 text-arc-success',
};

const icons: Record<CalloutVariant, typeof InformationCircleIcon> = {
  info: InformationCircleIcon,
  warning: ExclamationTriangleIcon,
  danger: XCircleIcon,
  success: InformationCircleIcon,
};

export default function Callout({
  children,
  variant = 'info',
  title,
  className = '',
}: CalloutProps) {
  const Icon = icons[variant];

  return (
    <div
      className={`
        flex gap-sm rounded-arc-md border p-md
        ${variantStyles[variant]}
        ${className}
      `}
    >
      <Icon className="h-5 w-5 flex-shrink-0 mt-0.5" />
      <div className="flex-1">
        {title && (
          <div className="mb-2xs font-semibold uppercase tracking-arc-tight text-sm">
            {title}
          </div>
        )}
        <div className="text-sm text-arc-text">{children}</div>
      </div>
    </div>
  );
}
